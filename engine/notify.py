# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Telling somebody when it matters.

A single webhook rather than an integration with anything in particular: the
URL goes in the settings, AmberSync posts a small JSON object, and whatever
is at the other end decides what to do with it. Home Assistant, ntfy, Gotify,
Slack, a script - they all take a POST.

Sending never blocks a run. A webhook that is slow, wrong or offline costs a
line in the log and nothing else.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from engine import db

TIMEOUT_SECONDS = 10

#: Levels, quietest first. The setting picks the floor.
LEVELS = ("info", "warning", "error")

#: What counts as worth sending, by setting.
THRESHOLD = {"off": None, "errors": "error", "warnings": "warning", "all": "info"}


def enabled() -> bool:
    return bool(db.get_setting("notify_url").strip()) \
        and db.get_setting("notify_level") != "off"


def wanted(level: str) -> bool:
    floor = THRESHOLD.get(db.get_setting("notify_level"), "warning")
    if floor is None:
        return False
    try:
        return LEVELS.index(level) >= LEVELS.index(floor)
    except ValueError:
        return True


def build_payload(level: str, title: str, message: str,
                  set_name: str | None = None, **extra) -> dict:
    return {
        "source": "ambersync",
        "level": level,
        "title": title,
        "message": message,
        "set": set_name,
        **extra,
    }


def post(url: str, payload: dict, headers: dict | None = None) -> tuple[bool, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "AmberSync")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return True, f"{response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, str(exc)


def custom_headers() -> dict:
    raw = db.get_setting("notify_headers").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


def send(level: str, title: str, message: str, set_name: str | None = None,
         **extra) -> None:
    """Fire and forget, in a thread, so nothing ever waits on a webhook."""
    if not enabled() or not wanted(level):
        return
    url = db.get_setting("notify_url").strip()
    payload = build_payload(level, title, message, set_name, **extra)
    headers = custom_headers()

    def deliver() -> None:
        ok, detail = post(url, payload, headers)
        if not ok:
            db.log_event("warning", f"notification failed: {detail}", set_name, "notify")

    threading.Thread(target=deliver, name="ambersync-notify", daemon=True).start()


def send_test(url: str, headers: dict | None = None) -> tuple[bool, str]:
    """Used by the button in the settings - this one does wait for an answer."""
    return post(url, build_payload(
        "info", "AmberSync", "This is a test from AmberSync."), headers)
