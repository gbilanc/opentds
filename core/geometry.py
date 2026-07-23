"""
Helper geometrici per il calcolo di intersezioni, punti in poligoni, bounding box.

Tutte le funzioni sono pure (nessuno stato) e usano coordinate in metri.
"""
from __future__ import annotations

import math
from typing import List, Tuple


def point_in_polygon(px: float, py: float,
                     poly: List[Tuple[float, float]]) -> bool:
    """Ray casting: True se (px, py) è dentro il poligono convesso."""
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > py) != (y2 > py)) and \
           (px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-9) + x1):
            inside = not inside
    return inside


def polygon_center(poly: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Centroide del poligono (media dei vertici)."""
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    return cx, cy


def point_in_rotated_rect(px: float, py: float,
                           cx: float, cy: float,
                           w: float, h: float,
                           angle_deg: float) -> bool:
    """True se (px, py) è dentro il rettangolo ruotato."""
    angle = math.radians(angle_deg)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    dx = px - cx
    dy = py - cy
    local_x = dx * cos_a + dy * sin_a
    local_y = -dx * sin_a + dy * cos_a
    return abs(local_x) <= w / 2 + 1e-6 and abs(local_y) <= h / 2 + 1e-6


def segments_intersect(a: Tuple[float, float],
                        b: Tuple[float, float],
                        c: Tuple[float, float],
                        d: Tuple[float, float]) -> bool:
    """True se il segmento a-b interseca c-d (esclusi estremi coincidenti)."""
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)

    # Caso collineare
    if abs(o1) < 1e-9 and abs(o2) < 1e-9 and abs(o3) < 1e-9 and abs(o4) < 1e-9:
        def between(v, s1, s2):
            return min(s1, s2) - 1e-6 <= v <= max(s1, s2) + 1e-6
        return (between(a[0], c[0], d[0]) or between(b[0], c[0], d[0]) or
                between(c[0], a[0], b[0]) or between(d[0], a[0], b[0]))

    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def line_intersects_rect(p1: Tuple[float, float],
                          p2: Tuple[float, float],
                          cx: float, cy: float,
                          w: float, h: float,
                          angle_deg: float) -> bool:
    """True se il segmento p1-p2 interseca il rettangolo ruotato."""
    # Estremo dentro il rettangolo
    if point_in_rotated_rect(p1[0], p1[1], cx, cy, w, h, angle_deg):
        return True
    if point_in_rotated_rect(p2[0], p2[1], cx, cy, w, h, angle_deg):
        return True

    # Intersezione con ogni lato
    angle = math.radians(angle_deg)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    hw, hh = w / 2, h / 2
    corners = []
    for dx, dy in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]:
        x = cx + dx * cos_a - dy * sin_a
        y = cy + dx * sin_a + dy * cos_a
        corners.append((x, y))

    n = len(corners)
    for i in range(n):
        if segments_intersect(p1, p2, corners[i], corners[(i + 1) % n]):
            return True
    return False


def euclidean_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """Distanza Euclidea tra due punti."""
    return math.hypot(x1 - x2, y1 - y2)


def angle_between_points(cx: float, cy: float, px: float, py: float,
                          qx: float, qy: float) -> float:
    """Angolo assoluto (gradi) tra i vettori (cx,cy)→(px,py) e (cx,cy)→(qx,qy).

    Ritorna un valore tra 0 e 180.
    """
    dx1 = px - cx
    dy1 = py - cy
    dx2 = qx - cx
    dy2 = qy - cy
    dot = dx1 * dx2 + dy1 * dy2
    mag1 = math.hypot(dx1, dy1)
    mag2 = math.hypot(dx2, dy2)
    if mag1 < 1e-9 or mag2 < 1e-9:
        return 0.0
    cos_a = dot / (mag1 * mag2)
    cos_a = max(-1.0, min(1.0, cos_a))
    return math.degrees(math.acos(cos_a))


def polygon_area(poly: list[tuple[float, float]]) -> float:
    """Area del poligono (formula di Gauss). Ritorna 0 per poligoni degenere."""
    n = len(poly)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def validate_polygon(poly: list[tuple[float, float]],
                     min_vertices: int = 4,
                     min_area: float = 0.1) -> tuple[bool, list[str]]:
    """Valida un poligono rappresentante l'area di tiro.

    Controlla:
    - Numero minimo di vertici
    - Area non degenere
    - Nessun vertice coincidente
    - Assenza auto-intersezioni (poligono semplice)
    - Ordine antiorario (opzionale)

    Returns:
        (valido, lista_errori)
    """
    errors: list[str] = []

    if len(poly) < min_vertices:
        errors.append(f"Poligono con {len(poly)} vertici (min {min_vertices})")
        return False, errors

    area = polygon_area(poly)
    if area < min_area:
        errors.append(f"Poligono degenere: area {area:.3f} m² (min {min_area})")
        return False, errors

    # Vertici coincidenti (distanza < 1cm)
    for i in range(len(poly)):
        for j in range(i + 1, len(poly)):
            d = euclidean_distance(poly[i][0], poly[i][1], poly[j][0], poly[j][1])
            if d < 0.01:
                errors.append(f"Vertici {i} e {j} coincidenti (distanza {d:.4f}m)")
                return False, errors

    # Auto-intersezioni (segmenti non consecutivi che si incrociano)
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        for j in range(i + 2, n):
            if (j + 1) % n == i:
                continue  # condividono un vertice
            c, d = poly[j], poly[(j + 1) % n]
            if (i + 1) % n == j or (j + 1) % n == i:
                continue  # adiacenti
            if segments_intersect(a, b, c, d):
                errors.append(f"Auto-intersezione tra segmento {i}→{(i+1)%n} e {j}→{(j+1)%n}")
                return False, errors

    return True, errors
