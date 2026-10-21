# PyInstaller spec for CIRIS Agent on Windows.
#
# Produces a single ciris-agent.exe (one-folder mode, NOT one-file) bundled
# alongside its dependencies in `dist/ciris-agent/`. One-folder mode is
# deliberate: one-file mode unpacks to %TEMP% on every run (slow startup,
# AV false positives, breaks the relative paths the launcher uses to find
# the desktop JAR / native libs / accord text).
#
# Entry point: `ciris_engine.cli:main` — the same console_script setup.py
# wires up. Starts the API server on 8080 by default and launches the
# Compose desktop app via the `desktop_launcher` wrapper.
#
# Build:
#     cd installers\windows
#     pyinstaller ciris-agent.spec --noconfirm
#
# The Inno Setup wrapper (ciris-installer.iss) packages dist/ciris-agent/
# plus the trimmed JRE and the desktop JAR into a single .exe installer.

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# When pyinstaller invokes this spec, __file__ is not set in the exec scope.
# Resolve relative to the cwd (which `pyinstaller .../ciris-agent.spec`
# leaves at the spec file's directory).
HERE = Path.cwd().resolve()
REPO_ROOT = HERE.parent.parent  # installers/windows/ → repo root

block_cipher = None

# ---------------------------------------------------------------------------
# Data files: every non-Python resource ciris_engine reads at runtime.
# Mirrors setup.py's package_data — keep in sync. PyInstaller copies these
# into the bundle relative to the destination paths below.
# ---------------------------------------------------------------------------
datas = []
datas += collect_data_files("ciris_engine", includes=[
    "data/*.txt",
    "data/localized/*.json",
    "data/localized/*.txt",
    "data/localized/*.md",
    "data/geo/*.db",
    "config/*.json",
    "ciris_templates/*.yaml",
    "logic/dma/prompts/*.yml",
    "logic/dma/prompts/localized/*/*.yml",
    "logic/persistence/migrations/sqlite/*.sql",
    "logic/persistence/migrations/postgres/*.sql",
])
# Localization strings live OUTSIDE ciris_engine in the source tree but are
# copied into ciris_engine/data/localized at build time by the localization
# loader. PyInstaller doesn't run that copy step, so include the source dir
# directly under the same destination path the loader expects.
loc_src = REPO_ROOT / "localization"
if loc_src.is_dir():
    datas += [(str(p), "ciris_engine/data/localized") for p in loc_src.glob("*.json")]

# ---------------------------------------------------------------------------
# Hidden imports: things PyInstaller's static analyzer misses.
# Pydantic v2 + instructor + openai are notorious for dynamic imports.
# When `ciris-agent.exe` crashes with `ModuleNotFoundError` at runtime, add
# the missing module here. Don't try to be minimal — generosity is cheap.
# ---------------------------------------------------------------------------
hiddenimports = []
hiddenimports += collect_submodules("ciris_engine")
hiddenimports += collect_submodules("ciris_adapters")
hiddenimports += collect_submodules("pydantic")
hiddenimports += collect_submodules("pydantic_core")
hiddenimports += collect_submodules("instructor")
hiddenimports += collect_submodules("openai")
hiddenimports += collect_submodules("anthropic")
hiddenimports += [
    # Pydantic v2 rust core — sometimes missed even with collect_submodules
    "pydantic_core._pydantic_core",
    # Discord adapter
    "discord",
    # SQLAlchemy + sqlite/postgres drivers
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.postgresql",
    "aiosqlite",
    "psycopg2",
    # FastAPI / starlette / uvicorn fragments
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    # httpx async transport
    "httpx._transports.default",
]

a = Analysis(
    [str(REPO_ROOT / "main.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Excluded modules: PyInstaller pulls these in transitively but they're
    # heavyweight (~50 MB) and not used by the agent. Trim them to keep the
    # installer under ~200 MB.
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "numpy.tests",
        "pandas",
        "PIL.ImageTk",
        # google-generativeai pulls grpc which pulls protobuf-compiled stubs
        # we never invoke. Keep google.genai / google.api_core for the
        # google-genai SDK (which IS used).
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ciris-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX compression triggers Windows Defender false positives
    console=True,  # CIRIS prints rich startup output; users want to see it
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: drop a CIRIS .ico here once branding is finalized
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ciris-agent",
)
