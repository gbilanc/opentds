#!/usr/bin/env python3
"""
Build script for OpenTDS — creates standalone executables via PyInstaller.

Usage:
    # Build for current platform
    python scripts/build.py

    # Build with verbose output
    python scripts/build.py --verbose

    # Clean build (remove previous build artifacts)
    python scripts/build.py --clean

    # Build macOS .app bundle
    python scripts/build.py --app

Requires PyInstaller: pip install pyinstaller
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SPEC_FILE = PROJECT_DIR / "opentds.spec"
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"


def main():
    parser = argparse.ArgumentParser(description="Build OpenTDS standalone executable")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument(
        "--clean", action="store_true", help="Clean build artifacts before building"
    )
    parser.add_argument("--app", action="store_true", help="Build macOS .app bundle")
    parser.add_argument(
        "--onefile", action="store_true", help="Build single-file executable (experimental)"
    )
    args = parser.parse_args()

    # ── Check prerequisites ─────────────────────────────────────────────
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("❌ PyInstaller non installato. Installa con:")
        print("   pip install pyinstaller")
        print("   oppure: uv sync --group dev")
        sys.exit(1)

    # ── Clean ───────────────────────────────────────────────────────────
    if args.clean:
        print("🧹 Pulizia build precedente...")
        for d in [DIST_DIR, BUILD_DIR]:
            if d.exists():
                shutil.rmtree(d)
                print(f"   Rimosso: {d}")
        # Remove .spec cache
        spec_cache = PROJECT_DIR / "__pycache__"
        if spec_cache.exists():
            shutil.rmtree(spec_cache)

        pycache_dirs = list(PROJECT_DIR.rglob("__pycache__"))
        for d in pycache_dirs:
            if d.exists() and ".venv" not in str(d):
                shutil.rmtree(d)
        print("✅ Pulizia completata")

    # ── Build ───────────────────────────────────────────────────────────
    if not SPEC_FILE.exists():
        print(f"❌ Spec file non trovato: {SPEC_FILE}")
        sys.exit(1)

    print(f"🔨 Build OpenTDS v{_get_version()} per {sys.platform}...")
    print(f"   Spec: {SPEC_FILE}")
    print(f"   Output: {DIST_DIR}")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC_FILE),
        "--noconfirm",
    ]

    if args.verbose:
        cmd.append("--log-level=DEBUG")
    else:
        cmd.append("--log-level=INFO")

    if args.onefile:
        # Modify spec for one-file mode
        cmd.extend(["--onefile"])

    try:
        result = subprocess.run(cmd, cwd=PROJECT_DIR, check=True)
        if result.returncode == 0:
            print()
            print("✅ Build completata con successo!")
            _print_output_info(args.app, args.onefile)
        else:
            print(f"❌ Build fallita (exit code {result.returncode})")
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"❌ Build fallita: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️ Build interrotta dall'utente")
        sys.exit(1)


def _get_version() -> str:
    """Read version from pyproject.toml."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    pyproject = PROJECT_DIR / "pyproject.toml"
    if pyproject.exists():
        data = tomllib.loads(pyproject.read_text())
        return data.get("project", {}).get("version", "0.1.0")
    return "0.1.0"


def _print_output_info(is_app: bool, is_onefile: bool):
    """Print info about the built executable."""
    platform = sys.platform
    if is_onefile:
        if platform == "win32":
            exe = DIST_DIR / "OpenTDS.exe"
        elif platform == "darwin":
            exe = DIST_DIR / "OpenTDS"
        else:
            exe = DIST_DIR / "OpenTDS"
        if exe.exists():
            size_mb = exe.stat().st_size / (1024 * 1024)
            print(f"   📦 Eseguibile: {exe} ({size_mb:.1f} MB)")
    else:
        app_dir = DIST_DIR / "OpenTDS"
        if app_dir.exists():
            size_mb = _dir_size(app_dir) / (1024 * 1024)
            print(f"   📦 Directory: {app_dir} ({size_mb:.1f} MB)")
            if platform == "win32":
                print(f"   ▶ Esegui: {app_dir / 'OpenTDS.exe'}")
            else:
                print(f"   ▶ Esegui: {app_dir / 'OpenTDS'}")

    if is_app:
        app_bundle = DIST_DIR / "OpenTDS.app"
        if app_bundle.exists():
            print(f"   🍎 Bundle macOS: {app_bundle}")

    print()
    print("   Per distribuire:")
    print("     Linux:   tar czf opentds-linux.tar.gz -C dist OpenTDS")
    print("     macOS:   zip -r opentds-macos.zip dist/OpenTDS.app")
    print("     Windows: compress-archive dist/OpenTDS opentds-windows.zip")


def _dir_size(path: Path) -> int:
    """Calculate total size of a directory in bytes."""
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


if __name__ == "__main__":
    main()
