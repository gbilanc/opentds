"""
Esportazione stage in OpenSCAD (.scad) per rendering 3D e stampa 3D.

Genera un modello 3D parametrico completo di:
  - Pavimento con griglia metrica
  - Parapalle (backstop) su tre lati
  - Tutti gli oggetti StageItem con colori IPSC-conformi
  - Zona partenza
  - Frecce direzionali UP-RANGE / DOWN-RANGE

Utilizzo:
    from services.openscad_exporter import export_scad
    export_scad(stage, Path("stage.scad"))

    # Rendering automatico (richiede openscad installato):
    from services.openscad_exporter import render_scad_to_png
    render_scad_to_png(Path("stage.scad"), Path("stage.png"))

Dipende solo dalla libreria standard.
"""
from __future__ import annotations

import math
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from core.models import Stage, StageItem, ItemType


# ═══════════════════════════════════════════════════════════════════════════
#  Costanti
# ═══════════════════════════════════════════════════════════════════════════

# Colori IPSC-conformi (Reg. 4.1.2, 4.1.3, 4.1.4)
ITEM_COLORS: dict[ItemType, str] = {
    ItemType.WALL:           "#475569",   # grigio ardesia
    ItemType.PAPER_TARGET:   "#8B4513",   # marrone IPSC carta (Reg. 4.1.2.1)
    ItemType.STEEL_TARGET:   "#d1d5db",   # grigio chiaro metallo (Reg. 4.1.2.2)
    ItemType.POPPER:         "#d1d5db",   # bianco metallico (App. C1-C2)
    ItemType.METAL_PLATE:    "#d1d5db",   # bianco metallico (App. C3)
    ItemType.MINI_TARGET:    "#8B4513",   # marrone carta ridotto
    ItemType.MICRO_TARGET:   "#8B4513",   # marrone carta micro
    ItemType.FAULT_LINE:     "#dc2626",   # rosso fault line (Reg. 2.2.1.4)
    ItemType.NO_SHOOT:       "#eab308",   # giallo no-shoot (Reg. 4.1.3)
    ItemType.BARRIER:        "#fbbf24",   # ambra barriera
    ItemType.DOOR:           "#92400e",   # marrone scuro porta
    ItemType.HARD_COVER:     "#1e293b",   # grigio antracite (Reg. 4.1.4.1)
    ItemType.SOFT_COVER:     "#94a3b8",   # grigio soft cover (Reg. 4.1.4.2)
    ItemType.SWINGER:        "#A0522D",   # marrone scuro mobile
    ItemType.DROP_TURNER:    "#8B6914",   # marrone dorato mobile
    ItemType.MOVER:          "#CD853F",   # marrone chiaro mobile
}


# Dimensioni 3D per ogni tipo (in metri)
# (sx=spessoreX, sy=spessoreY, sz=altezzaZ)
# Usati come default sovrascrivibili dalle dimensioni dello StageItem.
@dataclass
class ItemGeom3D:
    """Dimensioni 3D per un tipo di oggetto."""
    sx: float = 1.0   # larghezza in X
    sy: float = 0.1   # profondità in Y
    sz: float = 2.0   # altezza in Z
    shape: str = "cube"   # "cube", "cylinder", "fault_line"


