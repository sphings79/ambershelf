# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""SQLite storage.

One connection per thread; the scanner runs in a worker thread and the web
requests in others. WAL mode so a long running scan does not block the
interface.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Iterable

from engine import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS disks (
    id            INTEGER PRIMARY KEY,
    fs_uuid       TEXT NOT NULL UNIQUE,
    serial        TEXT,
    label         TEXT,
    model         TEXT,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    fs_type       TEXT,
    role          TEXT NOT NULL CHECK (role IN ('master', 'slave')),
    set_name      TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    last_seen_at  TEXT
);

CREATE TABLE IF NOT EXISTS sets (
    name          TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    split_enabled INTEGER NOT NULL DEFAULT 0
);

-- Which subtree of the master belongs on which slave. A path is covered by
-- the most specific assignment that is a prefix of it.
CREATE TABLE IF NOT EXISTS assignments (
    id       INTEGER PRIMARY KEY,
    set_name TEXT NOT NULL,
    path     TEXT NOT NULL,
    disk_id  INTEGER NOT NULL REFERENCES disks(id) ON DELETE CASCADE,
    UNIQUE (set_name, path)
);

CREATE TABLE IF NOT EXISTS scans (
    id           INTEGER PRIMARY KEY,
    disk_id      INTEGER NOT NULL REFERENCES disks(id) ON DELETE CASCADE,
    set_name     TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    state        TEXT NOT NULL,
    phase        TEXT,
    files_total  INTEGER NOT NULL DEFAULT 0,
    bytes_total  INTEGER NOT NULL DEFAULT 0,
    files_hashed INTEGER NOT NULL DEFAULT 0,
    bytes_hashed INTEGER NOT NULL DEFAULT 0,
    current_path TEXT,
    message      TEXT,
    -- Counts rather than a sentence, so the interface can phrase them in
    -- whichever language the reader picked.
    summary_json TEXT NOT NULL DEFAULT '{}'
);

