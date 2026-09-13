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
     and from then on the socket will only ever register it as a master
     again. That closes remove-and-re-add, which would otherwise be a way
     around rule 3.
  4. Only exfat, ntfs and ext4 are accepted, each with a fixed option set
     defined here.

Adding an unknown disk is harmless; re-labelling a known master as a slave is
not. That is the whole shape of what the socket may and may not do.
"""
from __future__ import annotations

import argparse
import grp
import json
import os
import re
import socket
import socketserver
import struct
import subprocess
import sys
import threading
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
        return {"version": 1, "disks": []}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"{CONFIG_PATH} is unreadable: {exc}") from exc
    data.setdefault("version", 1)
    data.setdefault("disks", [])
    return data


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


def disks_of_set(config: dict, set_name: str) -> list[dict]:
    return [d for d in config["disks"] if d["set_name"] == set_name]


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
        }
        if entry["type"] == "part" and entry["fs_type"]:
            entry["system"] = is_system_partition(entry)
            result.append(entry)
        for child in node.get("children") or []:
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
    if disk["role"] == "master":
        return MOUNT_ROOT / disk["set_name"] / "master"
    return MOUNT_ROOT / disk["set_name"] / "slaves" / disk["display_name"]


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

    # Master first. If it cannot be mounted read-only, nothing else happens.
    for disk in masters + [d for d in members if d["role"] == "slave"]:
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
        except RuntimeError:
            for entry in mounted:
                run_umount(Path(entry["mountpoint"]))
            raise

        flags = mount_flags(mountpoint) or []
        if read_only and "ro" not in flags:
            # Never proceed with a writable master. Undo everything.
            run_umount(mountpoint)
            for entry in mounted:
                run_umount(Path(entry["mountpoint"]))
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


def umount_set(set_name: str) -> dict:
    config = load_config()
    released, failed = [], []
    for disk in disks_of_set(config, set_name):
        mountpoint = mountpoint_for(disk)
        try:
            run_umount(mountpoint)
            released.append(str(mountpoint))
        except RuntimeError as exc:
            failed.append({"mountpoint": str(mountpoint), "error": str(exc)})
    return {"released": released, "failed": failed}


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
        return {"ok": True, "version": 1}

    if command == "list_disks":
        config = load_config()
        known = {d["fs_uuid"]: d for d in config["disks"]}
        devices = []
        for entry in list_block_devices():
            registration = known.get(entry["fs_uuid"] or "")
            devices.append({**entry, "registration": registration,
                            "ignored": is_ignored(config, entry["fs_uuid"] or "")})
        return {"ok": True, "disks": devices,
                "ignored": ignored_disks(config)}

    if command == "list_registrations":
        return {"ok": True, "disks": load_config()["disks"]}

    if command == "register":
        return handle_register(request)

    if command == "unregister":
        return handle_unregister(request)

    if command == "ignore":
        return handle_ignore(request)

    if command == "unignore":
        return handle_unignore(request)

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
    """Add a disk to the registry. Add-only, on purpose.

    Changing the role of a known disk or removing a registration is refused
    here; both need ``ambershelf-helper --admin`` on the host. Otherwise a
    compromised container could re-declare the master as a slave and get it
    mounted writable.
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
    existing = find_disk(config, fs_uuid)
    if existing is not None:
        if existing["role"] != role or existing["set_name"] != set_name:
            raise RuntimeError(
                "this disk is already registered with a different role or set. "
                "Changing that has to be done on the host with "
                "'ambershelf-helper --admin set-role'."
            )
        existing["display_name"] = display_name
        existing["last_seen_at"] = now()
        save_config(config)
        return {"ok": True, "disk": existing, "created": False}

    if role != "master" and fs_uuid in retired_masters(config):
        raise RuntimeError(
            "this disk has been a master. Registering it as a copy has to be "
            "done on the host with 'ambershelf-helper --admin forget', "
            "because otherwise removing a registration would be a way to turn "
            "a master into a copy.")

    if role == "master" and any(
        d["set_name"] == set_name and d["role"] == "master" for d in config["disks"]
    ):
        raise RuntimeError(f"set {set_name!r} already has a master")

    if any(d["display_name"] == display_name and d["set_name"] == set_name
           for d in config["disks"]):
        raise RuntimeError(f"the name {display_name!r} is already used in this set")

    device = list_block_devices()
    detected = next((e for e in device if (e["fs_uuid"] or "").upper() == fs_uuid.upper()), None)
    if detected is None:
        raise RuntimeError("this disk is not connected, so it cannot be registered")
    if (detected["fs_type"] or "").lower() not in FS_OPTIONS:
        raise RuntimeError(f"filesystem {detected['fs_type']!r} is not supported")
    if detected.get("system"):
        # The root filesystem as a "copy" would mean AmberShelf writing into
        # the machine it runs on. There is no sensible reason to allow it.
        raise RuntimeError(
            f"{detected['path']} belongs to the running system"
            + (f" (mounted at {detected['mountpoint']})" if detected["mountpoint"] else "")
            + " and cannot be registered")

    disk = {
        "fs_uuid": fs_uuid,
        "serial": detected["serial"],
        "label": detected["label"],
        "size": detected["size"],
        "fs_type": detected["fs_type"],
        "model": detected["model"],
        "role": role,
        "set_name": set_name,
        "display_name": display_name,
        "registered_at": now(),
        "last_seen_at": now(),
    }
    config["disks"].append(disk)
    save_config(config)
    log(f"registered {display_name!r} ({fs_uuid}) as {role} of set {set_name!r}")
    return {"ok": True, "disk": disk, "created": True}