TYPE_GEOM: dict[ItemType, ItemGeom3D] = {
    ItemType.WALL:           ItemGeom3D(sx=1.0, sy=0.1,  sz=2.0, shape="cube"),
    ItemType.PAPER_TARGET:   ItemGeom3D(sx=0.45, sy=0.02, sz=0.45, shape="cube"),
    ItemType.STEEL_TARGET:   ItemGeom3D(sx=0.30, sy=0.02, sz=0.30, shape="cube"),
    ItemType.POPPER:         ItemGeom3D(sx=0.30, sy=0.02, sz=0.30, shape="cylinder"),
    ItemType.METAL_PLATE:    ItemGeom3D(sx=0.20, sy=0.02, sz=0.20, shape="cylinder"),
    ItemType.MINI_TARGET:    ItemGeom3D(sx=0.30, sy=0.02, sz=0.30, shape="cube"),
    ItemType.MICRO_TARGET:   ItemGeom3D(sx=0.20, sy=0.02, sz=0.20, shape="cube"),
    ItemType.FAULT_LINE:     ItemGeom3D(sx=1.0, sy=0.01, sz=0.06, shape="fault_line"),
    ItemType.NO_SHOOT:       ItemGeom3D(sx=0.45, sy=0.02, sz=0.45, shape="cube"),
    ItemType.BARRIER:        ItemGeom3D(sx=1.0, sy=0.15, sz=1.2, shape="cube"),
    ItemType.DOOR:           ItemGeom3D(sx=0.9, sy=0.05, sz=2.0, shape="cube"),
    ItemType.HARD_COVER:     ItemGeom3D(sx=1.0, sy=0.1,  sz=2.0, shape="cube"),
    ItemType.SOFT_COVER:     ItemGeom3D(sx=1.0, sy=0.08, sz=2.0, shape="cube"),
    ItemType.SWINGER:        ItemGeom3D(sx=0.45, sy=0.02, sz=0.45, shape="cube"),
    ItemType.DROP_TURNER:    ItemGeom3D(sx=0.45, sy=0.02, sz=0.45, shape="cube"),
    ItemType.MOVER:          ItemGeom3D(sx=0.45, sy=0.02, sz=0.45, shape="cube"),
}


# ═══════════════════════════════════════════════════════════════════════════
#  Generatore SCAD
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ScadExportOptions:
    """Opzioni di esportazione OpenSCAD."""
    include_grid: bool = True
    include_floor: bool = True
    include_backstop: bool = True
    include_start_zone: bool = True
    include_direction_arrows: bool = True
    grid_spacing: float = 1.0  # metri tra le linee griglia
    wall_height: float = 2.0   # altezza predefinita muri
    scale_for_3d_print: bool = False  # se True, scala mm e ispessisce muri sottili


def _color_hex_to_openscad(hex_color: str) -> str:
    """Converte #RRGGBB in [R/255, G/255, B/255] per OpenSCAD."""
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return f"[{r:.3f}, {g:.3f}, {b:.3f}]"


def _item_label(it: StageItem) -> str:
    """Etichetta descrittiva per l'item."""
    if it.label:
        return it.label
    return it.item_type.name.replace("_", " ").title()


def _generate_floor(w: float, d: float, opts: ScadExportOptions) -> list[str]:
    """Genera il pavimento e la griglia."""
    lines: list[str] = []
    if opts.include_floor:
        lines.append("    // ── Pavimento ──")
        lines.append("    color([0.65, 0.65, 0.65, 0.9])")
        lines.append(f"    translate([{w/2:.3f}, {d/2:.3f}, -0.05])")
        lines.append(f"    cube([{w:.3f}, {d:.3f}, 0.1], center=true);")
        lines.append("")
    if opts.include_grid:
        lines.append("    // ── Griglia metrica ──")
        lines.append(f"    grid_floor({w:.3f}, {d:.3f}, {opts.grid_spacing:.3f});")
        lines.append("")
    return lines


def _generate_backstop(w: float, d: float, h: float = 2.5) -> list[str]:
    """Genera i parapalle (backstop) su tre lati."""
    lines: list[str] = []
    bh = h
    bt = 0.3  # spessore backstop
    lines.append("    // ── Parapalle (backstop) ──")
    # Fondo (down-range)
    lines.append("    color([0.36, 0.23, 0.12, 0.8])")
    lines.append(f"    translate([{w/2:.3f}, {d + bt/2:.3f}, {bh/2:.3f}])")
    lines.append(f"    cube([{w + 2:.3f}, {bt:.3f}, {bh:.3f}], center=true);")
    # Sinistra
    lines.append("    color([0.36, 0.23, 0.12, 0.8])")
    lines.append(f"    translate([-{bt/2:.3f}, {d/2:.3f}, {bh/2:.3f}])")
    lines.append(f"    cube([{bt:.3f}, {d:.3f}, {bh:.3f}], center=true);")
    # Destra
    lines.append("    color([0.36, 0.23, 0.12, 0.8])")
    lines.append(f"    translate([{w + bt/2:.3f}, {d/2:.3f}, {bh/2:.3f}])")
    lines.append(f"    cube([{bt:.3f}, {d:.3f}, {bh:.3f}], center=true);")
    lines.append("")
    return lines


