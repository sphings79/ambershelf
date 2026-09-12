# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Windows backend.

Windows gives a removable volume a drive letter as soon as it appears, so
there is nothing here to mount and nothing that needs administrator rights:
the backend reads what is already there through PowerShell.

**The master is not write-protected here, and cannot reasonably be.** Windows
has no read-only mount for a single volume. The nearest equivalent is a
disk-wide flag set through `diskpart`, which needs administrator rights and
*stays set* until somebody clears it - on this computer and every other one
the disk is later plugged into. Switching that on behind a user's back would
be worse than the problem it solves, so AmberShelf does not offer it and says
plainly on every page that other programs can still write to the master.

A volume is identified by its volume GUID (`\\\\?\\Volume{...}`), which
survives a changed drive letter, together with the serial of the disk it sits
on.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from platforms.base import BackendError, MountReport, Volume
from platforms.registry import JsonRegistry

TIMEOUT = 60

#: Keeps a console window from flashing up when the app has no terminal.
NO_WINDOW = 0x08000000 if sys.platform in ("win32", "cygwin") else 0

VOLUME_GUID = re.compile(r"Volume\{([0-9a-fA-F-]{36})\}")

SUPPORTED = {"exfat": "exfat", "ntfs": "ntfs", "fat32": "vfat", "fat": "vfat"}

