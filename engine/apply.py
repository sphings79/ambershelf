# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Carrying out a plan - the only place in AmberSync that writes.

Rules this file exists to keep:

  * Every file is written to a temporary name, flushed to the platter, read
    back, and only then renamed into place. A run that is interrupted leaves
    a leftover temporary file, never half a photo under the right name.
  * Adding is routine. Replacing, renaming and deleting happen only for items
    the user has approved, one by one or in bulk.
  * Nothing is removed before the additions are done, so a run that runs out
    of space has not deleted anything yet.
  * Replaced and deleted files are parked under .ambersync-trash unless the
    user asked for them to be gone for good.

Paths in a real archive contain spaces and exclamation marks, so everything
here is a path object. No string ever reaches a shell.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path

from engine import compare, config, db, fsutil, notify
from engine.jobs import Job
from platforms import backend

#: The order matters. Renames are free, copies need space, and removals come
#: last so that a run which fails part way through has taken nothing away.
ORDER = (compare.RENAMED, compare.NEW, compare.CHANGED, compare.DELETED)

#: Kinds that are carried out without asking.
AUTOMATIC = (compare.NEW,)


class ApplyRefused(RuntimeError):
    """The plan may not be carried out as it stands."""


# --------------------------------------------------------------- selection --

def selected_items(plan_id: int, set_name: str, kinds: tuple[str, ...] | None = None
                   ) -> dict[int, dict[str, list]]:
    """Group the items this run will touch by slave and kind.

    Everything that needs approval and has not got one is left out here, so
    the execution below never has to think about it again.
    """
    decisions = db.remembered_decisions(set_name)
    wanted = tuple(kinds) if kinds else ORDER

    grouped: dict[int, dict[str, list]] = {}
    for row in db.query(
            "SELECT * FROM plan_items WHERE plan_id = ? AND kind IN "
            f"({','.join('?' * len(wanted))}) ORDER BY slave_disk_id, kind, path",
            (plan_id, *wanted)):
        if row["kind"] not in AUTOMATIC:
            if decisions.get((row["slave_disk_id"], row["kind"], row["path"])) != "approve":
                continue
        grouped.setdefault(row["slave_disk_id"], {}).setdefault(row["kind"], []).append(row)
    return grouped


def pending_approvals(plan_id: int, set_name: str) -> int:
    """How many items are still waiting for an answer."""
    decisions = db.remembered_decisions(set_name)
    waiting = 0
    for row in db.query(
            "SELECT slave_disk_id, kind, path FROM plan_items "
            "WHERE plan_id = ? AND kind IN (?, ?, ?)",
            (plan_id, compare.CHANGED, compare.RENAMED, compare.DELETED)):
        if (row["slave_disk_id"], row["kind"], row["path"]) not in decisions:
            waiting += 1
    return waiting


# ----------------------------------------------------------------- copying --

def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb", buffering=0) as fh:
        while block := fh.read(config.COPY_BLOCK_SIZE):
            digest.update(block)
    return digest.hexdigest()


