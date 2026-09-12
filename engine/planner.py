# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Splitting a master across several slaves.

The unit of assignment is a folder, not a file - a year or an event stays
together and a slave disk remains something you can browse on its own.

Two rules that matter more than the packing itself:
  * an assignment never moves by itself, because reshuffling terabytes on
    every run is not a feature;
  * a folder that is covered by no slave is the dangerous case, so it is
    counted, named and shown at the top rather than buried in a report.
"""
from __future__ import annotations

from engine import db

ROOT_NODE = "(root)"

# How much room to leave on a slave, so a disk never runs dead full.
RESERVE_FACTOR = 0.02


def node_key(relative_path: str, depth: int) -> str:
    """The folder a file is assigned through, at the given tree depth."""
    parts = relative_path.split("/")
    cut = min(depth, len(parts) - 1)
    if cut <= 0:
        return ROOT_NODE
    return "/".join(parts[:cut])


def rebuild_tree(set_name: str, depth: int) -> int:
    """Recompute the folder aggregate for the master of this set."""
    master = db.master_of_set(set_name)
    if master is None:
        return 0

    totals: dict[str, list[int]] = {}
    for row in db.query("SELECT path, size FROM files WHERE disk_id = ?", (master["id"],)):
        key = node_key(row["path"], depth)
        entry = totals.setdefault(key, [0, 0])
        entry[0] += 1
        entry[1] += row["size"]

    connection = db.connect()
    connection.execute("BEGIN")
    connection.execute("DELETE FROM tree_nodes WHERE set_name = ? AND depth = ?",
                       (set_name, depth))
    connection.executemany(
        "INSERT INTO tree_nodes (set_name, depth, path, files, bytes) VALUES (?, ?, ?, ?, ?)",
        [(set_name, depth, path, values[0], values[1]) for path, values in totals.items()],
    )
    connection.execute("COMMIT")
    return len(totals)


def nodes(set_name: str, depth: int) -> list[db.sqlite3.Row]:
    return db.query(
        "SELECT * FROM tree_nodes WHERE set_name = ? AND depth = ? ORDER BY path",
        (set_name, depth))


def assignments(set_name: str) -> list[db.sqlite3.Row]:
    return db.query(
        "SELECT a.*, d.display_name FROM assignments a "
        "JOIN disks d ON d.id = a.disk_id WHERE a.set_name = ? ORDER BY length(a.path) DESC",
        (set_name,))


def resolve(node_path: str, rules: list[db.sqlite3.Row]) -> db.sqlite3.Row | None:
    """Longest matching prefix wins, so a deeper rule overrides a broader one."""
    best = None
    for rule in rules:
        path = rule["path"]
        if node_path == path or node_path.startswith(path + "/"):
            if best is None or len(path) > len(best["path"]):
                best = rule
    return best


def assign(set_name: str, path: str, disk_id: int | None) -> None:
    if disk_id is None:
        db.execute("DELETE FROM assignments WHERE set_name = ? AND path = ?", (set_name, path))
        return
    db.execute(
        "INSERT INTO assignments (set_name, path, disk_id) VALUES (?, ?, ?) "
        "ON CONFLICT (set_name, path) DO UPDATE SET disk_id = excluded.disk_id",
        (set_name, path, disk_id))


def overview(set_name: str, depth: int) -> dict:
    """Everything the assignment screen needs, in one pass."""
    slaves = db.slaves_of_set(set_name)
    split_enabled = bool(db.scalar(
        "SELECT split_enabled FROM sets WHERE name = ?", (set_name,), 0))
    rules = assignments(set_name)
    tree = nodes(set_name, depth)

    per_disk = {slave["id"]: {"disk": slave, "files": 0, "bytes": 0, "nodes": []}
                for slave in slaves}
    uncovered: list[dict] = []
    mixed: list[dict] = []
    rows: list[dict] = []

    deeper_rules = [r for r in rules if len(r["path"].split("/")) > depth]

    for node in tree:
        rule = resolve(node["path"], rules)
        entry = {
            "path": node["path"],
            "files": node["files"],
            "bytes": node["bytes"],
            "disk_id": rule["disk_id"] if rule else None,
            "assigned_via": rule["path"] if rule else None,
            "inherited": bool(rule and rule["path"] != node["path"]),
        }
        # A rule below the current depth splits this node between disks.
        if any(r["path"].startswith(node["path"] + "/") for r in deeper_rules):
            entry["mixed"] = True
            mixed.append(entry)
        rows.append(entry)

        if rule is None:
            uncovered.append(entry)
        elif rule["disk_id"] in per_disk:
            per_disk[rule["disk_id"]]["files"] += node["files"]
            per_disk[rule["disk_id"]]["bytes"] += node["bytes"]
            per_disk[rule["disk_id"]]["nodes"].append(node["path"])

    for values in per_disk.values():
        capacity = int(values["disk"]["size_bytes"] * (1 - RESERVE_FACTOR))
        values["capacity"] = capacity
        values["over"] = values["bytes"] > capacity
        values["percent"] = round(values["bytes"] * 100.0 / capacity, 1) if capacity else 0.0

    return {
        "split_enabled": split_enabled,
        "depth": depth,
        "nodes": rows,
        "slaves": list(per_disk.values()),
        "uncovered": uncovered,
        "uncovered_bytes": sum(n["bytes"] for n in uncovered),
        "uncovered_files": sum(n["files"] for n in uncovered),
        "mixed": mixed,
        "orphan_rules": [dict(r) for r in deeper_rules],
        "total_bytes": sum(n["bytes"] for n in tree),
        "total_files": sum(n["files"] for n in tree),
    }


def suggest(set_name: str, depth: int) -> list[tuple[str, int]]:
    """First fit decreasing over everything that is not assigned yet.

    Returns proposals, it does not write them. Moving data that already sits
    on a slave is never proposed.
    """
    state = overview(set_name, depth)
    if not state["slaves"]:
        return []

    remaining = {
        entry["disk"]["id"]: entry["capacity"] - entry["bytes"]
        for entry in state["slaves"]
    }
    proposals: list[tuple[str, int]] = []

    for node in sorted(state["uncovered"], key=lambda n: n["bytes"], reverse=True):
        target = max(remaining, key=lambda disk_id: remaining[disk_id])
        if remaining[target] < node["bytes"]:
            continue        # does not fit anywhere; stays uncovered and visible
        remaining[target] -= node["bytes"]
        proposals.append((node["path"], target))

    return proposals


def target_disk_for(set_name: str, relative_path: str, depth: int,
                    rules: list[db.sqlite3.Row] | None = None) -> int | None:
    """Which slave a single master file belongs on. None means nowhere."""
    if rules is None:
        rules = assignments(set_name)
    rule = resolve(node_key(relative_path, depth), rules)
    return rule["disk_id"] if rule else None
