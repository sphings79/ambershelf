# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Filesystem walking and hashing.

Nothing in here ever builds a shell command. Real archives contain folders
called "! Fotos !" - spaces and exclamation marks - so every path is handled
as a path object or as a plain argument, never as a string that some shell
gets to interpret.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable, Iterator

from . import config


def is_excluded_dir(name: str) -> bool:
    return name.lower() in config.EXCLUDED_DIRS


def is_excluded_file(name: str) -> bool:
    lowered = name.lower()
    if lowered in config.EXCLUDED_FILES:
        return True
    if lowered.endswith(config.TEMP_SUFFIX):
        return True
    return name.startswith(config.EXCLUDED_PREFIXES)


def walk(root: Path, on_error: Callable[[str, OSError], None] | None = None
         ) -> Iterator[tuple[str, int, float]]:
    """Yield (relative path, size, mtime) for every regular file below root.

    Symlinks are not followed and not reported. exFAT has none, but a slave
    might be ext4 one day and following links out of the tree would be a
    surprise nobody wants.
    """
    root = root.resolve()
    stack: list[Path] = [root]

    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            if on_error:
                on_error(str(directory), exc)
            continue

        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if not is_excluded_dir(entry.name):
                        stack.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                if is_excluded_file(entry.name):
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                if on_error:
                    on_error(entry.path, exc)
                continue

            relative = os.path.relpath(entry.path, root)
            yield relative.replace(os.sep, "/"), stat.st_size, stat.st_mtime


def sha256(path: Path, should_continue: Callable[[], bool] | None = None) -> str | None:
    """Hash one file. Returns None if the caller asked to stop."""
    digest = hashlib.sha256()
    with open(path, "rb", buffering=0) as fh:
        while True:
            if should_continue is not None and not should_continue():
                return None
            block = fh.read(config.HASH_BLOCK_SIZE)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def free_bytes(path: Path) -> int:
    stat = os.statvfs(path)
    return stat.f_bavail * stat.f_frsize


def total_bytes(path: Path) -> int:
    stat = os.statvfs(path)
    return stat.f_blocks * stat.f_frsize


def human_bytes(value: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(value) < 1024 or unit == "PB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def top_levels(relative_path: str, depth: int) -> str:
    """Cut a relative path down to its first `depth` components."""
    parts = relative_path.split("/")
    return "/".join(parts[:depth])