-- The index of one disk. sha256 stays NULL until the file has been hashed,
-- which is what makes a scan resumable.
CREATE TABLE IF NOT EXISTS files (
    disk_id   INTEGER NOT NULL REFERENCES disks(id) ON DELETE CASCADE,
    path      TEXT NOT NULL,
    size      INTEGER NOT NULL,
    mtime     REAL NOT NULL,
    sha256    TEXT,
    hashed_at TEXT,
    seen_scan INTEGER,
    -- What the integrity check made of it: ok, no_check, wrong_extension,
    -- header_mismatch, text_garbled, empty, unreadable. NULL means not
    -- looked at yet. Only the last three count as damage.
    health    TEXT,
    PRIMARY KEY (disk_id, path)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_files_sha  ON files (disk_id, sha256);
CREATE INDEX IF NOT EXISTS idx_files_scan ON files (disk_id, seen_scan);
CREATE INDEX IF NOT EXISTS idx_files_todo ON files (disk_id) WHERE sha256 IS NULL;
CREATE INDEX IF NOT EXISTS idx_files_health ON files (disk_id, health);

-- Aggregated view of the master tree, cut at a fixed depth. Rebuilt after a
-- master scan so the assignment screen does not have to touch every file.
CREATE TABLE IF NOT EXISTS tree_nodes (
    set_name TEXT NOT NULL,
    depth    INTEGER NOT NULL,
    path     TEXT NOT NULL,
    files    INTEGER NOT NULL DEFAULT 0,
    bytes    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (set_name, depth, path)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS plans (
    id           INTEGER PRIMARY KEY,
    set_name     TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    state        TEXT NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS plan_items (
    id            INTEGER PRIMARY KEY,
    plan_id       INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    slave_disk_id INTEGER NOT NULL REFERENCES disks(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,
    path          TEXT NOT NULL,
    other_path    TEXT,
    size          INTEGER NOT NULL DEFAULT 0,
    master_sha    TEXT,
    slave_sha     TEXT,
    flags         TEXT
);

CREATE INDEX IF NOT EXISTS idx_plan_items ON plan_items (plan_id, kind, slave_disk_id);

-- What AmberShelf itself has written to a copy. Without this there is no way
-- to tell a file that was deleted from the master from one that was never
-- there in the first place - so deletions simply are not offered until a
-- copy has been written to at least once.
CREATE TABLE IF NOT EXISTS synced (
    slave_disk_id INTEGER NOT NULL REFERENCES disks(id) ON DELETE CASCADE,
    path          TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    size          INTEGER NOT NULL DEFAULT 0,
    synced_at     TEXT NOT NULL,
    PRIMARY KEY (slave_disk_id, path)
) WITHOUT ROWID;

-- One application of a plan.
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY,
    plan_id      INTEGER REFERENCES plans(id) ON DELETE SET NULL,
    set_name     TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    state        TEXT NOT NULL,
    copied       INTEGER NOT NULL DEFAULT 0,
    replaced     INTEGER NOT NULL DEFAULT 0,
    renamed      INTEGER NOT NULL DEFAULT 0,
    deleted      INTEGER NOT NULL DEFAULT 0,
    failed       INTEGER NOT NULL DEFAULT 0,
    bytes        INTEGER NOT NULL DEFAULT 0,
    message      TEXT
);

CREATE TABLE IF NOT EXISTS run_items (
    id            INTEGER PRIMARY KEY,
    run_id        INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    slave_disk_id INTEGER NOT NULL,
    kind          TEXT NOT NULL,
    path          TEXT NOT NULL,
    other_path    TEXT,
    size          INTEGER NOT NULL DEFAULT 0,
    state         TEXT NOT NULL,
    error         TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_items ON run_items (run_id, state, kind);

-- Remembered answers, so the same fifty cases are not asked again every run.
CREATE TABLE IF NOT EXISTS decisions (
    id         INTEGER PRIMARY KEY,
    set_name   TEXT NOT NULL,
    disk_id    INTEGER,
    path       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    decision   TEXT NOT NULL CHECK (decision IN ('approve', 'skip_once', 'skip_forever')),
    decided_at TEXT NOT NULL,
    note       TEXT,
    UNIQUE (set_name, disk_id, path, kind)
);

-- Anything the integrity check objected to. Kept rather than recomputed, so
-- the interface can show it without touching the disk again.
CREATE TABLE IF NOT EXISTS findings (
    id       INTEGER PRIMARY KEY,
    set_name TEXT NOT NULL,
    disk_id  INTEGER,
    scan_id  INTEGER,
    kind     TEXT NOT NULL,
    path     TEXT,
    detail   TEXT,
    found_at TEXT NOT NULL,
    cleared  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_findings ON findings (set_name, cleared, kind);

-- Server-side sessions. The cookie carries nothing but the token, so signing
-- it would add a dependency for no gain, and logging out takes effect at once.
CREATE TABLE IF NOT EXISTS sessions (
    token        TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    address      TEXT,
    user_agent   TEXT
) WITHOUT ROWID;

-- The last thing a disk said about its own health. Kept so the page can
-- show it without spinning up a sleeping disk to ask again.
CREATE TABLE IF NOT EXISTS smart (
    disk_id    INTEGER PRIMARY KEY REFERENCES disks(id) ON DELETE CASCADE,
    checked_at TEXT NOT NULL,
    level      TEXT NOT NULL,        -- ok, warn, danger, unknown
    report     TEXT NOT NULL         -- the interpreted report, as JSON
);

CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY,
    at         TEXT NOT NULL,
    level      TEXT NOT NULL,
    set_name   TEXT,
    source     TEXT,
    message    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_at ON events (at DESC);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    connection = getattr(_local, "connection", None)
    if connection is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(config.DB_PATH, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        _local.connection = connection
    return connection


# Columns added after a table already existed somewhere. CREATE TABLE IF NOT
# EXISTS does not touch an existing table, so they are added by hand.
MIGRATIONS = [
    ("scans", "summary_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("files", "health", "TEXT"),
]


def migrate(connection: sqlite3.Connection) -> None:
    """Add columns that older databases are missing.

    Runs before the schema script, because that script builds indexes over
    these columns and an index cannot be created over something that is not
    there yet. A table that does not exist at all is skipped - the schema
    creates it complete.
    """
    for table, column, definition in MIGRATIONS:
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialise() -> None:
    connection = connect()
    # Columns first: the schema below creates indexes over columns that older
    # databases do not have yet, and an index cannot wait for a migration.
    migrate(connection)
    connection.executescript(SCHEMA)
    for key, value in config.DEFAULT_SETTINGS.items():
        connection.execute("INSERT OR IGNORE INTO settings (k, v) VALUES (?, ?)", (key, value))


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return connect().execute(sql, tuple(params)).fetchall()


def one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return connect().execute(sql, tuple(params)).fetchone()


def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    return connect().execute(sql, tuple(params))


def scalar(sql: str, params: Iterable[Any] = (), default: Any = None) -> Any:
    row = one(sql, params)
    if row is None or row[0] is None:
        return default
    return row[0]


# ---------------------------------------------------------------- settings --

def get_setting(key: str, default: str | None = None) -> str:
    value = scalar("SELECT v FROM settings WHERE k = ?", (key,))
    if value is not None:
        return value
    if default is not None:
        return default
    return config.DEFAULT_SETTINGS.get(key, "")


def get_int(key: str) -> int:
    try:
        return int(float(get_setting(key)))
    except ValueError:
        return int(float(config.DEFAULT_SETTINGS.get(key, "0")))


def get_float(key: str) -> float:
    try:
        return float(get_setting(key))
    except ValueError:
        return float(config.DEFAULT_SETTINGS.get(key, "0"))


def get_bool(key: str) -> bool:
    return get_setting(key) not in ("", "0", "false", "no")


def set_setting(key: str, value: str) -> None:
    execute("INSERT INTO settings (k, v) VALUES (?, ?) "
            "ON CONFLICT (k) DO UPDATE SET v = excluded.v", (key, value))


# ------------------------------------------------------------------ events --

def log_event(level: str, message: str, set_name: str | None = None,
              source: str | None = None) -> None:
    execute("INSERT INTO events (at, level, set_name, source, message) VALUES (?, ?, ?, ?, ?)",
            (now(), level, set_name, source, message))


# ------------------------------------------------------------------- disks --

def sync_disks_from_helper(registrations: list[dict]) -> None:
    """Mirror the host registry into the database.

    The host configuration is the authority for roles - this only copies it
    so the interface can join against it. A role that changed on the host
    wins here too.
    """
    connection = connect()
    for entry in registrations:
        connection.execute(
            """
            INSERT INTO disks (fs_uuid, serial, label, model, size_bytes, fs_type,
                               role, set_name, display_name, registered_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (fs_uuid) DO UPDATE SET
                serial       = excluded.serial,
                label        = excluded.label,
                model        = excluded.model,
                size_bytes   = excluded.size_bytes,
                fs_type      = excluded.fs_type,
                role         = excluded.role,
                set_name     = excluded.set_name,
                display_name = excluded.display_name
            """,
            (entry["fs_uuid"], entry.get("serial"), entry.get("label"), entry.get("model"),
             entry.get("size") or 0, entry.get("fs_type"), entry["role"], entry["set_name"],
             entry["display_name"], entry.get("registered_at") or now(),
             entry.get("last_seen_at")),
        )
        connection.execute(
            "INSERT OR IGNORE INTO sets (name, created_at) VALUES (?, ?)",
            (entry["set_name"], now()),
        )

    known = {entry["fs_uuid"] for entry in registrations}
    for row in query("SELECT id, fs_uuid FROM disks"):
        if row["fs_uuid"] not in known:
            # Removed on the host - drop the index with it, it is worthless now.
            connection.execute("DELETE FROM disks WHERE id = ?", (row["id"],))


def disk_by_uuid(fs_uuid: str) -> sqlite3.Row | None:
    return one("SELECT * FROM disks WHERE fs_uuid = ?", (fs_uuid,))


def disk_by_id(disk_id: int) -> sqlite3.Row | None:
    return one("SELECT * FROM disks WHERE id = ?", (disk_id,))


def disks_of_set(set_name: str) -> list[sqlite3.Row]:
    return query("SELECT * FROM disks WHERE set_name = ? "
                 "ORDER BY role = 'slave', display_name", (set_name,))


def master_of_set(set_name: str) -> sqlite3.Row | None:
    return one("SELECT * FROM disks WHERE set_name = ? AND role = 'master'", (set_name,))


def slaves_of_set(set_name: str) -> list[sqlite3.Row]:
    return query("SELECT * FROM disks WHERE set_name = ? AND role = 'slave' "
                 "ORDER BY display_name", (set_name,))


def all_sets() -> list[sqlite3.Row]:
    return query("SELECT * FROM sets ORDER BY name")


# ------------------------------------------------------------------- runs --

def start_run(set_name: str, plan_id: int) -> int:
    cursor = execute(
        "INSERT INTO runs (plan_id, set_name, started_at, state) VALUES (?, ?, ?, 'running')",
        (plan_id, set_name, now()))
    return int(cursor.lastrowid)


def finish_run(run_id: int, state: str, message: str = "") -> None:
    execute("UPDATE runs SET state = ?, finished_at = ?, message = ? WHERE id = ?",
            (state, now(), message, run_id))


def record_synced(slave_disk_id: int, path: str, sha256: str, size: int) -> None:
    execute(
        "INSERT INTO synced (slave_disk_id, path, sha256, size, synced_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (slave_disk_id, path) DO UPDATE SET "
        "sha256 = excluded.sha256, size = excluded.size, synced_at = excluded.synced_at",
        (slave_disk_id, path, sha256, size, now()))


def forget_synced(slave_disk_id: int, path: str) -> None:
    execute("DELETE FROM synced WHERE slave_disk_id = ? AND path = ?",
            (slave_disk_id, path))


def has_been_written_to(slave_disk_id: int) -> bool:
    """Whether AmberShelf has ever written to this copy.

    Everything about deletions hangs off this: before the first write there
    is nothing to compare against, and guessing would be worse than saying so.
    """
    return bool(scalar("SELECT 1 FROM synced WHERE slave_disk_id = ? LIMIT 1",
                       (slave_disk_id,), 0))


# --------------------------------------------------------------- decisions --

def remembered_decisions(set_name: str) -> dict:
    """{(disk_id, kind, path): decision}"""
    return {
        (row["disk_id"], row["kind"], row["path"]): row["decision"]
        for row in query("SELECT disk_id, kind, path, decision FROM decisions "
                         "WHERE set_name = ?", (set_name,))
    }


def remember_decision(set_name: str, disk_id: int | None, path: str, kind: str,
                      decision: str) -> None:
    if decision == "forget":
        execute("DELETE FROM decisions WHERE set_name = ? AND disk_id IS ? "
                "AND path = ? AND kind = ?", (set_name, disk_id, path, kind))
        return
    execute(
        "INSERT INTO decisions (set_name, disk_id, path, kind, decision, decided_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (set_name, disk_id, path, kind) DO UPDATE SET "
        "decision = excluded.decision, decided_at = excluded.decided_at",
        (set_name, disk_id, path, kind, decision, now()))


# ---------------------------------------------------------------- findings --

def record_finding(set_name: str, kind: str, path: str | None = None,
                   disk_id: int | None = None, scan_id: int | None = None,
                   detail: str | None = None) -> None:
    execute(
        "INSERT INTO findings (set_name, disk_id, scan_id, kind, path, detail, found_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (set_name, disk_id, scan_id, kind, path, detail, now()))


def open_findings(set_name: str | None = None, limit: int = 500) -> list:
    if set_name:
        return query("SELECT * FROM findings WHERE cleared = 0 AND set_name = ? "
                     "ORDER BY id DESC LIMIT ?", (set_name, limit))
    return query("SELECT * FROM findings WHERE cleared = 0 ORDER BY id DESC LIMIT ?",
                 (limit,))


def count_open_findings(set_name: str | None = None) -> int:
    if set_name:
        return scalar("SELECT COUNT(*) FROM findings WHERE cleared = 0 AND set_name = ?",
                      (set_name,), 0)
    return scalar("SELECT COUNT(*) FROM findings WHERE cleared = 0", (), 0)


def clear_findings(set_name: str, kind: str | None = None) -> int:
    if kind:
        return execute("UPDATE findings SET cleared = 1 WHERE set_name = ? AND kind = ?",
                       (set_name, kind)).rowcount
    return execute("UPDATE findings SET cleared = 1 WHERE set_name = ?",
                   (set_name,)).rowcount


def drop_findings_of_scan(disk_id: int) -> None:
    """A fresh scan of a disk replaces whatever the last one found."""
    execute("DELETE FROM findings WHERE disk_id = ?", (disk_id,))


# --------------------------------------------------------------- removal --

def forget_disk(disk_id: int) -> dict:
    """Drop everything this installation knows about one disk.

    Nothing on the disk itself is touched - this is the index, the plans and
    the history, not a single file.
    """
    removed = {}
    for table, where, params in (
        ("plan_items", "slave_disk_id = ?", (disk_id,)),
        ("run_items", "slave_disk_id = ?", (disk_id,)),
        ("assignments", "disk_id = ?", (disk_id,)),
        ("synced", "slave_disk_id = ?", (disk_id,)),
        ("decisions", "disk_id = ?", (disk_id,)),
        ("findings", "disk_id = ?", (disk_id,)),
        ("smart", "disk_id = ?", (disk_id,)),
        ("scans", "disk_id = ?", (disk_id,)),
        ("files", "disk_id = ?", (disk_id,)),
        ("disks", "id = ?", (disk_id,)),
    ):
        count = execute(f"DELETE FROM {table} WHERE {where}", params).rowcount
        if count:
            removed[table] = count
    return removed


RULES_VERSION_KEY = "integrity_rules_version"

#: Findings that come from looking inside a file, and are therefore only as
#: good as the signature table. Name-based ones are not affected.
CONTENT_FINDINGS = ("header_mismatch", "text_garbled", "empty")


def forget_verdicts_on_new_rules(version: int) -> int:
    """Throw away every integrity verdict when the rules behind it changed.

    Without this a corrected signature only ever helps files indexed after
    the correction, and the wrong verdicts on everything else stay on the
    page for good.
    """
    if get_setting(RULES_VERSION_KEY, "0") == str(version):
        return 0
    affected = execute("UPDATE files SET health = NULL WHERE health IS NOT NULL").rowcount
    marks = ", ".join("?" * len(CONTENT_FINDINGS))
    execute(f"DELETE FROM findings WHERE kind IN ({marks})", CONTENT_FINDINGS)
    set_setting(RULES_VERSION_KEY, str(version))
    return affected


def close_interrupted() -> dict[str, int]:
    """Finish anything that was still marked as running.

    A job only lives in the process that started it. If that process is gone
    - a container restart, a crash, a host that lost power - the row it left
    behind says "running" and will say so forever, which is worse than
    useless: it is the one state that means "wait, this is still working".
    Nothing can be resumed from here, so it is closed and said so.
    """
    closed: dict[str, int] = {}
    stamp = now()
    for table, extra in (("runs", ""), ("scans", ", phase = 'interrupted'")):
        count = execute(
            f"UPDATE {table} SET state = 'interrupted', finished_at = ?, "
            f"message = ?{extra} WHERE state IN ('running', 'paused', 'queued')",
            (stamp, "interrupted - AmberShelf was restarted while this was running"),
        ).rowcount
        if count:
            closed[table] = count
    return closed


def store_smart(disk_id: int, report: dict) -> str:
    """Keep the latest report, and say at which level it lands."""
    if not report.get("available"):
        level = "unknown"
    elif any(a["level"] == "danger" for a in report.get("alarms", [])):
        level = "danger"
    elif report.get("alarms"):
        level = "warn"
    else:
        level = "ok"
    execute("INSERT INTO smart (disk_id, checked_at, level, report) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (disk_id) DO UPDATE SET checked_at = excluded.checked_at, "
            "level = excluded.level, report = excluded.report",
            (disk_id, report.get("checked_at") or now(), level, json.dumps(report)))
    return level


def smart_reports() -> dict[int, dict]:
    """Every stored report, by disk, ready for a template."""
    result = {}
    for row in query("SELECT * FROM smart"):
        try:
            report = json.loads(row["report"])
        except ValueError:
            continue
        # A report written by an older version may not have the shape the
        # page expects. It is only a cache of the last answer, so it is
        # dropped rather than migrated - the next check writes a fresh one.
        if report.get("available") and "readings" not in report:
            continue
        report["level"] = row["level"]
        report["checked_at"] = row["checked_at"]
        result[row["disk_id"]] = report
    return result


def forget_set(set_name: str) -> dict:
    """Drop a whole set: every disk in it, and everything about the set."""
    removed: dict[str, int] = {}
    for row in query("SELECT id FROM disks WHERE set_name = ?", (set_name,)):
        for table, count in forget_disk(row["id"]).items():
            removed[table] = removed.get(table, 0) + count
    for table in ("plan_items", "plans", "run_items", "runs", "assignments",
                  "findings", "tree_nodes", "synced", "decisions", "sets"):
        column = "name" if table == "sets" else "set_name"
        try:
            count = execute(f"DELETE FROM {table} WHERE {column} = ?",
                            (set_name,)).rowcount
        except sqlite3.OperationalError:
            continue
        if count:
            removed[table] = removed.get(table, 0) + count
    return removed


def set_is_empty(set_name: str) -> bool:
    return not scalar("SELECT 1 FROM disks WHERE set_name = ? LIMIT 1",
                      (set_name,), 0)
