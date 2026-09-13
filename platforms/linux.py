# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Linux backend: everything goes through the root helper on the host.

This is the only backend that can hold the master read-only in a way the
kernel enforces, and the only one where the role of a disk is kept out of
reach of the application. Both come from the same thing - a small privileged
process that the rest of AmberShelf can only talk to over a socket with six
commands.
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

from platforms.base import BackendError, BackendUnavailable, MountReport, Volume

HELPER_SOCKET = Path(os.environ.get("AMBERSHELF_HELPER_SOCKET",
                                    "/run/ambershelf/helper.sock"))
MOUNT_ROOT = Path(os.environ.get("AMBERSHELF_MOUNT_ROOT", "/mnt/ambershelf"))


def call(command: str, **payload: Any) -> dict:
    request = {"cmd": command, **payload}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(300)
            sock.connect(str(HELPER_SOCKET))
            sock.sendall(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n")
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if chunks[-1].endswith(b"\n"):
                    break
    except FileNotFoundError as exc:
        raise BackendUnavailable(
            f"the host helper is not reachable at {HELPER_SOCKET}") from exc
    except (ConnectionError, socket.timeout, OSError) as exc:
        raise BackendError(f"talking to the host helper failed: {exc}") from exc

    raw = b"".join(chunks).decode("utf-8").strip()
    if not raw:
        raise BackendError("the host helper sent an empty answer")
    try:
        response = json.loads(raw)
    except ValueError as exc:
        raise BackendError(f"the host helper sent something unreadable: {exc}") from exc
    if not response.get("ok"):
        raise BackendError(response.get("error") or "the host helper refused the request")
    return response


def mount_options(mountpoint: Path) -> list[str]:
    target = str(mountpoint)
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        fields = line.split(" ")
        if len(fields) > 5 and fields[4].replace("\\040", " ") == target:
            return fields[5].split(",")
    return []


class LinuxBackend:
    name = "linux"
    enforces_write_protection = True
    manages_mounts = True
    registry_is_protected = True

    def available(self) -> bool:
        try:
            call("ping")
            return True
        except BackendError:
            return False

    def list_volumes(self) -> list[Volume]:
        volumes = []
        for entry in call("list_disks")["disks"]:
            volumes.append(Volume(
                id=entry.get("path") or entry.get("name") or "",
                fs_uuid=entry.get("fs_uuid"),
                serial=entry.get("serial"),
                label=entry.get("label"),
                fs_type=entry.get("fs_type"),
                size=int(entry.get("size") or 0),
                mountpoint=entry.get("mountpoint"),
                removable=bool(entry.get("removable")),
                system=bool(entry.get("system")),
                ignored=bool(entry.get("ignored")),
                usable=bool(entry.get("usable", True)),
                reason=entry.get("reason"),
                model=entry.get("model"),
                registration=entry.get("registration"),
            ))
        return volumes

    def registrations(self) -> list[dict]:
        return call("list_registrations")["disks"]

    def register(self, fs_uuid: str, role: str, set_name: str,
                 display_name: str) -> dict:
        return call("register", fs_uuid=fs_uuid, role=role,
                    set_name=set_name, display_name=display_name)

    def unregister(self, fs_uuid: str) -> dict:
        return call("unregister", fs_uuid=fs_uuid)

    def ignore(self, fs_uuid: str) -> dict:
        return call("ignore", fs_uuid=fs_uuid)

    def unignore(self, fs_uuid: str) -> dict:
        return call("unignore", fs_uuid=fs_uuid)

    def ignored_disks(self) -> list[dict]:
        return call("list_ignored")["ignored"]

    def attach(self, set_name: str) -> MountReport:
        result = call("mount_set", set_name=set_name)
        return MountReport(attached=result.get("mounted", []),
                           missing=result.get("missing", []))

    def detach(self, set_name: str) -> MountReport:
        result = call("umount_set", set_name=set_name)
        return MountReport(attached=[{"mountpoint": m} for m in result.get("released", [])],
                           failed=result.get("failed", []))

    def status(self, set_name: str) -> list[dict]:
        return call("mount_status", set_name=set_name)["disks"]

    def volume_state(self, fs_uuid: str, fs_type: str | None = None) -> dict:
        return call("volume_state", fs_uuid=fs_uuid, fs_type=fs_type)

    def mountpoint_of(self, disk) -> Path:
        if disk["role"] == "master":
            return MOUNT_ROOT / disk["set_name"] / "master"
        return MOUNT_ROOT / disk["set_name"] / "slaves" / disk["display_name"]

    def verify_readable(self, disk) -> None:
        mountpoint = self.mountpoint_of(disk)
        if not os.path.ismount(mountpoint):
            raise BackendError(
                f"{disk['display_name']} is not mounted at {mountpoint}")
        options = mount_options(mountpoint)
        if disk["role"] == "master" and "ro" not in options:
            # The helper checks this too. Checking again here costs nothing
            # and means no code path ever reads a master that is writable.
            raise BackendError(
                "refusing to read: the master is mounted with "
                f"{','.join(options)}, not read-only")
