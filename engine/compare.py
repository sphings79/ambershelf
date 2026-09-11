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

from engine import db, fsutil, planner, scanner
from engine.jobs import Job
from platforms import backend

# Kinds a plan item can have.
NEW = "new"                  # on the master, missing on this slave -> copy
CHANGED = "changed"          # both sides have it, contents differ -> ask
RENAMED = "renamed"          # same contents, different path -> ask
SLAVE_ONLY = "slave_only"    # only on the slave, not on the master -> report
OUT_OF_SCOPE = "out_of_scope"  # on the master, but assigned to another slave
UNREADABLE = "unreadable"    # could not be read while scanning -> report

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
    summary["brake"] = evaluate_brake(set_name, summary, master["id"])

    db.execute("UPDATE plans SET state = ?, summary_json = ? WHERE id = ?",
               ("blocked" if summary["brake"]["tripped"] else "ready",
                json.dumps(summary, ensure_ascii=False), plan_id))

    db.log_event(
        "warning" if summary["brake"]["tripped"] else "info",
        f"plan {plan_id}: " + ", ".join(f"{kind} {count:,}" for kind, count in totals.items()),
        set_name, "compare")
    job.message = ", ".join(f"{kind} {count:,}" for kind, count in totals.items()) or "no differences"
    return plan_id


def compare_one(connection, plan_id: int, master_id: int, slave,
                detect_renames: bool) -> dict:
    slave_id = slave["id"]
    items: list[tuple] = []

    def add(kind: str, path: str, size: int, master_sha=None, slave_sha=None,
            other_path=None) -> None:
        items.append((plan_id, slave_id, kind, path, other_path, size, master_sha, slave_sha))

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
            add(CHANGED, path, size, master_sha=master_sha, slave_sha=slave_sha)

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

        add(SLAVE_ONLY, path, size, slave_sha=slave_sha)

    # -- whatever is left really is new --------------------------------------
    for sha, entries in new_by_sha.items():
        for path, size in entries:
            if path not in renamed_paths:
                add(NEW, path, size, master_sha=sha)

    connection.execute("BEGIN")
    connection.executemany(
        "INSERT INTO plan_items (plan_id, slave_disk_id, kind, path, other_path, "
        "size, master_sha, slave_sha) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", items)
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
        "free_bytes": free,
        "needed_bytes": needed,
        "fits": free - needed >= db.get_int("slave_free_space_gb") * 1024**3,
    }


def evaluate_brake(set_name: str, summary: dict, master_id: int) -> dict:
    """Decide whether this plan may proceed without a second look."""
    total_master_files = db.scalar(
        "SELECT COUNT(*) FROM files WHERE disk_id = ?", (master_id,), 0) or 1

    replace_count = sum(
        values["counts"].get(CHANGED, {}).get("files", 0)
        for values in summary["slaves"].values())
    rename_count = sum(
        values["counts"].get(RENAMED, {}).get("files", 0)
        for values in summary["slaves"].values())
    unreadable_count = sum(
        values["counts"].get(UNREADABLE, {}).get("files", 0)
        for values in summary["slaves"].values())

    reasons: list[dict] = []
    limit_absolute = db.get_int("brake_replace_absolute")
    limit_percent = db.get_float("brake_replace_percent")
    percent = replace_count * 100.0 / total_master_files

    if replace_count > limit_absolute:
        reasons.append({"key": "brake.replace_absolute",
                        "params": {"count": f"{replace_count:,}",
                                   "limit": f"{limit_absolute:,}"}})
    if percent > limit_percent:
        reasons.append({"key": "brake.replace_percent",
                        "params": {"percent": f"{percent:.2f}",
                                   "limit": limit_percent}})
    if unreadable_count:
        reasons.append({"key": "brake.unreadable",
                        "params": {"count": f"{unreadable_count:,}"}})

    for values in summary["slaves"].values():
        if not values["fits"]:
            reasons.append({"key": "brake.free_space",
                            "params": {"disk": values["display_name"],
                                       "limit": db.get_int("slave_free_space_gb")}})

    return {
        "tripped": bool(reasons),
        "reasons": reasons,
        "replace_count": replace_count,
        "rename_count": rename_count,
        "unreadable_count": unreadable_count,
        "replace_percent": round(percent, 3),
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
