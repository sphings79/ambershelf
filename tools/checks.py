#!/usr/bin/env python3
# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""The checks that used to be run by hand before every deploy.

Run from the repository root:  python3 tools/checks.py
"""
from __future__ import annotations

import ast
import compileall
import importlib.util
import io
import os
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("engine", "platforms", "server", "tools")

failures: list[str] = []
notes: list[str] = []


def check(title: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {title}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(title)


def compiles() -> None:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        ok = compileall.compile_dir(str(ROOT), quiet=2, force=True,
                                    rx=re.compile(r"(\.git|__pycache__|data)"))
    check("every python file compiles", bool(ok), buffer.getvalue().strip()[:200])


def load(module_path: Path):
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def translations_match() -> None:
    """Both languages have to carry exactly the same keys."""
    i18n = load(ROOT / "server" / "i18n.py")
    german = set(i18n.STRINGS["de"])
    english = set(i18n.STRINGS["en"])
    difference = sorted(german ^ english)
    check(f"both languages carry the same {len(german)} keys",
          not difference, ", ".join(difference[:6]))


def templates_have_their_keys() -> None:
    """Every t('...') a template uses must exist in both languages."""
    i18n = load(ROOT / "server" / "i18n.py")
    literal = re.compile(r"(?<![a-zA-Z_])t\(\s*'([a-zA-Z0-9_.]+)'")
    dynamic = re.compile(r"(?<![a-zA-Z_])t\(\s*'([a-zA-Z0-9_.]+)'\s*~")

    used: set[str] = set()
    built: set[str] = set()
    for path in (ROOT / "server" / "templates").glob("*.html"):
        text = path.read_text(encoding="utf-8")
        used.update(match.group(1) for match in literal.finditer(text))
        built.update(match.group(1) for match in dynamic.finditer(text))

    # Prefixes the templates assemble at runtime.
    expanded = {
        "role.": ("master", "slave"),
        "job.": ("queued", "running", "paused", "done", "failed", "cancelled"),
        "job.phase.": ("walk", "hash", "check", "scope", "compare", "apply"),
        "findings.kind.": ("header_mismatch", "text_garbled", "empty", "unreadable",
                           "ransom_note", "double_extension", "burst"),
        "settings.notify_level.": ("off", "errors", "warnings", "all"),
        "settings.desktop_mode.": ("local", "remote"),
        "login.": ("title", "password", "submit", "logout", "wrong", "locked", "hint"),
        "first.": ("title", "body", "submit", "hint"),
        "disks.reason.": ("no_filesystem", "unsupported_filesystem"),
        "plan.kind.": ("new", "changed", "renamed", "deleted", "slave_only",
                       "out_of_scope", "unreadable"),
        "plan.state.": ("building", "ready", "blocked", "cancelled", "applied"),
        "run.state.": ("running", "done", "done_with_errors", "failed", "cancelled"),
    }
    for prefix, values in expanded.items():
        for value in values:
            used.add(prefix + value)
            if prefix == "plan.kind.":
                used.add(f"{prefix}{value}.help")
    used -= built

    missing = sorted(key for key in used
                     for language in ("de", "en")
                     if key not in i18n.STRINGS[language])
    check(f"{len(used)} template keys are translated", not missing,
          ", ".join(sorted(set(missing))[:6]))


def engine_stays_platform_blind() -> None:
    """The engine must not learn how disks are mounted."""
    forbidden = re.compile(r"/proc/|ismount|MOUNT_ROOT|diskutil|mount -o|Get-Volume")
    offenders = []
    for path in (ROOT / "engine").glob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden.search(line) and not line.strip().startswith("#"):
                offenders.append(f"{path.name}:{number}")
    check("the engine holds no platform specifics", not offenders,
          ", ".join(offenders[:4]))


def integrity_recognises_files() -> None:
    """The header and name checks, against known good and known bad input.

    These are the cases the whole ransomware story rests on, so they run on
    every push rather than living in my head.
    """
    integrity = load(ROOT / "engine" / "integrity.py")

    headers = [
        ("urlaub.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF", "ok"),
        ("urlaub.jpg", b"ENCRYPTED!!!!!!!\x00\x01\x02", "header_mismatch"),
        ("clip.mp4", b"\x00\x00\x00\x18ftypmp42", "ok"),
        ("clip.mp4", b"Salted__\x8a\x1f\x00\x00\x00\x00", "header_mismatch"),
        ("alt.mov", b"\x00\x00\x00\x14moov\x00\x00", "ok"),
        # AVCHD camcorders put a four-byte timestamp in front of every
        # packet, so the 0x47 sync byte sits at four. 709 perfectly good
        # holiday videos were called damaged over this.
        ("20090422.MTS", b"\x00\x00\x00\x00\x47\x40\x00\x10\x00\x00\xb0\x11", "ok"),
        ("plain.mts", b"\x47\x40\x00\x10\x00\x00\xb0\x11\x00\x00\x00\x00", "ok"),
        ("clip.m2ts", b"\x00\x00\x00\x60\x47\x40\x00\x10\x00\x00\xb0\x11", "ok"),
        ("fake.mts", b"Salted__\x8a\x1f\x00\x00\x00\x00", "header_mismatch"),
        ("scan.pdf", b"%PDF-1.7\n%\xe2\xe3", "ok"),
        ("bild.png", b"\x89PNG\r\n\x1a\n\x00\x00", "ok"),
        ("raw.cr2", b"II*\x00\x10\x00\x00\x00CR", "ok"),
        ("fuji.raf", b"FUJIFILMCCD-RAW ", "ok"),
        ("notiz.txt", "Umlaute: \u00e4\u00f6\u00fc".encode(), "ok"),
        ("notiz.txt", bytes(range(0, 200)), "text_garbled"),
        ("unbekannt.xyz", b"\x00\x01\x02", "no_check"),
        ("leer.jpg", b"", "empty"),
        # Nero writes its cover images with a .bmp extension whatever they
        # really are. Intact, only misnamed - and never damage.
        ("cover_1.bmp", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "wrong_extension"),
        ("cover_11.bmp", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01", "wrong_extension"),
        # Encrypted content matches nothing at all and stays a mismatch.
        ("urlaub.jpg", b"\x00\x00\x00\x87\x02x\x9c\xe3b``f\xe0vI,", "header_mismatch"),
        # macOS sidecars borrow the name of the file they belong to.
        ("._urlaub.jpg", b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X", "no_check"),
        ("._notreally.jpg", b"ENCRYPTED!!!!!!!\x00\x01\x02", "header_mismatch"),
        # BitLocker recovery keys are UTF-16, which is text, not garbage.
        ("key.TXT", "\ufeffBitLocker\u2011Wiederherstellungsschl\u00fcssel".encode("utf-16-le"),
         "ok"),
        ("key.txt", "\ufeffPasswort".encode("utf-16-be"), "ok"),
        ("kaputt.txt", b"\xff\xfe" + b"\x00" * 200, "text_garbled"),
        ("steuerzeichen.txt", b"\xff\xfe" + b"\x01\x00\x02\x00\x03\x00" * 30,
         "text_garbled"),
        # Valid UTF-8 is not the same as readable - a run of NUL decodes fine.
        ("genullt.txt", b"\x00" * 300, "text_garbled"),
    ]
    names = [
        ("HOW_TO_DECRYPT.txt", "ransom_note"),
        ("!!!README!!!.hta", "ransom_note"),
        ("RESTORE-MY-FILES.txt", "ransom_note"),
        ("YOUR FILES ARE ENCRYPTED.html", "ransom_note"),
        ("urlaub.jpg.a7f3k2", "double_extension"),
        ("urlaub.jpg.locked", "double_extension"),
        # Real archives are full of names that must not trip this.
        ("IMG_0001.jpg", None),
        ("\u00dcml\u00e4ute und \u00c4rger 01.dat", None),
        ("punkt.im.namen.02.csv", None),
        ("! Fotos ! 2019.zip", None),
        ("readme.txt", None),
    ]

    wrong = []
    for name, header, expected in headers:
        got = integrity.check_header(name, header)
        if got != expected:
            wrong.append(f"{name}: {got} != {expected}")
    for name, expected in names:
        got = integrity.suspicious_name(name)
        if got != expected:
            wrong.append(f"{name}: {got} != {expected}")

    check(f"the integrity check judges {len(headers) + len(names)} known cases",
          not wrong, "; ".join(wrong[:3]))


def authentication_holds() -> None:
    """The password, the sessions and the lockout, against real input."""
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("AMBERSHELF_DATA_DIR",
                          str(Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "ambershelf-checks"))
    from engine import auth, config, db

    db.initialise()
    wrong = []

    stored = auth.hash_password("correct horse battery")
    if not auth.verify_password("correct horse battery", stored):
        wrong.append("the right password was rejected")
    if auth.verify_password("correct horse batterz", stored):
        wrong.append("a wrong password was accepted")
    if auth.verify_password("", stored):
        wrong.append("an empty password was accepted")
    if auth.verify_password("x", "not-a-hash"):
        wrong.append("a malformed hash was accepted")
    if auth.hash_password("same") == auth.hash_password("same"):
        wrong.append("two hashes of one password are identical - no salt")
    check("passwords hash and verify", not wrong, "; ".join(wrong[:2]))

    try:
        auth.set_password("short")
        too_short_refused = False
    except ValueError:
        too_short_refused = True
    check("a password under eight characters is refused", too_short_refused)

    generated = auth.random_password()
    check("the generated password is long enough and unambiguous",
          len(generated) >= 16 and not (set(generated) & set("Il1O0")))

    token = auth.create_session("192.0.2.1", "checks")
    other = auth.create_session("192.0.2.2", "checks")
    problems = []
    if not auth.session_valid(token):
        problems.append("a fresh session was not accepted")
    if auth.session_valid("nonsense"):
        problems.append("an invented token was accepted")
    if auth.session_valid(None):
        problems.append("no token at all was accepted")
    auth.revoke_all(keep=token)
    if auth.session_valid(other):
        problems.append("a revoked session still works")
    if not auth.session_valid(token):
        problems.append("the kept session was revoked as well")
    auth.revoke_session(token)
    if auth.session_valid(token):
        problems.append("a session survived being revoked")
    check("sessions are created, kept and revoked", not problems, "; ".join(problems[:2]))

    # The generated password must open the door and nothing else.
    db.set_setting(auth.MUST_CHANGE_KEY, "0")
    db.set_setting(auth.PASSWORD_KEY, "")
    generated_again = auth.ensure_password()
    flagged = auth.must_change()
    auth.set_password("a proper password")
    cleared = not auth.must_change()
    check("a generated password has to be replaced before anything else",
          bool(generated_again) and flagged and cleared)

    address = "198.51.100.7"
    auth.clear_failures(address)
    locked_early = auth.locked_for(address) > 0
    for _ in range(auth.MAX_FAILURES):
        auth.record_failure(address)
    locked_after = auth.locked_for(address) > 0
    auth.clear_failures(address)
    freed = auth.locked_for(address) == 0
    check("too many failures lock an address out",
          not locked_early and locked_after and freed)

    # The one that must never be wrong: an unknown bind address means a login.
    original = config.BIND_HOST
    cases = [("127.0.0.1", False), ("localhost", False), ("::1", False),
             ("0.0.0.0", True), ("192.168.1.5", True), ("", True)]
    bad = []
    for host, expected in cases:
        config.BIND_HOST = host
        if config.login_required() != expected:
            bad.append(f"{host or '(unset)'} -> {not expected}")
    config.BIND_HOST = original
    check("a login is required unless the server is loopback only",
          not bad, ", ".join(bad))


def system_partitions_are_recognised() -> None:
    """Never offer the machine's own filesystem as a backup disk."""
    helper = load(ROOT / "docker" / "helper" / "ambershelf-helper.py")
    cases = [
        ({"fs_type": "ext4", "mountpoint": "/"}, True),
        ({"fs_type": "ext4", "mountpoint": "/home"}, True),
        ({"fs_type": "vfat", "mountpoint": "/boot/efi"}, True),
        ({"fs_type": "swap", "mountpoint": None}, True),
        ({"fs_type": "crypto_LUKS", "mountpoint": None}, True),
        ({"fs_type": "lvm2_member", "mountpoint": None}, True),
        # Unmounted external disks and our own mounts are fine.
        ({"fs_type": "exfat", "mountpoint": None}, False),
        ({"fs_type": "ntfs", "mountpoint": "/mnt/ambershelf/set/master"}, False),
        ({"fs_type": "exfat", "mountpoint": "/media/usb"}, False),
        ({"fs_type": "ext4", "mountpoint": "/run/media/dennis/backup"}, False),
    ]
    wrong = [f"{c['fs_type']} at {c['mountpoint']}"
             for c, expected in cases
             if helper.is_system_partition(c) is not expected]
    check(f"the {len(cases)} system-partition cases are judged correctly",
          not wrong, "; ".join(wrong[:3]))


