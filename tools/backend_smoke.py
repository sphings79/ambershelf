#!/usr/bin/env python3
# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Does the platform backend work on a real machine of this kind?

Run on the macOS and Windows runners. A build machine has no external disks,
so this cannot prove that a USB drive is recognised - what it proves is that
the system tools answer, that their output parses, and that nothing throws.
That is the part most likely to be wrong, and it is the part I cannot try on
my own desk for Windows.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AMBERSHELF_DESKTOP", "1")

failures: list[str] = []


def check(title: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {title}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(title)


def main() -> int:
    from platforms import backend
    from platforms.registry import JsonRegistry

    print(f"AmberShelf backend smoke test on {sys.platform}\n")
    check(f"backend chosen: {backend.name}",
          backend.name in ("macos", "windows", "linux"))
    check("the backend reports no write protection on a desktop system",
          backend.enforces_write_protection is False or backend.name == "linux")
    check("the system tools answer", backend.available())

    try:
        volumes = backend.list_volumes()
        ok = True
        detail = f"{len(volumes)} volume(s)"
    except Exception as exc:                                  # noqa: BLE001
        ok, volumes, detail = False, [], f"{type(exc).__name__}: {exc}"
    check("volumes can be listed and parsed", ok, detail)

    for volume in volumes:
        print(f"        {volume.id:10} {str(volume.fs_type):8} "
              f"{str(volume.label)[:18]:18} {volume.size / 1024**3:8.1f} GB  "
              f"removable={volume.removable} ro={volume.read_only}")
        if not volume.fs_uuid:
            failures.append("a volume came back without an identity")

    check("every volume carries an identity",
          all(volume.fs_uuid for volume in volumes))

    # The registry has to round-trip on this platform's filesystem.
    registry = JsonRegistry(Path(os.environ.get("RUNNER_TEMP", "."))
                            / "ambershelf-smoke-disks.json")
    try:
        registry.register("SMOKE-0001", "master", "smoke", "Master")
        registry.register("SMOKE-0002", "slave", "smoke", "Copy")
        roles = {d["fs_uuid"]: d["role"] for d in registry.all()}
        second_master_refused = False
        try:
            registry.register("SMOKE-0002", "master", "smoke", "Copy")
        except ValueError:
            second_master_refused = True
        check("the registry stores roles", roles.get("SMOKE-0001") == "master")
        check("a second master is refused", second_master_refused)
    finally:
        registry.path.unlink(missing_ok=True)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
