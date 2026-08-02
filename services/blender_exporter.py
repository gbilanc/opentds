"""
Servizio di esportazione stage → descrizione scena 3D per Blender.

Converte uno Stage (o JSON v3) in una descrizione di scena neutra e
serializzabile che ``scripts/blender_render.py`` (eseguito in Blender
headless) trasforma in geometria, materiali e render EEVEE.

Coordinate:
    - Lo stage usa (x, y) sul piano orizzontale, rotazione in gradi
      (0 = allineato a +X).
    - Blender usa Y verso l'alto: stage (x, y) → Blender (x, z).
    - La rotazione sull'asse verticale dello stage diventa rotazione
      attorno a Y in Blender.

La scena viene emessa come dict JSON-serializzabile con oggetti di
kind: ``box``, ``cylinder_v``, ``board_box``, ``board_cylinder``,
``polygon`` (vedi docstring di ``build_scene``).

Utilizzo:
    from services.blender_exporter import build_scene, export_scene
    scene = build_scene(stage)
    export_scene(stage, Path("build/stage_scene.json"))
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.models import ItemType, Stage, StageItem
from services.openscad_exporter import ITEM_COLORS

# ═══════════════════════════════════════════════════════════════════════
#  Costanti di geometria
# ═══════════════════════════════════════════════════════════════════════

TARGETS_DIR = Path("resources/targets/custom")

# Dimensione bersagli cartacei (larghezza, altezza) in metri.
TARGET_BOARD_SIZE: dict[ItemType, tuple[float, float]] = {
    ItemType.PAPER_TARGET: (0.45, 0.75),
    ItemType.MINI_TARGET: (0.30, 0.30),
    ItemType.MICRO_TARGET: (0.20, 0.20),
    ItemType.NO_SHOOT: (0.45, 0.75),
}

# SVG silhouette di default per tipo di bersaglio cartaceo.
DEFAULT_SVG: dict[ItemType, str] = {
    ItemType.PAPER_TARGET: "ipsc_target.svg",
    ItemType.MINI_TARGET: "ipsc_mini_target.svg",
    ItemType.MICRO_TARGET: "ipsc_mini_target.svg",
    ItemType.NO_SHOOT: "ipsc_no_shoot.svg",
}

STICK_HEIGHT = 1.5  # altezza stecche laterali bersaglio
STICK_RADIUS = 0.02
STICK_OFFSET = 0.245  # distanza stecche dal centro del pannello
BOARD_THICKNESS = 0.02  # spessore pannello bersaglio

# Metallici: palo + disco (come il navigatore Three.js).
STEEL_POLE_RADIUS = 0.04
STEEL_POLE_HEIGHT = 1.2
STEEL_DISC_RADIUS = 0.15
STEEL_DISC_THICKNESS = 0.04
PLATE_POLE_RADIUS = 0.03
PLATE_POLE_HEIGHT = 0.8
PLATE_DISC_THICKNESS = 0.03
STEEL_COLOR = "#87CEEB"

# Muro perimetrale attorno al mondo (bai IPSC).
BOUNDARY_WALL_HEIGHT = 3.0
BOUNDARY_WALL_THICKNESS = 0.2
BOUNDARY_COLOR = "#6b7280"

GROUND_COLOR = "#8f8f8f"  # pavimento in cemento
GRAVEL_COLOR = "#b0a898"  # overlay area di tiro

# Colori posizioni di tiro (come il navigatore).
POSITION_START_COLOR = "#22c55e"
POSITION_COLOR = "#3b82f6"


@dataclass(frozen=True)
class Geom:
    """Dimensioni 3D di default per un tipo di oggetto (metri)."""

    sx: float = 1.0  # larghezza
    sy: float = 0.1  # spessore
    sz: float = 2.0  # altezza


TYPE_GEOM: dict[ItemType, Geom] = {
    ItemType.WALL: Geom(1.0, 0.10, 2.0),
    ItemType.BARRIER: Geom(1.0, 0.15, 1.0),
    ItemType.HARD_COVER: Geom(1.0, 0.10, 2.0),
    ItemType.SOFT_COVER: Geom(1.0, 0.08, 1.5),
    ItemType.DOOR: Geom(0.9, 0.05, 2.0),
}

# Materiali Principled BSDF usati dallo script Blender.
BOX_MATERIAL: dict[ItemType, str] = {
    ItemType.WALL: "brick",
    ItemType.BARRIER: "wood",
    ItemType.HARD_COVER: "solid",
    ItemType.SOFT_COVER: "solid",
    ItemType.DOOR: "wood",
}


@dataclass
class BlenderExportOptions:
    """Opzioni di esportazione della scena Blender."""

    margin: float = 6.0  # margine attorno allo stage per i muri perimetrali
    include_boundary: bool = True  # muri perimetrali intorno al mondo
    auto_face: bool = True  # i bersagli guardano il centro dell'area di tiro
    svg_dir: Path = field(default_factory=lambda: Path(".build/svg"))
    decimal_places: int = 3


# ═══════════════════════════════════════════════════════════════════════
#  Utility
# ═══════════════════════════════════════════════════════════════════════


def _r(value: float, n: int) -> float:
    """Arrotonda un float per una scena JSON compatta."""
    return round(float(value), n)


def _item_color(item: StageItem) -> str:
    """Colore dell'item: quello esplicito se presente, altrimenti il default."""
    if item.color and item.color != "#808080":
        return item.color
    return ITEM_COLORS.get(item.item_type, "#808080")


