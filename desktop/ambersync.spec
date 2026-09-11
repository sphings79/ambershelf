# AmberSync - AGPL-3.0-or-later
# PyInstaller build for the macOS and Windows applications.
#
# One directory rather than one file: a single-file build unpacks itself into
# a temporary folder on every start, which for an application that walks
# disks for hours is a waste with no upside.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent

datas = [
    (str(ROOT / "server" / "templates"), "server/templates"),
    (str(ROOT / "server" / "static"), "server/static"),
]

hidden = [
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    "engine.apply", "engine.compare", "engine.integrity", "engine.notify",
    "engine.planner", "engine.scanner",
    "platforms.macos", "platforms.windows", "platforms.linux",
]

analysis = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "test", "unittest", "pydoc_data"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    exclude_binaries=True,
    name="AmberSync",
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="AmberSync",
)

if sys.platform == "darwin":
    app = BUNDLE(
        collection,
        name="AmberSync.app",
        icon=None,
        bundle_identifier="de.dennis-arning.ambersync",
        info_plist={
            "CFBundleName": "AmberSync",
            "CFBundleDisplayName": "AmberSync",
            "CFBundleShortVersionString": "0.6.0",
            "CFBundleVersion": "0.6.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            # Reading an external disk needs the user's permission from
            # Ventura onwards, and macOS shows this sentence when it asks.
            "NSRemovableVolumesUsageDescription":
                "AmberSync reads your master disk and writes to the copies you "
                "registered.",
            "NSDesktopFolderUsageDescription":
                "AmberSync only touches the disks you registered.",
        },
    )
