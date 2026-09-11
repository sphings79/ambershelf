# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""SQLite storage.

One connection per thread; the scanner runs in a worker thread and the web
requests in others. WAL mode so a long running scan does not block the
interface.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Iterable

from . import config

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
    PRIMARY KEY (disk_id, path)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_files_sha  ON files (disk_id, sha256);
CREATE INDEX IF NOT EXISTS idx_files_scan ON files (disk_id, seen_scan);
CREATE INDEX IF NOT EXISTS idx_files_todo ON files (disk_id) WHERE sha256 IS NULL;

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
]


def migrate(connection: sqlite3.Connection) -> None:
    for table, column, definition in MIGRATIONS:
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue        # the table itself is new, the schema already has it
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialise() -> None:
    connection = connect()
    connection.executescript(SCHEMA)
    migrate(connection)
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
