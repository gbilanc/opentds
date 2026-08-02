# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for OpenTDS — Open Tactical Dynamic Stage Generator.

Build:
    pyinstaller opentds.spec

Test:
    dist/opentds/opentds  (Linux/macOS)
    dist\opentds\opentds.exe  (Windows)
"""
import sys
from pathlib import Path

# ── Metadata ────────────────────────────────────────────────────────────────

APP_NAME = "OpenTDS"
APP_VERSION = "0.1.0"
APP_DESCRIPTION = "Open Tactical Dynamic Stage Generator for IPSC practical shooting"
AUTHOR = "opentds-dev"

# ── Paths ───────────────────────────────────────────────────────────────────

PROJECT_DIR = Path(__file__).parent
RESOURCES_DIR = PROJECT_DIR / "resources"
UI_RESOURCES_DIR = PROJECT_DIR / "ui" / "resources"

# ── Data files to bundle ────────────────────────────────────────────────────

# SVG target images
target_svgs = list((RESOURCES_DIR / "targets").glob("*.svg"))
target_pngs = list((RESOURCES_DIR / "targets").glob("*.png"))

# Predefined stages
predefined_stages = list((RESOURCES_DIR / "stages").glob("*.opentds"))

# QSS theme files
qss_files = list((UI_RESOURCES_DIR / "styles").glob("*.qss"))

# Build datas list for PyInstaller
datas = []
for f in target_svgs + target_pngs:
    datas.append((str(f), "resources/targets"))
for f in predefined_stages:
    datas.append((str(f), "resources/stages"))
for f in qss_files:
    datas.append((str(f), "ui/resources/styles"))

# ── Hidden imports (auto-detected may miss some) ────────────────────────────

hidden_imports = [
    # PySide6 submodules
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtSvg",
    "PySide6.QtPrintSupport",
    # Shapely
    "shapely",
    "shapely.geometry",
    "shapely.ops",
    "shapely.affinity",
    "shapely.algorithms",
    # Core modules
    "core.models",
    "core.constants",
    "core.geometry",
    "core.collision",
    "core.generator",
    "core.ipsc_rules",
    "core.scoring",
    "core.shapes",
    "core.placement",
    "core.visibility",
    "core.repair",
    "core.path",
    # Services
    "services.serializer",
    "services.exporter",
    "services.library",
    # UI
    "ui.main_window",
    "ui.theme",
    "ui.editor.stage_scene",
    "ui.editor.stage_view",
    "ui.editor.property_dock",
    "ui.editor.generator_panel",
    "ui.editor.stage_info",
    "ui.editor.target_images",
    "ui.editor.path_editor",
    "ui.dialogs.target_config_dialog",
    "ui.dialogs.library_dialog",
    "ui.workers.generator_worker",
]

# ── Excludes (reduce bundle size) ───────────────────────────────────────────

excludes = [
    "tkinter",
    "matplotlib",
    "PIL",
    "cv2",
    "notebook",
    "ipython",
    "jupyter",
    "pandas",
    "numpy",
    "scipy",
    "PyQt5",
    "PyQt6",
]

# ── Block cipher (optional, for obfuscation) ────────────────────────────────
# block_cipher = None

# ── Analysis ─────────────────────────────────────────────────────────────────

a = Analysis(
    [str(PROJECT_DIR / "main.py")],
    pathex=[str(PROJECT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    # block_cipher=block_cipher,
)

# ── Pyz (bytecode archive) ──────────────────────────────────────────────────

pyz = PYZ(a.pure, a.zipped_data)

# ── Executable ──────────────────────────────────────────────────────────────

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,         # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(RESOURCES_DIR / "icon.png") if (RESOURCES_DIR / "icon.png").exists() else None,
)

# ── Bundle (one-directory deployment) ───────────────────────────────────────

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

# ── macOS .app bundle ───────────────────────────────────────────────────────

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=str(RESOURCES_DIR / "icon.icns") if (RESOURCES_DIR / "icon.icns").exists() else None,
    bundle_identifier="dev.opentds.app",
    info_plist={
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    },
)