def copy_file(source: Path, target: Path, expected_sha: str, job: Job,
              verify: bool, keep_mtime: bool) -> None:
    """Copy one file and prove it arrived intact.

    Raises on any mismatch, after removing the temporary file - a wrong copy
    must never end up under the right name.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + config.TEMP_SUFFIX)

    digest = hashlib.sha256()
    try:
        with open(source, "rb", buffering=0) as reader, open(temporary, "wb") as writer:
            while True:
                if not job.should_continue():
                    raise InterruptedError("cancelled")
                block = reader.read(config.COPY_BLOCK_SIZE)
                if not block:
                    break
                digest.update(block)
                writer.write(block)
            writer.flush()
            os.fsync(writer.fileno())

        if digest.hexdigest() != expected_sha:
            raise OSError("the source changed while it was being read")

        if verify:
            # Read it back from the target. Hashing what we just held in
            # memory would only prove that memory is consistent with itself.
            if hash_file(temporary) != expected_sha:
                raise OSError("the copy does not match the original")

        if keep_mtime:
            stat = source.stat()
            os.utime(temporary, (stat.st_atime, stat.st_mtime))

        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def move_to_trash(root: Path, relative: str, stamp: str) -> Path:
    """Park a file under .ambersync-trash instead of destroying it."""
    target = root / config.TRASH_DIR / stamp / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(root / relative), str(target))
    return target


def remove_file(root: Path, relative: str, stamp: str, mode: str) -> str:
    if mode == "trash":
        move_to_trash(root, relative, stamp)
        return "trash"
    (root / relative).unlink(missing_ok=True)
    return "removed"


def prune_empty_parents(root: Path, relative: str) -> None:
    """Tidy up folders a removal has emptied, never touching the root."""
    directory = (root / relative).parent
    while directory != root and root in directory.parents:
        try:
            next(directory.iterdir())
            return
        except StopIteration:
            directory.rmdir()
        except OSError:
            return
        directory = directory.parent


# --------------------------------------------------------------- execution --

def precheck(plan_id: int, kinds: tuple[str, ...] | None = None) -> tuple:
    """Everything that can refuse a run, checked before one is started.

    The interface calls this first so a refusal is a message on the page, not
    a job that quietly fails a second later.
    """
    plan = db.one("SELECT * FROM plans WHERE id = ?", (plan_id,))
    if plan is None:
        raise ApplyRefused("apply.refused.gone")
    set_name = plan["set_name"]

    latest = db.one("SELECT id FROM plans WHERE set_name = ? ORDER BY id DESC LIMIT 1",
                    (set_name,))
    if latest is None or latest["id"] != plan_id:
        raise ApplyRefused("apply.refused.stale")
    if plan["state"] == "blocked":
        raise ApplyRefused("apply.refused.blocked")
    if plan["state"] == "applied":
        raise ApplyRefused("apply.refused.applied")

    master = db.master_of_set(set_name)
    if master is None:
        raise ApplyRefused("apply.refused.no_master")

    # Reading the master is the same promise as everywhere else: the platform
    # has to confirm it first.
    try:
        backend.verify_readable(master)
    except Exception as exc:                                  # noqa: BLE001
        raise ApplyRefused(str(exc)) from exc

    grouped = selected_items(plan_id, set_name, kinds)
    if not grouped:
        raise ApplyRefused("apply.refused.nothing")

    return plan, master, grouped


def apply_plan(job: Job, plan_id: int, kinds: tuple[str, ...] | None = None) -> int:
    plan, master, grouped = precheck(plan_id, kinds)
    set_name = plan["set_name"]
    master_root = backend.mountpoint_of(master)

    verify = db.get_bool("verify_after_copy")
    keep_mtime = db.get_bool("keep_mtime")
    delete_mode = db.get_setting("delete_mode")
    reserve = db.get_int("slave_free_space_gb") * 1024**3
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    run_id = db.start_run(set_name, plan_id)
    job.set_name = set_name
    job.phase = "apply"

    totals = {"copied": 0, "replaced": 0, "renamed": 0, "deleted": 0,
              "failed": 0, "bytes": 0}
    job.files_total = sum(len(items) for kinds_ in grouped.values()
                          for items in kinds_.values())
    job.bytes_total = sum(
        row["size"] for kinds_ in grouped.values()
        for kind, items in kinds_.items() if kind in (compare.NEW, compare.CHANGED)
        for row in items)
    job.files_done = 0
    job.bytes_done = 0

    for slave_id, by_kind in grouped.items():
        slave = db.disk_by_id(slave_id)
        if slave is None:
            continue
        slave_root = backend.mountpoint_of(slave)
        if not slave_root.is_dir():
            db.log_event("error", f"{slave['display_name']} is not available",
                         set_name, "apply")
            continue

        needed = sum(row["size"] for kind in (compare.NEW, compare.CHANGED)
                     for row in by_kind.get(kind, []))
        try:
            free = fsutil.free_bytes(slave_root)
        except OSError:
            free = 0
        if needed and free - needed < reserve:
            db.log_event(
                "error",
                f"{slave['display_name']}: {fsutil.human_bytes(needed)} needed, "
                f"{fsutil.human_bytes(free)} free - skipped", set_name, "apply")
            continue

        for kind in ORDER:
            for row in by_kind.get(kind, []):
                if not job.should_continue():
                    db.finish_run(run_id, "cancelled",
                                  f"cancelled after {job.files_done} operations")
                    return run_id
                job.current_path = row["path"]
                outcome, error = apply_one(
                    kind, row, master_root, slave_root, slave_id, job,
                    verify=verify, keep_mtime=keep_mtime,
                    delete_mode=delete_mode, stamp=stamp)

                db.execute(
                    "INSERT INTO run_items (run_id, slave_disk_id, kind, path, "
                    "other_path, size, state, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_id, slave_id, kind, row["path"], row["other_path"],
                     row["size"], "done" if error is None else "failed", error))

                job.files_done += 1
                if error is None:
                    totals[outcome] = totals.get(outcome, 0) + 1
                    if kind in (compare.NEW, compare.CHANGED):
                        totals["bytes"] += row["size"]
                        job.bytes_done += row["size"]
                else:
                    totals["failed"] += 1

                db.execute(
                    "UPDATE runs SET copied = ?, replaced = ?, renamed = ?, "
                    "deleted = ?, failed = ?, bytes = ? WHERE id = ?",
                    (totals["copied"], totals["replaced"], totals["renamed"],
                     totals["deleted"], totals["failed"], totals["bytes"], run_id))

    state = "done" if not totals["failed"] else "done_with_errors"
    message = (f"{totals['copied']} copied, {totals['replaced']} replaced, "
               f"{totals['renamed']} renamed, {totals['deleted']} deleted, "
               f"{totals['failed']} failed")
    db.finish_run(run_id, state, message)
    db.execute("UPDATE plans SET state = 'applied' WHERE id = ?", (plan_id,))
    db.log_event("warning" if totals["failed"] else "info",
                 f"run {run_id}: {message}", set_name, "apply")
    notify.send("error" if totals["failed"] else "info",
                "AmberSync: run finished" if not totals["failed"]
                else "AmberSync: run finished with errors",
                message, set_name, run=run_id, bytes=totals["bytes"])
    job.message = message
    job.current_path = ""
    return run_id


def apply_one(kind: str, row, master_root: Path, slave_root: Path, slave_id: int,
              job: Job, *, verify: bool, keep_mtime: bool, delete_mode: str,
              stamp: str) -> tuple[str, str | None]:
    """Carry out a single item. Returns (outcome, error)."""
    path = row["path"]
    target = slave_root / path

    try:
        if kind == compare.RENAMED:
            source = slave_root / row["other_path"]
            if not source.exists():
                return "renamed", "the file to rename is not there any more"
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            prune_empty_parents(slave_root, row["other_path"])
            db.execute("UPDATE files SET path = ? WHERE disk_id = ? AND path = ?",
                       (path, slave_id, row["other_path"]))
            db.forget_synced(slave_id, row["other_path"])
            db.record_synced(slave_id, path, row["slave_sha"] or "", row["size"])
            return "renamed", None

        if kind == compare.DELETED:
            if target.exists():
                remove_file(slave_root, path, stamp, delete_mode)
                prune_empty_parents(slave_root, path)
            db.execute("DELETE FROM files WHERE disk_id = ? AND path = ?",
                       (slave_id, path))
            db.forget_synced(slave_id, path)
            return "deleted", None

        # new and changed both end in a copy
        source = master_root / path
        if not source.exists():
            return "copied", "the original is not there any more"

        if kind == compare.CHANGED and target.exists():
            remove_file(slave_root, path, stamp, delete_mode)

        copy_file(source, target, row["master_sha"], job,
                  verify=verify, keep_mtime=keep_mtime)

        stat = target.stat()
        db.execute(
            "INSERT INTO files (disk_id, path, size, mtime, sha256, hashed_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (disk_id, path) DO UPDATE SET size = excluded.size, "
            "mtime = excluded.mtime, sha256 = excluded.sha256, "
            "hashed_at = excluded.hashed_at",
            (slave_id, path, stat.st_size, stat.st_mtime, row["master_sha"], db.now()))
        db.record_synced(slave_id, path, row["master_sha"], stat.st_size)
        return ("replaced" if kind == compare.CHANGED else "copied"), None

    except InterruptedError:
        raise
    except (OSError, shutil.Error) as exc:
        return ("copied" if kind in (compare.NEW, compare.CHANGED) else kind), str(exc)


# ----------------------------------------------------------------- reading --

def run_summary(run_id: int) -> dict | None:
    row = db.one("SELECT * FROM runs WHERE id = ?", (run_id,))
    return dict(row) if row else None


def run_items(run_id: int, state: str | None = None, offset: int = 0,
              limit: int = 200) -> list:
    where = ["run_id = ?"]
    params: list = [run_id]
    if state:
        where.append("state = ?")
        params.append(state)
    params.extend([limit, offset])
    return db.query(
        f"SELECT * FROM run_items WHERE {' AND '.join(where)} "
        "ORDER BY state = 'done', kind, path LIMIT ? OFFSET ?", params)


def recent_runs(set_name: str | None = None, limit: int = 20) -> list:
    if set_name:
        return db.query("SELECT * FROM runs WHERE set_name = ? ORDER BY id DESC LIMIT ?",
                        (set_name, limit))
    return db.query("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))
