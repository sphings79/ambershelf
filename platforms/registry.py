# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""The disk registry for the desktop builds.

On Linux the mapping from disk to role lives in a root-owned file that the
application cannot reach. A desktop build has no privileged half, so the same
file is simply a JSON document the user owns - and therefore something the
user can change.

That is a real difference and the interface says so rather than pretending
otherwise: `registry_is_protected` is False for these backends, which puts a
line in the warning band.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from engine.paths import app_data_dir

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,62}$")
VALID_ROLES = ("master", "slave")


class JsonRegistry:
    """disks.json next to the database, with the same shape the helper uses."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_dir() / "disks.json")

    # ------------------------------------------------------------- storage --

    def load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "disks": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"version": 1, "disks": []}
        data.setdefault("version", 1)
        data.setdefault("disks", [])
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        os.replace(temporary, self.path)

    # -------------------------------------------------------------- access --

    def all(self) -> list[dict]:
        return self.load()["disks"]

    def find(self, fs_uuid: str) -> dict | None:
        return next((d for d in self.all() if d["fs_uuid"] == fs_uuid), None)

    def register(self, fs_uuid: str, role: str, set_name: str, display_name: str,
                 volume=None) -> dict:
        if role not in VALID_ROLES:
            raise ValueError("role must be master or slave")
        if not NAME_RE.match(set_name) or not NAME_RE.match(display_name):
            raise ValueError("invalid name")

        data = self.load()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        existing = next((d for d in data["disks"] if d["fs_uuid"] == fs_uuid), None)

        # A set with two masters is broken whatever the privileges are, so this
        # is checked on both paths - changing a role as well as adding one.
        if role == "master" and any(
                d["set_name"] == set_name and d["role"] == "master"
                and d["fs_uuid"] != fs_uuid for d in data["disks"]):
            raise ValueError(f"set {set_name!r} already has a master")

        if existing is not None:
            # Unlike the host helper this can be changed, because there is no
            # privileged half to stop it. Changing a role still takes a
            # deliberate act, and the warning band says the registry is open.
            existing.update({"role": role, "set_name": set_name,
                             "display_name": display_name, "last_seen_at": now})
            self.save(data)
            return existing

        entry = {
            "fs_uuid": fs_uuid,
            "serial": getattr(volume, "serial", None),
            "label": getattr(volume, "label", None),
            "size": getattr(volume, "size", 0),
            "fs_type": getattr(volume, "fs_type", None),
            "model": getattr(volume, "model", None),
            "role": role,
            "set_name": set_name,
            "display_name": display_name,
            "registered_at": now,
            "last_seen_at": now,
        }
        data["disks"].append(entry)
        self.save(data)
        return entry

    def remove(self, fs_uuid: str) -> bool:
        data = self.load()
        before = len(data["disks"])
        data["disks"] = [d for d in data["disks"] if d["fs_uuid"] != fs_uuid]
        if len(data["disks"]) != before:
            self.save(data)
            return True
        return False

    def of_set(self, set_name: str) -> list[dict]:
        return [d for d in self.all() if d["set_name"] == set_name]
