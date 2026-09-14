#!/usr/bin/env python3
# AmberShelf - disk mirroring with an approval workflow
# Copyright (C) 2026 Dennis Arning
# Licensed under the GNU Affero General Public License v3.0 or later.
"""AmberShelf host helper.

Runs as root on the Docker host. It is the only component allowed to mount
anything. The container talks to it over a unix socket and can only ask for a
whole *set* to be mounted - it can never name a device, a mount option or a
role.

The guarantees this file exists to provide:

  1. A disk registered as ``master`` is always mounted read-only. The kernel
     enforces it, so neither a bug in the container nor an attacker who owns
     the container can write to it.
  2. After mounting, the flags are read back from /proc/self/mountinfo. If a
     master is not actually read-only, everything is unmounted again and the
     request fails.
  3. Roles of already registered disks cannot be changed over the socket.
     Registrations *can* be removed - forgetting a mistyped disk is ordinary
     work - but a disk that has been a master is written to a retired list,
     and from then on it will only ever be registered as a master again. That
     closes remove-and-re-add, which would otherwise be a way around rule 3.
  4. Only exfat, ntfs and ext4 are accepted, each with a fixed option set
     defined here.

Adding an unknown disk is harmless; re-labelling a known master as a slave is
not. That is the whole shape of what the socket may and may not do.

One deliberate exception to rule 3
----------------------------------
``demote`` takes a disk off the retired list, which is what lets a former
master become a copy. It exists because the owner of the machine has to be
able to repurpose their own disk without a terminal, and it is worth being
honest about the price: this command runs over the same socket as everything
else, so an attacker who owns the container and can get hold of the
application password can reach it too.

What it does *not* give away: it only ever removes a registration, never
rewrites one. A demoted disk is unregistered and unknown afterwards, so
turning it into a writable copy takes a second, separate, deliberate
registration. And it refuses while the set is mounted, so it can never change
the role of a disk that is mounted read-only right now.

If that trade is not worth it on a particular machine, put
``"allow_demote": false`` in the config file. The socket then refuses the
command outright and the ``--admin`` commands below are the only way left.
"""
from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import re
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

CONFIG_PATH = Path("/etc/ambershelf/disks.conf")
SOCKET_PATH = Path("/run/ambershelf/helper.sock")
MOUNT_ROOT = Path("/mnt/ambershelf")
SOCKET_GROUP = "ambershelf"

# The container runs as this user; exfat and ntfs have no own ownership model,
# so the files need to be handed to it at mount time.
APP_UID = 1000
APP_GID = 1000

# Only these filesystems, only these options. Nothing here is taken from the
# client - the client never gets to influence how something is mounted.
FS_OPTIONS = {
    "exfat": "uid={uid},gid={gid},umask=0022,errors=remount-ro",
    "ntfs": "uid={uid},gid={gid},umask=0022",
    "ntfs3": "uid={uid},gid={gid},umask=0022",
    "ext4": "",
}
FS_DRIVER = {"exfat": "exfat", "ntfs": "ntfs3", "ntfs3": "ntfs3", "ext4": "ext4"}

VALID_ROLES = ("master", "slave")

#: Filesystems that are never a backup disk, whatever else is true of them.
SYSTEM_FILESYSTEMS = {"swap", "linux_raid_member", "lvm2_member", "crypto_luks",
                      "zfs_member", "ddf_raid_member", "isw_raid_member"}

#: A volume mounted anywhere outside these is part of the running system -
#: the root filesystem, /boot, /home. Registering one of those as a copy
#: would have AmberShelf write into the machine it runs on.
REMOVABLE_MOUNT_ROOTS = ("/mnt", "/media", "/run/media")


#: Filesystems the helper can create, and how. Quick formats only - a full
#: surface write on a four terabyte disk is hours for no benefit here.
#: Reading SMART needs root, so it belongs here rather than in the container.
#: Only the raw answer is handed back - what the numbers mean is decided in
#: one place, in the application.
#: The shape of /etc/ambershelf/disks.conf. Version 2 pulled the role and the
#: set out of the disk entry, so that one master can serve several sets while
#: still being one disk with one index behind it.
CONFIG_VERSION = 2

#: Set by load_config() when it had to bring an older file up to date, so
#: startup can write the result back exactly once.
migrated_on_load = False

SMARTCTL = "/usr/sbin/smartctl"

MKFS = {
    "exfat": ["/usr/sbin/mkfs.exfat", "-L", "{label}", "{device}"],
    "ntfs": ["/usr/sbin/mkfs.ntfs", "--quick", "--label", "{label}", "{device}"],
}

#: How long a volume label may be, per filesystem. exFAT inherited FAT's
#: eleven characters; mkfs.exfat does not truncate, it refuses with "input
#: string is too long" and leaves the disk unformatted. Cutting it here beats
#: handing that back to somebody who typed a twelve-letter name.
LABEL_LIMITS = {"exfat": 11, "ntfs": 32}

#: Microsoft basic data - what macOS and Windows create for exFAT and NTFS,
#: and what they both recognise without argument.
PARTITION_TYPE = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"

SFDISK = "/usr/sbin/sfdisk"
WIPEFS = "/usr/sbin/wipefs"
PARTPROBE = "/usr/sbin/partprobe"


