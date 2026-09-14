# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Indexing a disk: walk it, then hash what changed.

Both phases are resumable. The walk writes size and mtime and clears the
stored hash whenever either changed; the hash phase then only works on rows
without one. A scan that was interrupted simply starts again and finds
almost everything already done.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from engine import db, fsutil, integrity, notify
from engine.jobs import Job
from platforms import backend

# A file is considered unchanged when size and mtime match. exFAT stores
# timestamps with 10 ms resolution and a timezone offset, so an exact
# comparison would produce false positives; two seconds of slack is the same
# window rsync uses for FAT-like filesystems.
MTIME_TOLERANCE = 2.0

WALK_BATCH = 500
HASH_COMMIT_FILES = 64
HASH_COMMIT_SECONDS = 5.0


def mountpoint_of(disk: "db.sqlite3.Row") -> Path:
    return backend.mountpoint_of(disk)


def require_readable(disk: "db.sqlite3.Row") -> Path:
    """Ask the platform whether this disk may be read right now.

    On Linux that means proving the master really is mounted read-only; on a
    desktop system it only checks that the volume is there.
    """
    backend.verify_readable(disk)
    return backend.mountpoint_of(disk)


def start_scan_record(disk_id: int, set_name: str) -> int:
    cursor = db.execute(
        "INSERT INTO scans (disk_id, set_name, started_at, state, phase) "
        "VALUES (?, ?, ?, 'running', 'walk')",
        (disk_id, set_name, db.now()),
    )
    return int(cursor.lastrowid)


def finish_scan_record(scan_id: int, state: str, message: str = "") -> None:
    db.execute("UPDATE scans SET state = ?, finished_at = ?, message = ?, current_path = NULL "
               "WHERE id = ?", (state, db.now(), message, scan_id))


