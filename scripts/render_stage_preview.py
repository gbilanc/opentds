"""
CLI per renderizzare l'anteprima 3D di uno stage OpenTDS con Blender.

Flusso:
    1. Carica lo stage (JSON v3) o usa i parametri per costruirlo.
    2. Genera la descrizione di scena (services.blender_exporter).
    3. Trova il binario Blender (variabile BLENDER o path noti).
    4. Lancia ``blender -b -P scripts/blender_render.py`` headless.
    5. Stampa i percorsi di PNG e .blend generati.

Utilizzo:
    uv run python scripts/render_stage_preview.py examples/stage2.json \
        -o .build/preview.png

Opzioni:
    --blend PATH     salva anche il file .blend editabile
    --no-boundary    salta i muri perimetrali
    --no-auto-face   non orientare i bersagli verso il centro area
    --resolution WxH risoluzione del render (default 1920x1080)
    --blender PATH   percorso esplicito del binario Blender
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.blender_exporter import BlenderExportOptions, export_scene  # noqa: E402
from services.serializer import load_stage  # noqa: E402

# Path noti del binario Blender (Linux/macOS/Windows).
KNOWN_BLENDER = (
    "blender",
    "/snap/bin/blender",
    "/usr/bin/blender",
    "/opt/blender/blender",
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe",
    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe",
)

DEFAULT_RESOLUTION = "1920x1080"


def find_blender(explicit: str | None) -> str:
    """Rileva il binario Blender: argomento, env BLENDER o path noti."""
    if explicit:
        return explicit
    env = shutil.which("blender")
    if env:
        return env
    for candidate in KNOWN_BLENDER:
        if shutil.which(candidate) or Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        "Blender non trovato. Installa Blender 4.2+ o passa --blender /path/to/blender"
    )


def run_render(
    scene_path: Path,
    out_png: Path,
    out_blend: Path | None,
    blender: str,
    resolution: str,
    timeout: int = 600,
    no_nav: bool = False,
) -> Path:
    """Lancia Blender headless e renderizza la scena."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        blender,
        "-b",
        "-P",
        str(PROJECT_ROOT / "scripts" / "blender_render.py"),
        "--",
        str(scene_path),
        str(out_png),
    ]
    if out_blend:
        cmd.append(str(out_blend))
        # Il marker è significativo solo se viene salvato il .blend.
        if no_nav:
            cmd.append("no-nav")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"Render Blender scaduto dopo {timeout}s") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError("Render Blender fallito:\n" + "\n".join(detail[-20:]))
    if not out_png.exists():
        raise RuntimeError("Blender è terminato senza produrre il PNG")
    if out_blend and not Path(out_blend).exists():
        raise RuntimeError("Blender è terminato senza produrre il file .blend")
    return out_png


def parse_resolution(value: str) -> tuple[int, int]:
    """'1920x1080' → (1920, 1080)."""
    try:
        w, h = value.lower().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError(f"risoluzione non valida: {value}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render 3D dell'anteprima stage con Blender")
    parser.add_argument("stage", type=Path, help="file stage JSON (v3)")
    parser.add_argument("-o", "--output", type=Path, default=Path(".build/preview.png"))
    parser.add_argument("--blend", type=Path, default=None, help="salva anche il .blend")
    parser.add_argument("--no-nav", action="store_true",
                        help=".blend senza telecamere di navigazione (solo render)")
    parser.add_argument("--no-boundary", action="store_true", help="salta i muri perimetrali")
    parser.add_argument("--no-auto-face", action="store_true",
                        help="usa la rotazione originale dei bersagli")
    parser.add_argument("--resolution", type=parse_resolution,
                        default=parse_resolution(DEFAULT_RESOLUTION))
    parser.add_argument("--blender", type=str, default=None, help="percorso esplicito del binario")
    args = parser.parse_args(argv)

    if not args.stage.exists():
        print(f"✗ Stage non trovato: {args.stage}", file=sys.stderr)
        return 1

    blender = find_blender(args.blender)
    print(f"🖥 Blender: {blender}")

    # 1. Carica lo stage e genera la scena.
    try:
        stage = load_stage(args.stage)
    except Exception as exc:
        print(f"✗ Impossibile leggere lo stage: {exc}", file=sys.stderr)
        return 1

    opts = BlenderExportOptions(
        include_boundary=not args.no_boundary,
        auto_face=not args.no_auto_face,
        svg_dir=Path(".build/svg"),
    )
    scene_path = args.output.parent / f"{args.stage.stem}_scene.json"
    export_scene(stage, scene_path, opts)
    print(f"🎬 Scena generata: {scene_path} ({len(stage.items)} item)")

    # 2. Render headless.
    try:
        run_render(
            scene_path, args.output, args.blend, blender, args.resolution, no_nav=args.no_nav
        )
    except (FileNotFoundError, TimeoutError, RuntimeError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    print(f"✅ Anteprima: {args.output.resolve()}")
    if args.blend:
        print(f"   File .blend: {args.blend.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
