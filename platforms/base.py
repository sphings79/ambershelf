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

from platforms import smart


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
    #: Has been a master at some point, so it cannot become a copy until it
    #: is demoted. Only the protected registry keeps such a list.
    retired: bool = False
    #: False when there is nothing AmberShelf can work with here.
    usable: bool = True
    #: Why not, as a key the interface can translate.
    reason: str | None = None
    #: Opaque handle the interface may hand back. The container never names a
    #: device; the platform resolves this itself.
    token: str | None = None
    model: str | None = None
    registration: dict | None = None

    def suggested_name(self) -> str:
        """What to put in the name field - never a device path.

        The path contains slashes, which a name may not, so offering it as a
        default meant offering something the next screen would refuse.
        """
        for candidate in (self.label, self.model):
            if candidate and candidate.strip():
                return candidate.strip()[:63]
        return self.id.rsplit("/", 1)[-1].strip(":\\") or "Platte"

    def as_dict(self) -> dict:
        return {
            "id": self.id, "path": self.id, "name": self.suggested_name(),
            "usable": self.usable, "reason": self.reason, "token": self.token,
            "fs_uuid": self.fs_uuid, "serial": self.serial, "label": self.label,
            "fs_type": self.fs_type, "size": self.size, "mountpoint": self.mountpoint,
            "removable": self.removable, "read_only": self.read_only,
            "system": self.system, "ignored": self.ignored,
            "retired": self.retired,
            "model": self.model, "registration": self.registration,
        }


@dataclass
class MountReport:
    attached: list[dict] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)


def sets_from_registrations(entries: list[dict]) -> list[dict]:
    """Group flat registrations into sets.

    Only the host helper keeps sets as a thing of their own. On a desktop the
    registry is a flat list, so the sets are read back out of it - which
    works because there each disk still belongs to exactly one.
    """
    grouped: dict[str, dict] = {}
    for entry in entries:
        name = entry.get("set_name")
        if not name:
            continue
        found = grouped.setdefault(
            name, {"name": name, "master": None, "copies": [],
                   "created_at": entry.get("registered_at")})
        if entry.get("role") == "master":
            found["master"] = entry["fs_uuid"]
        else:
            found["copies"].append(entry["fs_uuid"])
    return [s for s in grouped.values() if s["master"]]


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

    def sets(self) -> list[dict]:
        """Which sets exist and who is in them."""
        return sets_from_registrations(self.registrations())

    def register(self, fs_uuid: str, role: str, set_name: str,
                 display_name: str) -> dict: ...

    def unregister(self, fs_uuid: str) -> dict:
        """Forget a disk. Never touches what is on it."""

    def smart(self, fs_uuid: str) -> dict:
        """What the disk says about its own health, already interpreted.

        Always answers - a disk that cannot be asked comes back with
        ``available`` False and a reason, because "no answer" is itself
        something the interface has to show.
        """
        return smart.interpret({"ok": False, "reason": "smart.unsupported"})

    def forget_set(self, set_name: str) -> dict:
        """Dissolve a set. The disks in it stay registered.

        Where the registry keeps no sets of its own, a set stops existing as
        soon as nothing claims to be in it, so there is nothing to do.
        """
        return {"ok": True}

    def can_demote(self) -> bool:
        """Whether giving up a master is reachable from here at all.

        False when the owner of the host has switched it off, so the
        interface can say that rather than offer a button that is refused.
        """
        return True

    def demote_master(self, fs_uuid: str) -> dict:
        """Give up a master, so the disk may be a copy again.

        Removes the registration and whatever the platform remembers about
        the disk having been a master. Never touches what is on it, and never
        writes a new role - registering it again is a separate act.
        """

    def ignore(self, fs_uuid: str) -> dict:
        """Leave this disk alone from now on."""

    def unignore(self, fs_uuid: str) -> dict: ...

    def ignored_disks(self) -> list[dict]: ...

    def peek(self, token: str) -> dict:
        """Look at what is on a disk without changing anything."""

    def can_format(self) -> bool:
        """Whether this platform can create a filesystem itself."""
        return False

    def format(self, token: str, filesystem: str, label: str) -> dict:
        """Erase a disk and put a fresh filesystem on it."""

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
