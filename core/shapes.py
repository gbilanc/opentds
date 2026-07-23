"""
Forme alfabetiche per l'area di tiro e generazione del perimetro poligonale.

Ogni forma è definita come lista di vertici in coordinate normalizzate (0-1)
in senso antiorario. (0,0) = angolo basso-sinistra dello stage.
La forma viene scalata alle dimensioni dello stage e perturbata.
"""
from __future__ import annotations

import math
import random
from typing import List, Tuple

from core.constants import (
    MIN_TARGET_TO_EDGE,
    MIN_BACKSTOP_DEPTH,
    MIN_STEEL_PLACEMENT_DISTANCE,
    MIN_POLY_DIM,
    FRONT_OPEN_GAP,
    TARGET_COLORS,
)
from core.models import Stage, StageItem, ItemType
from core.geometry import (
    segments_intersect,
    point_in_polygon,
    validate_polygon,
)

# ═══════════════════════════════════════════════════════════════════════════════
#  Forme alfabetiche per l'area di tiro
# ═══════════════════════════════════════════════════════════════════════════════

LETTER_SHAPES: dict[str, List[Tuple[float, float]]] = {
    "L": [
        (0.00, 0.00), (1.00, 0.00), (1.00, 0.35),
        (0.35, 0.35), (0.35, 1.00), (0.00, 1.00),
    ],
    "T": [
        (0.00, 0.65), (0.35, 0.65), (0.35, 0.00),
        (0.65, 0.00), (0.65, 0.65), (1.00, 0.65),
        (1.00, 1.00), (0.00, 1.00),
    ],
    "U": [
        (0.00, 0.00), (1.00, 0.00), (1.00, 1.00),
        (0.70, 1.00), (0.70, 0.25), (0.30, 0.25),
        (0.30, 1.00), (0.00, 1.00),
    ],
    "C": [
        (0.00, 0.00), (1.00, 0.00), (1.00, 0.20),
        (0.20, 0.20), (0.20, 0.80), (1.00, 0.80),
        (1.00, 1.00), (0.00, 1.00),
    ],
    "H": [
        (0.00, 0.00), (0.30, 0.00), (0.30, 0.35),
        (0.70, 0.35), (0.70, 0.00), (1.00, 0.00),
        (1.00, 1.00), (0.70, 1.00), (0.70, 0.65),
        (0.30, 0.65), (0.30, 1.00), (0.00, 1.00),
    ],
    "F": [
        (0.25, 0.00), (1.00, 0.00), (1.00, 0.25),
        (0.55, 0.25), (0.55, 0.50), (1.00, 0.50),
        (1.00, 0.75), (0.55, 0.75), (0.55, 1.00),
        (0.25, 1.00), (0.25, 0.00),
    ],
    "O": [
        (0.00, 0.00), (1.00, 0.00), (1.00, 1.00), (0.00, 1.00),
    ],
    "Z": [
        (0.00, 0.65), (0.65, 0.65), (0.00, 0.00),
        (1.00, 0.00), (0.35, 0.65), (1.00, 0.65),
        (1.00, 1.00), (0.00, 1.00),
    ],
    "S": [
        (0.00, 0.00), (1.00, 0.00), (1.00, 0.20),
        (0.25, 0.20), (0.25, 0.40), (1.00, 0.40),
        (1.00, 0.60), (0.25, 0.60), (0.25, 0.80),
        (1.00, 0.80), (1.00, 1.00), (0.00, 1.00),
    ],
    "X": [
        (0.35, 0.00), (0.65, 0.00), (0.65, 0.35),
        (1.00, 0.35), (1.00, 0.65), (0.65, 0.65),
        (0.65, 1.00), (0.35, 1.00), (0.35, 0.65),
        (0.00, 0.65), (0.00, 0.35), (0.35, 0.35),
    ],
    "Y": [
        (0.40, 0.00), (0.60, 0.00), (0.60, 0.40),
        (1.00, 0.70), (1.00, 1.00), (0.00, 1.00),
        (0.00, 0.70), (0.40, 0.40),
    ],
    "M": [
        (0.00, 0.00), (0.25, 0.00), (0.25, 1.00),
        (0.50, 0.50), (0.75, 1.00), (0.75, 0.00),
        (1.00, 0.00), (1.00, 1.00), (0.00, 1.00),
    ],
    "N": [
        (0.00, 0.00), (0.25, 0.00), (0.25, 0.70),
        (0.75, 0.00), (1.00, 0.00), (1.00, 1.00),
        (0.75, 1.00), (0.75, 0.30), (0.25, 1.00),
        (0.00, 1.00),
    ],
    "E": [
        (0.00, 0.00), (1.00, 0.00), (1.00, 0.25),
        (0.30, 0.25), (0.30, 0.40), (1.00, 0.40),
        (1.00, 0.60), (0.30, 0.60), (0.30, 0.75),
        (1.00, 0.75), (1.00, 1.00), (0.00, 1.00),
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Helper geometrici
# ═══════════════════════════════════════════════════════════════════════════════

def _clamp_poly(poly: List[Tuple[float, float]],
                w: float, d_eff: float, margin: float) -> List[Tuple[float, float]]:
    """Blocca i vertici dentro i confini dello stage."""
    result = []
    for px, py in poly:
        nx = max(margin + 0.1, min(w - margin - 0.1, px))
        ny = max(margin + 0.1, min(d_eff - margin - 0.1, py))
        result.append((round(nx, 2), round(ny, 2)))
    return result


def _rotate_poly(poly: List[Tuple[float, float]], angle_deg: float,
                 cx: float, cy: float) -> List[Tuple[float, float]]:
    """Ruota il poligono attorno al punto (cx, cy)."""
    angle = math.radians(angle_deg)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    result = []
    for px, py in poly:
        dx = px - cx
        dy = py - cy
        nx = cx + dx * cos_a - dy * sin_a
        ny = cy + dx * sin_a + dy * cos_a
        result.append((round(nx, 2), round(ny, 2)))
    return result


def _perturb_poly(poly: List[Tuple[float, float]], amount: float = 0.3) -> List[Tuple[float, float]]:
    """Applica una leggera perturbazione casuale ai vertici."""
    result = []
    for px, py in poly:
        nx = px + random.uniform(-amount, amount)
        ny = py + random.uniform(-amount, amount)
        result.append((round(nx, 2), round(ny, 2)))
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Generazione poligono area di tiro
# ═══════════════════════════════════════════════════════════════════════════════

def generate_perimeter_polygon(
    stage: Stage,
    letter_shape: str = "random",
    has_steel: bool = False,
    back_y: float | None = None,
    rotation: float | None = None,
) -> List[Tuple[float, float]]:
    """Genera il poligono dell'area di tiro a forma di lettera dell'alfabeto.

    La lettera viene scalata alle dimensioni dello stage, ruotata
    casualmente di 0/90/180/270 gradi, e leggermente perturbata.
    Il perimetro è completamente chiuso.

    Il poligono risultato è validato con validate_polygon() per
    garantire: area > 0, nessuna auto-intersezione, vertici non coincidenti.

    Returns:
        Lista di vertici (x, y) in senso antiorario.
    """
    margin = MIN_TARGET_TO_EDGE
    w = stage.width
    backstop_margin = MIN_BACKSTOP_DEPTH
    d_eff = back_y if back_y is not None else stage.depth - backstop_margin

    # Sceglie la lettera
    if letter_shape in LETTER_SHAPES:
        letter = letter_shape
    else:
        letter = random.choice(list(LETTER_SHAPES.keys()))
    norm_verts = LETTER_SHAPES[letter]

    # Calcola margine dinamico in base ai tipi di bersaglio
    if has_steel:
        dynamic_inset = max(margin + 1.0, MIN_STEEL_PLACEMENT_DISTANCE + 3.0)
    else:
        dynamic_inset = margin + 1.0

    max_inset_w = (w - MIN_POLY_DIM) / 2
    max_inset_d = (d_eff - MIN_POLY_DIM) / 2
    inset = min(dynamic_inset, max_inset_w, max_inset_d)
    scale_x = w - 2 * inset
    scale_y = d_eff - 2 * inset

    if scale_x < MIN_POLY_DIM or scale_y < MIN_POLY_DIM:
        inset = margin + 1.0
        scale_x = w - 2 * inset
        scale_y = d_eff - 2 * inset

    poly = []
    for nx, ny in norm_verts:
        x = inset + nx * scale_x
        y = inset + ny * scale_y
        poly.append((x, y))

    # Rotazione casuale
    if rotation is None:
        rotation = random.choice([0, 90, 180, 270])
    if rotation != 0:
        cx, cy = w / 2, d_eff / 2
        poly = _rotate_poly(poly, rotation, cx, cy)
        poly = _clamp_poly(poly, w, d_eff, margin)

    # Tentativo con perturbazione: se invalido, usa poligono pulito
    for _ in range(5):
        test_poly = _perturb_poly(poly, amount=0.3)
        clamped = _clamp_poly(test_poly, w, d_eff, margin)
        valid, _ = validate_polygon(clamped, min_vertices=4)
        if valid:
            return clamped

    # Fallback: poligono pulito senza perturbazione
    valid, _ = validate_polygon(poly, min_vertices=4)
    if not valid:
        # Ultima risorsa: lettera O semplice
        norm_verts = LETTER_SHAPES["O"]
        poly = [(inset + nx * scale_x, inset + ny * scale_y) for nx, ny in norm_verts]
    return _clamp_poly(poly, w, d_eff, margin)


def perimeter_to_items(
    poly: List[Tuple[float, float]],
    style: str = "fault_lines",
) -> List[StageItem]:
    """Converte il poligono del perimetro in item Stage.

    Per fault lines: genera tutti i segmenti (linee a terra non bloccano).
    Per barriere/walls: lascia un'apertura di FRONT_OPEN_GAP sul fronte
    (lato up-range) identificando il segmento orizzontale frontale più
    lungo e accorciandolo.

    Tutti gli item perimetrali ricevono `properties["perimeter"] = True`
    e `properties["closed_chain"] = True` per indicare che formano un
    ciclo chiuso.
    """
    items: List[StageItem] = []
    n = len(poly)

    if n < 3:
        return items

    is_blocking = style in ("barriers", "walls", "mixed")
    skip_idx = -1

    # Per barriere/walls: trova il segmento frontale (y minima) da accorciare
    if is_blocking:
        best_idx = -1
        best_y = float('inf')
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            mid_y = (y1 + y2) / 2
            seg_len = math.hypot(x2 - x1, y2 - y1)
            angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180)
            is_horizontal = angle < 30 or angle > 150
            if is_horizontal and seg_len >= FRONT_OPEN_GAP and mid_y < best_y:
                best_y = mid_y
                best_idx = i

        if best_idx >= 0:
            x1, y1 = poly[best_idx]
            x2, y2 = poly[(best_idx + 1) % n]
            seg_len = math.hypot(x2 - x1, y2 - y1)
            gap_half = max(0.05, (seg_len - FRONT_OPEN_GAP) / 2 / seg_len)
            for (sx1, sy1, sx2, sy2) in [
                (x1, y1,
                 x1 + (x2 - x1) * gap_half, y1 + (y2 - y1) * gap_half),
                (x1 + (x2 - x1) * (1 - gap_half), y1 + (y2 - y1) * (1 - gap_half),
                 x2, y2)
            ]:
                cx = (sx1 + sx2) / 2
                cy = (sy1 + sy2) / 2
                seg_len = math.hypot(sx2 - sx1, sy2 - sy1)
                if seg_len < 0.3:
                    continue
                angle = math.degrees(math.atan2(sy2 - sy1, sx2 - sx1))
                if style == "mixed":
                    itype, thick, color, label = ItemType.FAULT_LINE, 0.0, TARGET_COLORS["fault_line"], "Fault Line"
                elif style == "barriers":
                    itype, thick, color, label = ItemType.BARRIER, 0.15, TARGET_COLORS["barrier"], "Barriera"
                else:
                    itype, thick, color, label = ItemType.WALL, 0.2, TARGET_COLORS["wall"], "Muro"
                item = StageItem(0, itype, cx, cy, seg_len, thick, angle, color, label)
                item.properties["perimeter"] = True
                item.properties["closed_chain"] = True
                items.append(item)
            skip_idx = best_idx

    # Genera i segmenti rimanenti
    style_map = {
        "fault_lines": (ItemType.FAULT_LINE, 0.0, TARGET_COLORS["fault_line"], "Fault Line"),
        "barriers":    (ItemType.BARRIER, 0.15, TARGET_COLORS["barrier"], "Barriera"),
        "walls":       (ItemType.WALL, 0.2, TARGET_COLORS["wall"], "Muro"),
    }

    for i in range(n):
        if i == skip_idx:
            continue
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 0.3:
            continue
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))

        if style == "mixed":
            if abs(cy - stage.depth / 2) > abs(cx - stage.width / 2):
                itype, thick, color, label = ItemType.BARRIER, 0.15, TARGET_COLORS["barrier"], "Barriera"
            else:
                itype, thick, color, label = ItemType.FAULT_LINE, 0.0, TARGET_COLORS["fault_line"], "Fault Line"
        else:
            itype, thick, color, label = style_map.get(style, style_map["fault_lines"])

        item = StageItem(0, itype, cx, cy, length, thick, angle, color, label)
        item.properties["perimeter"] = True
        item.properties["closed_chain"] = True
        items.append(item)

    return items


def polygon_to_shapely(poly: List[Tuple[float, float]]):
    """Converte una lista di vertici in un Polygon Shapely.

    Restituisce None se il poligono non è valido (meno di 3 vertici).
    """
    if not poly or len(poly) < 3:
        return None
    from shapely.geometry import Polygon as ShapelyPolygon
    return ShapelyPolygon(poly)