def demotion_is_the_only_way_out_of_a_master() -> None:
    """A master may be given up, but never quietly turned into a copy.

    This is the rule the whole read-only guarantee rests on, so it is checked
    rather than trusted: registering a retired disk as a copy is refused,
    demoting it clears the retirement, and a mounted master is refused.
    """
    helper = load(ROOT / "docker" / "helper" / "ambershelf-helper.py")
    uuid = "8A87-5E2B"

    with tempfile.TemporaryDirectory() as folder:
        helper.CONFIG_PATH = Path(folder) / "disks.conf"
        helper.save_config({"version": 1, "retired_masters": [uuid], "disks": [
            {"fs_uuid": uuid, "role": "master", "set_name": "fotoarchiv",
             "display_name": "Master", "serial": "x", "label": None, "size": 1,
             "fs_type": "exfat", "model": None},
        ]})
        helper.is_mounted = lambda _: False
        helper.log = lambda _message: None
        problems = []

        try:
            helper.handle_register({"fs_uuid": uuid, "role": "slave",
                                    "set_name": "fotoarchiv",
                                    "display_name": "Kopie"})
            problems.append("a retired master could be registered as a copy")
        except RuntimeError:
            pass

        helper.is_mounted = lambda _: True
        try:
            helper.handle_demote({"fs_uuid": uuid})
            problems.append("a mounted master could be demoted")
        except RuntimeError:
            pass

        helper.is_mounted = lambda _: False
        helper.handle_demote({"fs_uuid": uuid})
        config = helper.load_config()
        if config["disks"]:
            problems.append("the registration survived the demotion")
        if uuid in helper.retired_masters(config):
            problems.append("the disk stayed on the retired list")

        try:
            helper.handle_demote({"fs_uuid": "1111-2222"})
            problems.append("an unknown disk could be demoted")
        except RuntimeError:
            pass

        # The host owner may close this door entirely.
        helper.save_config({"version": 1, "allow_demote": False,
                            "retired_masters": [uuid], "disks": []})
        if helper.handle({"cmd": "ping"}).get("allow_demote") is not False:
            problems.append("the switch is not reported to the container")
        try:
            helper.handle_demote({"fs_uuid": uuid})
            problems.append("demoting worked although the switch is off")
        except RuntimeError:
            pass
        if uuid not in helper.retired_masters(helper.load_config()):
            problems.append("the refused demotion still cleared the retirement")

    check("a master can be given up but never rewritten into a copy",
          not problems, "; ".join(problems))