def _area_center(stage: Stage) -> tuple[float, float]:
    """Centro dell'area di tiro: baricentro del perimetro, altrimenti stage."""
    poly = stage.properties.get("perimeter_poly")
    if isinstance(poly, list) and len(poly) >= 3:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    return stage.width / 2, stage.depth / 2


def _auto_face_angle(item: StageItem, center: tuple[float, float]) -> float:
    """Angolo (gradi, 0 = +X) che fa guardare il bersaglio al centro area."""
    return math.degrees(math.atan2(center[1] - item.y, center[0] - item.x))


def _facing_angle(item: StageItem, center: tuple[float, float], auto_face: bool) -> float:
    """Angolo di faccia del bersaglio: auto-oriented o rotazione dell'item."""
    if auto_face:
        return _auto_face_angle(item, center)
    return item.rotation


def _resolve_svg(item: StageItem) -> Path | None:
    """Risolve il path assoluto dell'SVG di un bersaglio (custom o default)."""
    custom = item.properties.get("custom_svg_path")
    if isinstance(custom, str) and custom.strip():
        candidate = TARGETS_DIR / Path(custom).name
        if candidate.exists():
            return candidate.resolve()
    default = DEFAULT_SVG.get(item.item_type)
    if default:
        candidate = TARGETS_DIR / default
        if candidate.exists():
            return candidate.resolve()
    return None


def clean_svg(src: Path, color: str, out_dir: Path) -> Path:
    """Prepara un SVG per l'import in Blender.

    - Sostituisce ``currentColor`` e ``fill="none"`` (silhouette tintabile)
      con il colore del bersaglio.
    - Rimuove gli elementi ``<text>`` (etichette zona) che importerebbero
      come curve di testo.

    Returns:
        Path del file SVG pulito.
    """
    text = src.read_text(encoding="utf-8")
    text = text.replace("currentColor", color)
    text = re.sub(r'fill="none"', f'fill="{color}"', text)
    text = re.sub(r"<text[^>]*>.*?</text>", "", text, flags=re.S)
    text = re.sub(r"<text[^>]*/>", "", text)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{src.stem}_{color.lstrip('#')}.svg"
    out.write_text(text, encoding="utf-8")
    return out


# ═══════════════════════════════════════════════════════════════════════
#  Builder di oggetti
# ═══════════════════════════════════════════════════════════════════════


def _box(
    obj_id: str,
    item: StageItem,
    size: tuple[float, float, float],
    rotation_y: float,
    color: str,
    material: str,
    svg: Path | None = None,
) -> dict[str, Any]:
    """Oggetto box (parallelepipedo, centro al suolo = base a terra)."""
    sx, sy, sz = size
    obj: dict[str, Any] = {
        "id": obj_id,
        "kind": "box",
        "position": [_r(item.x, 3), _r(sy / 2, 3), _r(item.y, 3)],
        "size": [_r(sx, 3), _r(sy, 3), _r(sz, 3)],
        "rotation_y": _r(rotation_y, 3),
        "color": color,
        "material": material,
    }
    if svg is not None:
        obj["svg"] = str(svg)
    return obj


