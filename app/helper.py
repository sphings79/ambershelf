# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Client for the host helper.

Every mount related operation goes through here. The container deliberately
has no way to mount anything itself, so if the socket is missing the honest
answer is 'no disks', not a guess.
"""
from __future__ import annotations

import json
import socket
from typing import Any

from . import config


class HelperError(RuntimeError):
    """The helper refused a request or could not be reached."""


class HelperUnavailable(HelperError):
    """The socket is not there at all."""


def call(command: str, **payload: Any) -> dict:
    request = {"cmd": command, **payload}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(300)
            sock.connect(str(config.HELPER_SOCKET))
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
        raise HelperUnavailable(
            f"the host helper is not reachable at {config.HELPER_SOCKET}"
        ) from exc
    except (ConnectionError, socket.timeout, OSError) as exc:
        raise HelperError(f"talking to the host helper failed: {exc}") from exc

    raw = b"".join(chunks).decode("utf-8").strip()
    if not raw:
        raise HelperError("the host helper sent an empty answer")
    try:
        response = json.loads(raw)
    except ValueError as exc:
        raise HelperError(f"the host helper sent something unreadable: {exc}") from exc
    if not response.get("ok"):
        raise HelperError(response.get("error") or "the host helper refused the request")
    return response


def available() -> bool:
    try:
        call("ping")
        return True
    except HelperError:
        return False


def list_disks() -> list[dict]:
    return call("list_disks")["disks"]


def list_registrations() -> list[dict]:
    return call("list_registrations")["disks"]


def register(fs_uuid: str, role: str, set_name: str, display_name: str) -> dict:
    return call("register", fs_uuid=fs_uuid, role=role,
                set_name=set_name, display_name=display_name)


def mount_set(set_name: str) -> dict:
    return call("mount_set", set_name=set_name)


def umount_set(set_name: str) -> dict:
    return call("umount_set", set_name=set_name)


def mount_status(set_name: str) -> dict:
    return call("mount_status", set_name=set_name)


def volume_state(fs_uuid: str, fs_type: str | None = None) -> dict:
    return call("volume_state", fs_uuid=fs_uuid, fs_type=fs_type)