def a_restart_closes_what_it_interrupted() -> None:
    """Nothing may keep claiming to be running after the process is gone.

    "running" is the one state that tells a user to wait, so a row left in
    it by a crash or a restart is worse than a wrong number.
    """
    from engine import db

    db.initialise()
    # This check owns these two tables for its duration.
    for table in ("run_items", "runs", "scans", "files"):
        db.execute(f"DELETE FROM {table}")
    db.execute("DELETE FROM disks WHERE fs_uuid = 'CHECK-ONLY'")
    disk_id = db.execute(
        "INSERT INTO disks (fs_uuid, set_name, role, display_name, size_bytes, "
        "registered_at) VALUES ('CHECK-ONLY', 'checks', 'master', 'M', 0, ?)",
        ("2026-01-01T00:00:00+00:00",)).lastrowid

    for state in ("running", "paused", "queued", "done"):
        db.execute("INSERT INTO runs (set_name, started_at, state) VALUES (?, ?, ?)",
                   ("checks", "2026-01-01T00:00:00+00:00", state))
        db.execute("INSERT INTO scans (disk_id, set_name, started_at, state) "
                   "VALUES (?, ?, ?, ?)",
                   (disk_id, "checks", "2026-01-01T00:00:00+00:00", state))

    closed = db.close_interrupted()
    problems = []
    if closed.get("runs") != 3 or closed.get("scans") != 3:
        problems.append(f"closed {closed}, expected three of each")

    for table in ("runs", "scans"):
        left = db.scalar(f"SELECT COUNT(*) FROM {table} WHERE state IN "
                         "('running', 'paused', 'queued')", (), 0)
        if left:
            problems.append(f"{left} row(s) in {table} still claim to be running")
        if db.scalar(f"SELECT COUNT(*) FROM {table} WHERE state = 'done'", (), 0) != 1:
            problems.append(f"a finished {table} row was touched")
        if db.scalar(f"SELECT COUNT(*) FROM {table} WHERE state = 'interrupted' "
                     "AND finished_at IS NULL", (), 0):
            problems.append(f"an interrupted {table} row has no end time")

    # Doing it twice has to be as harmless as doing it once.
    if db.close_interrupted():
        problems.append("a second pass found something to close")

    for table in ("run_items", "runs", "scans", "files"):
        db.execute(f"DELETE FROM {table}")
    db.execute("DELETE FROM disks WHERE fs_uuid = 'CHECK-ONLY'")

    check("a restart closes what it interrupted", not problems, "; ".join(problems[:3]))


