# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""macOS backend.

Planned for the desktop build. Volumes are already mounted under /Volumes by
the time a disk appears, so this backend never mounts anything and needs no
privileges at all - it reads what is there, using `diskutil info -plist` for
identity (volume UUID, media serial, filesystem, read-only flags).

The master is *not* held read-only here, by decision: doing that would mean
unmounting and remounting a volume the system already mounted writable, and
the few seconds in between would be a false promise. The interface says so
plainly instead.
"""
from __future__ import annotations

from pathlib import Path

from platforms.base import BackendUnavailable, MountReport, Volume

NOT_YET = ("the macOS backend is not built yet - it arrives with the desktop "
           "application")


class MacBackend:
    name = "macos"
    enforces_write_protection = False
    manages_mounts = False
    registry_is_protected = False

    def available(self) -> bool:
        return False

    def list_volumes(self) -> list[Volume]:
        raise BackendUnavailable(NOT_YET)

    def registrations(self) -> list[dict]:
        raise BackendUnavailable(NOT_YET)

    def register(self, fs_uuid: str, role: str, set_name: str,
                 display_name: str) -> dict:
        raise BackendUnavailable(NOT_YET)

    def attach(self, set_name: str) -> MountReport:
        raise BackendUnavailable(NOT_YET)

    def detach(self, set_name: str) -> MountReport:
        raise BackendUnavailable(NOT_YET)

    def status(self, set_name: str) -> list[dict]:
        raise BackendUnavailable(NOT_YET)

    def volume_state(self, fs_uuid: str, fs_type: str | None = None) -> dict:
        raise BackendUnavailable(NOT_YET)

    def mountpoint_of(self, disk) -> Path | None:
        raise BackendUnavailable(NOT_YET)

    def verify_readable(self, disk) -> None:
        raise BackendUnavailable(NOT_YET)