def scan_disk(job: Job, disk_id: int, set_name: str | None = None) -> None:
    """Index one disk. The set is only context, never the subject.

    What is found belongs to the disk - a master shared by two sets is read
    once and both see the result. The set is carried along so that findings
    and log entries end up where the reader started from.
    """
    disk = db.disk_by_id(disk_id, set_name)
    if disk is None:
        raise RuntimeError("this disk is no longer registered")

    mountpoint = require_readable(disk)
    scan_id = start_scan_record(disk_id, disk["set_name"])
    job.scan_id = scan_id
    job.disk_id = disk_id
    job.set_name = disk["set_name"]

    errors: list[str] = []

    def on_error(path: str, exc: OSError) -> None:
        if len(errors) < 200:
            errors.append(f"{path}: {exc.strerror or exc}")

    # ------------------------------------------------------------ phase 1 --
    job.phase = "walk"
    db.execute("UPDATE scans SET phase = 'walk' WHERE id = ?", (scan_id,))
    connection = db.connect()
    batch: list[tuple] = []
    files_seen = 0
    bytes_seen = 0

    def flush() -> None:
        if not batch:
            return
        connection.execute("BEGIN")
        connection.executemany(
            """
            INSERT INTO files (disk_id, path, size, mtime, seen_scan)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (disk_id, path) DO UPDATE SET
                size      = excluded.size,
                mtime     = excluded.mtime,
                seen_scan = excluded.seen_scan,
                sha256    = CASE WHEN files.size <> excluded.size
                                   OR abs(files.mtime - excluded.mtime) > ?
                                 THEN NULL ELSE files.sha256 END,
                hashed_at = CASE WHEN files.size <> excluded.size
                                   OR abs(files.mtime - excluded.mtime) > ?
                                 THEN NULL ELSE files.hashed_at END
            """,
            [(*row, MTIME_TOLERANCE, MTIME_TOLERANCE) for row in batch],
        )
        connection.execute("COMMIT")
        batch.clear()

    db.drop_findings_of_scan(disk_id)
    suspicious_names: list[tuple[str, str]] = []

    for relative, size, mtime in fsutil.walk(mountpoint, on_error):
        if not job.should_continue():
            flush()
            finish_scan_record(scan_id, "cancelled", "cancelled during the walk")
            return
        batch.append((disk_id, relative, size, mtime, scan_id))
        files_seen += 1
        bytes_seen += size

        # Ransom notes and meaningless second extensions show up in the name
        # alone, so this is free while we are walking anyway.
        finding = integrity.suspicious_name(relative.rsplit("/", 1)[-1])
        if finding and len(suspicious_names) < 5000:
            suspicious_names.append((finding, relative))
        if len(batch) >= WALK_BATCH:
            flush()
            job.files_total = files_seen
            job.bytes_total = bytes_seen
            job.current_path = relative
            job.message = f"{files_seen:,}"
    flush()

    # Anything not seen in this walk is gone from the disk.
    removed = db.execute(
        "DELETE FROM files WHERE disk_id = ? AND (seen_scan IS NULL OR seen_scan <> ?)",
        (disk_id, scan_id),
    ).rowcount

    db.execute("UPDATE scans SET files_total = ?, bytes_total = ? WHERE id = ?",
               (files_seen, bytes_seen, scan_id))

    # ------------------------------------------------------------ phase 2 --
    job.phase = "hash"
    db.execute("UPDATE scans SET phase = 'hash' WHERE id = ?", (scan_id,))

    todo_files = db.scalar(
        "SELECT COUNT(*) FROM files WHERE disk_id = ? AND sha256 IS NULL", (disk_id,), 0)
    todo_bytes = db.scalar(
        "SELECT COALESCE(SUM(size), 0) FROM files WHERE disk_id = ? AND sha256 IS NULL",
        (disk_id,), 0)

    job.files_total = todo_files
    job.bytes_total = todo_bytes
    job.files_done = 0
    job.bytes_done = 0
    job.message = f"{todo_files:,} / {fsutil.human_bytes(todo_bytes)}"

    hashed = 0
    hashed_bytes = 0
    pending: list[tuple] = []
    last_commit = time.monotonic()
    vanished: list[str] = []

    def commit_hashes() -> None:
        nonlocal last_commit
        if not pending:
            return
        connection.execute("BEGIN")
        connection.executemany(
            "UPDATE files SET sha256 = ?, hashed_at = ?, health = ? "
            "WHERE disk_id = ? AND path = ?",
            pending,
        )
        connection.execute("COMMIT")
        pending.clear()
        last_commit = time.monotonic()

    while True:
        rows = db.query(
            "SELECT path, size FROM files WHERE disk_id = ? AND sha256 IS NULL "
            "ORDER BY path LIMIT 500", (disk_id,))
        if not rows:
            break

        progressed = False
        for row in rows:
            if not job.should_continue():
                commit_hashes()
                db.execute(
                    "UPDATE scans SET files_hashed = ?, bytes_hashed = ? WHERE id = ?",
                    (hashed, hashed_bytes, scan_id))
                finish_scan_record(scan_id, "cancelled",
                                   f"cancelled after hashing {hashed:,} files")
                return

            full_path = mountpoint / row["path"]
            job.current_path = row["path"]
            health = None
            try:
                header = integrity.read_header(full_path)
                if header is not None:
                    health = integrity.check_header(row["path"].rsplit("/", 1)[-1], header)
                digest = fsutil.sha256(full_path, job.should_continue)
            except FileNotFoundError:
                vanished.append(row["path"])
                db.execute("DELETE FROM files WHERE disk_id = ? AND path = ?",
                           (disk_id, row["path"]))
                progressed = True
                continue
            except OSError as exc:
                on_error(str(full_path), exc)
                # Leave the hash empty and move on; the next scan tries again.
                db.execute("UPDATE files SET seen_scan = ? WHERE disk_id = ? AND path = ?",
                           (scan_id, disk_id, row["path"]))
                # Without a hash it would be picked up forever, so park it.
                db.execute("UPDATE files SET sha256 = ?, hashed_at = ? "
                           "WHERE disk_id = ? AND path = ?",
                           ("unreadable", db.now(), disk_id, row["path"]))
                progressed = True
                continue

            if digest is None:      # paused and then cancelled mid-file
                commit_hashes()
                finish_scan_record(scan_id, "cancelled",
                                   f"cancelled after hashing {hashed:,} files")
                return

            pending.append((digest, db.now(), health, disk_id, row["path"]))
            hashed += 1
            hashed_bytes += row["size"]
            job.files_done = hashed
            job.bytes_done = hashed_bytes
            progressed = True

            if (len(pending) >= HASH_COMMIT_FILES
                    or time.monotonic() - last_commit > HASH_COMMIT_SECONDS):
                commit_hashes()
                db.execute(
                    "UPDATE scans SET files_hashed = ?, bytes_hashed = ?, current_path = ? "
                    "WHERE id = ?", (hashed, hashed_bytes, row["path"], scan_id))

        commit_hashes()
        if not progressed:
            break

    commit_hashes()
    db.execute("UPDATE scans SET files_hashed = ?, bytes_hashed = ? WHERE id = ?",
               (hashed, hashed_bytes, scan_id))

    # ------------------------------------------------------------ phase 3 --
    # Files carried over from an earlier index were never looked at. Reading
    # their first half kilobyte is cheap next to hashing them again.
    job.phase = "check"
    db.execute("UPDATE scans SET phase = 'check' WHERE id = ?", (scan_id,))
    unchecked = db.scalar(
        "SELECT COUNT(*) FROM files WHERE disk_id = ? AND health IS NULL", (disk_id,), 0)
    job.files_total = unchecked
    job.bytes_total = 0
    job.files_done = 0
    checked = 0

    while True:
        rows = db.query("SELECT path FROM files WHERE disk_id = ? AND health IS NULL "
                        "ORDER BY path LIMIT 500", (disk_id,))
        if not rows:
            break
        updates = []
        for row in rows:
            if not job.should_continue():
                break
            job.current_path = row["path"]
            updates.append((integrity.check_file(mountpoint / row["path"],
                                                 row["path"].rsplit("/", 1)[-1]),
                            disk_id, row["path"]))
            checked += 1
            job.files_done = checked
        connection.execute("BEGIN")
        connection.executemany(
            "UPDATE files SET health = ? WHERE disk_id = ? AND path = ?", updates)
        connection.execute("COMMIT")
        if not job.should_continue():
            break

    # ------------------------------------------------------------ findings --
    for kind, relative in suspicious_names:
        db.record_finding(disk["set_name"], kind, relative, disk_id, scan_id)

    damaged = db.query(
        "SELECT path, health FROM files WHERE disk_id = ? AND health IN "
        "('header_mismatch', 'text_garbled', 'empty') ORDER BY path LIMIT 2000",
        (disk_id,))
    for row in damaged:
        db.record_finding(disk["set_name"], row["health"], row["path"], disk_id, scan_id)

    summary = {
        "files": files_seen,
        "bytes": bytes_seen,
        "hashed": hashed,
        "removed": removed,
        "vanished": len(vanished),
        "errors": len(errors),
        "checked": checked,
        "damaged": len(damaged),
        "suspicious": len(suspicious_names),
    }
    for message in errors[:20]:
        db.log_event("warning", message, disk["set_name"], "scan")

    prose = (f"{files_seen:,} files, {fsutil.human_bytes(bytes_seen)}, "
             f"{hashed:,} newly hashed")
    finish_scan_record(scan_id, "done", prose)
    db.execute("UPDATE scans SET summary_json = ? WHERE id = ?",
               (json.dumps(summary), scan_id))
    db.execute("UPDATE disks SET last_seen_at = ? WHERE id = ?", (db.now(), disk_id))
    db.log_event("info", f"{disk['display_name']}: {prose}", disk["set_name"], "scan")

    if damaged or suspicious_names:
        notify.send(
            "error",
            f"AmberShelf: {disk['display_name']}",
            f"{len(damaged)} damaged file(s) and {len(suspicious_names)} suspicious "
            f"name(s) found while indexing.",
            disk["set_name"], disk=disk["display_name"],
            damaged=len(damaged), suspicious=len(suspicious_names))
    elif errors:
        notify.send("warning", f"AmberShelf: {disk['display_name']}",
                    f"{len(errors)} file(s) could not be read while indexing.",
                    disk["set_name"], disk=disk["display_name"])
    # Numbers only - the job panel is refreshed by script and stays neutral.
    job.message = f"{files_seen:,} / {fsutil.human_bytes(bytes_seen)}"
    job.current_path = ""