def a_message_is_shown_once_and_then_gone() -> None:
    """A message belongs to one page view, not to a URL.

    In a query parameter it came back on every reload as if it had just
    happened, and it put disk names and paths into the browser history and
    every proxy log on the way.
    """
    sys.path.insert(0, str(ROOT))
    try:
        from server import main
    except ImportError:
        notes.append("fastapi is missing - the message check was skipped")
        return

    class Request:
        def __init__(self, cookies=None):
            self.cookies = cookies or {}
            self.headers = {}
            self.url = type("U", (), {"scheme": "http"})()

    problems = []
    response = main.flash(Request(), "/disks", "forget.done", "ok")

    if response.headers.get("location") != "/disks":
        problems.append(f"the address carries the message: "
                        f"{response.headers.get('location')}")
    cookie = response.headers.get("set-cookie", "")
    lowered = cookie.lower()
    if main.FLASH_COOKIE not in cookie:
        problems.append("no handle was handed out")
    if "httponly" not in lowered or "samesite=lax" not in lowered:
        problems.append(f"the handle is not protected: {cookie}")
    if "forget.done" in cookie:
        problems.append("the message itself is in the cookie")

    handle = cookie.split("=", 1)[1].split(";", 1)[0]
    first = main.take_flash(Request({main.FLASH_COOKIE: handle}))
    if first != ("forget.done", "ok"):
        problems.append(f"the message did not arrive: {first}")
    second = main.take_flash(Request({main.FLASH_COOKIE: handle}))
    if second != (None, "info"):
        problems.append(f"the message came a second time: {second}")
    if main.take_flash(Request()) != (None, "info"):
        problems.append("a reader without a handle was given a message")

    # Nothing may pile up: a handle nobody ever redeems has to age out.
    main.flash(Request(), "/", "never.read", "ok")
    with main._flash_lock:
        for key in list(main._flashes):
            message, level, _ = main._flashes[key]
            main._flashes[key] = (message, level, 0.0)
    main.take_flash(Request({main.FLASH_COOKIE: "nonsense"}))
    if main._flashes:
        problems.append(f"{len(main._flashes)} stale message(s) were kept")

    check("a message is shown once and then gone", not problems,
          "; ".join(problems[:3]))