def handle_unregister(request: dict) -> dict:
    """Forget a disk. Its data is never touched - only this file changes."""
    fs_uuid = require_uuid(request.get("fs_uuid"))
    config = load_config()
    disk = find_disk(config, fs_uuid)
    if disk is None:
        raise RuntimeError("this disk is not registered")

    mountpoint = mountpoint_for(disk)
    if is_mounted(mountpoint):
        raise RuntimeError(
            f"{disk['display_name']} is still mounted - eject the set first")

    if disk["role"] == "master":
        retire_master(config, fs_uuid)

    config["disks"] = [d for d in config["disks"] if d["fs_uuid"] != fs_uuid]
    save_config(config)
    log(f"unregistered {disk['display_name']!r} ({fs_uuid}, was {disk['role']})")
    return {"ok": True, "disk": disk}


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
        for disk in config["disks"]:
            connected = "connected" if device_for_uuid(disk["fs_uuid"]) else "not connected"
            print(f"{disk['role']:<7} {disk['set_name']:<16} {disk['display_name']:<24} "
                  f"{disk['fs_uuid']:<38} {disk['fs_type']:<6} {connected}")
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
        if args.role == "master" and any(
            d["set_name"] == disk["set_name"] and d["role"] == "master"
            and d["fs_uuid"] != disk["fs_uuid"] for d in config["disks"]
        ):
            sys.exit(f"set {disk['set_name']!r} already has a master")
        print(f"{disk['display_name']}: {disk['role']} -> {args.role}")
        if input("type YES to confirm: ") != "YES":
            sys.exit("cancelled")
        disk["role"] = args.role
        save_config(config)
        print("done - restart ambershelf-helper so running mounts are re-evaluated")
        return

    if args.action == "remove":
        print(f"removing {disk['display_name']} ({disk['role']} of {disk['set_name']})")
        if input("type YES to confirm: ") != "YES":
            sys.exit("cancelled")
        if disk["role"] == "master":
            retire_master(config, args.fs_uuid)
            print("noted as a former master - registering it as a copy later "
                  "needs 'ambershelf-helper --admin forget' first")
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
