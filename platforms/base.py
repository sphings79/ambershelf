# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""What the rest of AmberShelf is allowed to know about disks.

Everything operating-system specific lives behind this interface: how volumes
are found, how they are made readable, and whether the source can be
write-protected at all. The engine and the web interface never learn which
system they are running on - that separation is what keeps the master safe on
Linux, and what makes a desktop build possible without touching the parts
that do the actual work.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class Volume:
    """One mountable filesystem, as the operating system reports it."""
    id: str                      # /dev/sdb1, disk4s1, E: - never shown to users
    fs_uuid: str | None = None
    serial: str | None = None
    label: str | None = None
    fs_type: str | None = None
    size: int = 0
    mountpoint: str | None = None
    removable: bool = False
    read_only: bool = False
    #: Part of the running system - the root filesystem, swap, /boot. Never
    #: registrable, whatever the interface shows.
    system: bool = False
    #: Put out of reach by the user: never listed, never registered, never
    #: mounted.
    ignored: bool = False
    model: str | None = None
    registration: dict | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id, "path": self.id, "name": self.label or self.id,
            "fs_uuid": self.fs_uuid, "serial": self.serial, "label": self.label,
            "fs_type": self.fs_type, "size": self.size, "mountpoint": self.mountpoint,
            "removable": self.removable, "read_only": self.read_only,
            "system": self.system, "ignored": self.ignored,
            "model": self.model, "registration": self.registration,
        }


@dataclass
class MountReport:
    attached: list[dict] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)


class BackendError(RuntimeError):
    """Anything the platform layer refuses or cannot do."""


class BackendUnavailable(BackendError):
    """The platform layer is not usable here at all."""


@runtime_checkable
class Backend(Protocol):
    #: "linux", "macos", "windows"
    name: str

    #: True when the master is held read-only by the kernel rather than by
    #: politeness. Drives the warning banner in the interface - if this is
    #: False, the user is told plainly that other programs can still write.
    enforces_write_protection: bool

    #: True when this backend mounts and unmounts by itself. On desktop
    #: systems the volumes are already mounted when the disk is plugged in,
    #: so there is nothing to do and nothing that needs privileges.
    manages_mounts: bool

    #: True when roles are kept outside the reach of the application - the
    #: host-owned registry on Linux. False means a user can change a role in
    #: the interface, which is worth saying out loud.
    registry_is_protected: bool

    def available(self) -> bool: ...

    def list_volumes(self) -> list[Volume]: ...

    def registrations(self) -> list[dict]: ...

    def register(self, fs_uuid: str, role: str, set_name: str,
                 display_name: str) -> dict: ...

    def unregister(self, fs_uuid: str) -> dict:
        """Forget a disk. Never touches what is on it."""

    def ignore(self, fs_uuid: str) -> dict:
        """Leave this disk alone from now on."""

    def unignore(self, fs_uuid: str) -> dict: ...

    def ignored_disks(self) -> list[dict]: ...

    def attach(self, set_name: str) -> MountReport: ...

    def detach(self, set_name: str) -> MountReport: ...

    def status(self, set_name: str) -> list[dict]: ...

    def volume_state(self, fs_uuid: str, fs_type: str | None = None) -> dict: ...

    def mountpoint_of(self, disk) -> Path | None: ...

    def verify_readable(self, disk) -> None:
        """Raise unless this disk is safe to read right now.

        On Linux this is where a master that is not actually mounted
        read-only stops the run.
        """