def corrected_rules_drop_their_verdicts() -> None:
    """A corrected signature has to reach the files already judged by the old one."""
    from engine import db

    db.initialise()
    db.execute("DELETE FROM findings WHERE set_name = 'checks'")
    db.execute("DELETE FROM disks WHERE fs_uuid = 'CHECK-ONLY'")
    disk_id = db.execute(
        "INSERT INTO disks (fs_uuid, set_name, role, display_name, size_bytes, "
        "registered_at) VALUES ('CHECK-ONLY', 'checks', 'master', 'M', 0, ?)",
        ("2026-01-01T00:00:00+00:00",)).lastrowid
    for path, health in (("a.mts", "header_mismatch"), ("b.jpg", "ok"),
                         ("c.txt", "text_garbled")):
        db.execute("INSERT INTO files (disk_id, path, size, mtime, health) "
                   "VALUES (?, ?, 1, 0, ?)", (disk_id, path, health))
    for kind in ("header_mismatch", "ransom_note"):
        db.record_finding("checks", kind, "a.mts", disk_id, None)

    db.set_setting(db.RULES_VERSION_KEY, "1")
    problems = []
    if db.forget_verdicts_on_new_rules(2) != 3:
        problems.append("not every verdict was dropped")
    if db.scalar("SELECT COUNT(*) FROM files WHERE disk_id = ? AND health IS NOT NULL",
                 (disk_id,), 0):
        problems.append("a verdict survived the rule change")
    kinds = {r["kind"] for r in db.query(
        "SELECT kind FROM findings WHERE set_name = 'checks'")}
    if "header_mismatch" in kinds:
        problems.append("a finding from the old rules is still there")
    if "ransom_note" not in kinds:
        # That one comes from the file's name, which the rules never touched.
        problems.append("a name-based finding was thrown away with the rest")
    if db.forget_verdicts_on_new_rules(2) != 0:
        problems.append("the same version dropped verdicts a second time")

    db.execute("DELETE FROM findings WHERE set_name = 'checks'")
    db.execute("DELETE FROM files WHERE disk_id = ?", (disk_id,))
    db.execute("DELETE FROM disks WHERE fs_uuid = 'CHECK-ONLY'")

    check("a corrected signature reaches the files already judged",
          not problems, "; ".join(problems[:3]))