def _structural_objects(item: StageItem) -> list[dict[str, Any]]:
    """Muri, barriere, coperture e porte → box con rotazione attorno a Y.

    In Blender Y è l'altezza: size = (larghezza, altezza, spessore).
    """
    geom = TYPE_GEOM.get(item.item_type, Geom())
    sx = item.width if item.width > 0 else geom.sx
    return [
        _box(
            f"{item.item_type.name.lower()}-{item.id}",
            item,
            (sx, geom.sz, geom.sy),
            rotation_y=-item.rotation,
            color=_item_color(item),
            material=BOX_MATERIAL.get(item.item_type, "solid"),
        )
    ]


def _fault_line_objects(item: StageItem) -> list[dict[str, Any]]:
    """Fault line: cordolo rosso basso, emissivo per la preview."""
    is_perimeter = item.properties.get("perimeter") is True
    return [
        _box(
            f"fault-{item.id}",
            item,
            (item.width if item.width > 0 else 1.0, 0.12, 0.04),
            rotation_y=-item.rotation,
            color="#b91c1c" if is_perimeter else "#dc2626",
            material="fault",
        )
    ]


def _target_objects(
    item: StageItem,
    center: tuple[float, float],
    opts: BlenderExportOptions,
    vert_offset: float = 0.0,
) -> list[dict[str, Any]]:
    """Bersaglio cartaceo: due stecche di legno + pannello con SVG."""
    facing = _facing_angle(item, center, opts.auto_face)
    rad = math.radians(facing)
    board_w, board_h = TARGET_BOARD_SIZE.get(item.item_type, (0.45, 0.75))
    color = _item_color(item)
    board_center_y = STICK_HEIGHT - board_h / 2 + 0.05

    # Stecche ai lati, perpendicolari alla direzione di faccia.
    perp_x = math.sin(rad) * STICK_OFFSET
    perp_z = -math.cos(rad) * STICK_OFFSET
    objects: list[dict[str, Any]] = []
    for side, sign in (("l", -1.0), ("r", 1.0)):
        objects.append(
            {
                "id": f"target-{item.id}-stick-{side}",
                "kind": "cylinder_v",
                "position": [
                    _r(item.x + sign * perp_x, 3),
                    _r(STICK_HEIGHT / 2 + vert_offset, 3),
                    _r(item.y + sign * perp_z, 3),
                ],
                "radius": STICK_RADIUS,
                "height": STICK_HEIGHT,
                "color": "#8B6914",
                "material": "wood",
            }
        )

    svg = _resolve_svg(item)
    cleaned_svg: Path | None = None
    if svg is not None:
        cleaned_svg = clean_svg(svg, color, opts.svg_dir)

    objects.append(
        {
            "id": f"target-{item.id}-board",
            "kind": "board_box",
            "position": [
                _r(item.x, 3),
                _r(board_center_y + vert_offset, 3),
                _r(item.y, 3),
            ],
            "size": [board_w, board_h, BOARD_THICKNESS],
            "rotation_y": _r(90 - facing, 3),
            "color": color,
            "material": "paper",
        }
    )
    if cleaned_svg is not None:
        objects[-1]["svg"] = str(cleaned_svg)
    return objects


def _steel_objects(
    item: StageItem,
    center: tuple[float, float],
    opts: BlenderExportOptions,
    radius: float,
    pole_radius: float,
    pole_height: float,
    thickness: float,
) -> list[dict[str, Any]]:
    """Metallico: palo verticale + disco rotante verso il centro area."""
    facing = _facing_angle(item, center, opts.auto_face)
    return [
        {
            "id": f"steel-{item.id}-pole",
            "kind": "cylinder_v",
            "position": [_r(item.x, 3), _r(pole_height / 2, 3), _r(item.y, 3)],
            "radius": pole_radius,
            "height": pole_height,
            "color": "#4b5563",
            "material": "metal",
        },
        {
            "id": f"steel-{item.id}-plate",
            "kind": "board_cylinder",
            "position": [_r(item.x, 3), _r(pole_height + thickness / 2, 3), _r(item.y, 3)],
            "radius": radius,
            "thickness": thickness,
            "rotation_y": _r(90 - facing, 3),
            "color": STEEL_COLOR,
            "material": "metal",
        },
    ]