def _generate_start_zone(w: float, d: float) -> list[str]:
    """Genera l'area di partenza."""
    lines: list[str] = []
    sw, sh = 2.0, 2.0
    lines.append("    // ── Zona partenza ──")
    lines.append("    color([0.09, 0.50, 0.24, 0.4])")
    lines.append(f"    translate([{w/2:.3f}, {sh/2:.3f}, 0.005])")
    lines.append(f"    cube([{sw:.3f}, {sh:.3f}, 0.01], center=true);")
    lines.append("")
    return lines


def _generate_direction_arrows(w: float, d: float) -> list[str]:
    """Genera frecce direzionali UP-RANGE e DOWN-RANGE."""
    lines: list[str] = []
    lines.append("    // ── Frecce direzionali ──")
    # UP-RANGE (ingresso, verde)
    lines.append("    color([0.13, 0.77, 0.37])")
    lines.append(f"    translate([{w/2:.3f}, 0, 0.6])")
    lines.append("    rotate([90, 0, 0])")
    lines.append("    cylinder(h=0.8, r1=0.3, r2=0, center=true);")
    # DOWN-RANGE (verso backstop, rosso)
    lines.append("    color([0.94, 0.27, 0.27])")
    lines.append(f"    translate([{w/2:.3f}, {d:.3f}, 0.6])")
    lines.append("    rotate([-90, 0, 0])")
    lines.append("    cylinder(h=0.8, r1=0.3, r2=0, center=true);")
    lines.append("")
    return lines


def _generate_item_module(name: str, it: StageItem,
                          opts: ScadExportOptions) -> list[str]:
    """Genera il modulo OpenSCAD per un singolo StageItem."""
    lines: list[str] = []

    geom = TYPE_GEOM.get(it.item_type, ItemGeom3D())
    color = ITEM_COLORS.get(it.item_type, "#808080")
    color_scad = _color_hex_to_openscad(color)

    # Dimensioni 3D:
    #   X = it.width (orizzontale, es. lunghezza muro o larghezza bersaglio)
    #   Y = geom.sy   (spessore/profondità, dal tipo)
    #   Z = geom.sz   (altezza verticale, dal tipo — NON it.height che è 2D)
    sx = it.width if it.width > 0 else geom.sx
    sy = geom.sy
    sz = geom.sz

    if opts.scale_for_3d_print:
        # Per stampa 3D: scala tutto in mm, ispessisce pareti sottili
        scale = 1000.0  # metri → mm
    else:
        scale = 1.0

    # Posizione: stage (x,y) → OpenSCAD (x, y, z)
    # La rotazione è intorno all'asse Z
    px = it.x * scale
    py = it.y * scale
    rot_z = it.rotation

    # Altezza dal pavimento (y in OpenSCAD = verticale)
    # Per default: center=true e y=sz/2 (poggia a terra)
    if geom.shape == "fault_line":
        # Fault line: striscia rossa molto bassa sul pavimento
        sx = it.width * scale if it.width > 0 else 1.0 * scale
        sy = 0.01 * scale
        sz = 0.06 * scale
        lines.append(f"    // Fault line — {_item_label(it)}")
        lines.append(f"    color({color_scad}, 0.8)")
        lines.append(f"    translate([{px:.3f}, {py:.3f}, {sz/2:.3f}])")
        lines.append(f"    rotate([0, 0, {rot_z:.1f}])")
        lines.append(f"    cube([{sx:.3f}, {sy:.3f}, {sz:.3f}], center=true);")

    elif geom.shape == "cylinder":
        # Cilindro verticale: per popper e piatti metallici
        # Sono dischi metallici verticali: raggio = it.width/2, spessore = 0.02
        r = sx / 2 * scale if sx > 0 else 0.15 * scale
        thickness = sy * scale  # spessore in Y (dopo rotazione)
        lines.append(f"    // {_item_label(it)} — {it.item_type.name}")
        lines.append(f"    color({color_scad})")
        lines.append(f"    translate([{px:.3f}, {py:.3f}, {r:.3f}])")
        lines.append(f"    rotate([0, 0, {rot_z:.1f}])")
        lines.append(f"    rotate([90, 0, 0])  // cilindro in piedi")
        lines.append(f"    cylinder(h={thickness:.3f}, r={r:.3f}, center=true);")

    else:
        # Cubo standard: muri, bersagli, barriere, porte, coperture
        # sx = larghezza (X), sy = spessore (Y), sz = altezza (Z)
        lines.append(f"    // {_item_label(it)} — {it.item_type.name}")
        lines.append(f"    color({color_scad})")
        lines.append(f"    translate([{px:.3f}, {py:.3f}, {sz/2:.3f}])")
        lines.append(f"    rotate([0, 0, {rot_z:.1f}])")
        lines.append(f"    cube([{sx:.3f}, {sy:.3f}, {sz:.3f}], center=true);")

    return lines


