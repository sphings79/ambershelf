# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Telling a damaged file from an intact one.

What this does, and why each part is here:

  * **Header against extension.** A JPEG begins FF D8 FF, a PNG with its
    eight-byte signature, an MP4 carries "ftyp" at offset four. Encrypted
    files fail this every time - including the fast kind of ransomware that
    only encrypts the first few hundred kilobytes, because that is exactly
    where the header lives.
  * **Text that is no longer text.** A sidecar or a note whose first bytes
    are not printable is broken, whatever did it.
  * **Ransom notes.** Files whose names read like instructions for paying
    somebody, appearing across many folders at once.
  * **A second extension that means nothing.** photo.jpg.a7f3k2 - generic,
    so it does not go stale the way a list of malware family names would.

What this deliberately does *not* do: measure entropy. JPEG and MP4 are
already compressed and look almost perfectly random, so "looks random"
catches nothing here and would only lend false confidence. Text files are
covered by the printable check instead.

None of this protects against a compromised host. It protects a copy from a
master that is already damaged - the disk that spent an afternoon in an
infected Windows machine.
"""
from __future__ import annotations

import re
from pathlib import Path

#: How much of a file the checks need.
HEADER_BYTES = 512

OK = "ok"
NO_CHECK = "no_check"
HEADER_MISMATCH = "header_mismatch"
TEXT_GARBLED = "text_garbled"
EMPTY = "empty"
UNREADABLE = "unreadable"

#: (offset, magic) pairs. A file passes if any pair matches.
SIGNATURES: dict[str, tuple[tuple[int, bytes], ...]] = {
    "jpg":  ((0, b"\xff\xd8\xff"),),
    "jpeg": ((0, b"\xff\xd8\xff"),),
    "jpe":  ((0, b"\xff\xd8\xff"),),
    "png":  ((0, b"\x89PNG\r\n\x1a\n"),),
    "gif":  ((0, b"GIF87a"), (0, b"GIF89a")),
    "bmp":  ((0, b"BM"),),
    "webp": ((0, b"RIFF"),),
    "tif":  ((0, b"II*\x00"), (0, b"MM\x00*")),
    "tiff": ((0, b"II*\x00"), (0, b"MM\x00*")),
    "heic": ((4, b"ftyp"),),
    "heif": ((4, b"ftyp"),),
    "avif": ((4, b"ftyp"),),
    # Raw formats are almost all TIFF underneath.
    "cr2":  ((0, b"II*\x00"), (0, b"MM\x00*")),
    "cr3":  ((4, b"ftyp"),),
    "nef":  ((0, b"II*\x00"), (0, b"MM\x00*")),
    "arw":  ((0, b"II*\x00"), (0, b"MM\x00*")),
    "orf":  ((0, b"IIRO"), (0, b"IIRS"), (0, b"MMOR")),
    "rw2":  ((0, b"IIU\x00"), (0, b"II*\x00")),
    "dng":  ((0, b"II*\x00"), (0, b"MM\x00*")),
    "raf":  ((0, b"FUJIFILM"),),
    "pef":  ((0, b"II*\x00"), (0, b"MM\x00*")),
    # Video and audio. Older QuickTime files start with an atom, not ftyp.
    "mp4":  ((4, b"ftyp"),),
    "m4v":  ((4, b"ftyp"),),
    "m4a":  ((4, b"ftyp"),),
    "mov":  ((4, b"ftyp"), (4, b"moov"), (4, b"mdat"), (4, b"free"),
             (4, b"skip"), (4, b"wide"), (4, b"pnot")),
    "3gp":  ((4, b"ftyp"),),
    "avi":  ((0, b"RIFF"),),
    "wav":  ((0, b"RIFF"),),
    "mkv":  ((0, b"\x1a\x45\xdf\xa3"),),
    "webm": ((0, b"\x1a\x45\xdf\xa3"),),
    "mts":  ((0, b"\x47"), (0, b"\x00\x00\x01")),
    "mp3":  ((0, b"ID3"), (0, b"\xff\xfb"), (0, b"\xff\xf3"), (0, b"\xff\xf2"),
             (0, b"\xff\xfa"), (0, b"\xff\xe3")),
    "flac": ((0, b"fLaC"),),
    "ogg":  ((0, b"OggS"),),
    # Documents and containers.
    "pdf":  ((0, b"%PDF-"),),
    "zip":  ((0, b"PK\x03\x04"), (0, b"PK\x05\x06"), (0, b"PK\x07\x08")),
    "docx": ((0, b"PK\x03\x04"),),
    "xlsx": ((0, b"PK\x03\x04"),),
    "pptx": ((0, b"PK\x03\x04"),),
    "odt":  ((0, b"PK\x03\x04"),),
    "epub": ((0, b"PK\x03\x04"),),
    "gz":   ((0, b"\x1f\x8b"),),
    "7z":   ((0, b"7z\xbc\xaf\x27\x1c"),),
    "rar":  ((0, b"Rar!"),),
    "doc":  ((0, b"\xd0\xcf\x11\xe0"),),
    "xls":  ((0, b"\xd0\xcf\x11\xe0"),),
    "ppt":  ((0, b"\xd0\xcf\x11\xe0"),),
    "sqlite": ((0, b"SQLite format 3"),),
}

#: Extensions whose content has to read as text.
TEXT_EXTENSIONS = {
    "txt", "csv", "tsv", "log", "md", "xmp", "json", "xml", "html", "htm",
    "srt", "vtt", "ini", "cfg", "conf", "yml", "yaml", "sql", "nfo",
}

#: Filenames that read like a demand rather than a document.
RANSOM_NOTE = re.compile(
    r"(how[\W_]{0,3}to[\W_]{0,3}(decrypt|restore|recover|back)"
    r"|(readme|read[\W_]{0,3}me)[\W_]*.{0,20}(decrypt|restore|recover|ransom|encrypt)"
    r"|(decrypt|recover|restore)[\W_]{0,3}(my[\W_]{0,3})?(file|data|instruction)"
    r"|your[\W_]{0,3}(files|data)[\W_]{0,3}(are|have|were)"
    r"|!{2,}[\W_]*read[\W_]*me"
    r"|attention.{0,10}(your|all)[\W_]{0,3}files)",
    re.IGNORECASE)

#: The handful of second extensions that say it outright.
BLATANT_EXTENSIONS = {
    "locked", "encrypted", "crypt", "crypted", "enc", "cry", "wncry", "wcry",
    "ransom", "pay", "payms", "readme",
}

#: A second extension of this shape carries no meaning and is a bad sign on
#: top of a real one - photo.jpg.a7f3k2 rather than photo.jpg.
RANDOM_LOOKING = re.compile(r"^[a-z0-9]{4,10}$", re.IGNORECASE)

KNOWN_EXTENSIONS = set(SIGNATURES) | TEXT_EXTENSIONS


def extension_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def check_header(name: str, header: bytes) -> str:
    """Does the content match what the name claims? Reads nothing itself."""
    if not header:
        return EMPTY
    extension = extension_of(name)
    signatures = SIGNATURES.get(extension)

    if signatures:
        for offset, magic in signatures:
            if header[offset:offset + len(magic)] == magic:
                return OK
        return HEADER_MISMATCH

    if extension in TEXT_EXTENSIONS:
        sample = header[:HEADER_BYTES]
        try:
            sample.decode("utf-8")
            return OK
        except UnicodeDecodeError:
            pass
        # Not valid UTF-8 - still fine if it reads as plain single-byte text.
        printable = sum(1 for byte in sample
                        if 32 <= byte < 127 or byte in (9, 10, 13) or byte >= 160)
        return OK if printable >= len(sample) * 0.9 else TEXT_GARBLED

    return NO_CHECK


def read_header(path: Path) -> bytes | None:
    try:
        with open(path, "rb", buffering=0) as fh:
            return fh.read(HEADER_BYTES)
    except OSError:
        return None


def check_file(path: Path, name: str | None = None) -> str:
    header = read_header(path)
    if header is None:
        return UNREADABLE
    return check_header(name or path.name, header)


def suspicious_name(name: str) -> str | None:
    """A ransom note, or a second extension that means nothing?"""
    if RANSOM_NOTE.search(name):
        return "ransom_note"

    parts = name.lower().split(".")
    if len(parts) >= 3:
        last, previous = parts[-1], parts[-2]
        if last in BLATANT_EXTENSIONS:
            return "double_extension"
        # A real extension followed by a meaningless one.
        if previous in KNOWN_EXTENSIONS and last not in KNOWN_EXTENSIONS \
                and RANDOM_LOOKING.match(last):
            return "double_extension"
    elif len(parts) == 2 and parts[-1] in BLATANT_EXTENSIONS:
        return "double_extension"
    return None


def describes_damage(health: str) -> bool:
    return health in (HEADER_MISMATCH, TEXT_GARBLED, EMPTY)
