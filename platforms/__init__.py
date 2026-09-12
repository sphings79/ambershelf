# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Picks the platform backend once, at import time."""
from __future__ import annotations

import os
import sys

from platforms.base import Backend, BackendError, BackendUnavailable, MountReport, Volume

__all__ = ["Backend", "BackendError", "BackendUnavailable", "MountReport", "Volume",
           "backend", "backend_name"]


def _choose() -> Backend:
    forced = os.environ.get("AMBERSHELF_BACKEND", "").strip().lower()
    if forced:
        name = forced
    elif sys.platform == "darwin":
        name = "macos"
    elif sys.platform in ("win32", "cygwin"):
        name = "windows"
    else:
        name = "linux"

    if name == "linux":
        from platforms.linux import LinuxBackend
        return LinuxBackend()
    if name == "macos":
        from platforms.macos import MacBackend
        return MacBackend()
    if name == "windows":
        from platforms.windows import WindowsBackend
        return WindowsBackend()
    raise BackendUnavailable(f"unknown backend {name!r}")


backend: Backend = _choose()
backend_name: str = backend.name