def _generate_grid_module() -> str:
    """Genera il modulo OpenSCAD per la griglia del pavimento."""
    return """
// Modulo griglia metrica
module grid_floor(w, d, spacing) {
    for (x = [0:spacing:w]) {
        color([0.28, 0.33, 0.41, 0.4])
        translate([x, 0, 0.002])
        cube([0.02, d, 0.01], center=false);
    }
    for (y = [0:spacing:d]) {
        color([0.28, 0.33, 0.41, 0.4])
        translate([0, y, 0.002])
        cube([w, 0.02, 0.01], center=false);
    }
}
"""


# ═══════════════════════════════════════════════════════════════════════════
#  API pubblica
# ═══════════════════════════════════════════════════════════════════════════

def stage_to_scad(stage: Stage, opts: Optional[ScadExportOptions] = None) -> str:
    """Converte uno Stage in una stringa OpenSCAD (.scad).

    Args:
        stage: Lo stage IPSC da esportare.
        opts: Opzioni di esportazione (default: ragionevoli).

    Returns:
        Stringa contenente il codice OpenSCAD completo.
    """
    if opts is None:
        opts = ScadExportOptions()

    w = stage.width
    d = stage.depth
    lines: list[str] = []

    # Intestazione
    lines.append(f"// ═══════════════════════════════════════════════════════════")
    lines.append(f"// OpenTDS — OpenSCAD Stage Export")
    lines.append(f"// Stage: {stage.name}")
    lines.append(f"// Dimensioni: {w:.1f}m × {d:.1f}m")
    lines.append(f"// Oggetti: {len(stage.items)}")
    lines.append(f"// Generato da OpenTDS")
    lines.append(f"// ═══════════════════════════════════════════════════════════")
    lines.append("")
    lines.append("/*")
    lines.append(" * Istruzioni:")
    lines.append(" *   openscad -o stage.png --camera 0,0,0,55,0,-25,25 --imgsize 1920,1080 stage.scad")
    lines.append(" *   openscad -o stage.stl stage.scad")
    lines.append(" */")
    lines.append("")

    if opts.scale_for_3d_print:
        lines.append("// ⚠ Modalità stampa 3D: dimensioni in mm")
        lines.append("//   1 m = 1000 mm")
        lines.append("")

    # Moduli di supporto
    lines.append(_generate_grid_module().strip())
    lines.append("")

    # Assemblea principale
    lines.append("// ═══════════════════════════════════════════════════════════")
    lines.append("// Assemblea principale")
    lines.append("// ═══════════════════════════════════════════════════════════")
    lines.append("module stage_assembly() {")

    # Floor + grid
    lines.extend(_generate_floor(w, d, opts))

    # Backstop
    if opts.include_backstop:
        lines.extend(_generate_backstop(w, d))

    # Start zone
    if opts.include_start_zone:
        lines.extend(_generate_start_zone(w, d))

    # Direction arrows
    if opts.include_direction_arrows:
        lines.extend(_generate_direction_arrows(w, d))

    # Oggetti stage
    lines.append("    // ═══════════════════════════════════════════════════════")
    lines.append(f"    // Oggetti stage ({len(stage.items)})")
    lines.append("    // ═══════════════════════════════════════════════════════")
    lines.append("")
    for it in stage.items:
        lines.extend(_generate_item_module("item", it, opts))

    lines.append("}")
    lines.append("")
    lines.append("// ── Render ──")
    lines.append("stage_assembly();")

    return "\n".join(lines)


