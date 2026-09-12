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
import re
import sys
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
        ("scan.pdf", b"%PDF-1.7\n%\xe2\xe3", "ok"),
        ("bild.png", b"\x89PNG\r\n\x1a\n\x00\x00", "ok"),
        ("raw.cr2", b"II*\x00\x10\x00\x00\x00CR", "ok"),
        ("fuji.raf", b"FUJIFILMCCD-RAW ", "ok"),
        ("notiz.txt", "Umlaute: \u00e4\u00f6\u00fc".encode(), "ok"),
        ("notiz.txt", bytes(range(0, 200)), "text_garbled"),
        ("unbekannt.xyz", b"\x00\x01\x02", "no_check"),
        ("leer.jpg", b"", "empty"),
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
