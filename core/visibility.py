"""
Line-of-sight and visibility utilities for IPSC stage generation.

Pure functions — no state, no side effects. Used by PlacementEngine,
RepairEngine, and StageGenerator.
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple

from core.constants import INTERIOR_SAMPLE_COUNT, SAME_LINE_OF_FIRE_THRESHOLD_DEG
from core.geometry import line_intersects_rect, point_in_polygon, polygon_center
from core.models import ItemType, StageItem
from core.scoring import is_scoring_target


def get_blocking_walls(items: List[StageItem]) -> List[StageItem]:
    """Return items that block line of sight (walls, barriers, doors, covers)."""
    from core.scoring import is_blocking_wall

    return [it for it in items if is_blocking_wall(it.item_type)]


def is_target_visible(
    target: StageItem,
    blockers: List[StageItem],
    interior_samples: List[Tuple[float, float]],
) -> bool:
    """Check if target is visible from at least one interior point."""
    target_pos = (target.x, target.y)
    for obs_x, obs_y in interior_samples:
        visible = True
        for wall in blockers:
            if line_intersects_rect(
                (obs_x, obs_y),
                target_pos,
                wall.x,
                wall.y,
                wall.width,
                wall.height,
                wall.rotation,
            ):
                visible = False
                break
        if visible:
            return True
    return False


def targets_on_same_line(
    target_x: float,
    target_y: float,
    existing: List[StageItem],
    perimeter_poly: List[Tuple[float, float]],
    threshold_deg: float = SAME_LINE_OF_FIRE_THRESHOLD_DEG,
) -> bool:
    """True if target is on the same line of fire as an existing target.

    Calculates the angle from the center of the shooting area to each target.
    If the angular difference is < threshold_deg, they share the same line of fire.
    """
    if not perimeter_poly:
        return False

    cx = sum(v[0] for v in perimeter_poly) / len(perimeter_poly)
    cy = sum(v[1] for v in perimeter_poly) / len(perimeter_poly)

    new_angle = math.degrees(math.atan2(target_y - cy, target_x - cx))

    for other in existing:
        if not is_scoring_target(other.item_type):
            continue
        other_angle = math.degrees(math.atan2(other.y - cy, other.x - cx))
        diff = abs(new_angle - other_angle)
        diff = min(diff, 360.0 - diff)
        if diff < threshold_deg:
            return True
    return False


def is_behind_shooting_area(
    target_x: float,
    target_y: float,
    poly: List[Tuple[float, float]],
) -> bool:
    """True if target is in the sector behind the shooting area (outside safe engagement).

    The main engagement direction goes from the centroid toward the backstop
    (highest y). 'Behind' = beyond ±90° from this direction.
    """
    if not poly or len(poly) < 3:
        return False

    cx = sum(v[0] for v in poly) / len(poly)
    cy = sum(v[1] for v in poly) / len(poly)

    # Engagement direction: centroid → backstop (highest y)
    back_x, back_y = cx, max(v[1] for v in poly)
    dx_forward = back_x - cx
    dy_forward = back_y - cy
    forward_len = math.hypot(dx_forward, dy_forward)
    if forward_len < 0.1:
        return False

    dx_target = target_x - cx
    dy_target = target_y - cy
    target_len = math.hypot(dx_target, dy_target)
    if target_len < 0.01:
        return False

    dot = dx_forward * dx_target + dy_forward * dy_target
    cos_angle = dot / (forward_len * target_len)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    angle = math.degrees(math.acos(cos_angle))
    return angle > 90.0


def sample_interior_points(
    perimeter_poly: List[Tuple[float, float]],
    count: int = INTERIOR_SAMPLE_COUNT,
) -> List[Tuple[float, float]]:
    """Sample random points inside the perimeter polygon (for visibility checks)."""
    if not perimeter_poly:
        return [(5.0, 5.0)]

    xs = [p[0] for p in perimeter_poly]
    ys = [p[1] for p in perimeter_poly]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    points: list[tuple[float, float]] = []
    for _ in range(count * 5):
        if len(points) >= count:
            break
        x = random.uniform(min_x, max_x)
        y = random.uniform(min_y, max_y)
        if point_in_polygon(x, y, perimeter_poly):
            points.append((x, y))

    if points:
        return points[:count]
    return [polygon_center(perimeter_poly)]


def ensure_target_visibility(
    items: List[StageItem],
    interior_samples: List[Tuple[float, float]],
) -> List[StageItem]:
    """Remove obstacles blocking targets until 100% visibility is achieved.

    Each target must be visible from at least one interior point.
    If an obstacle blocks more targets than it frees, it gets removed.
    """
    targets = [
        it
        for it in items
        if it.item_type
        in (
            ItemType.PAPER_TARGET,
            ItemType.STEEL_TARGET,
            ItemType.SWINGER,
            ItemType.DROP_TURNER,
            ItemType.MOVER,
        )
    ]
    if not targets or not interior_samples:
        return items

    min_visible = len(targets)

    for _ in range(100):
        blockers = [b for b in get_blocking_walls(items) if not b.properties.get("protected")]
        if not blockers:
            break

        visible = sum(1 for t in targets if is_target_visible(t, blockers, interior_samples))
        if visible >= min_visible:
            break

        best_gain = 0
        best_item: StageItem | None = None
        for b in blockers:
            test_items = [it for it in items if it is not b]
            test_blockers = [
                x for x in get_blocking_walls(test_items) if not x.properties.get("protected")
            ]
            all_blockers = test_blockers + [
                x for x in get_blocking_walls(test_items) if x.properties.get("protected")
            ]
            test_visible = sum(
                1 for t in targets if is_target_visible(t, all_blockers, interior_samples)
            )
            gain = test_visible - visible
            if gain > best_gain:
                best_gain = gain
                best_item = b

        if best_item is None or best_gain == 0:
            wall_hits: dict[int, int] = {}
            wall_map: dict[int, StageItem] = {}
            for w in blockers:
                wall_hits[id(w)] = 0
                wall_map[id(w)] = w

            invisible = [
                t
                for t in targets
                if not is_target_visible(
                    t,
                    [x for x in get_blocking_walls(items) if not x.properties.get("protected")],
                    interior_samples,
                )
            ]
            for t in invisible:
                for ox, oy in interior_samples:
                    for w in blockers:
                        if line_intersects_rect(
                            (ox, oy),
                            (t.x, t.y),
                            w.x,
                            w.y,
                            w.width,
                            w.height,
                            w.rotation,
                        ):
                            wall_hits[id(w)] = wall_hits.get(id(w), 0) + 1

            if not wall_hits or max(wall_hits.values()) == 0:
                break
            best_id = max(wall_hits, key=wall_hits.get)
            best_item = wall_map[best_id]

        items = [it for it in items if it is not best_item]

    return items