def export_scad(stage: Stage, path: Path,
                opts: Optional[ScadExportOptions] = None) -> Path:
    """Esporta uno stage in un file .scad.

    Args:
        stage: Lo stage IPSC.
        path: Percorso del file .scad da creare.
        opts: Opzioni di esportazione.

    Returns:
        Il path del file creato.
    """
    content = stage_to_scad(stage, opts)
    path.write_text(content, encoding="utf-8")
    return path


def openscad_available() -> bool:
    """Verifica se OpenSCAD è installato e accessibile."""
    return shutil.which("openscad") is not None


def render_scad_to_png(scad_path: Path, png_path: Path,
                       camera: Optional[str] = None,
                       imgsize: str = "1920,1080",
                       projection: str = "ortho") -> Optional[Path]:
    """Renderizza un file .scad in PNG usando OpenSCAD CLI.

    Args:
        scad_path: Percorso del file .scad.
        png_path: Percorso del file PNG da generare.
        camera: Parametri camera OpenSCAD (x,y,z,rx,ry,rz,dist).
                Default: overhead isometrico.
        imgsize: Dimensioni immagine (W,H).
        projection: 'ortho' o 'perspective'.

    Returns:
        Path del PNG se il rendering è riuscito, None altrimenti.
    """
    if not openscad_available():
        return None

    if camera is None:
        camera = "10,5,10,55,0,-25,25"

    cmd = [
        "openscad",
        "-o", str(png_path),
        "--camera", camera,
        "--imgsize", imgsize,
        "--projection", projection,
        "--colorscheme", "Tomorrow Night",
        str(scad_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"OpenSCAD warning: {result.stderr.strip()}")
            return None
        return png_path
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"OpenSCAD error: {e}")
        return None


def render_scad_to_stl(scad_path: Path, stl_path: Path) -> Optional[Path]:
    """Esporta un file .scad in STL per stampa 3D.

    Args:
        scad_path: Percorso del file .scad.
        stl_path: Percorso del file STL da generare.

    Returns:
        Path del file STL se riuscito, None altrimenti.
    """
    if not openscad_available():
        return None

    cmd = [
        "openscad",
        "-o", str(stl_path),
        str(scad_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"OpenSCAD STL warning: {result.stderr.strip()}")
            return None
        return stl_path
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"OpenSCAD STL error: {e}")
        return None


def render_scad_to_3mf(scad_path: Path, threemf_path: Path) -> Optional[Path]:
    """Esporta un file .scad in 3MF per stampa 3D.

    Args:
        scad_path: Percorso del file .scad.
        threemf_path: Percorso del file .3mf da generare.

    Returns:
        Path del file 3MF se riuscito, None altrimenti.
    """
    if not openscad_available():
        return None

    cmd = [
        "openscad",
        "-o", str(threemf_path),
        str(scad_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"OpenSCAD 3MF warning: {result.stderr.strip()}")
            return None
        return threemf_path
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"OpenSCAD 3MF error: {e}")
        return None