def rehash_disk(disk_id: int) -> int:
    """Drop every stored hash so the next scan recomputes all of them."""
    return db.execute("UPDATE files SET sha256 = NULL, hashed_at = NULL WHERE disk_id = ?",
                      (disk_id,)).rowcount


def scan_state(disk_id: int) -> dict:
    row = db.one("SELECT * FROM scans WHERE disk_id = ? ORDER BY id DESC LIMIT 1", (disk_id,))
    # A fresh copy holds nothing at all, so "has files" is not the same question
    # as "has been read". Only a finished scan counts.
    scanned = bool(db.scalar(
        "SELECT COUNT(*) FROM scans WHERE disk_id = ? AND state = 'done'", (disk_id,), 0))
    indexed = db.scalar("SELECT COUNT(*) FROM files WHERE disk_id = ?", (disk_id,), 0)
    unhashed = db.scalar(
        "SELECT COUNT(*) FROM files WHERE disk_id = ? AND sha256 IS NULL", (disk_id,), 0)
    size = db.scalar("SELECT COALESCE(SUM(size), 0) FROM files WHERE disk_id = ?",
                     (disk_id,), 0)
    summary = {}
    if row is not None:
        try:
            summary = json.loads(row["summary_json"] or "{}")
        except (ValueError, IndexError, KeyError):
            summary = {}

    return {
        "last_scan": dict(row) if row else None,
        "summary": summary,
        "scanned": scanned,
        "files": indexed,
        "unhashed": unhashed,
        "bytes": size,
        "complete": scanned and unhashed == 0,
    }