def device_token(entry: dict) -> str:
    """A stable handle for a device that the container may pass back.

    The container is never allowed to name a device - that is what keeps a
    compromised one from mounting or erasing whatever it likes. A blank disk
    has no filesystem UUID to refer to, so the helper hands out a token
    derived from what the hardware reports and resolves it again itself.
    """
    material = "|".join(str(entry.get(key) or "") for key in
                        ("path", "serial", "size", "model", "vendor", "fs_uuid"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def device_for_token(token: str) -> dict:
    """Resolve a token back to exactly one device, or refuse."""
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{16}", token):
        raise RuntimeError("invalid disk token")
    matches = [entry for entry in list_block_devices()
               if device_token(entry) == token]
    if not matches:
        raise RuntimeError("this disk is not connected any more")
    if len(matches) > 1:
        raise RuntimeError("this token matches more than one disk - refusing")
    return matches[0]


def is_system_partition(entry: dict) -> bool:
    if (entry.get("fs_type") or "").lower() in SYSTEM_FILESYSTEMS:
        return True
    mountpoint = entry.get("mountpoint")
    if mountpoint:
        return not mountpoint.startswith(REMOVABLE_MOUNT_ROOTS)
    return False
#: A name becomes a folder under /mnt/ambershelf, so it may not contain a
#: path separator or anything a filesystem cannot hold. Everything else is
#: allowed - umlauts, brackets, exclamation marks. Real archives are called
#: things like "! Fotos !" and "Größe", and a tool that refuses those is
#: making the user work around it for no reason.
FORBIDDEN_IN_NAME = {"/", "\\", "\0"} | {chr(code) for code in range(32)}
MAX_NAME_LENGTH = 63

UUID_RE = re.compile(r"^[A-Za-z0-9-]{4,40}$")

MAX_REQUEST = 64 * 1024

_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(message: str) -> None:
    print(f"[ambershelf-helper] {message}", flush=True)


# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"version": CONFIG_VERSION, "disks": [], "sets": []}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"{CONFIG_PATH} is unreadable: {exc}") from exc
    data.setdefault("version", 1)
    data.setdefault("disks", [])
    if int(data["version"]) < 2:
        migrate_to_sets(data)
    data.setdefault("sets", [])
    return data


def migrate_to_sets(data: dict) -> None:
    """Version 1 kept the role and the set inside the disk entry.

    That made a disk a member of exactly one set with exactly one role, which
    is why a master could not serve two sets. The disk entry now describes
    the disk and nothing else; who belongs to which set is written down once,
    in the set.
    """
    sets: dict[str, dict] = {}
    for disk in data["disks"]:
        name = disk.pop("set_name", None)
        role = disk.pop("role", "slave")
        if not name:
            continue
        entry = sets.setdefault(name, {"name": name, "master": None, "copies": [],
                                       "created_at": disk.get("registered_at") or now()})
        if role == "master":
            entry["master"] = disk["fs_uuid"]
        else:
            entry["copies"].append(disk["fs_uuid"])
    data["sets"] = [s for s in sets.values() if s["master"]]
    data["version"] = CONFIG_VERSION
    global migrated_on_load
    migrated_on_load = True
    log(f"registry migrated to version {CONFIG_VERSION}: "
        f"{len(data['disks'])} disk(s), {len(data['sets'])} set(s)")


def persist_migration() -> None:
    """Write the migrated shape back once, at startup.

    Reading must not have side effects, so load_config() only migrates in
    memory. Left at that, the file on disk would stay in the old shape for as
    long as nobody changed anything - and anyone opening it would read a
    description of the world that the program no longer believes.
    """
    global migrated_on_load
    config = load_config()
    if not migrated_on_load:
        return
    save_config(config)
    migrated_on_load = False
    log(f"registry written back in version {CONFIG_VERSION}")


def save_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, CONFIG_PATH)


def ignored_disks(config: dict) -> list[dict]:
    """Disks AmberShelf is to leave alone entirely.

    Every machine has one: the disk that holds something else's backup, a
    scratch drive, a disk somebody else uses. Keeping them off the list is
    half the point; the other half is that the helper refuses to register or
    mount them at all, so a mistake in the interface cannot reach them.
    """
    return config.setdefault("ignored", [])


def is_ignored(config: dict, fs_uuid: str) -> bool:
    return any(entry["fs_uuid"] == fs_uuid for entry in ignored_disks(config))


def demote_allowed(config: dict) -> bool:
    """Whether the socket may take a disk off the retired list at all.

    The one command that can end up with a former master registered as a copy
    is also the one an owner might not want reachable from the container on a
    particular machine. Setting ``"allow_demote": false`` in the config file
    closes it; the host commands below keep working either way.
    """
    return config.get("allow_demote", True) is not False


def retired_masters(config: dict) -> list[str]:
    return config.setdefault("retired_masters", [])


def retire_master(config: dict, fs_uuid: str) -> None:
    """Remember that this disk was a master once.

    Nothing else in the file survives a removal, so without this a master
    could be forgotten and registered again as a copy - which is exactly the
    transition the socket is not allowed to make.
    """
    retired = retired_masters(config)
    if fs_uuid not in retired:
        retired.append(fs_uuid)


def find_disk(config: dict, fs_uuid: str) -> dict | None:
    for disk in config["disks"]:
        if disk["fs_uuid"] == fs_uuid:
            return disk
    return None


# --------------------------------------------------------------------------
# sets: who a disk works with, kept apart from what a disk is
# --------------------------------------------------------------------------

def all_sets(config: dict) -> list[dict]:
    return config.setdefault("sets", [])


def find_set(config: dict, name: str) -> dict | None:
    return next((s for s in all_sets(config) if s["name"] == name), None)


def role_in(entry: dict, fs_uuid: str) -> str | None:
    if entry["master"] == fs_uuid:
        return "master"
    if fs_uuid in entry["copies"]:
        return "slave"
    return None


def sets_of_disk(config: dict, fs_uuid: str) -> list[dict]:
    """Every set this disk takes part in. A master may serve several."""
    return [s for s in all_sets(config) if role_in(s, fs_uuid)]


def is_master_anywhere(config: dict, fs_uuid: str) -> bool:
    return any(s["master"] == fs_uuid for s in all_sets(config))


def is_copy_anywhere(config: dict, fs_uuid: str) -> bool:
    return any(fs_uuid in s["copies"] for s in all_sets(config))


def uuids_of_set(entry: dict) -> list[str]:
    return [entry["master"], *entry["copies"]]


def membership(config: dict, fs_uuid: str) -> dict:
    """What this disk is, and where. A master can be in several sets.

    ``role`` and ``set_name`` are kept for everything that only ever deals
    with one set at a time; ``sets`` is the full truth.
    """
    names = [s["name"] for s in sets_of_disk(config, fs_uuid)]
    if is_master_anywhere(config, fs_uuid):
        role = "master"
    elif is_copy_anywhere(config, fs_uuid):
        role = "slave"
    else:
        role = None
    return {"role": role, "set_name": names[0] if names else None, "sets": names}


def disks_of_set(config: dict, set_name: str) -> list[dict]:
    """The disk entries of one set, master first, in registration order."""
    entry = find_set(config, set_name)
    if entry is None:
        return []
    found = []
    for fs_uuid in uuids_of_set(entry):
        disk = find_disk(config, fs_uuid)
        if disk is not None:
            found.append({**disk, "role": role_in(entry, fs_uuid),
                          "set_name": set_name})
    return found


# --------------------------------------------------------------------------
# block device inspection
# --------------------------------------------------------------------------

def list_block_devices() -> list[dict]:
    """Every partition that carries a filesystem, with its parent's serial."""
    columns = "NAME,PATH,TYPE,SIZE,FSTYPE,LABEL,UUID,SERIAL,TRAN,HOTPLUG,RM,MOUNTPOINT,MODEL,VENDOR"
    try:
        raw = subprocess.run(
            ["lsblk", "-J", "-b", "-o", columns],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout
    except (subprocess.SubprocessError, OSError) as exc:
        raise RuntimeError(f"lsblk failed: {exc}") from exc

    result: list[dict] = []

    def walk(node: dict, parent: dict | None) -> None:
        entry = {
            "name": node.get("name"),
            "path": node.get("path"),
            "type": node.get("type"),
            "size": node.get("size") or 0,
            "fs_type": node.get("fstype"),
            "label": node.get("label"),
            "fs_uuid": node.get("uuid"),
            "mountpoint": node.get("mountpoint"),
            "serial": node.get("serial") or (parent or {}).get("serial"),
            "transport": node.get("tran") or (parent or {}).get("transport"),
            "removable": bool(node.get("hotplug") or node.get("rm")
                              or (parent or {}).get("removable")),
            "model": (node.get("model") or (parent or {}).get("model") or "").strip(),
            "vendor": (node.get("vendor") or (parent or {}).get("vendor") or "").strip(),
            "parent_path": (parent or {}).get("path"),
        }
        children = node.get("children") or []
        entry["system"] = is_system_partition(entry)

        entry["token"] = device_token(entry)

        if entry["fs_type"] and entry["type"] in ("part", "disk", "loop"):
            # A filesystem, whether on a partition or straight on the disk -
            # external drives are often formatted without a partition table.
            entry["usable"] = (entry["fs_type"] or "").lower() in FS_OPTIONS \
                and not entry["system"]
            if not entry["usable"] and not entry["system"]:
                entry["reason"] = "unsupported_filesystem"
            result.append(entry)
        elif entry["type"] == "part" or (entry["type"] in ("disk", "loop")
                                         and not children):
            # Nothing readable here. Reported rather than dropped: a disk that
            # simply vanishes from the list leaves the user guessing why.
            entry["usable"] = False
            entry["reason"] = "no_filesystem"
            result.append(entry)

        for child in children:
            walk(child, entry)

    for node in json.loads(raw).get("blockdevices", []):
        walk(node, None)
    return result


def device_for_uuid(fs_uuid: str) -> Path | None:
    """Resolve a filesystem UUID to a device node - never a client-supplied path."""
    candidate = Path("/dev/disk/by-uuid") / fs_uuid
    if candidate.exists():
        return candidate.resolve()
    # exfat and vfat UUIDs are case-insensitive short serials; by-uuid uses
    # upper case, so try that before giving up.
    candidate = Path("/dev/disk/by-uuid") / fs_uuid.upper()
    if candidate.exists():
        return candidate.resolve()
    for entry in list_block_devices():
        if entry["fs_uuid"] and entry["fs_uuid"].upper() == fs_uuid.upper():
            return Path(entry["path"])
    return None


def exfat_volume_state(device: Path) -> dict:
    """Read the exFAT VolumeFlags from the boot sector.

    Offset 106 holds a 16 bit field; bit 1 is VolumeDirty, set while the
    volume is mounted and left set when it was not unmounted cleanly. Bit 2
    is MediaFailure. Reading this needs the raw device, which is another
    reason it belongs in the helper and not in the container.
    """
    try:
        with open(device, "rb") as fh:
            sector = fh.read(512)
    except OSError as exc:
        return {"readable": False, "error": str(exc)}
    if len(sector) < 512 or sector[3:11] != b"EXFAT   ":
        return {"readable": False, "error": "not an exFAT boot sector"}
    flags = struct.unpack_from("<H", sector, 106)[0]
    return {
        "readable": True,
        "flags": flags,
        "dirty": bool(flags & 0x0002),
        "media_failure": bool(flags & 0x0004),
    }


def volume_state(fs_uuid: str, fs_type: str | None = None) -> dict:
    device = device_for_uuid(fs_uuid)
    if device is None:
        return {"present": False}
    state = {"present": True, "device": str(device)}
    if (fs_type or "").lower() == "exfat":
        state.update(exfat_volume_state(device))
    return state


# --------------------------------------------------------------------------
# mounting
# --------------------------------------------------------------------------

def read_mountinfo() -> list[dict]:
    entries = []
    for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
        fields = line.split(" ")
        try:
            separator = fields.index("-")
        except ValueError:
            continue
        entries.append({
            "mountpoint": fields[4].replace("\\040", " "),
            "options": fields[5].split(","),
            "fs_type": fields[separator + 1],
            "source": fields[separator + 2],
        })
    return entries


def mount_flags(mountpoint: Path) -> list[str] | None:
    target = str(mountpoint)
    for entry in read_mountinfo():
        if entry["mountpoint"] == target:
            return entry["options"]
    return None


def is_mounted(mountpoint: Path) -> bool:
    return mount_flags(mountpoint) is not None


def mountpoint_for(disk: dict) -> Path:
    """Where a disk goes. One disk, one place - whatever it takes part in.

    A master may serve several sets, and mounting it once per set would mean
    the same device mounted several times over. It is held read-only either
    way, but two mounts of one exFAT volume is a thing to avoid rather than
    to reason about. So the path says what the disk *is*, not who is using
    it, and a set points at it.
    """
    if disk["role"] == "master":
        return MOUNT_ROOT / "masters" / disk["display_name"]
    return MOUNT_ROOT / "copies" / disk["display_name"]


def run_mount(device: Path, mountpoint: Path, fs_type: str, read_only: bool) -> None:
    driver = FS_DRIVER.get(fs_type.lower())
    if driver is None:
        raise RuntimeError(f"filesystem {fs_type!r} is not allowed")
    options = [("ro" if read_only else "rw")]
    extra = FS_OPTIONS[fs_type.lower()].format(uid=APP_UID, gid=APP_GID)
    if extra:
        options.append(extra)
    mountpoint.mkdir(parents=True, exist_ok=True)
    # Arguments as a list, never as a shell string - these paths contain
    # spaces and exclamation marks in real life.
    command = ["mount", "-t", driver, "-o", ",".join(options), str(device), str(mountpoint)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"mount exited with {result.returncode}")


def run_umount(mountpoint: Path) -> None:
    if not is_mounted(mountpoint):
        return
    result = subprocess.run(["umount", str(mountpoint)], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"umount exited with {result.returncode}")


def ensure_shared_mount_root() -> None:
    """Make MOUNT_ROOT a shared mount so mounts appear inside the container."""
    MOUNT_ROOT.mkdir(parents=True, exist_ok=True)
    if not is_mounted(MOUNT_ROOT):
        subprocess.run(["mount", "--bind", str(MOUNT_ROOT), str(MOUNT_ROOT)],
                       capture_output=True, text=True, timeout=30)
    subprocess.run(["mount", "--make-rshared", str(MOUNT_ROOT)],
                   capture_output=True, text=True, timeout=30)


def mount_set(set_name: str) -> dict:
    config = load_config()
    members = disks_of_set(config, set_name)
    if not members:
        raise RuntimeError(f"no disks registered for set {set_name!r}")

    masters = [d for d in members if d["role"] == "master"]
    if len(masters) != 1:
        raise RuntimeError(f"set {set_name!r} needs exactly one master, found {len(masters)}")

    ensure_shared_mount_root()
    mounted: list[dict] = []
    missing: list[dict] = []
    #: Only what this call mounted is undone on failure - a master another
    #: set is already reading from stays where it is.
    ours: list[Path] = []

    # Master first. If it cannot be mounted read-only, nothing else happens.
    for disk in masters + [d for d in members if d["role"] != "master"]:
        if is_ignored(config, disk["fs_uuid"]):
            # Belt and braces: an excluded disk cannot be registered, so this
            # should be unreachable - which is exactly when a check is worth
            # having.
            raise RuntimeError(f"{disk['display_name']} is on the excluded list")
        device = device_for_uuid(disk["fs_uuid"])
        if device is None:
            missing.append({"fs_uuid": disk["fs_uuid"], "display_name": disk["display_name"],
                            "role": disk["role"]})
            if disk["role"] == "master":
                raise RuntimeError("the master disk of this set is not connected")
            continue

        mountpoint = mountpoint_for(disk)
        read_only = disk["role"] == "master"
        try:
            if not is_mounted(mountpoint):
                run_mount(device, mountpoint, disk["fs_type"], read_only)
                ours.append(mountpoint)
        except RuntimeError:
            for path in ours:
                run_umount(path)
            raise

        flags = mount_flags(mountpoint) or []
        if read_only and "ro" not in flags:
            # Never proceed with a writable master. Undo everything.
            for path in ours:
                run_umount(path)
            raise RuntimeError(
                "refusing to continue: the master was not mounted read-only "
                f"(flags: {','.join(flags)})"
            )

        mounted.append({
            "fs_uuid": disk["fs_uuid"],
            "display_name": disk["display_name"],
            "role": disk["role"],
            "mountpoint": str(mountpoint),
            "read_only": "ro" in flags,
            "flags": flags,
        })

    log(f"set {set_name!r}: mounted {len(mounted)} disk(s), {len(missing)} missing")
    return {"mounted": mounted, "missing": missing}


def master_still_needed(config: dict, fs_uuid: str, except_set: str) -> str | None:
    """Is another set still using this master? Name it if so.

    The master is mounted once and shared, so it may only be released when
    nothing else is reading from it. Anything else would pull the ground out
    from under a comparison running in another set.
    """
    for entry in all_sets(config):
        if entry["name"] == except_set or entry["master"] != fs_uuid:
            continue
        for copy_uuid in entry["copies"]:
            disk = find_disk(config, copy_uuid)
            if disk is None:
                continue
            if is_mounted(mountpoint_for({**disk, "role": "slave"})):
                return entry["name"]
    return None


def umount_set(set_name: str) -> dict:
    config = load_config()
    entry = find_set(config, set_name)
    if entry is None:
        raise RuntimeError(f"no set named {set_name!r}")

    released, failed, kept = [], [], []
    for disk in disks_of_set(config, set_name):
        if disk["role"] == "master":
            in_use = master_still_needed(config, disk["fs_uuid"], set_name)
            if in_use:
                kept.append({"display_name": disk["display_name"], "used_by": in_use})
                continue
        mountpoint = mountpoint_for(disk)
        try:
            run_umount(mountpoint)
            released.append(str(mountpoint))
        except RuntimeError as exc:
            failed.append({"mountpoint": str(mountpoint), "error": str(exc)})
    return {"released": released, "failed": failed, "kept": kept}


def mount_status(set_name: str) -> dict:
    config = load_config()
    status = []
    for disk in disks_of_set(config, set_name):
        mountpoint = mountpoint_for(disk)
        flags = mount_flags(mountpoint)
        status.append({
            "fs_uuid": disk["fs_uuid"],
            "display_name": disk["display_name"],
            "role": disk["role"],
            "mountpoint": str(mountpoint),
            "mounted": flags is not None,
            "read_only": bool(flags and "ro" in flags),
            "flags": flags or [],
            "connected": device_for_uuid(disk["fs_uuid"]) is not None,
        })
    return {"disks": status}


# --------------------------------------------------------------------------
# request handling
# --------------------------------------------------------------------------

def handle(request: dict) -> dict:
    command = request.get("cmd")

    if command == "ping":
        return {"ok": True, "version": 1,
                "allow_demote": demote_allowed(load_config())}

    if command == "list_disks":
        config = load_config()
        known = {d["fs_uuid"]: d for d in config["disks"]}
        devices = []
        for entry in list_block_devices():
            fs_uuid = entry["fs_uuid"] or ""
            registration = known.get(fs_uuid)
            if registration is not None:
                registration = {**registration, **membership(config, fs_uuid)}
            devices.append({**entry, "registration": registration,
                            "ignored": is_ignored(config, fs_uuid),
                            "retired": fs_uuid in retired_masters(config)})
        return {"ok": True, "disks": devices,
                "ignored": ignored_disks(config)}

    if command == "list_registrations":
        config = load_config()
        return {"ok": True,
                "disks": [{**d, **membership(config, d["fs_uuid"])}
                          for d in config["disks"]],
                "sets": [{"name": s["name"], "master": s["master"],
                          "copies": list(s["copies"]),
                          "created_at": s.get("created_at")}
                         for s in all_sets(config)]}

    if command == "list_sets":
        config = load_config()
        return {"ok": True, "sets": [
            {"name": s["name"], "master": s["master"], "copies": list(s["copies"]),
             "created_at": s.get("created_at")} for s in all_sets(config)]}

    if command == "register":
        return handle_register(request)

    if command == "unregister":
        return handle_unregister(request)

    if command == "demote":
        return handle_demote(request)

    if command == "forget_set":
        return handle_forget_set(request)

    if command == "ignore":
        return handle_ignore(request)

    if command == "unignore":
        return handle_unignore(request)

    if command == "peek":
        return handle_peek(request)

    if command == "format":
        return handle_format(request)

    if command == "list_ignored":
        return {"ok": True, "ignored": ignored_disks(load_config())}

    if command == "mount_set":
        set_name = require_name(request.get("set_name"), "set_name")
        return {"ok": True, **mount_set(set_name)}

    if command == "umount_set":
        set_name = require_name(request.get("set_name"), "set_name")
        return {"ok": True, **umount_set(set_name)}

    if command == "mount_status":
        set_name = require_name(request.get("set_name"), "set_name")
        return {"ok": True, **mount_status(set_name)}

    if command == "smart":
        return handle_smart(request)

    if command == "volume_state":
        fs_uuid = require_uuid(request.get("fs_uuid"))
        return {"ok": True, **volume_state(fs_uuid, request.get("fs_type"))}

    raise RuntimeError(f"unknown command {command!r}")


def require_name(value, field: str) -> str:
    """Check a name that is going to be a folder, and say what is wrong."""
    if not isinstance(value, str):
        raise RuntimeError(f"{field} is missing")
    name = value.strip()
    if not name:
        raise RuntimeError(f"{field} must not be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise RuntimeError(
            f"{field} is {len(name)} characters, the limit is {MAX_NAME_LENGTH}")
    offending = sorted({character for character in name
                        if character in FORBIDDEN_IN_NAME})
    if offending:
        shown = " ".join("a slash" if c == "/" else
                         "a backslash" if c == "\\" else
                         "a control character" for c in offending)
        raise RuntimeError(f"{field} must not contain {shown}")
    if name in (".", ".."):
        raise RuntimeError(f"{field} must not be {name!r}")
    return name


def require_uuid(value) -> str:
    if not isinstance(value, str) or not UUID_RE.match(value):
        raise RuntimeError("invalid fs_uuid")
    return value


def handle_register(request: dict) -> dict:
    """Put a disk into a set. Add-only, on purpose.

    Two rules hold the whole read-only guarantee up, and both live here:

      * A disk is either a master or a copy, never both and never in turn.
        A master may serve any number of sets - the same archive backed up
        in two directions is ordinary - but the moment it could also be a
        copy somewhere, "master" would stop meaning anything.
      * A copy belongs to exactly one set. Two masters writing onto one disk
        would each believe they owned it.

    Changing a role is not possible at all. A master is given up (which
    removes it), and then registered afresh.
    """
    fs_uuid = require_uuid(request.get("fs_uuid"))
    role = request.get("role")
    if role not in VALID_ROLES:
        raise RuntimeError("role must be master or slave")
    set_name = require_name(request.get("set_name"), "the set name")
    display_name = require_name(request.get("display_name"), "the disk name")

    config = load_config()
    if is_ignored(config, fs_uuid):
        raise RuntimeError(
            "this disk is excluded - take it off the excluded list first")

    if role == "master" and is_copy_anywhere(config, fs_uuid):
        raise RuntimeError(
            "this disk is a copy in another set. A disk is either a master or "
            "a copy - forget it there first if it should become a master.")
    if role != "master":
        if is_master_anywhere(config, fs_uuid):
            raise RuntimeError(
                "this disk is the master of another set and cannot also be a "
                "copy. Give the master up first if that is what you want.")
        if fs_uuid in retired_masters(config):
            raise RuntimeError(
                "this disk has been a master. Demote it first - that is a "
                "separate, deliberate step, because otherwise forgetting a "
                "registration would quietly turn a master into a copy.")
        other = next((s for s in all_sets(config)
                      if fs_uuid in s["copies"] and s["name"] != set_name), None)
        if other is not None:
            raise RuntimeError(
                f"this disk is already a copy in set {other['name']!r}. A copy "
                "belongs to one master only.")

    entry = find_set(config, set_name)
    if entry is not None and role == "master" and entry["master"] not in (None, fs_uuid):
        raise RuntimeError(f"set {set_name!r} already has a master")
    if entry is None and role != "master":
        raise RuntimeError(
            f"set {set_name!r} has no master yet - register the master first")

    clash = next((d for d in config["disks"]
                  if d["display_name"] == display_name and d["fs_uuid"] != fs_uuid), None)
    if clash is not None:
        # Names are mount points now, and a master is mounted once for every
        # set it serves, so they have to be unique across the whole registry.
        raise RuntimeError(f"the name {display_name!r} is already taken")

    existing = find_disk(config, fs_uuid)
    if existing is None:
        detected = next((e for e in list_block_devices()
                         if (e["fs_uuid"] or "").upper() == fs_uuid.upper()), None)
        if detected is None:
            raise RuntimeError("this disk is not connected, so it cannot be registered")
        if not detected.get("fs_type"):
            raise RuntimeError(
                f"{detected['path']} has no filesystem - format it first, "
                "exFAT if the disk also has to work on macOS and Windows")
        if (detected["fs_type"] or "").lower() not in FS_OPTIONS:
            raise RuntimeError(f"filesystem {detected['fs_type']!r} is not supported")
        if detected.get("system"):
            # The root filesystem as a "copy" would mean AmberShelf writing
            # into the machine it runs on. There is no sensible reason to
            # allow it.
            raise RuntimeError(
                f"{detected['path']} belongs to the running system"
                + (f" (mounted at {detected['mountpoint']})" if detected["mountpoint"] else "")
                + " and cannot be registered")
        existing = {
            "fs_uuid": fs_uuid,
            "serial": detected["serial"],
            "label": detected["label"],
            "size": detected["size"],
            "fs_type": detected["fs_type"],
            "model": detected["model"],
            "display_name": display_name,
            "registered_at": now(),
            "last_seen_at": now(),
        }
        config["disks"].append(existing)
    else:
        existing["display_name"] = display_name
        existing["last_seen_at"] = now()

    if entry is None:
        entry = {"name": set_name, "master": None, "copies": [], "created_at": now()}
        all_sets(config).append(entry)
    if role == "master":
        entry["master"] = fs_uuid
    elif fs_uuid not in entry["copies"]:
        entry["copies"].append(fs_uuid)

    save_config(config)
    log(f"registered {display_name!r} ({fs_uuid}) as {role} of set {set_name!r}")
    return {"ok": True, "disk": {**existing, "role": role, "set_name": set_name},
            "created": True}


def drop_from_sets(config: dict, fs_uuid: str) -> list[str]:
    """Take a disk out of every set it takes part in, and say which."""
    touched = []
    for entry in list(all_sets(config)):
        role = role_in(entry, fs_uuid)
        if role is None:
            continue
        touched.append(entry["name"])
        if role == "master":
            # A set without its master is not a set. Its copies become
            # ordinary registered disks again, free to be used elsewhere.
            all_sets(config).remove(entry)
        else:
            entry["copies"].remove(fs_uuid)
    return touched


def handle_unregister(request: dict) -> dict:
    """Forget a disk. Its data is never touched - only this file changes."""
    fs_uuid = require_uuid(request.get("fs_uuid"))
    config = load_config()
    disk = find_disk(config, fs_uuid)
    if disk is None:
        raise RuntimeError("this disk is not registered")

    was_master = is_master_anywhere(config, fs_uuid)
    role = "master" if was_master else "slave"
    if is_mounted(mountpoint_for({**disk, "role": role})):
        raise RuntimeError(
            f"{disk['display_name']} is still mounted - eject the set first")

    if was_master:
        retire_master(config, fs_uuid)

    touched = drop_from_sets(config, fs_uuid)
    config["disks"] = [d for d in config["disks"] if d["fs_uuid"] != fs_uuid]
    save_config(config)
    log(f"unregistered {disk['display_name']!r} ({fs_uuid}, was {role}) "
        f"from set(s) {', '.join(touched) or 'none'}")
    return {"ok": True, "disk": {**disk, "role": role}, "sets": touched}


def handle_forget_set(request: dict) -> dict:
    """Dissolve one set. The disks in it stay registered.

    Taking the disks with it would be wrong now that a master can serve
    several sets: dropping one of them would pull the master out from under
    the others, and put it on the retired list for good measure.
    """
    set_name = require_name(request.get("set_name"), "the set name")
    config = load_config()
    entry = find_set(config, set_name)
    if entry is None:
        raise RuntimeError(f"no set named {set_name!r}")

    for disk in disks_of_set(config, set_name):
        if is_mounted(mountpoint_for(disk)):
            raise RuntimeError(
                f"{disk['display_name']} is still mounted - eject the set first")

    all_sets(config).remove(entry)
    save_config(config)
    log(f"set {set_name!r} dissolved - its {len(entry['copies']) + 1} disk(s) "
        f"stay registered")
    return {"ok": True, "set": entry}


def handle_demote(request: dict) -> dict:
    """Let a disk that has been a master be an ordinary disk again.

    This is the one command that undoes a retirement, so it is the only way
    the socket can end up with a former master registered as a copy. It is
    kept as narrow as it can be: the registration is removed rather than
    rewritten, and a mounted set is refused outright, so nothing that is
    mounted read-only right now can have its role changed underneath it.
    """
    fs_uuid = require_uuid(request.get("fs_uuid"))
    config = load_config()
    if not demote_allowed(config):
        raise RuntimeError(
            "giving up a master is switched off on this host. It can be done "
            "with 'ambershelf-helper --admin remove' followed by "
            "'--admin forget', or by setting \"allow_demote\": true in "
            f"{CONFIG_PATH}")
    disk = find_disk(config, fs_uuid)

    if disk is not None:
        if not is_master_anywhere(config, fs_uuid):
            raise RuntimeError(
                f"{disk['display_name']} is not a master - "
                "an ordinary disk is forgotten, not demoted")
        if is_mounted(mountpoint_for({**disk, "role": "master"})):
            raise RuntimeError(
                f"{disk['display_name']} is still mounted - eject the set first")
        drop_from_sets(config, fs_uuid)
        config["disks"] = [d for d in config["disks"] if d["fs_uuid"] != fs_uuid]
    elif fs_uuid not in retired_masters(config):
        raise RuntimeError("this disk is not a master and has never been one")

    retired = retired_masters(config)
    if fs_uuid in retired:
        retired.remove(fs_uuid)
    save_config(config)

    name = disk["display_name"] if disk else fs_uuid
    log(f"demoted {name!r} ({fs_uuid}): registration removed and taken off the "
        f"retired list - it may be registered as a copy from now on")
    return {"ok": True, "disk": disk}


def handle_smart(request: dict) -> dict:
    """Ask one disk what it thinks of itself.

    Read-only in every sense: it asks the disk for its own log and changes
    nothing, not the disk and not the registry. The whole disk is asked, not
    the partition, because SMART lives in the drive rather than in a
    filesystem.
    """
    fs_uuid = require_uuid(request.get("fs_uuid"))
    entry = next((e for e in list_block_devices()
                  if (e["fs_uuid"] or "").upper() == fs_uuid.upper()), None)
    if entry is None:
        raise RuntimeError("this disk is not connected")
    device = entry.get("parent_path") or entry["path"]

    if not Path(SMARTCTL).exists():
        return {"ok": True, "smart": {"ok": False, "reason": "smart.no_binary"}}

    # A USB enclosure either answers straight away or has to be told that it
    # is SATA underneath. Both are tried; the difference is not visible from
    # the outside.
    last = {"ok": False, "reason": "smart.unreadable"}
    for arguments in ([], ["-d", "sat"]):
        try:
            finished = subprocess.run(
                [SMARTCTL, "--json=c", "-a", *arguments, device],
                capture_output=True, timeout=90)
        except subprocess.TimeoutExpired:
            return {"ok": True, "smart": {"ok": False, "reason": "smart.timeout"}}
        except OSError as exc:
            raise RuntimeError(f"smartctl could not be run: {exc}") from exc

        try:
            data = json.loads(finished.stdout.decode("utf-8", "replace") or "{}")
        except ValueError:
            continue

        # The exit status is a bit field; the low three bits mean smartctl
        # could not reach the device, anything above is the disk reporting.
        status = int(data.get("smartctl", {}).get("exit_status", 0))
        has_data = ("ata_smart_attributes" in data
                    or "nvme_smart_health_information_log" in data)
        if status & 0b111 or not has_data:
            messages = data.get("smartctl", {}).get("messages", [])
            text = "; ".join(m.get("string", "") for m in messages).strip()
            last = {"ok": False, "reason": text or "smart.unsupported"}
            continue
        return {"ok": True, "smart": {"ok": True, "data": data}}

    return {"ok": True, "smart": last}


def handle_ignore(request: dict) -> dict:
    """Put a disk out of reach. Nothing on it is touched, ever."""
    fs_uuid = require_uuid(request.get("fs_uuid"))
    config = load_config()

    if find_disk(config, fs_uuid) is not None:
        raise RuntimeError(
            "this disk is registered - forget it first, then exclude it")
    if is_ignored(config, fs_uuid):
        return {"ok": True, "already": True}

    detected = next((e for e in list_block_devices()
                     if (e["fs_uuid"] or "").upper() == fs_uuid.upper()), None)
    entry = {
        "fs_uuid": fs_uuid,
        "label": (detected or {}).get("label"),
        "serial": (detected or {}).get("serial"),
        "size": (detected or {}).get("size") or 0,
        "fs_type": (detected or {}).get("fs_type"),
        "added_at": now(),
    }
    ignored_disks(config).append(entry)
    save_config(config)
    log(f"excluded {fs_uuid} ({entry['label'] or 'no label'})")
    return {"ok": True, "disk": entry}


def handle_unignore(request: dict) -> dict:
    fs_uuid = require_uuid(request.get("fs_uuid"))
    config = load_config()
    before = len(ignored_disks(config))
    config["ignored"] = [e for e in ignored_disks(config) if e["fs_uuid"] != fs_uuid]
    if len(config["ignored"]) == before:
        raise RuntimeError("this disk is not excluded")
    save_config(config)
    log(f"no longer excluded: {fs_uuid}")
    return {"ok": True}


def refuse_unless_free(entry: dict, config: dict) -> None:
    """Every reason a disk must be left alone, checked in one place."""
    if entry.get("system"):
        raise RuntimeError(
            f"{entry['path']} belongs to the running system"
            + (f" (mounted at {entry['mountpoint']})" if entry.get("mountpoint") else ""))
    if entry.get("mountpoint"):
        raise RuntimeError(f"{entry['path']} is mounted at {entry['mountpoint']}")

    uuid = entry.get("fs_uuid") or ""
    if uuid and find_disk(config, uuid) is not None:
        raise RuntimeError(
            f"{entry['path']} is registered - forget it first")
    if uuid and is_ignored(config, uuid):
        raise RuntimeError(f"{entry['path']} is on the excluded list")

    # A partition of a disk that carries something registered counts too.
    parent = entry.get("parent_path")
    for other in list_block_devices():
        if other["path"] == entry["path"]:
            continue
        related = (other.get("parent_path") == entry["path"]
                   or other["path"] == parent)
        if not related:
            continue
        if other.get("mountpoint"):
            raise RuntimeError(
                f"{other['path']} on the same disk is mounted at {other['mountpoint']}")
        other_uuid = other.get("fs_uuid") or ""
        if other_uuid and find_disk(config, other_uuid) is not None:
            raise RuntimeError(f"{other['path']} on the same disk is registered")
        if other_uuid and is_ignored(config, other_uuid):
            raise RuntimeError(f"{other['path']} on the same disk is excluded")


def handle_peek(request: dict) -> dict:
    """Mount a disk read-only for a moment and say what is on it.

    The most honest warning before erasing something is its own contents.
    Read-only, so looking cannot break anything.
    """
    entry = device_for_token(request.get("token"))
    if not entry.get("fs_type"):
        return {"ok": True, "readable": False, "entries": [], "count": 0}
    if (entry["fs_type"] or "").lower() not in FS_OPTIONS:
        return {"ok": True, "readable": False, "entries": [], "count": 0}
    if entry.get("mountpoint"):
        root = Path(entry["mountpoint"])
        return {"ok": True, **describe_contents(root)}

    temporary = Path("/run/ambershelf/peek")
    temporary.mkdir(parents=True, exist_ok=True)
    try:
        run_mount(Path(entry["path"]), temporary, entry["fs_type"], read_only=True)
    except RuntimeError as exc:
        return {"ok": True, "readable": False, "entries": [], "count": 0,
                "error": str(exc)}
    try:
        return {"ok": True, **describe_contents(temporary)}
    finally:
        run_umount(temporary)


def describe_contents(root: Path) -> dict:
    try:
        names = sorted(child.name for child in root.iterdir()
                       if not child.name.startswith("."))
    except OSError as exc:
        return {"readable": False, "entries": [], "count": 0, "error": str(exc)}
    return {"readable": True, "entries": names[:12], "count": len(names)}


def handle_format(request: dict) -> dict:
    """Erase a disk and put a fresh filesystem on it.

    The most destructive thing this program can do, so every guard is here
    and the caller has had to confirm twice before reaching it.
    """
    entry = device_for_token(request.get("token"))
    config = load_config()
    refuse_unless_free(entry, config)

    filesystem = str(request.get("filesystem") or "exfat").lower()
    if filesystem not in MKFS:
        raise RuntimeError(f"cannot create {filesystem!r}")
    label = require_name(request.get("label") or "AmberShelf", "the label")
    label = label[:LABEL_LIMITS.get(filesystem, 11)]

    whole_disk = entry["type"] in ("disk", "loop")
    device = entry["path"]
    log(f"formatting {device} as {filesystem}, label {label!r}")

    if whole_disk:
        # A partition table, because that is what macOS and Windows create
        # and what they read back without complaint.
        step(["wipefs", "--all", device], WIPEFS)
        step(["sfdisk", "--label", "gpt", device], SFDISK,
             stdin=f'type={PARTITION_TYPE}\n')
        step(["partprobe", device], PARTPROBE, check=False)
        subprocess.run(["udevadm", "settle"], capture_output=True, timeout=30)
        target = f"{device}p1" if device[-1].isdigit() else f"{device}1"
        for _ in range(20):
            if Path(target).exists():
                break
            time.sleep(0.25)
        if not Path(target).exists():
            raise RuntimeError(f"the new partition {target} did not appear")
    else:
        target = device
        step(["wipefs", "--all", device], WIPEFS)

    command = [part.format(label=label, device=target) for part in MKFS[filesystem]]
    step(command, command[0])
    subprocess.run(["udevadm", "settle"], capture_output=True, timeout=30)

    fresh = next((e for e in list_block_devices() if e["path"] == target), None)
    log(f"formatted {target}: {(fresh or {}).get('fs_uuid')}")
    return {"ok": True, "device": target,
            "fs_uuid": (fresh or {}).get("fs_uuid"), "label": label}


def step(command: list[str], binary: str, stdin: str | None = None,
         check: bool = True) -> None:
    command = [binary, *command[1:]]
    if not Path(binary).exists():
        raise RuntimeError(f"{binary} is not installed on this host")
    result = subprocess.run(command, capture_output=True, timeout=900,
                            input=(stdin or "").encode() if stdin else None)
    if check and result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(f"{Path(binary).name} failed: {detail[:300]}")


class Handler(socketserver.StreamRequestHandler):
    timeout = 300

    def handle(self) -> None:
        raw = self.rfile.readline(MAX_REQUEST)
        if not raw:
            return
        try:
            request = json.loads(raw.decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
        except (ValueError, UnicodeDecodeError) as exc:
            self.reply({"ok": False, "error": f"malformed request: {exc}"})
            return
        try:
            with _lock:
                response = handle(request)
        except Exception as exc:  # noqa: BLE001 - every failure goes back as text
            log(f"error: {exc}")
            response = {"ok": False, "error": str(exc)}
        self.reply(response)

    def reply(self, payload: dict) -> None:
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


def serve() -> None:
    if os.geteuid() != 0:
        sys.exit("the helper has to run as root - it is the part that mounts things")
    persist_migration()
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()

    ensure_shared_mount_root()
    server = Server(str(SOCKET_PATH), Handler)

    try:
        gid = grp.getgrnam(SOCKET_GROUP).gr_gid
        os.chown(SOCKET_PATH, 0, gid)
        os.chmod(SOCKET_PATH, 0o660)
    except KeyError:
        log(f"group {SOCKET_GROUP!r} does not exist - socket stays root-only")
        os.chmod(SOCKET_PATH, 0o600)

    log(f"listening on {SOCKET_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        SOCKET_PATH.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# host-only administration
# --------------------------------------------------------------------------

def admin(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="ambershelf-helper --admin")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    set_role = sub.add_parser("set-role")
    set_role.add_argument("fs_uuid")
    set_role.add_argument("role", choices=VALID_ROLES)
    remove = sub.add_parser("remove")
    remove.add_argument("fs_uuid")
    forget = sub.add_parser("forget")
    forget.add_argument("fs_uuid")
    sub.add_parser("scan")
    sub.add_parser("retired")
    sub.add_parser("excluded")
    exclude = sub.add_parser("exclude")
    exclude.add_argument("fs_uuid")
    include = sub.add_parser("include")
    include.add_argument("fs_uuid")
    args = parser.parse_args(argv)

    if args.action == "list":
        config = load_config()
        if not config["disks"]:
            print("no disks registered")
            return
        for entry in all_sets(config):
            print(f"set {entry['name']}")
            for disk in disks_of_set(config, entry["name"]):
                connected = ("connected" if device_for_uuid(disk["fs_uuid"])
                             else "not connected")
                print(f"  {disk['role']:<7} {disk['display_name']:<24} "
                      f"{disk['fs_uuid']:<38} {disk['fs_type'] or '-':<6} {connected}")
        loose = [d for d in config["disks"] if not sets_of_disk(config, d["fs_uuid"])]
        if loose:
            print("\nregistered but in no set:")
            for disk in loose:
                print(f"  {disk['display_name']:<24} {disk['fs_uuid']}")
        return

    if args.action == "retired":
        retired = retired_masters(load_config())
        if not retired:
            print("no disk has been a master and been removed")
            return
        print("these have been a master, so the socket will only register them "
              "as one again:")
        for fs_uuid in retired:
            print(f"  {fs_uuid}")
        print("\nclear one with: ambershelf-helper --admin forget <fs-uuid>")
        return

    if args.action == "excluded":
        entries = ignored_disks(load_config())
        if not entries:
            print("no disk is excluded")
            return
        print("AmberShelf leaves these alone entirely:")
        for entry in entries:
            print(f"  {entry['fs_uuid']:<38} {entry.get('label') or '-':<20} "
                  f"{entry.get('fs_type') or '-'}")
        return

    if args.action == "scan":
        for entry in list_block_devices():
            marks = []
            if entry.get("system"):
                marks.append("system")
            if entry.get("removable"):
                marks.append("removable")
            if entry.get("reason"):
                marks.append(entry["reason"])
            print(f"{entry['path']:<14} {entry['fs_type'] or '-':<6} "
                  f"{(entry['fs_uuid'] or '-'):<38} {(entry['label'] or '-'):<20} "
                  f"{int(entry['size']) / 1024**3:8.1f} GB  "
                  f"{'usb' if entry['transport'] == 'usb' else entry['transport'] or '-':<6} "
                  f"{' '.join(marks)}")
        return

    config = load_config()

    if args.action == "exclude":
        print(handle_ignore({"fs_uuid": args.fs_uuid}))
        return

    if args.action == "include":
        print(handle_unignore({"fs_uuid": args.fs_uuid}))
        return

    if args.action == "forget":
        retired = retired_masters(config)
        if args.fs_uuid not in retired:
            sys.exit(f"{args.fs_uuid} is not on the retired list")
        print(f"{args.fs_uuid} may be registered as a copy again after this.")
        if input("type YES to confirm: ") != "YES":
            sys.exit("cancelled")
        retired.remove(args.fs_uuid)
        save_config(config)
        print("done")
        return

    disk = find_disk(config, args.fs_uuid)
    if disk is None:
        sys.exit(f"{args.fs_uuid} is not registered")

    if args.action == "set-role":
        # A role is no longer something a disk has - it is something a set
        # says about a disk. Rewriting one in place would have to guess which
        # set was meant, and would be exactly the quiet master-to-copy change
        # this program exists to prevent.
        sys.exit("roles are not rewritten any more: remove the disk and "
                 "register it again in the role you want")

    if args.action == "remove":
        where = [s["name"] for s in sets_of_disk(config, args.fs_uuid)]
        was_master = is_master_anywhere(config, args.fs_uuid)
        print(f"removing {disk['display_name']} "
              f"({'master' if was_master else 'copy'} of {', '.join(where) or 'no set'})")
        if was_master and where:
            print(f"the set(s) {', '.join(where)} will be dissolved - their "
                  "copies stay registered but belong to nobody")
        if input("type YES to confirm: ") != "YES":
            sys.exit("cancelled")
        if was_master:
            retire_master(config, args.fs_uuid)
            print("noted as a former master - registering it as a copy later "
                  "needs demoting it first, here or in AmberShelf")
        drop_from_sets(config, args.fs_uuid)
        config["disks"] = [d for d in config["disks"] if d["fs_uuid"] != args.fs_uuid]
        save_config(config)
        print("done")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--admin":
        admin(sys.argv[2:])
    else:
        serve()


if __name__ == "__main__":
    main()
