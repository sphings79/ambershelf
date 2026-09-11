# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Comparing a master against its slaves and turning that into a plan.

Everything is compared by size and content hash, never by timestamp. exFAT
stores time with 10 ms resolution in local time, and the same file can carry
different timestamps depending on which machine wrote it - so timestamps are
only ever a hint, never evidence.

A plan is written to the database and shown before anything happens. This
stage never writes to a disk.
"""
from __future__ import annotations

import json

from engine import db, fsutil, integrity, notify, planner, scanner
from engine.jobs import Job
from platforms import backend

# Kinds a plan item can have.
NEW = "new"                  # on the master, missing on this slave -> copy
CHANGED = "changed"          # both sides have it, contents differ -> ask
RENAMED = "renamed"          # same contents, different path -> ask
DELETED = "deleted"          # we put it here, the master no longer has it -> ask
SLAVE_ONLY = "slave_only"    # only on the slave, never came from us -> report
OUT_OF_SCOPE = "out_of_scope"  # on the master, but assigned to another slave
UNREADABLE = "unreadable"    # could not be read while scanning -> report

#: Kinds that never happen without the user saying so, one by one.
NEEDS_APPROVAL = (CHANGED, RENAMED, DELETED)

#: Marks a changed file whose *copy* was altered, not the master.
COPY_MODIFIED = "copy_modified"

UNREADABLE_MARKER = "unreadable"


class NotReady(RuntimeError):
    """The index is incomplete, so a comparison would be guesswork."""


def readiness(set_name: str) -> dict:
    master = db.master_of_set(set_name)
    slaves = db.slaves_of_set(set_name)
    problems: list[str] = []

    if master is None:
        problems.append({"key": "ready.no_master", "params": {}})
    for disk in ([master] if master else []) + list(slaves):
        state = scanner.scan_state(disk["id"])
        if not state["scanned"]:
            problems.append({"key": "ready.not_indexed",
                             "params": {"disk": disk["display_name"]}})
        elif state["unhashed"]:
            problems.append({"key": "ready.unhashed",
                             "params": {"disk": disk["display_name"],
                                        "count": f"{state['unhashed']:,}"}})
    if not slaves:
        problems.append({"key": "ready.no_slave", "params": {}})

    return {"ready": not problems, "problems": problems,
            "master": master, "slaves": slaves}


def build_scope(connection, set_name: str, depth: int, master_id: int,
                split_enabled: bool, slave_ids: list[int]) -> None:
    """Map every master file to the slave it belongs on, in a temp table."""
    connection.execute("DROP TABLE IF EXISTS temp.plan_scope")
    # Keyed by both columns: without splitting every slave carries the same
    # paths, and a key on the path alone would let one slave overwrite the
    # scope of the next.
    connection.execute(
        "CREATE TEMP TABLE plan_scope (path TEXT NOT NULL, disk_id INTEGER NOT NULL, "
        "PRIMARY KEY (disk_id, path)) WITHOUT ROWID")

    if not split_enabled:
        # Without splitting every slave carries everything, so the scope is
        # filled once per slave.
        for slave_id in slave_ids:
            connection.execute(
                "INSERT OR REPLACE INTO temp.plan_scope (path, disk_id) "
                "SELECT path, ? FROM files WHERE disk_id = ?", (slave_id, master_id))
        return

    rules = planner.assignments(set_name)
    batch: list[tuple[str, int]] = []
    for row in connection.execute("SELECT path FROM files WHERE disk_id = ?", (master_id,)):
        rule = planner.resolve(planner.node_key(row[0], depth), rules)
        if rule is None:
            continue
        batch.append((row[0], rule["disk_id"]))
        if len(batch) >= 5000:
            connection.executemany(
                "INSERT OR REPLACE INTO temp.plan_scope (path, disk_id) VALUES (?, ?)", batch)
            batch.clear()
    if batch:
        connection.executemany(
            "INSERT OR REPLACE INTO temp.plan_scope (path, disk_id) VALUES (?, ?)", batch)


def build_plan(job: Job, set_name: str) -> int:
    state = readiness(set_name)
    if not state["ready"]:
        raise NotReady("; ".join(problem["key"] for problem in state["problems"]))

    master = state["master"]
    slaves = state["slaves"]
    depth = db.get_int("assignment_depth")
    split_enabled = bool(db.scalar(
        "SELECT split_enabled FROM sets WHERE name = ?", (set_name,), 0))
    detect_renames = db.get_bool("detect_renames")

    connection = db.connect()
    job.phase = "scope"
    job.message = "working out what belongs where"
    build_scope(connection, set_name, depth, master["id"], split_enabled,
                [s["id"] for s in slaves])

    cursor = db.execute(
        "INSERT INTO plans (set_name, created_at, state) VALUES (?, ?, 'building')",
        (set_name, db.now()))
    plan_id = int(cursor.lastrowid)

    summary: dict = {"slaves": {}, "totals": {}}
    job.files_total = len(slaves)
    job.files_done = 0

    for slave in slaves:
        if not job.should_continue():
            db.execute("UPDATE plans SET state = 'cancelled' WHERE id = ?", (plan_id,))
            return plan_id
        job.phase = "compare"
        job.message = f"comparing {slave['display_name']}"
        summary["slaves"][str(slave["id"])] = compare_one(
            connection, plan_id, master["id"], slave, detect_renames)
        job.files_done += 1

    totals: dict[str, int] = {}
    for values in summary["slaves"].values():
        for kind, counts in values["counts"].items():
            totals[kind] = totals.get(kind, 0) + counts["files"]
    summary["totals"] = totals

    burst = detect_burst(plan_id, set_name, master["id"])
    if burst:
        db.record_finding(set_name, "burst", None, master["id"],
                          detail=f"{burst['files']} of {burst['total']} "
                                 f"within {burst['minutes']} minutes")
    summary["burst"] = burst
    summary["findings"] = [dict(row) for row in db.open_findings(set_name, limit=50)]
    summary["brake"] = evaluate_brake(set_name, summary, master["id"])

    db.execute("UPDATE plans SET state = ?, summary_json = ? WHERE id = ?",
               ("blocked" if summary["brake"]["tripped"] else "ready",
                json.dumps(summary, ensure_ascii=False), plan_id))

    headline = ", ".join(f"{kind} {count:,}" for kind, count in totals.items())
    db.log_event("warning" if summary["brake"]["tripped"] else "info",
                 f"plan {plan_id}: {headline}", set_name, "compare")

    if summary["brake"]["tripped"]:
        notify.send("warning", "AmberSync: the brake tripped",
                    f"The comparison was held back. {headline}.",
                    set_name, plan=plan_id,
                    reasons=[reason["key"] for reason in summary["brake"]["reasons"]])
    job.message = ", ".join(f"{kind} {count:,}" for kind, count in totals.items()) or "no differences"
    return plan_id


def compare_one(connection, plan_id: int, master_id: int, slave,
                detect_renames: bool) -> dict:
    slave_id = slave["id"]
    items: list[tuple] = []

    # What AmberSync itself put on this copy. A file that is in here and gone
    # from the master was deleted; one that is not was never ours to judge.
    written = {
        row[0]: row[1]
        for row in connection.execute(
            "SELECT path, sha256 FROM synced WHERE slave_disk_id = ?", (slave_id,))
    }

    def add(kind: str, path: str, size: int, master_sha=None, slave_sha=None,
            other_path=None, flags=None) -> None:
        items.append((plan_id, slave_id, kind, path, other_path, size,
                      master_sha, slave_sha, flags))

    # -- on the master, missing here -----------------------------------------
    new_by_sha: dict[str, list[tuple[str, int]]] = {}
    new_rows = connection.execute(
        """
        SELECT m.path, m.size, m.sha256
        FROM temp.plan_scope ps
        JOIN files m ON m.disk_id = ? AND m.path = ps.path
        LEFT JOIN files s ON s.disk_id = ? AND s.path = ps.path
        WHERE ps.disk_id = ? AND s.path IS NULL
        ORDER BY m.path
        """, (master_id, slave_id, slave_id)).fetchall()

    for path, size, sha in new_rows:
        if sha == UNREADABLE_MARKER:
            add(UNREADABLE, path, size, master_sha=sha)
            continue
        new_by_sha.setdefault(sha, []).append((path, size))

    # -- present on both sides, different contents ---------------------------
    for path, size, master_sha, slave_sha in connection.execute(
        """
        SELECT m.path, m.size, m.sha256, s.sha256
        FROM temp.plan_scope ps
        JOIN files m ON m.disk_id = ? AND m.path = ps.path
        JOIN files s ON s.disk_id = ? AND s.path = ps.path
        WHERE ps.disk_id = ? AND m.sha256 <> s.sha256
        ORDER BY m.path
        """, (master_id, slave_id, slave_id)).fetchall():
        if UNREADABLE_MARKER in (master_sha, slave_sha):
            add(UNREADABLE, path, size, master_sha=master_sha, slave_sha=slave_sha)
        else:
            # If the copy no longer holds what we wrote, the copy was altered -
            # worth saying, because it is a different story from a changed master.
            altered = written.get(path) not in (None, slave_sha)
            add(CHANGED, path, size, master_sha=master_sha, slave_sha=slave_sha,
                flags=COPY_MODIFIED if altered else None)

    # -- here but not expected here ------------------------------------------
    renamed_paths: set[str] = set()
    for path, size, slave_sha in connection.execute(
        """
        SELECT s.path, s.size, s.sha256
        FROM files s
        LEFT JOIN temp.plan_scope ps ON ps.path = s.path AND ps.disk_id = ?
        WHERE s.disk_id = ? AND ps.path IS NULL
        ORDER BY s.path
        """, (slave_id, slave_id)).fetchall():

        on_master = connection.execute(
            "SELECT 1 FROM files WHERE disk_id = ? AND path = ? LIMIT 1",
            (master_id, path)).fetchone()
        if on_master:
            # The master has this file, it is just assigned to another slave.
            add(OUT_OF_SCOPE, path, size, slave_sha=slave_sha)
            continue

        if detect_renames and slave_sha and slave_sha != UNREADABLE_MARKER:
            candidates = new_by_sha.get(slave_sha) or []
            # Only an unambiguous match counts. With duplicates in the archive
            # a guess would be worse than no guess.
            if len(candidates) == 1:
                new_path, new_size = candidates[0]
                add(RENAMED, new_path, new_size, master_sha=slave_sha,
                    slave_sha=slave_sha, other_path=path)
                renamed_paths.add(new_path)
                new_by_sha.pop(slave_sha, None)
                continue

        if path in written:
            # We put this here and the master does not have it any more.
            add(DELETED, path, size, slave_sha=slave_sha,
                flags=COPY_MODIFIED if written[path] != slave_sha else None)
        else:
            add(SLAVE_ONLY, path, size, slave_sha=slave_sha)

    # -- whatever is left really is new --------------------------------------
    for sha, entries in new_by_sha.items():
        for path, size in entries:
            if path not in renamed_paths:
                add(NEW, path, size, master_sha=sha)

    connection.execute("BEGIN")
    connection.executemany(
        "INSERT INTO plan_items (plan_id, slave_disk_id, kind, path, other_path, "
        "size, master_sha, slave_sha, flags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", items)
    connection.execute("COMMIT")

    counts: dict[str, dict[str, int]] = {}
    for row in connection.execute(
        "SELECT kind, COUNT(*), COALESCE(SUM(size), 0) FROM plan_items "
        "WHERE plan_id = ? AND slave_disk_id = ? GROUP BY kind", (plan_id, slave_id)):
        counts[row[0]] = {"files": row[1], "bytes": row[2]}

    mountpoint = backend.mountpoint_of(slave)
    try:
        free = fsutil.free_bytes(mountpoint)
    except OSError:
        free = 0
    needed = (counts.get(NEW, {}).get("bytes", 0) + counts.get(CHANGED, {}).get("bytes", 0))

    return {
        "display_name": slave["display_name"],
        "counts": counts,
        "ever_written": bool(written),
        "free_bytes": free,
        "needed_bytes": needed,
        "fits": free - needed >= db.get_int("slave_free_space_gb") * 1024**3,
    }


#: A cluster of changes this tight in an archive that sits still for years is
#: not somebody editing photographs.
BURST_WINDOW_SECONDS = 3600
BURST_MINIMUM_FILES = 20
BURST_SHARE = 0.8


def detect_burst(plan_id: int, set_name: str, master_id: int) -> dict | None:
    """Did the changed files all change at nearly the same moment?

    A photo archive gains files in bursts - that is an import. It does not
    *change* in bursts. Timestamps are never evidence on their own here, so
    this only ever adds a reason to look, never a verdict.
    """
    rows = db.query(
        "SELECT f.mtime FROM plan_items p JOIN files f "
        "ON f.disk_id = ? AND f.path = p.path "
        "WHERE p.plan_id = ? AND p.kind = ?",
        (master_id, plan_id, CHANGED))
    times = sorted(row["mtime"] for row in rows if row["mtime"])
    if len(times) < BURST_MINIMUM_FILES:
        return None

    # Widest run of timestamps that fits inside the window.
    best = start = 0
    for end in range(len(times)):
        while times[end] - times[start] > BURST_WINDOW_SECONDS:
            start += 1
        best = max(best, end - start + 1)

    if best < len(times) * BURST_SHARE:
        return None
    return {"files": best, "total": len(times),
            "minutes": BURST_WINDOW_SECONDS // 60}


def evaluate_brake(set_name: str, summary: dict, master_id: int) -> dict:
    """Decide whether this plan may proceed without a second look.

    Two limits per category, absolute and proportional, because neither alone
    is enough: forty files out of two hundred is a catastrophe and forty out
    of a million is a Tuesday.
    """
    total_master_files = db.scalar(
        "SELECT COUNT(*) FROM files WHERE disk_id = ?", (master_id,), 0) or 1

    def total(kind: str) -> int:
        return sum(values["counts"].get(kind, {}).get("files", 0)
                   for values in summary["slaves"].values())

    replace_count = total(CHANGED)
    delete_count = total(DELETED)
    rename_count = total(RENAMED)
    unreadable_count = total(UNREADABLE)

    reasons: list[dict] = []

    replace_percent = replace_count * 100.0 / total_master_files
    if replace_count > db.get_int("brake_replace_absolute"):
        reasons.append({"key": "brake.replace_absolute",
                        "params": {"count": f"{replace_count:,}",
                                   "limit": f"{db.get_int('brake_replace_absolute'):,}"}})
    if replace_percent > db.get_float("brake_replace_percent"):
        reasons.append({"key": "brake.replace_percent",
                        "params": {"percent": f"{replace_percent:.2f}",
                                   "limit": db.get_float("brake_replace_percent")}})

    delete_percent = delete_count * 100.0 / total_master_files
    if delete_count > db.get_int("brake_delete_absolute"):
        reasons.append({"key": "brake.delete_absolute",
                        "params": {"count": f"{delete_count:,}",
                                   "limit": f"{db.get_int('brake_delete_absolute'):,}"}})
    if delete_percent > db.get_float("brake_delete_percent"):
        reasons.append({"key": "brake.delete_percent",
                        "params": {"percent": f"{delete_percent:.2f}",
                                   "limit": db.get_float("brake_delete_percent")}})

    if unreadable_count:
        reasons.append({"key": "brake.unreadable",
                        "params": {"count": f"{unreadable_count:,}"}})

    damaged = db.count_open_findings(set_name)
    if damaged:
        reasons.append({"key": "brake.integrity", "params": {"count": f"{damaged:,}"}})

    for values in summary["slaves"].values():
        if not values["fits"]:
            reasons.append({"key": "brake.free_space",
                            "params": {"disk": values["display_name"],
                                       "limit": db.get_int("slave_free_space_gb")}})

    return {
        "tripped": bool(reasons),
        "reasons": reasons,
        "replace_count": replace_count,
        "delete_count": delete_count,
        "rename_count": rename_count,
        "unreadable_count": unreadable_count,
        "replace_percent": round(replace_percent, 3),
        "delete_percent": round(delete_percent, 3),
        # What the user has to type to release a blocked plan.
        "confirm_number": replace_count + delete_count,
    }


def plan_summary(plan_id: int) -> dict | None:
    row = db.one("SELECT * FROM plans WHERE id = ?", (plan_id,))
    if row is None:
        return None
    data = dict(row)
    try:
        data["summary"] = json.loads(row["summary_json"])
    except ValueError:
        data["summary"] = {}
    return data


def plan_items(plan_id: int, kind: str | None = None, slave_disk_id: int | None = None,
               offset: int = 0, limit: int = 200) -> list[db.sqlite3.Row]:
    where = ["plan_id = ?"]
    params: list = [plan_id]
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if slave_disk_id:
        where.append("slave_disk_id = ?")
        params.append(slave_disk_id)
    params.extend([limit, offset])
    return db.query(
        f"SELECT * FROM plan_items WHERE {' AND '.join(where)} "
        f"ORDER BY kind, path LIMIT ? OFFSET ?", params)


def latest_plan(set_name: str) -> db.sqlite3.Row | None:
    return db.one("SELECT * FROM plans WHERE set_name = ? ORDER BY id DESC LIMIT 1",
                  (set_name,))