def _shooting_position_objects(item: StageItem) -> list[dict[str, Any]]:
    """Posizione di tiro: cerchio a terra + freccia di direzione."""
    color = POSITION_START_COLOR if item.is_start else POSITION_COLOR
    rad = math.radians(item.angle)
    arrow_len = 0.5
    return [
        {
            "id": f"sp-{item.id}-circle",
            "kind": "cylinder_v",
            "position": [_r(item.x, 3), 0.005, _r(item.y, 3)],
            "radius": 0.4,
            "height": 0.01,
            "color": color,
            "material": "solid",
        },
        {
            "id": f"sp-{item.id}-arrow",
            "kind": "box",
            "position": [
                _r(item.x + (arrow_len / 2) * math.cos(rad), 3),
                0.01,
                _r(item.y + (arrow_len / 2) * math.sin(rad), 3),
            ],
            "size": [arrow_len, 0.01, 0.08],
            "rotation_y": _r(-item.angle, 3),
            "color": color,
            "material": "solid",
        },
    ]


def _split_composite(item: StageItem) -> list[StageItem]:
    """Espande i bersagli compositi in singoli item virtuali.

    Mimetizza la logica del navigatore Three.js (OpenTDSLoader.ts).
    """
    results: list[StageItem] = []

    def clone(type_: ItemType, offset_x: float, offset_y: float, label: str) -> StageItem:
        return StageItem(
            id=item.id,
            item_type=type_,
            x=item.x + offset_x,
            y=item.y + offset_y,
            width=item.width,
            height=item.height,
            rotation=item.rotation,
            color=item.color,
            label=label,
            properties=dict(item.properties),
        )

    if item.item_type == ItemType.DOUBLET_SIDE:
        # Due paper affiancati (±15 cm perpendicolari alla faccia).
        rad = math.radians(item.rotation + 90)
        for i, sign in ((1, -0.15), (2, 0.15)):
            results.append(
                clone(
                    ItemType.PAPER_TARGET,
                    sign * math.cos(rad),
                    sign * math.sin(rad),
                    f"{item.label or 'Paper'} {i}",
                )
            )
    elif item.item_type == ItemType.DOUBLET_OVERLAP:
        # Due paper sovrapposti verticalmente (±20 cm).
        results.extend(
            [
                clone(ItemType.PAPER_TARGET, 0.0, 0.0, f"{item.label or 'Paper'} 1"),
                clone(ItemType.PAPER_TARGET, 0.0, 0.0, f"{item.label or 'Paper'} 2"),
            ]
        )
        for i, offset in enumerate((-0.20, 0.20)):
            results[i].properties["_vert_offset"] = offset
    elif item.item_type == ItemType.DOUBLET_SIDE_HOSTAGE:
        # No-shoot al centro, due paper ai lati.
        results.append(clone(ItemType.NO_SHOOT, 0.0, 0.0, "No-Shoot"))
        rad = math.radians(item.rotation + 90)
        for i, sign in ((1, -0.15), (2, 0.15)):
            results.append(
                clone(
                    ItemType.PAPER_TARGET,
                    sign * math.cos(rad),
                    sign * math.sin(rad),
                    f"{item.label or 'Paper'} {i}",
                )
            )
    elif item.item_type == ItemType.DOUBLET_OVERLAP_HOSTAGE:
        # No-shoot al centro, paper a ±20 cm.
        results.append(clone(ItemType.NO_SHOOT, 0.0, 0.0, "No-Shoot"))
        for i, offset in enumerate((-0.20, 0.20)):
            results.append(clone(ItemType.PAPER_TARGET, 0.0, 0.0, f"{item.label or 'Paper'} {i}"))
            results[-1].properties["_vert_offset"] = offset
    elif item.item_type == ItemType.TARGET_PLUS_NOSHOOT:
        results.append(clone(ItemType.PAPER_TARGET, 0.0, 0.0, "Paper + No-Shoot"))
        results.append(clone(ItemType.NO_SHOOT, 0.0, 0.0, "No-Shoot"))
    elif item.item_type == ItemType.DOUBLE_BOBBER:
        rad = math.radians(item.rotation + 90)
        for sign in (-0.15, 0.15):
            results.append(
                clone(ItemType.BOBBER_PLATE, sign * math.cos(rad), sign * math.sin(rad), "Bobber")
            )
    else:
        results.append(item)
    return results


