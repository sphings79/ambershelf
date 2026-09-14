# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""macOS backend.

macOS mounts a removable volume the moment it is plugged in, so there is
nothing here to mount and nothing that needs privileges: the backend reads
what is already under /Volumes and asks `diskutil` who it is.

**The master is not write-protected here.** macOS *can* mount a volume
read-only without administrator rights - `diskutil unmount` followed by
`diskutil mount readOnly` works as the logged-in user - but the system has
already mounted the disk writable by the time AmberShelf sees it, so the few
seconds in between would make the promise a half-truth. Rather than half a
guarantee, the interface states plainly on every page that other programs on
this computer can still write to the master. AmberShelf itself never does.
"""
from __future__ import annotations

import os
import plistlib
import re
import subprocess
from pathlib import Path

from platforms import smart
from platforms.base import BackendError, MountReport, Volume, sets_from_registrations
from platforms.registry import JsonRegistry

#: Filesystems the engine can work with, as diskutil spells them.
SUPPORTED = {"exfat": "exfat", "ntfs": "ntfs", "msdos": "vfat",
             "apfs": "apfs", "hfs+": "hfs", "journaled hfs+": "hfs"}

TIMEOUT = 60


def diskutil(subcommand: str, *arguments: str) -> dict:
    """Run diskutil and read its property list.

    The flag belongs directly after the subcommand - `diskutil list -plist
    external`, not `diskutil list external -plist`, which diskutil reads as
    the name of a disk. Arguments are always a list, never a string.
    """
    try:
        result = subprocess.run(["diskutil", subcommand, "-plist", *arguments],
                                capture_output=True, timeout=TIMEOUT, check=True)
    except FileNotFoundError as exc:
        raise BackendError("diskutil is not available") from exc
    except subprocess.CalledProcessError as exc:
        raise BackendError(
            (exc.stderr or b"").decode("utf-8", "replace").strip() or "diskutil failed"
        ) from exc
    except subprocess.SubprocessError as exc:
        raise BackendError(f"diskutil failed: {exc}") from exc
    try:
        return plistlib.loads(result.stdout)
    except Exception as exc:                                  # noqa: BLE001
        raise BackendError(f"diskutil returned something unreadable: {exc}") from exc


def normalise_filesystem(name: str | None) -> str | None:
    if not name:
        return None
    return SUPPORTED.get(name.strip().lower(), name.strip().lower())


class MacBackend:
    name = "macos"
    enforces_write_protection = False
    manages_mounts = False
    registry_is_protected = False

    def __init__(self) -> None:
        self.registry = JsonRegistry()

    def available(self) -> bool:
        try:
            diskutil("list")
            return True
        except BackendError:
            return False

    # ------------------------------------------------------------- volumes --

    def list_volumes(self) -> list[Volume]:
        known = {d["fs_uuid"]: d for d in self.registry.all()}
        excluded = {e["fs_uuid"] for e in self.registry.ignored()}
        listing = diskutil("list", "external")
        volumes: list[Volume] = []

        for disk in listing.get("AllDisksAndPartitions", []):
            for partition in disk.get("Partitions", []) or []:
                identifier = partition.get("DeviceIdentifier")
                if not identifier:
                    continue
                try:
                    info = diskutil("info", identifier)
                except BackendError:
                    continue
                uuid = info.get("VolumeUUID")
                if not uuid:
                    continue

                volumes.append(Volume(
                    id=identifier,
                    fs_uuid=uuid,
                    serial=info.get("IORegistryEntryName") or None,
                    label=info.get("VolumeName") or None,
                    fs_type=normalise_filesystem(info.get("FilesystemName")),
                    size=int(info.get("VolumeSize") or info.get("Size") or 0),
                    mountpoint=info.get("MountPoint") or None,
                    removable=bool(info.get("Removable")
                                   or info.get("RemovableMediaOrExternalDevice")),
                    read_only=not info.get("WritableVolume", True),
                    # Only external disks are listed at all, so a system
                    # volume never reaches this point.
                    system=False,
                    model=(info.get("MediaName") or "").strip() or None,
                    registration=known.get(uuid),
                    ignored=uuid in excluded,
                ))
        return volumes

    def volume_by_uuid(self, fs_uuid: str) -> Volume | None:
        return next((v for v in self.list_volumes() if v.fs_uuid == fs_uuid), None)

    # ------------------------------------------------------------ registry --

    def registrations(self) -> list[dict]:
        return self.registry.all()

    def sets(self) -> list[dict]:
        return sets_from_registrations(self.registry.all())

    def register(self, fs_uuid: str, role: str, set_name: str,
                 display_name: str) -> dict:
        volume = self.volume_by_uuid(fs_uuid)
        if volume is None:
            raise BackendError("this disk is not connected, so it cannot be registered")
        if self.registry.is_ignored(fs_uuid):
            raise BackendError("this disk is excluded - take it off that list first")
        if volume.fs_type not in ("exfat", "ntfs", "vfat", "apfs", "hfs"):
            raise BackendError(f"filesystem {volume.fs_type!r} is not supported")
        try:
            return {"ok": True, "disk": self.registry.register(
                fs_uuid, role, set_name, display_name, volume)}
        except ValueError as exc:
            raise BackendError(str(exc)) from exc

    def unregister(self, fs_uuid: str) -> dict:
        if not self.registry.remove(fs_uuid):
            raise BackendError("this disk is not registered")
        return {"ok": True}

    def smart(self, fs_uuid: str) -> dict:
        """Ask the whole disk, not the slice - SMART lives in the drive.

        smartctl is not part of macOS. When it is not there the interface
        says so and names the one command that installs it, rather than
        pretending the disk had nothing to report.
        """
        volume = self.volume_by_uuid(fs_uuid)
        if volume is None:
            return smart.interpret({"ok": False, "reason": "smart.not_connected"})
        whole = re.sub(r"s\d+$", "", volume.id.rsplit("/", 1)[-1])
        return smart.interpret(smart.run_smartctl(f"/dev/{whole}"))

    def forget_set(self, set_name: str) -> dict:
        for disk in self.registry.all():
            if disk.get("set_name") == set_name:
                self.registry.remove(disk["fs_uuid"])
        return {"ok": True}

    def can_demote(self) -> bool:
        return True

    def demote_master(self, fs_uuid: str) -> dict:
        """The same as forgetting it - nothing here remembers a retirement.

        This registry is not protected from the application in the first
        place (the warning band says so), so there is no list to clear.
        """
        return self.unregister(fs_uuid)

    def ignore(self, fs_uuid: str) -> dict:
        try:
            return self.registry.ignore(fs_uuid, self.volume_by_uuid(fs_uuid))
        except ValueError as exc:
            raise BackendError(str(exc)) from exc

    def unignore(self, fs_uuid: str) -> dict:
        try:
            return self.registry.unignore(fs_uuid)
        except ValueError as exc:
            raise BackendError(str(exc)) from exc

    def ignored_disks(self) -> list[dict]:
        return self.registry.ignored()

    def peek(self, token: str) -> dict:
        return {"ok": True, "readable": False, "entries": [], "count": 0}

    def can_format(self) -> bool:
        # Disk Utility already does this, knows the conventions of this
        # system, and is the thing a user of it expects to be told about.
        return False

    def format(self, token: str, filesystem: str, label: str) -> dict:
        raise BackendError("format the disk with Disk Utility")

    # -------------------------------------------------------------- mounts --

    def attach(self, set_name: str) -> MountReport:
        """Nothing to mount - report what the system already did."""
        present = {v.fs_uuid: v for v in self.list_volumes()}
        report = MountReport()
        for disk in self.registry.of_set(set_name):
            volume = present.get(disk["fs_uuid"])
            if volume is None or not volume.mountpoint:
                report.missing.append({"fs_uuid": disk["fs_uuid"],
                                       "display_name": disk["display_name"],
                                       "role": disk["role"]})
                continue
            report.attached.append({
                "fs_uuid": disk["fs_uuid"], "display_name": disk["display_name"],
                "role": disk["role"], "mountpoint": volume.mountpoint,
                "read_only": volume.read_only, "flags": [],
            })
        if not any(entry["role"] == "master" for entry in report.attached):
            raise BackendError("the master disk of this set is not connected")
        return report

    def detach(self, set_name: str) -> MountReport:
        """Eject properly, which is what "safe removal" means here."""
        present = {v.fs_uuid: v for v in self.list_volumes()}
        report = MountReport()
        for disk in self.registry.of_set(set_name):
            volume = present.get(disk["fs_uuid"])
            if volume is None:
                continue
            try:
                subprocess.run(["diskutil", "eject", volume.id],
                               capture_output=True, timeout=TIMEOUT, check=True)
                report.attached.append({"mountpoint": volume.mountpoint or volume.id})
            except (subprocess.SubprocessError, OSError) as exc:
                detail = getattr(exc, "stderr", b"") or b""
                report.failed.append({
                    "mountpoint": volume.mountpoint or volume.id,
                    "error": detail.decode("utf-8", "replace").strip() or str(exc)})
        return report

    def status(self, set_name: str) -> list[dict]:
        present = {v.fs_uuid: v for v in self.list_volumes()}
        rows = []
        for disk in self.registry.of_set(set_name):
            volume = present.get(disk["fs_uuid"])
            rows.append({
                "fs_uuid": disk["fs_uuid"],
                "display_name": disk["display_name"],
                "role": disk["role"],
                "mountpoint": volume.mountpoint if volume else None,
                "mounted": bool(volume and volume.mountpoint),
                "read_only": bool(volume and volume.read_only),
                "flags": [],
                "connected": volume is not None,
            })
        return rows

    def volume_state(self, fs_uuid: str, fs_type: str | None = None) -> dict:
        """The exFAT dirty flag needs the raw device, which needs root here."""
        volume = self.volume_by_uuid(fs_uuid)
        if volume is None:
            return {"present": False}
        return {"present": True, "device": volume.id, "readable": False,
                "error": "reading the boot sector needs administrator rights on macOS"}

    def mountpoint_of(self, disk) -> Path | None:
        volume = self.volume_by_uuid(disk["fs_uuid"])
        return Path(volume.mountpoint) if volume and volume.mountpoint else None

    def verify_readable(self, disk) -> None:
        mountpoint = self.mountpoint_of(disk)
        if mountpoint is None or not mountpoint.is_dir():
            raise BackendError(f"{disk['display_name']} is not connected")
        if not os.access(mountpoint, os.R_OK):
            raise BackendError(f"{disk['display_name']} cannot be read")
        # No read-only check: this platform does not hold the master, and the
        # interface says so instead of a check pretending to.