#: PowerShell start-up costs a second or two, and the join has to happen
#: inside it: asking Get-Disk once per volume turned a page load into half a
#: dozen interpreter starts. Three cmdlet calls, one process, one answer.
LIST_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$disks = @{}
foreach ($d in Get-Disk) { $disks[[string]$d.Number] = $d }
$parts = @{}
foreach ($p in Get-Partition) {
    if ($p.DriveLetter) { $parts[[string]$p.DriveLetter] = $p }
}
$rows = @()
foreach ($v in Get-Volume) {
    if (-not $v.DriveLetter) { continue }
    $letter = [string]$v.DriveLetter
    $part = $parts[$letter]
    $disk = $null
    if ($part) { $disk = $disks[[string]$part.DiskNumber] }
    $rows += [pscustomobject]@{
        DriveLetter = $letter
        Label       = $v.FileSystemLabel
        FileSystem  = $v.FileSystem
        Size        = [int64]$v.Size
        Free        = [int64]$v.SizeRemaining
        UniqueId    = [string]$v.UniqueId
        DriveType   = [string]$v.DriveType
        Serial      = if ($disk) { ([string]$disk.SerialNumber).Trim() } else { $null }
        Model       = if ($disk) { [string]$disk.FriendlyName } else { $null }
        BusType     = if ($disk) { [string]$disk.BusType } else { $null }
        ReadOnly    = if ($disk) { [bool]$disk.IsReadOnly } else { $false }
        IsSystem    = ($letter + ":") -eq $env:SystemDrive
    }
}
ConvertTo-Json -InputObject $rows -Depth 3 -Compress
"""

#: How long a listing stays good. One page render asks for the volumes several
#: times - once for the overview, once per disk for its state - and starting
#: PowerShell for each of those is what made the page feel slow.
CACHE_SECONDS = 3.0


def powershell(script: str) -> list[dict]:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=TIMEOUT, check=True, creationflags=NO_WINDOW)
    except FileNotFoundError as exc:
        raise BackendError("powershell is not available") from exc
    except subprocess.CalledProcessError as exc:
        raise BackendError(
            (exc.stderr or b"").decode("utf-8", "replace").strip() or "powershell failed"
        ) from exc
    except subprocess.SubprocessError as exc:
        raise BackendError(f"powershell failed: {exc}") from exc

    raw = result.stdout.decode("utf-8", "replace").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise BackendError(f"powershell returned something unreadable: {exc}") from exc
    # A single result comes back as an object rather than a list.
    if isinstance(parsed, dict):
        return [parsed]
    return [row for row in parsed if isinstance(row, dict)]


def volume_uuid(unique_id: str | None) -> str | None:
    """The volume GUID, which survives a changed drive letter."""
    if not unique_id:
        return None
    match = VOLUME_GUID.search(unique_id)
    return match.group(1).upper() if match else None


class WindowsBackend:
    name = "windows"
    enforces_write_protection = False
    manages_mounts = False
    registry_is_protected = False

    def __init__(self) -> None:
        self.registry = JsonRegistry()
        self._cache: list[Volume] | None = None
        self._cached_at = 0.0

    def available(self) -> bool:
        try:
            powershell("Write-Output '[]'")
            return True
        except BackendError:
            return False

    # ------------------------------------------------------------- volumes --

    def list_volumes(self, fresh: bool = False) -> list[Volume]:
        if not fresh and self._cache is not None \
                and time.monotonic() - self._cached_at < CACHE_SECONDS:
            # Registrations may have changed since, so those are re-joined.
            known = {d["fs_uuid"]: d for d in self.registry.all()}
            for volume in self._cache:
                volume.registration = known.get(volume.fs_uuid or "")
            return self._cache

        known = {d["fs_uuid"]: d for d in self.registry.all()}
        volumes: list[Volume] = []

        for row in powershell(LIST_SCRIPT):
            uuid = volume_uuid(row.get("UniqueId"))
            if not uuid:
                continue
            letter = (row.get("DriveLetter") or "").strip()
            filesystem = (row.get("FileSystem") or "").strip().lower()
            volumes.append(Volume(
                id=f"{letter}:" if letter else uuid,
                fs_uuid=uuid,
                serial=(row.get("Serial") or None),
                label=(row.get("Label") or None),
                fs_type=SUPPORTED.get(filesystem, filesystem or None),
                size=int(row.get("Size") or 0),
                mountpoint=f"{letter}:\\" if letter else None,
                removable=(row.get("DriveType") == "Removable"
                           or row.get("BusType") in ("USB", "SD", "MMC")),
                read_only=bool(row.get("ReadOnly")),
                system=bool(row.get("IsSystem")),
                model=(row.get("Model") or None),
                registration=known.get(uuid),
            ))

        self._cache = volumes
        self._cached_at = time.monotonic()
        return volumes

    def volume_by_uuid(self, fs_uuid: str) -> Volume | None:
        return next((v for v in self.list_volumes() if v.fs_uuid == fs_uuid), None)

    # ------------------------------------------------------------ registry --

    def registrations(self) -> list[dict]:
        return self.registry.all()

    def register(self, fs_uuid: str, role: str, set_name: str,
                 display_name: str) -> dict:
        volume = self.volume_by_uuid(fs_uuid)
        if volume is None:
            raise BackendError("this disk is not connected, so it cannot be registered")
        if volume.system:
            raise BackendError(f"{volume.id} is the system drive and cannot be registered")
        if volume.fs_type not in ("exfat", "ntfs", "vfat"):
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

    # -------------------------------------------------------------- mounts --

    def attach(self, set_name: str) -> MountReport:
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
        """Windows has no user-level eject, so this says so rather than failing."""
        raise BackendError(
            "Windows cannot eject a drive without administrator rights - "
            "use the 'Safely Remove Hardware' icon in the system tray")

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
        """Reading the boot sector needs administrator rights on Windows too."""
        volume = self.volume_by_uuid(fs_uuid)
        if volume is None:
            return {"present": False}
        return {"present": True, "device": volume.id, "readable": False,
                "error": "reading the boot sector needs administrator rights on Windows"}

    def mountpoint_of(self, disk) -> Path | None:
        volume = self.volume_by_uuid(disk["fs_uuid"])
        return Path(volume.mountpoint) if volume and volume.mountpoint else None

    def verify_readable(self, disk) -> None:
        mountpoint = self.mountpoint_of(disk)
        if mountpoint is None or not mountpoint.is_dir():
            raise BackendError(f"{disk['display_name']} is not connected")
        if not os.access(mountpoint, os.R_OK):
            raise BackendError(f"{disk['display_name']} cannot be read")
