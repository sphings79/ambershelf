# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Reading what a disk says about itself, and saying what it means.

smartctl speaks JSON, which is the same on every operating system. So the
command is run wherever it can be run - by the host helper on Linux, by the
backend itself on macOS and Windows - and everything after that, the reading
and the judging, happens here once.

The judgement is deliberately narrow. Only a handful of attributes say
anything an owner can act on, and every one of them is reported as a count
that is either zero or not:

  5   sectors the disk has already given up on and replaced
  197 sectors it currently cannot read and has not replaced yet
  198 sectors it could not read and could not recover
  199 transfers that arrived damaged - the cable, the enclosure or the power,
      not the disk

Everything else is shown as a number without an opinion attached.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone

#: ATA attribute id -> the name this interface uses for it.
WATCHED = {
    5: "reallocated",
    9: "power_on_hours",
    12: "power_cycles",
    193: "load_cycles",
    194: "temperature",
    196: "reallocated_events",
    197: "pending",
    198: "uncorrectable",
    199: "crc_errors",
}

#: A count above zero on these is worth saying out loud. The value is the
#: level the interface shows it at.
ALARMS = {
    "pending": "danger",
    "uncorrectable": "danger",
    "reallocated": "warn",
    "crc_errors": "warn",
}

#: Above this the disk is hotter than a disk in a cupboard should ever be.
HOT_CELSIUS = 55

#: Where a desktop system might have put smartctl.
CANDIDATES = (
    "smartctl",
    "/usr/local/sbin/smartctl",
    "/opt/homebrew/sbin/smartctl",
    "/usr/sbin/smartctl",
    r"C:\Program Files\smartmontools\bin\smartctl.exe",
    r"C:\Program Files (x86)\smartmontools\bin\smartctl.exe",
)


def find_smartctl() -> str | None:
    for candidate in CANDIDATES:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def run_smartctl(device: str, binary: str | None = None,
                 timeout: float = 60.0) -> dict:
    """Ask one device for its SMART data and hand back smartctl's JSON.

    USB enclosures are the awkward case: some answer straight away, some need
    to be told they are really SATA underneath. Both are tried before giving
    up, because the difference is invisible from the outside.
    """
    binary = binary or find_smartctl()
    if binary is None:
        return {"ok": False, "reason": "smart.no_binary"}

    last = {"ok": False, "reason": "smart.unreadable"}
    for arguments in ([], ["-d", "sat"]):
        command = [binary, "--json=c", "-a", *arguments, device]
        try:
            finished = subprocess.run(command, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "reason": "smart.timeout"}
        except OSError as exc:
            return {"ok": False, "reason": f"smartctl could not be run: {exc}"}

        try:
            data = json.loads(finished.stdout.decode("utf-8", "replace") or "{}")
        except ValueError:
            last = {"ok": False, "reason": "smart.unreadable"}
            continue

        # The exit status is a bit field. The low three bits mean smartctl
        # could not talk to the device at all; everything above that is the
        # disk reporting something, which is exactly what we came for.
        status = int(data.get("smartctl", {}).get("exit_status", 0))
        if status & 0b111 or "ata_smart_attributes" not in data \
                and "nvme_smart_health_information_log" not in data:
            messages = data.get("smartctl", {}).get("messages", [])
            text = "; ".join(m.get("string", "") for m in messages).strip()
            last = {"ok": False, "reason": text or "smart.unsupported"}
            continue
        return {"ok": True, "data": data}
    return last


def interpret(payload: dict) -> dict:
    """Turn smartctl's JSON into the few numbers worth putting on a page."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not payload.get("ok"):
        return {"available": False, "reason": payload.get("reason", "smart.unreadable"),
                "checked_at": now, "readings": {}, "alarms": []}

    data = payload.get("data") or {}
    # Not called "values": a template reaching for .values on a dict gets
    # the method instead of the key, and fails silently.
    readings: dict[str, int] = {}

    for entry in data.get("ata_smart_attributes", {}).get("table", []):
        name = WATCHED.get(int(entry.get("id", 0)))
        if name is not None:
            readings[name] = int((entry.get("raw") or {}).get("value", 0))

    # NVMe keeps the same facts under different names.
    nvme = data.get("nvme_smart_health_information_log")
    if nvme:
        readings.setdefault("power_on_hours", int(nvme.get("power_on_hours", 0)))
        readings.setdefault("power_cycles", int(nvme.get("power_cycles", 0)))
        readings.setdefault("uncorrectable", int(nvme.get("media_errors", 0)))
        readings["spare_percent"] = int(nvme.get("available_spare", 100))
        readings["used_percent"] = int(nvme.get("percentage_used", 0))

    current = (data.get("temperature") or {}).get("current")
    if current is not None:
        readings["temperature"] = int(current)
    hours = (data.get("power_on_time") or {}).get("hours")
    if hours is not None:
        readings.setdefault("power_on_hours", int(hours))

    passed = (data.get("smart_status") or {}).get("passed")

    alarms = []
    if passed is False:
        alarms.append({"key": "smart.alarm.failed", "level": "danger", "count": None})
    for name, level in ALARMS.items():
        count = readings.get(name, 0)
        if count:
            alarms.append({"key": f"smart.alarm.{name}", "level": level, "count": count})
    if readings.get("temperature", 0) >= HOT_CELSIUS:
        alarms.append({"key": "smart.alarm.hot", "level": "warn",
                       "count": readings["temperature"]})
    if readings.get("spare_percent", 100) < 20:
        alarms.append({"key": "smart.alarm.spare", "level": "danger",
                       "count": readings["spare_percent"]})

    return {
        "available": True,
        "reason": None,
        "passed": passed,
        "model": data.get("model_name"),
        "serial": data.get("serial_number"),
        "firmware": data.get("firmware_version"),
        "rotation": (data.get("rotation_rate") or 0) or None,
        "readings": readings,
        "alarms": alarms,
        "checked_at": now,
    }
