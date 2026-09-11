#!/usr/bin/env python3
# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Start the built application and ask it for a page.

A build that imports cleanly but cannot find its own templates is a build
that fails on the user's machine and nowhere else, so the packaged binary is
started for real here rather than merely produced.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PORT = 8123
PAGES = ("/healthz", "/", "/disks", "/settings", "/findings", "/events")


def executable() -> Path:
    macos = Path("dist/AmberSync.app/Contents/MacOS/AmberSync")
    if macos.exists():
        return macos
    for candidate in (Path("dist/AmberSync/AmberSync.exe"), Path("dist/AmberSync/AmberSync")):
        if candidate.exists():
            return candidate
    raise SystemExit("no build found under dist/")


def fetch(path: str) -> int:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=5) as answer:
            return answer.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError):
        return 0


def main() -> int:
    binary = executable()
    print(f"  starting {binary}")

    environment = dict(os.environ)
    environment["AMBERSYNC_DATA_DIR"] = tempfile.mkdtemp(prefix="ambersync-smoke-")
    environment["AMBERSYNC_DESKTOP"] = "1"

    process = subprocess.Popen(
        [str(binary), "--no-window", "--port", str(PORT)],
        env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if fetch("/healthz") == 200:
                break
            if process.poll() is not None:
                print(process.stdout.read() if process.stdout else "")
                raise SystemExit("the application exited before answering")
            time.sleep(1)
        else:
            raise SystemExit("the application did not answer in time")

        failed = []
        for page in PAGES:
            status = fetch(page)
            print(f"  {status}  {page}")
            if status != 200:
                failed.append(page)
        if failed:
            raise SystemExit(f"pages did not answer: {', '.join(failed)}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()

    print("  the packaged build starts and serves its pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