def _item_to_objects(
    item: StageItem,
    center: tuple[float, float],
    opts: BlenderExportOptions,
) -> list[dict[str, Any]]:
    """Converte uno StageItem in oggetti di scena Blender."""
    t = item.item_type
    objects: list[dict[str, Any]] = []

    if t in (
        ItemType.WALL,
        ItemType.BARRIER,
        ItemType.HARD_COVER,
        ItemType.SOFT_COVER,
        ItemType.DOOR,
    ):
        return _structural_objects(item)
    if t == ItemType.FAULT_LINE:
        return _fault_line_objects(item)
    if t in (
        ItemType.PAPER_TARGET,
        ItemType.MINI_TARGET,
        ItemType.MICRO_TARGET,
        ItemType.NO_SHOOT,
        ItemType.SWINGER,
        ItemType.DROP_TURNER,
        ItemType.MOVER,
    ):
        vert_offset = float(item.properties.get("_vert_offset", 0.0))
        return _target_objects(item, center, opts, vert_offset=vert_offset)
    if t in (ItemType.STEEL_TARGET, ItemType.POPPER):
        return _steel_objects(
            item,
            center,
            opts,
            STEEL_DISC_RADIUS,
            STEEL_POLE_RADIUS,
            STEEL_POLE_HEIGHT,
            STEEL_DISC_THICKNESS,
        )
    if t in (ItemType.METAL_PLATE, ItemType.BOBBER_PLATE):
        radius = item.width if item.width > 0 else 0.20
        return _steel_objects(
            item, center, opts, radius, PLATE_POLE_RADIUS, PLATE_POLE_HEIGHT, PLATE_DISC_THICKNESS
        )
    # Tipi sconosciuti: niente in scena.
    return objects


def _ground_and_boundary(stage: Stage, opts: BlenderExportOptions) -> list[dict[str, Any]]:
    """Pavimento, overlay area di tiro e muri perimetrali."""
    objects: list[dict[str, Any]] = []
    w, d = stage.width, stage.depth

    # Pavimento in cemento sotto tutto il mondo.
    objects.append(
        {
            "id": "floor",
            "kind": "box",
            "position": [_r(w / 2, 3), -0.05, _r(d / 2, 3)],
            "size": [_r(w, 3), 0.1, _r(d, 3)],
            "rotation_y": 0.0,
            "color": GROUND_COLOR,
            "material": "concrete",
        }
    )

    # Overlay dell'area di tiro (poligono del perimetro, ghiaia).
    poly = stage.properties.get("perimeter_poly")
    if isinstance(poly, list) and len(poly) >= 3:
        points = [[_r(p[0], 3), _r(p[1], 3)] for p in poly]
    else:
        points = [[0.0, 0.0], [w, 0.0], [w, d], [0.0, d]]
    objects.append(
        {
            "id": "shooting-area",
            "kind": "polygon",
            "points": points,
            "height": 0.006,
            "color": GRAVEL_COLOR,
            "material": "gravel",
        }
    )

    if opts.include_boundary:
        m = opts.margin
        bw, bh, bt = BOUNDARY_WALL_THICKNESS, BOUNDARY_WALL_HEIGHT, 0.2
        world_w, world_d = w + 2 * m, d + 2 * m
        for obj_id, pos, size in (
            ("boundary-n", (world_w / 2, bh / 2, 0.0), (world_w, bh, bw)),
            ("boundary-s", (world_w / 2, bh / 2, world_d), (world_w, bh, bw)),
            ("boundary-w", (0.0, bh / 2, world_d / 2), (bt, bh, world_d)),
            ("boundary-e", (world_w, bh / 2, world_d / 2), (bt, bh, world_d)),
        ):
            objects.append(
                {
                    "id": obj_id,
                    "kind": "box",
                    "position": [_r(pos[0], 3), _r(pos[1], 3), _r(pos[2], 3)],
                    "size": [_r(size[0], 3), _r(size[1], 3), _r(size[2], 3)],
                    "rotation_y": 0.0,
                    "color": BOUNDARY_COLOR,
                    "material": "stone",
                }
            )
    return objects


