#!/usr/bin/env python3
# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""The desktop application: a window around the same interface.

Two modes, chosen in the settings and read again at start-up:

  local   the engine runs here, and the disks plugged into this computer are
          the ones it works with
  remote  the window is a view onto an AmberSync running somewhere else, for
          instance the Docker one on a Linux machine

If a remote is configured but unreachable, the application falls back to
local rather than showing an empty window - and says so. ``--local`` forces
that too, which is how you get back to the settings if a remote was entered
wrongly.
"""
from __future__ import annotations

import argparse
import os
import socket
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# Running from a checkout rather than a bundle, the repository root has to be
# importable before anything else.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("AMBERSYNC_DESKTOP", "1")

from engine import paths                                       # noqa: E402

WINDOW_TITLE = "AmberSync"
WINDOW_SIZE = (1180, 820)
START_TIMEOUT = 25


def stored_setting(key: str, default: str = "") -> str:
    """Read a setting straight from the database, before the server exists."""
    database = paths.app_data_dir() / "ambersync.db"
    if not database.exists():
        return default
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=5)
        try:
            row = connection.execute(
                "SELECT v FROM settings WHERE k = ?", (key,)).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return default
    return row[0] if row and row[0] is not None else default


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def reachable(url: str, timeout: float = 4.0) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/healthz", timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def serve_locally(port: int) -> threading.Thread:
    import uvicorn
    from server.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="ambersync-server", daemon=True)
    thread.start()
    return thread


def wait_until_up(url: str) -> bool:
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if reachable(url, timeout=1.5):
            return True
        time.sleep(0.3)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ambersync", description=__doc__)
    parser.add_argument("--local", action="store_true",
                        help="ignore a configured remote and run the engine here")
    parser.add_argument("--no-window", action="store_true",
                        help="serve without opening a window, for troubleshooting")
    parser.add_argument("--port", type=int, default=0, help="use this port")
    arguments = parser.parse_args(argv)

    mode = "local" if arguments.local else stored_setting("desktop_mode", "local")
    remote = stored_setting("desktop_remote_url", "").strip()

    if mode == "remote" and remote:
        if reachable(remote):
            url = remote.rstrip("/")
        else:
            print(f"{remote} is not answering - starting locally instead",
                  file=sys.stderr)
            mode = "local"
    if mode != "remote" or not remote:
        port = arguments.port or free_port()
        url = f"http://127.0.0.1:{port}"
        serve_locally(port)
        if not wait_until_up(url):
            print("the local server did not start", file=sys.stderr)
            return 1

    if arguments.no_window:
        print(f"AmberSync is at {url} - press Ctrl+C to stop")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    try:
        import webview
    except ImportError:
        print("pywebview is not installed; open this address in a browser:",
              file=sys.stderr)
        print(f"  {url}")
        return 1

    webview.create_window(WINDOW_TITLE, url,
                          width=WINDOW_SIZE[0], height=WINDOW_SIZE[1],
                          min_size=(900, 600))
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
