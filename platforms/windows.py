# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Windows backend.

Planned for the desktop build. Volumes carry drive letters by the time a disk
appears, so this backend never mounts anything and needs no privileges - it
reads what is there, using PowerShell (Get-Volume, Get-Disk) for identity.

Windows has no read-only mount for a single volume; the only equivalent is a
disk-wide flag set through diskpart, which needs administrator rights and
stays set until somebody clears it - even on another computer. That is not
something an application should switch on behind a user's back, so the master
is not write-protected here and the interface says so.
"""
from __future__ import annotations

from pathlib import Path

from platforms.base import BackendUnavailable, MountReport, Volume

NOT_YET = ("the Windows backend is not built yet - it arrives with the desktop "
           "application")


class WindowsBackend:
    name = "windows"
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
