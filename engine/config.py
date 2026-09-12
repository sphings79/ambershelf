# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Runtime configuration, all overridable by environment variables.

Nothing platform specific belongs here - mount roots and socket paths
live with the backend that uses them.
"""
from __future__ import annotations

import os

from engine import paths

DATA_DIR = paths.app_data_dir()
DB_PATH = DATA_DIR / "ambershelf.db"

# Which address the server was told to listen on. The launcher sets this; a
# container or a hand-started uvicorn does not, and then a login is required.
BIND_HOST = os.environ.get("AMBERSHELF_BIND", "").strip().lower()
LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}


def login_required() -> bool:
    """Whether the interface asks for a password.

    Off only when the server is demonstrably reachable from this computer
    alone - the desktop application talking to itself. Anything unknown
    counts as reachable, because a forgotten switch must never be the reason
    an interface stands open.
    """
    override = os.environ.get("AMBERSHELF_REQUIRE_LOGIN", "auto").strip().lower()
    if override in ("1", "yes", "true", "on"):
        return True
    if override in ("0", "no", "false", "off"):
        return False
    return BIND_HOST not in LOOPBACK

DEFAULT_LANGUAGE = os.environ.get("AMBERSHELF_LANGUAGE", "de")

# Read size while hashing. Large enough that a spinning USB disk stays busy,
# small enough that a pause is noticed quickly.
HASH_BLOCK_SIZE = 4 * 1024 * 1024

# Directories and files that never belong in a copy. Matched case-insensitively
# against a path component (directories) or a whole name (files).
EXCLUDED_DIRS = {
    "$recycle.bin",
    "system volume information",
    ".trash-1000",
    ".trashes",
    ".spotlight-v100",
    ".fseventsd",
    ".documentrevisions-v100",
    ".temporaryitems",
    "found.000",
    ".ambershelf",
    ".ambershelf-trash",
}
EXCLUDED_FILES = {
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
    "ehthumbs.db",
    ".ambershelf.json",
}
# Prefixes that mark a file as noise rather than content.
EXCLUDED_PREFIXES = ("._",)
# Our own half-written files, should a run ever be interrupted.
TEMP_SUFFIX = ".ambershelf-part"

# Where replaced and deleted files are parked on the copy. Keeping them costs
# space; losing them by accident costs more.
TRASH_DIR = ".ambershelf-trash"

# Read and write in blocks this size while copying.
COPY_BLOCK_SIZE = 4 * 1024 * 1024

# Defaults for the brake. Stored in the database on first start and editable
# in the user interface afterwards.
# Same palette and the same five accents as AmberChest, so the two look like
# they belong together.
THEMES = ("system", "light", "dark")
ACCENTS = ("amber", "violet", "blue", "emerald", "rose")

DEFAULT_SETTINGS = {
    "theme": "system",
    "accent": "amber",
    "brake_delete_absolute": "50",
    "brake_delete_percent": "1.0",
    "brake_replace_absolute": "50",
    "brake_replace_percent": "1.0",
    "slave_free_space_gb": "10",
    "detect_renames": "1",
    "verify_after_copy": "1",
    # "trash" parks removed and replaced files under .ambershelf-trash on the
    # copy; "remove" deletes them for good.
    "delete_mode": "trash",
    "keep_mtime": "1",
    # A webhook rather than one particular service: off, errors, warnings, all.
    "notify_url": "",
    "notify_level": "warnings",
    "notify_headers": "",
    "integrity_check": "1",
    # Desktop builds only: "local" runs the engine here, "remote" turns the
    # window into a view onto an AmberShelf running somewhere else.
    "desktop_mode": "local",
    "desktop_remote_url": "",
    "session_days": "30",
    "assignment_depth": "2",
}