def smart_values_are_judged() -> None:
    """The numbers only help if the right ones raise their hand.

    The cases are taken from real disks: a healthy one, one whose media is
    fine but whose cable is not, and one that is losing sectors.
    """
    from platforms import smart

    def ata(pairs: dict, passed: bool = True) -> dict:
        return {"ok": True, "data": {
            "smart_status": {"passed": passed},
            "ata_smart_attributes": {"table": [
                {"id": i, "raw": {"value": v}} for i, v in pairs.items()]},
        }}

    healthy = {5: 0, 9: 1308, 194: 37, 197: 0, 198: 0, 199: 0}
    cable = {5: 0, 9: 16876, 194: 39, 197: 0, 198: 0, 199: 1}
    dying = {5: 24, 9: 40000, 194: 58, 197: 8, 198: 3, 199: 0}

    def keys(report):
        return {a["key"] for a in report["alarms"]}

    problems = []
    report = smart.interpret(ata(healthy))
    if report["alarms"]:
        problems.append(f"a healthy disk raised {keys(report)}")
    if report["readings"].get("power_on_hours") != 1308:
        problems.append("power-on hours were not read")

    report = smart.interpret(ata(cable))
    if keys(report) != {"smart.alarm.crc_errors"}:
        problems.append(f"the cable case gave {keys(report)}")
    if any(a["level"] == "danger" for a in report["alarms"]):
        problems.append("a transfer error was called serious")

    report = smart.interpret(ata(dying))
    expected = {"smart.alarm.pending", "smart.alarm.uncorrectable",
                "smart.alarm.reallocated", "smart.alarm.hot"}
    if keys(report) != expected:
        problems.append(f"the failing case gave {keys(report)}")
    if not any(a["level"] == "danger" for a in report["alarms"]):
        problems.append("unreadable sectors were not called serious")

    report = smart.interpret(ata(healthy, passed=False))
    if "smart.alarm.failed" not in keys(report):
        problems.append("a disk declaring itself failed was not reported")

    # No answer is a state of its own, never silently "fine".
    report = smart.interpret({"ok": False, "reason": "smart.unsupported"})
    if report["available"] or report["reason"] != "smart.unsupported":
        problems.append("a disk that cannot be asked was not reported as such")

    check("SMART values are judged the way the disks meant them",
          not problems, "; ".join(problems[:3]))


