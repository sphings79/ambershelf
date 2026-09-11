# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Where things live, per platform.

Its own module on purpose: the engine and the platform layer both need this,
and neither may import the other.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def desktop_build() -> bool:
    """True when running as the packaged application rather than in Docker."""
    return os.environ.get("AMBERSYNC_DESKTOP") == "1" or getattr(sys, "frozen", False)


def app_data_dir() -> Path:
    """Where this platform expects an application to keep its things."""
    override = os.environ.get("AMBERSYNC_DATA_DIR")
    if override:
        return Path(override)
    if not desktop_build():
        return Path("/data")               # the volume the container mounts
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AmberSync"
    if sys.platform in ("win32", "cygwin"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "AmberSync"
    return Path(os.environ.get("XDG_DATA_HOME",
                               Path.home() / ".local" / "share")) / "ambersync"


def resource_dir() -> Path:
    """Where the templates and stylesheets are, bundled or not."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle)
    return Path(__file__).resolve().parent.parent
