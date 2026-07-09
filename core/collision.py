"""
Collision detection e geometria con Shapely.

Fornisce helper per creare e testare interazioni tra oggetti stage
usando il robusto motore geometrico di Shapely (buffer, intersezione,
distanza, point-in-polygon, OBB).
"""
from __future__ import annotations

import math
from typing import List, Tuple

import shapely
from shapely import affinity, buffer, contains, distance, intersects
from shapely.geometry import Point, Polygon, box


def make_stage_boundary(width: float, depth: float, margin: float = 0) -> Polygon:
    """Crea il poligono del perimetro dello stage, opzionalmente ristretto di `margin`."""
    return box(margin, margin, width - margin, depth - margin)


def make_obb(cx: float, cy: float, w: float, h: float,
             angle_deg: float = 0) -> Polygon:
    """Crea un oriented bounding box (rettangolo ruotato)."""
    rect = box(-w / 2, -h / 2, w / 2, h / 2)
    rect = affinity.rotate(rect, angle_deg, origin=(0, 0))
    rect = affinity.translate(rect, cx, cy)
    return rect


def min_distance_between(a: Polygon, b: Polygon) -> float:
    """Distanza minima tra due poligoni (0 se si sovrappongono)."""
    return distance(a, b)


def overlaps(a: Polygon, b: Polygon, min_gap: float = 0) -> bool:
    """True se `a` e `b` distano meno di `min_gap`."""
    return distance(a, b) < min_gap


def point_in_polygon_shapely(px: float, py: float,
                              polygon: Polygon) -> bool:
    """True se il punto è dentro il poligono."""
    return contains(polygon, Point(px, py))


def line_intersects_rect_shapely(p1: Tuple[float, float],
                                  p2: Tuple[float, float],
                                  rect: Polygon) -> bool:
    """True se il segmento p1-p2 interseca il rettangolo ruotato."""
    from shapely.geometry import LineString
    line = LineString([p1, p2])
    return intersects(line, rect)


def item_obb(item) -> Polygon | None:
    """Crea l'OBB di un StageItem, o None se non applicabile."""
    from core.models import ItemType
    if item.item_type in (ItemType.FAULT_LINE,):
        # Fault line: linea sottile → segmento, non area
        angle = math.radians(item.rotation)
        half_len = item.width / 2
        dx = math.cos(angle) * half_len
        dy = math.sin(angle) * half_len
        from shapely.geometry import LineString
        return LineString([(item.x - dx, item.y - dy),
                           (item.x + dx, item.y + dy)]).buffer(0.05)
    return make_obb(item.x, item.y, item.width, item.height, item.rotation)