def names_are_only_as_restricted_as_a_path() -> None:
    """A disk name becomes a folder - that is the only reason to restrict it.

    Real archives are called "! Fotos !" and live on a disk somebody named
    "Größe". A tool that refuses those makes its user work around it.
    """
    helper = load(ROOT / "docker" / "helper" / "ambershelf-helper.py")

    allowed = ["Fotoarchiv", "Kopie 1", "Größe", "Müller", "Fotos & Videos",
               "4 TB (extern)", "! Fotos !", "Fotos+Videos", "Kopie #1",
               "Sicherung!", "2019-2024", "a"]
    refused = ["Archiv/2019", "back\\slash", ".", "..", "", "   ", "x" * 64,
               "with\ttab", "with\nnewline"]

    wrong = []
    for name in allowed:
        try:
            helper.require_name(name, "name")
        except Exception as exc:                              # noqa: BLE001
            wrong.append(f"{name!r} refused: {exc}")
    for name in refused:
        try:
            helper.require_name(name, "name")
            wrong.append(f"{name!r} was accepted")
        except Exception:                                     # noqa: BLE001,S110
            pass

    # Surrounding spaces are trimmed rather than refused.
    if helper.require_name("  Fotoarchiv  ", "name") != "Fotoarchiv":
        wrong.append("surrounding spaces were not trimmed")

    check(f"names allow everything a folder can hold ({len(allowed)} yes, "
          f"{len(refused)} no)", not wrong, "; ".join(wrong[:3]))


def imports_resolve() -> None:
    sys.path.insert(0, str(ROOT))
    try:
        import platforms                                    # noqa: F401
        from engine import compare, config, db, fsutil, jobs, planner, scanner  # noqa: F401
        from server import i18n                             # noqa: F401
        check("every package imports", True)
    except Exception as exc:                                # noqa: BLE001
        check("every package imports", False, f"{type(exc).__name__}: {exc}")


def application_answers() -> None:
    """Start the application in-process and ask it how it is."""
    sys.path.insert(0, str(ROOT))
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        notes.append("fastapi.testclient needs httpx - smoke test skipped")
        return
    try:
        from server.main import app
        with TestClient(app) as client:
            health = client.get("/healthz")
            pages = {path: client.get(path).status_code
                     for path in ("/", "/disks", "/events", "/settings")}
        ok = health.status_code == 200 and all(code == 200 for code in pages.values())
        check("the application starts and serves its pages", ok,
              f"health={health.status_code} " +
              " ".join(f"{p}={c}" for p, c in pages.items()))
    except Exception as exc:                                # noqa: BLE001
        check("the application starts and serves its pages", False,
              f"{type(exc).__name__}: {exc}")


def no_unused_imports() -> None:
    offenders = []
    for package in PACKAGES:
        for path in (ROOT / package).glob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update((a.asname or a.name).split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.update(a.asname or a.name for a in node.names
                                    if a.name != "annotations")
            body = "\n".join(line for line in source.splitlines()
                             if not line.startswith(("import ", "from ")))
            words = set(re.findall(r"\b\w+\b", body))
            for name in sorted(imported - words):
                offenders.append(f"{package}/{path.name}: {name}")
    check("no unused imports", not offenders, ", ".join(offenders[:4]))


def main() -> int:
    print("AmberShelf checks\n")
    compiles()
    imports_resolve()
    integrity_recognises_files()
    authentication_holds()
    system_partitions_are_recognised()
    demotion_is_the_only_way_out_of_a_master()
    smart_values_are_judged()
    a_restart_closes_what_it_interrupted()
    corrected_rules_drop_their_verdicts()
    a_message_is_shown_once_and_then_gone()
    names_are_only_as_restricted_as_a_path()
    translations_match()
    templates_have_their_keys()
    engine_stays_platform_blind()
    no_unused_imports()
    application_answers()

    for note in notes:
        print(f"  NOTE  {note}")
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