def _compute_camera(stage: Stage, opts: BlenderExportOptions) -> dict[str, Any]:
    """Camera 3/4 statica dall'up-range, dentro i muri perimetrali.

    Framing tecnico pulito: lo stage riempie gran parte dell'inquadratura
    e i bersagli restano leggibili (~50px a testa a 1080p).
    """
    w, d = stage.width, stage.depth
    m = opts.margin
    world_w, world_d = w + 2 * m, d + 2 * m
    cx, cz = w / 2, d / 2  # centro dello stage = centro del mondo
    # Massima distanza orizzontale consentita restando dentro i muri (1.5m di margine).
    max_h = min(world_w, world_d) / 2 - 1.5
    dist_h = min(math.hypot(w, d) / 2 * 1.4, max_h)
    el = math.radians(30)
    cam_x = cx + dist_h
    cam_y = 0.6 + dist_h * math.tan(el)
    cam_z = cz - dist_h
    return {
        "position": [_r(cam_x, 3), _r(cam_y, 3), _r(cam_z, 3)],
        "target": [_r(cx, 3), 0.6, _r(cz, 3)],
        "lens": 24.0,
    }


def _compute_lights(stage: Stage, opts: BlenderExportOptions) -> list[dict[str, Any]]:
    """Sole direzionale dall'up-range + area fill di contrasto."""
    w, d = stage.width, stage.depth
    m = opts.margin
    cx, cz = (w + 2 * m) / 2, (d + 2 * m) / 2

    def normalize(v: tuple[float, float, float]) -> list[float]:
        norm = math.sqrt(sum(c * c for c in v))
        return [_r(c / norm, 3) for c in v]

    return [
        {
            "kind": "sun",
            "color": "#fff3d6",
            "energy": 7.0,
            # Dal lato up-range, verso il basso: illumina il fronte dei bersagli.
            "direction": normalize((0.35, -0.75, 0.5)),
        },
        {
            "kind": "area",
            "color": "#dbeafe",
            "energy": 30.0,
            "size": 8.0,
            "position": [_r(cx, 3), 5.0, _r(cz, 3)],
        },
    ]


# ═══════════════════════════════════════════════════════════════════════
#  API pubblica
# ═══════════════════════════════════════════════════════════════════════


def build_scene(stage: Stage, opts: BlenderExportOptions | None = None) -> dict[str, Any]:
    """Costruisce la descrizione di scena Blender da uno Stage.

    Returns:
        Dict JSON-serializzabile con:
        - ``objects``: oggetti di kind ``box``, ``cylinder_v``,
          ``board_box``, ``board_cylinder``, ``polygon``
        - ``camera``: posizione/target/lens della camera statica
        - ``lights``: sole direzionale + area light di fill
    """
    if opts is None:
        opts = BlenderExportOptions()

    center = _area_center(stage)
    objects: list[dict[str, Any]] = []

    # Item dello stage (compositi espansi).
    for item in stage.items:
        for virtual in _split_composite(item):
            objects.extend(_item_to_objects(virtual, center, opts))

    # Posizioni di tiro.
    for sp in stage.shooting_positions:
        objects.extend(_shooting_position_objects(sp))

    # Pavimento, area di tiro e muri perimetrali.
    objects.extend(_ground_and_boundary(stage, opts))

    return {
        "version": 1,
        "name": stage.name,
        "width": _r(stage.width, 3),
        "depth": _r(stage.depth, 3),
        "objects": objects,
        "camera": _compute_camera(stage, opts),
        "lights": _compute_lights(stage, opts),
    }


def export_scene(stage: Stage, path: Path, opts: BlenderExportOptions | None = None) -> Path:
    """Esporta la descrizione di scena Blender come JSON."""
    scene = build_scene(stage, opts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scene, indent=2), encoding="utf-8")
    return path
