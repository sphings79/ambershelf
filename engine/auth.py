# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""One password, one session table, no dependencies.

Deliberate choices:

  * **scrypt from the standard library**, not argon2. Both are memory-hard;
    argon2 would mean a C extension to keep working inside the macOS and
    Windows bundles, which is a maintenance cost with no benefit for a
    single-user login.
  * **A random password on first start**, written to the log, rather than a
    setup screen. A setup screen on a reachable address belongs to whoever
    finds it first.
  * **Server-side sessions.** The cookie carries nothing but a random token,
    so signing it is unnecessary and logging out takes effect immediately,
    everywhere.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import string
import threading
import time
from datetime import datetime, timedelta, timezone

from engine import db

# Around 32 MB and a few tenths of a second per attempt on ordinary hardware -
# unnoticeable once, ruinous a billion times.
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_LENGTH = 32

#: OpenSSL refuses a scrypt call that wants more than 32 MB unless it is told
#: otherwise, and 128 * N * r is exactly 32 MB here - so without this the
#: hardening we chose scrypt for is what makes it fail. The throttle above
#: keeps the allocation from becoming a way to exhaust memory.
SCRYPT_MAXMEM = 128 * 1024 * 1024

PASSWORD_KEY = "password_hash"

#: Set while the password in use is the one AmberShelf made up. The generated
#: password gets you through the door and no further: until a real one is
#: chosen, every page leads back to choosing it.
MUST_CHANGE_KEY = "password_must_change"

COOKIE_NAME = "ambershelf_session"
TOKEN_BYTES = 32

#: Failed attempts allowed from one address before it has to wait.
MAX_FAILURES = 5
LOCKOUT_SECONDS = 30
FAILURE_WINDOW = 600

_failures: dict[str, list[float]] = {}
_failure_lock = threading.Lock()


# -------------------------------------------------------------- passwords --

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N,
                         r=SCRYPT_R, p=SCRYPT_P, dklen=KEY_LENGTH,
                         maxmem=SCRYPT_MAXMEM)
    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(key).decode("ascii"))


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, key_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(key_b64)
        candidate = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                                   n=int(n), r=int(r), p=int(p),
                                   dklen=len(expected), maxmem=SCRYPT_MAXMEM)
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(candidate, expected)


def password_is_set() -> bool:
    return bool(db.get_setting(PASSWORD_KEY, ""))


def set_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("a password needs at least eight characters")
    db.set_setting(PASSWORD_KEY, hash_password(password))
    db.set_setting(MUST_CHANGE_KEY, "0")


def must_change() -> bool:
    """Is the password in use still the one that was made up?"""
    return db.get_setting(MUST_CHANGE_KEY, "0") == "1"


def check_password(password: str) -> bool:
    stored = db.get_setting(PASSWORD_KEY, "")
    if not stored:
        return False
    return verify_password(password, stored)


def random_password(length: int = 16) -> str:
    # No look-alike characters: this one gets read off a terminal and typed.
    alphabet = "".join(c for c in string.ascii_letters + string.digits
                       if c not in "Il1O0")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def ensure_password() -> str | None:
    """Make one up on first start and hand it back so it can be logged."""
    if password_is_set():
        return None
    password = random_password()
    db.set_setting(PASSWORD_KEY, hash_password(password))
    db.set_setting(MUST_CHANGE_KEY, "1")
    return password


# --------------------------------------------------------------- sessions --

def session_days() -> int:
    try:
        return max(1, db.get_int("session_days"))
    except (ValueError, TypeError):
        return 30


def create_session(address: str | None, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    now = db.now()
    db.execute(
        "INSERT INTO sessions (token, created_at, last_seen_at, address, user_agent) "
        "VALUES (?, ?, ?, ?, ?)",
        (token, now, now, address, (user_agent or "")[:200]))
    prune_sessions()
    return token


def session_valid(token: str | None, touch: bool = True) -> bool:
    if not token:
        return False
    row = db.one("SELECT last_seen_at FROM sessions WHERE token = ?", (token,))
    if row is None:
        return False
    try:
        last_seen = datetime.fromisoformat(row["last_seen_at"])
    except ValueError:
        return False
    if datetime.now(timezone.utc) - last_seen > timedelta(days=session_days()):
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        return False
    if touch:
        db.execute("UPDATE sessions SET last_seen_at = ? WHERE token = ?",
                   (db.now(), token))
    return True


def revoke_session(token: str | None) -> None:
    if token:
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))


def revoke_all(keep: str | None = None) -> int:
    if keep:
        return db.execute("DELETE FROM sessions WHERE token <> ?", (keep,)).rowcount
    return db.execute("DELETE FROM sessions").rowcount


def active_sessions() -> list:
    prune_sessions()
    return db.query("SELECT * FROM sessions ORDER BY last_seen_at DESC")


def prune_sessions() -> int:
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=session_days())).isoformat(timespec="seconds")
    return db.execute("DELETE FROM sessions WHERE last_seen_at < ?", (cutoff,)).rowcount


# --------------------------------------------------------------- throttle --

def locked_for(address: str) -> float:
    """Seconds this address still has to wait, 0 if it may try."""
    with _failure_lock:
        attempts = [t for t in _failures.get(address, [])
                    if time.monotonic() - t < FAILURE_WINDOW]
        _failures[address] = attempts
        if len(attempts) < MAX_FAILURES:
            return 0.0
        waited = time.monotonic() - attempts[-1]
        return max(0.0, LOCKOUT_SECONDS - waited)


def record_failure(address: str) -> None:
    with _failure_lock:
        _failures.setdefault(address, []).append(time.monotonic())


def clear_failures(address: str) -> None:
    with _failure_lock:
        _failures.pop(address, None)
