"""
Placement engine for targets and obstacles in IPSC stages.

Delegates line-of-sight and geometry checks to core/visibility.py and core/geometry.py.
Used by StageGenerator and RepairEngine.
"""
from __future__ import annotations

import math
import random
from typing import Callable, List, Optional, Tuple

from shapely.geometry import Polygon as ShapelyPolygon
from shapely import intersects as shapely_intersects

from core.models import Stage, StageItem, ItemType, ShootingPosition
from core.constants import (
    MIN_TARGET_TO_EDGE,
    MIN_TARGET_TO_TARGET,
    MIN_BACKSTOP_DEPTH,
    MIN_STEEL_PLACEMENT_DISTANCE,
    INTERIOR_SAMPLE_COUNT,
    SAME_LINE_OF_FIRE_THRESHOLD_DEG,
    TARGET_COLORS,
    TARGET_DIMENSIONS,
)
from core.geometry import point_in_polygon, line_intersects_rect
from core.collision import item_obb, min_distance_between as obb_distance
from core.scoring import is_scoring_target, is_paper_like
from core.ipsc_rules import IPSCRulesEngine
from core.shapes import polygon_to_shapely as _perimeter_to_shapely_polygon
from core.visibility import (
    get_blocking_walls,
    is_target_visible,
    is_behind_shooting_area,
    targets_on_same_line,
    sample_interior_points,
)


def compute_target_rotation(
    target_x: float, target_y: float,
    ref_x: float, ref_y: float,
    target_w: float, target_h: float,
) -> float:
    """Calculate optimal rotation so the shooter sees the widest side.

    Points the larger dimension (width or height) perpendicular to the
    shooter→target line of sight.

    Returns:
        Rotation in degrees (0 = aligned with scene X axis).
    """
    base_angle = math.degrees(math.atan2(ref_y - target_y, ref_x - target_x))
    if target_h > target_w:
        base_angle += 90.0
    return base_angle % 360.0


def push_outside_perimeter(
    wx: float, wy: float,
    poly: list[tuple[float, float]],
    min_dist: float = 0.3,
) -> tuple[float, float]:
    """Push point (wx, wy) outside the perimeter if it lies inside.

    Finds the closest point on the polygon boundary and pushes outward
    along the normal.
    """
    if not point_in_polygon(wx, wy, poly):
        return (wx, wy)

    best_dist = float('inf')
    best_nx = best_ny = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        sx, sy = x2 - x1, y2 - y1
        seg_len = math.hypot(sx, sy)
        if seg_len < 0.01:
            continue
        t = ((wx - x1) * sx + (wy - y1) * sy) / (seg_len * seg_len)
        t = max(0.0, min(1.0, t))
        px = x1 + t * sx
        py = y1 + t * sy
        d = math.hypot(wx - px, wy - py)
        if d < best_dist:
            best_dist = d
            best_nx = sy / seg_len
            best_ny = -sx / seg_len

    if best_dist < float('inf'):
        wx = wx + best_nx * (min_dist + best_dist * 1.1)
        wy = wy + best_ny * (min_dist + best_dist * 1.1)

    return (wx, wy)


class PlacementEngine:
    """Engine for placing targets, walls, barriers, and no-shoots.

    Orchestrates positioning logic using the perimeter polygon, config,
    and visibility utilities.
    """

    def __init__(
        self,
        perimeter_poly: list[tuple[float, float]],
        config: object,
        stage: Stage,
        interior_samples: list[tuple[float, float]] | None = None,
    ):
        self._perimeter_poly = perimeter_poly
        self._config = config
        self._stage = stage
        self._interior_samples = (
            interior_samples
            if interior_samples is not None
            else sample_interior_points(perimeter_poly)
        )

    # ── Target dimension/color helpers ──────────────────────────────────

    @staticmethod
    def _target_params(ttype: ItemType, is_moving: bool = False) -> dict:
        """Return (width, height, color, label, min_dist) for a target type."""
        params = {
            ItemType.STEEL_TARGET: (0.30, 0.30, TARGET_COLORS.get("steel_generic", "#d1d5db"), "Steel", MIN_STEEL_PLACEMENT_DISTANCE),
            ItemType.POPPER: (0.30, 0.30, TARGET_COLORS.get("popper", "#d1d5db"), "Popper", MIN_STEEL_PLACEMENT_DISTANCE),
            ItemType.METAL_PLATE: (0.20, 0.20, TARGET_COLORS.get("metal_plate", "#e5e7eb"), "Plate", MIN_STEEL_PLACEMENT_DISTANCE),
            ItemType.MINI_TARGET: (0.34, 0.34, TARGET_COLORS.get("mini", "#A0522D"), "Mini", 1.0),
            ItemType.MICRO_TARGET: (0.23, 0.23, TARGET_COLORS.get("micro", "#8B4513"), "Micro", 1.0),
            # Compositi
            ItemType.DOUBLET_SIDE: (0.95, 0.75, TARGET_COLORS.get("doublet_side", "#8B4513"), "Doppio aff.", 1.0),
            ItemType.DOUBLET_OVERLAP: (0.65, 0.75, TARGET_COLORS.get("doublet_overlap", "#8B4513"), "Doppio sovr.", 1.0),
            ItemType.DOUBLET_SIDE_HOSTAGE: (1.20, 0.75, TARGET_COLORS.get("doublet_side_hostage", "#8B4513"), "Doppio+ost.", 1.0),
            ItemType.DOUBLET_OVERLAP_HOSTAGE: (0.90, 0.75, TARGET_COLORS.get("doublet_overlap_hostage", "#8B4513"), "Doppio+ost.s.", 1.0),
            ItemType.BOBBER_PLATE: (0.20, 0.20, TARGET_COLORS.get("bobber_plate", "#f97316"), "Bobber", MIN_STEEL_PLACEMENT_DISTANCE),
            ItemType.DOUBLE_BOBBER: (0.50, 0.20, TARGET_COLORS.get("double_bobber", "#f97316"), "Doppio bobber", MIN_STEEL_PLACEMENT_DISTANCE),
        }
        moving_labels = {
            ItemType.SWINGER: "Swinger",
            ItemType.DROP_TURNER: "Drop Turner",
            ItemType.MOVER: "Mover",
        }
        if is_moving and ttype in moving_labels:
            return (0.45, 0.45, TARGET_COLORS.get("paper", "#8B4513"), moving_labels[ttype], 1.0)
        if ttype in params:
            return params[ttype]
        # Default: paper target
        return (0.45, 0.45, TARGET_COLORS.get("paper", "#8B4513"), "Paper", 1.0)

    # ── Wall/barrier generation ─────────────────────────────────────────

    def generate_walls(self, existing: List[StageItem]) -> List[StageItem]:
        """Generate walls OUTSIDE the perimeter that obscure targets."""
        avg_len = (
            3.0 if getattr(self._config, 'difficulty', 'medium') == "easy" else
            5.0 if getattr(self._config, 'difficulty', 'medium') == "hard" else
            4.0
        )
        return self._place_blocking_items(
            existing=existing,
            count=getattr(self._config, 'num_walls', 1),
            item_type=ItemType.WALL,
            base_width=lambda: random.uniform(avg_len * 0.7, avg_len * 1.3),
            base_height=0.2,
            color=TARGET_COLORS.get("wall", "#475569"),
            label="Muro",
        )

    def generate_barriers(self, existing: List[StageItem]) -> List[StageItem]:
        """Generate barriers OUTSIDE the perimeter that obscure targets."""
        return self._place_blocking_items(
            existing=existing,
            count=getattr(self._config, 'num_barriers', 4),
            item_type=ItemType.BARRIER,
            base_width=lambda: random.uniform(1.5, 3.0),
            base_height=0.15,
            color=TARGET_COLORS.get("barrier", "#fbbf24"),
            label="Barriera",
        )

    # ── Entrance corridor check ─────────────────────────────────────────

    def blocks_entrance_corridor(self, item: StageItem, stage_width: float = 0) -> bool:
        """True if the item blocks the entrance corridor to the shooting area.

        The entrance corridor is the space between the stage front (y=0)
        and the front edge of the shooting area (minimum y of the polygon).
        Barriers MUST NOT be placed here.
        """
        if not self._perimeter_poly:
            return False
        front_y = min(v[1] for v in self._perimeter_poly)
        if front_y < 0.5:
            return False  # shooting area reaches almost to the edge

        item_obb_geom = item_obb(item)
        if item_obb_geom is None:
            return False

        w = stage_width if stage_width > 0 else 40.0
        entrance = ShapelyPolygon([
            (0, 0), (w, 0), (w, front_y), (0, front_y),
        ])
        return shapely_intersects(item_obb_geom, entrance)

    # ── Placement: block walls/barriers ─────────────────────────────────

    def _place_blocking_items(
        self,
        existing: List[StageItem],
        count: int,
        item_type: ItemType,
        base_width: Callable[[], float],
        base_height: float,
        color: str,
        label: str,
    ) -> List[StageItem]:
        """Place blocking items (walls/barriers) outside the shooting area.

        Strategy:
        1. Try to place along the line of sight (between area and target)
        2. Push outside if it falls inside the area
        3. Fallback: place along the edge of the perimeter

        Rules:
        - Must block at least 1 target (line of sight)
        - MUST NOT intersect the shooting area (OBB check)
        - MUST NOT overlap with other barriers/walls
        - MUST NOT block the entrance corridor
        """
        items: list[StageItem] = []
        targets = [it for it in existing if is_scoring_target(it.item_type)]
        if not self._perimeter_poly or not targets:
            return items

        area_poly = _perimeter_to_shapely_polygon(self._perimeter_poly)
        min_visible = max(1, math.ceil(len(targets) * 0.7)) if targets else 1
        margin = MIN_TARGET_TO_EDGE

        max_attempts = getattr(self._config, 'max_attempts', 500)

        for _ in range(count):
            placed = False

            # Pass 1: place on line of sight, push outside if needed
            for _ in range(150):
                if not targets or not self._interior_samples:
                    break
                t = random.choice(targets)
                ox, oy = random.choice(self._interior_samples)

                dx = t.x - ox
                dy = t.y - oy
                dist = math.hypot(dx, dy)
                if dist < 2.0:
                    continue
                nx, ny = dx / dist, dy / dist

                t_frac = random.uniform(0.3, 0.7)
                wx = ox + nx * dist * t_frac
                wy = oy + ny * dist * t_frac

                wx, wy = push_outside_perimeter(wx, wy, self._perimeter_poly, min_dist=0.3)
                wx = max(margin, min(self._stage.width - margin, wx))
                wy = max(margin, min(self._stage.depth - margin, wy))

                angle_to_target = math.degrees(math.atan2(dy, dx))
                rotation = angle_to_target + random.choice([-90, 90])

                item = StageItem(0, item_type, wx, wy,
                                 base_width(), base_height,
                                 rotation, color, label)

                item_obb_geom = item_obb(item)
                if item_obb_geom is not None and area_poly is not None:
                    if shapely_intersects(item_obb_geom, area_poly):
                        continue

                if item_obb_geom is not None:
                    overlaps = False
                    for e_it in existing + items:
                        if e_it.item_type in (ItemType.WALL, ItemType.BARRIER,
                                              ItemType.DOOR, ItemType.HARD_COVER):
                            e_obb = item_obb(e_it)
                            if e_obb is not None and shapely_intersects(item_obb_geom, e_obb):
                                overlaps = True
                                break
                    if overlaps:
                        continue

                if self.blocks_entrance_corridor(item, self._stage.width):
                    continue

                blocks_any = False
                for t2 in targets:
                    for ox2, oy2 in self._interior_samples:
                        if line_intersects_rect(
                            (ox2, oy2), (t2.x, t2.y),
                            item.x, item.y, item.width, item.height, item.rotation,
                        ):
                            blocks_any = True
                            break
                    if blocks_any:
                        break
                if not blocks_any:
                    continue

                local_engine = IPSCRulesEngine(self._stage)
                if not local_engine.is_valid_position(item, existing + items):
                    continue

                test_items = existing + items + [item]
                test_blockers = get_blocking_walls(test_items)
                visible_now = sum(
                    1 for t2 in targets
                    if is_target_visible(t2, test_blockers, self._interior_samples)
                )
                if visible_now >= min_visible:
                    item.properties["protected"] = True
                    items.append(item)
                    placed = True
                    break

            # Pass 2 (fallback): place at perimeter edge
            if not placed:
                for _ in range(100):
                    if not targets or not self._perimeter_poly:
                        break
                    t = random.choice(targets)
                    poly = self._perimeter_poly
                    n = len(poly)
                    edge_idx = random.randint(0, n - 1)
                    x1, y1 = poly[edge_idx]
                    x2, y2 = poly[(edge_idx + 1) % n]
                    t_frac = random.uniform(0.2, 0.8)
                    wx = x1 + (x2 - x1) * t_frac
                    wy = y1 + (y2 - y1) * t_frac

                    seg_len = math.hypot(x2 - x1, y2 - y1)
                    if seg_len < 0.3:
                        continue
                    nx = (y2 - y1) / seg_len
                    ny = -(x2 - x1) / seg_len
                    out_dist = random.uniform(0.3, 1.5)
                    wx += nx * out_dist
                    wy += ny * out_dist

                    wx = max(margin, min(self._stage.width - margin, wx))
                    wy = max(margin, min(self._stage.depth - margin, wy))

                    dx = t.x - wx
                    dy = t.y - wy
                    angle_to_target = math.degrees(math.atan2(dy, dx))
                    rotation = angle_to_target + random.choice([-90, 90])

                    item = StageItem(0, item_type, wx, wy,
                                     base_width(), base_height,
                                     rotation, color, label)

                    item_obb_geom = item_obb(item)
                    if item_obb_geom is not None and area_poly is not None:
                        if shapely_intersects(item_obb_geom, area_poly):
                            continue

                    if self.blocks_entrance_corridor(item, self._stage.width):
                        continue

                    blocks_any = False
                    for t2 in targets:
                        for o2x, o2y in self._interior_samples:
                            if line_intersects_rect(
                                (o2x, o2y), (t2.x, t2.y),
                                item.x, item.y, item.width, item.height, item.rotation,
                            ):
                                blocks_any = True
                                break
                        if blocks_any:
                            break
                    if not blocks_any:
                        continue

                    local_engine = IPSCRulesEngine(self._stage)
                    if local_engine.is_valid_position(item, existing + items):
                        item.properties["protected"] = True
                        items.append(item)
                        placed = True
                        break

            if not placed:
                break
        return items

    # ── Target placement ────────────────────────────────────────────────

    def place_target_around(
        self,
        existing: List[StageItem],
        ttype: ItemType,
        engine: IPSCRulesEngine,
        is_moving: bool = False,
        override_min_dist: float | None = None,
    ) -> Optional[StageItem]:
        """Place a target AROUND the shooting area perimeter.

        Rules:
        - Targets are placed OUTSIDE the perimeter polygon
        - ONLY between shooting area and backstop/side walls
        - NEVER inside the shooting area
        - NEVER toward the entrance (normal ny < -0.3)
        - Steel targets: fixed 8m from perimeter
        - All targets must be visible from the shooting area
        """
        if not self._perimeter_poly or len(self._perimeter_poly) < 3:
            return None

        margin = engine.MIN_TARGET_TO_EDGE
        poly = self._perimeter_poly
        n = len(poly)

        w, h, tcolor, tlabel, min_dist_from_edge = self._target_params(ttype, is_moving)

        if override_min_dist is not None:
            min_dist_from_edge = override_min_dist

        # Classify polygon edges for placement:
        # - Backstop zone (priority): edges whose outward normal points toward backstop (ny > 0)
        #   and within 60° of backstop perpendicular
        # - Lateral zone (fallback): side edges (|nx| > 0.7)
        # - Front (excluded): edges with ny < -0.3
        backstop_dx = 0.0
        backstop_dy = 1.0

        back_edges: list[int] = []
        side_edges: list[int] = []
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            seg_len = math.hypot(x2 - x1, y2 - y1)
            if seg_len < 0.3:
                continue
            nx = (y2 - y1) / seg_len
            ny = -(x2 - x1) / seg_len

            dot_n = nx * backstop_dx + ny * backstop_dy
            angle_n = math.degrees(math.acos(max(-1.0, min(1.0, dot_n))))

            if angle_n < 60.0:
                back_edges.append(i)
            elif abs(nx) > 0.7 and ny >= -0.3:
                side_edges.append(i)

        candidate_edges = list(back_edges)
        if not candidate_edges or len(candidate_edges) < 2:
            candidate_edges.extend(side_edges)
        if not candidate_edges or len(candidate_edges) < 2:
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                seg_len = math.hypot(x2 - x1, y2 - y1)
                if seg_len < 0.3:
                    continue
                ny = -(x2 - x1) / seg_len
                if ny >= -0.3:
                    candidate_edges.append(i)
            if not candidate_edges:
                candidate_edges = list(range(n))

        # Guided sampling: pre-calculate available space per edge
        _half_h = h / 2
        max_y = self._stage.depth - MIN_BACKSTOP_DEPTH - _half_h - 0.2
        guided_edges: list[tuple[int, float]] = []
        for e_idx in candidate_edges:
            x1, y1 = poly[e_idx]
            x2, y2 = poly[(e_idx + 1) % n]
            seg_len = math.hypot(x2 - x1, y2 - y1)
            if seg_len < 0.3:
                continue
            n_x = (y2 - y1) / seg_len
            n_y = -(x2 - x1) / seg_len
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2

            if n_x > 0:
                md_x = (self._stage.width - margin - mx) / max(n_x, 0.001)
            elif n_x < 0:
                md_x = (mx - margin) / max(-n_x, 0.001)
            else:
                md_x = float('inf')
            if n_y > 0:
                md_y = (max_y - my) / max(n_y, 0.001)
            elif n_y < 0:
                md_y = (my - margin) / max(-n_y, 0.001)
            else:
                md_y = float('inf')

            max_dist_edge = min(md_x, md_y)
            if max_dist_edge >= min_dist_from_edge:
                guided_edges.append((e_idx, max_dist_edge))

        use_guided = len(guided_edges) >= 2
        max_attempts = getattr(self._config, 'max_attempts', 500)

        for _ in range(max_attempts):
            if use_guided:
                edge_idx, max_dist = random.choice(guided_edges)
            else:
                edge_idx = random.choice(candidate_edges)
                max_dist = max(self._stage.depth, self._stage.width)

            x1, y1 = poly[edge_idx]
            x2, y2 = poly[(edge_idx + 1) % n]
            dx_e = x2 - x1
            dy_e = y2 - y1
            length = math.hypot(dx_e, dy_e)

            t = random.uniform(0.1, 0.9)
            ex = x1 + dx_e * t
            ey = y1 + dy_e * t

            n_x = dy_e / length
            n_y = -dx_e / length
            if max_dist < min_dist_from_edge:
                continue

            dist = random.uniform(
                min_dist_from_edge,
                min(max_dist, min_dist_from_edge + 3.0),
            )
            px = ex + n_x * dist
            py = ey + n_y * dist

            if not (margin <= px <= self._stage.width - margin and
                    margin <= py <= max_y):
                continue

            if point_in_polygon(px, py, poly):
                continue

            if is_behind_shooting_area(px, py, poly):
                continue

            if targets_on_same_line(
                px, py, existing, self._perimeter_poly,
                threshold_deg=SAME_LINE_OF_FIRE_THRESHOLD_DEG,
            ):
                continue

            poly_cx = sum(p[0] for p in self._perimeter_poly) / len(self._perimeter_poly)
            poly_cy = sum(p[1] for p in self._perimeter_poly) / len(self._perimeter_poly)
            rot = compute_target_rotation(px, py, poly_cx, poly_cy, w, h)
            rot += random.uniform(-10, 10)

            if is_moving:
                mov_props = {
                    ItemType.SWINGER: {"amplitude": random.uniform(30, 60),
                                       "speed": random.uniform(0.5, 2.0)},
                    ItemType.DROP_TURNER: {"trigger": "hit",
                                            "fall_time": random.uniform(0.3, 1.0)},
                    ItemType.MOVER: {"distance": random.uniform(2.0, 5.0),
                                     "speed": random.uniform(0.5, 2.0)},
                }
                props = mov_props.get(ttype, {})
            else:
                props = {}

            if ttype == ItemType.METAL_PLATE:
                props["mount_height"] = 1.0

            it = StageItem(0, ttype, px, py, w, h, rot, tcolor, tlabel, properties=props)

            if engine.is_valid_position(it, existing):
                it_obb = item_obb(it)
                ok = True
                if it_obb:
                    for other in existing:
                        if other.item_type in (ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
                                               ItemType.NO_SHOOT):
                            it_is_paper = ttype in (
                                ItemType.PAPER_TARGET, ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
                                ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
                            other_is_paper = other.item_type in (
                                ItemType.PAPER_TARGET, ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
                                ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
                            if it_is_paper and other_is_paper:
                                continue
                            o_obb = item_obb(other)
                            if o_obb and obb_distance(it_obb, o_obb) < engine.MIN_TARGET_TO_TARGET - 0.05:
                                ok = False
                                break
                if ok:
                    return it
        return None

    def place_steel_fallback(
        self,
        existing: List[StageItem],
        ttype: ItemType,
        engine: IPSCRulesEngine,
        min_dist_from_shooter: float = 7.0,
    ) -> Optional[StageItem]:
        """Place steel target as fallback at stage edges.

        When standard perimeter placement fails, this places steel along
        stage edges while maintaining safe distance from the shooting area center.
        """
        if not self._perimeter_poly:
            return None

        poly = self._perimeter_poly
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)

        margin = engine.MIN_TARGET_TO_EDGE
        tcolor = TARGET_COLORS.get("popper" if ttype == ItemType.POPPER else "metal_plate", "#d1d5db")
        w, h = (0.30, 0.30) if ttype == ItemType.POPPER else (0.20, 0.20)
        label = "Popper" if ttype == ItemType.POPPER else "Plate"

        # Generate candidate positions along stage edges
        edge_positions: list[tuple[float, float]] = []
        step = 0.5
        for x_f in [i * step for i in range(int(margin // step), int((self._stage.width - margin) // step))]:
            edge_positions.append((x_f, self._stage.depth - margin))
        for y_f in [i * step for i in range(int(margin // step), int((self._stage.depth - margin) // step))]:
            edge_positions.append((margin, y_f))
        for y_f in [i * step for i in range(int(margin // step), int((self._stage.depth - margin) // step))]:
            edge_positions.append((self._stage.width - margin, y_f))

        random.shuffle(edge_positions)

        for px, py in edge_positions:
            if point_in_polygon(px, py, poly):
                continue
            dist = math.hypot(px - cx, py - cy)
            if dist < min_dist_from_shooter:
                continue

            rot = compute_target_rotation(px, py, cx, cy, w, h)
            props = {"mount_height": 1.0} if ttype == ItemType.METAL_PLATE else {}
            it = StageItem(0, ttype, px, py, w, h, rot, tcolor, label, properties=props)

            if engine.is_valid_position(it, existing):
                it_obb = item_obb(it)
                ok = True
                if it_obb:
                    for other in existing:
                        if other.item_type in (ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
                                               ItemType.NO_SHOOT):
                            o_obb = item_obb(other)
                            if o_obb and obb_distance(it_obb, o_obb) < engine.MIN_TARGET_TO_TARGET - 0.05:
                                ok = False
                                break
                if ok:
                    return it
        return None

    def place_no_shoot(
        self,
        existing: List[StageItem],
        engine: IPSCRulesEngine,
    ) -> Optional[StageItem]:
        """Place a no-shoot IN FRONT OF a paper target.

        No-shoots are positioned on the line from the shooting area center
        toward the paper target, 0.3-0.8m in front of it.
        """
        papers = [it for it in existing if it.item_type == ItemType.PAPER_TARGET]
        if not papers or not self._perimeter_poly:
            return None
        poly = self._perimeter_poly
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)

        max_attempts = getattr(self._config, 'max_attempts', 500)
        for _ in range(max_attempts):
            paper = random.choice(papers)
            dx = paper.x - cx
            dy = paper.y - cy
            dist = math.hypot(dx, dy)
            if dist < 0.5:
                continue
            nx = dx / dist
            ny = dy / dist
            ns_dist = random.uniform(0.3, 0.8)
            x = paper.x - nx * ns_dist
            y = paper.y - ny * ns_dist
            if point_in_polygon(x, y, poly):
                continue
            it = StageItem(0, ItemType.NO_SHOOT, x, y, 0.45, 0.45, 0,
                           TARGET_COLORS.get("no_shoot", "#eab308"), "No-Shoot")
            if engine.is_valid_position(it, existing):
                return it
        return None

    # ── Separation ──────────────────────────────────────────────────────

    def separate_overlapping(
        self,
        items: List[StageItem],
        engine: IPSCRulesEngine,
    ) -> List[StageItem]:
        """Separate targets that are too close to each other or to walls.

        Moves targets to guarantee minimum distance. Removes if impossible.
        """
        targets = [it for it in items if is_scoring_target(it.item_type)]
        walls = [it for it in items if it.item_type in (
            ItemType.WALL, ItemType.BARRIER, ItemType.DOOR, ItemType.HARD_COVER)]
        margin = engine.MIN_TARGET_TO_EDGE

        for _ in range(8):
            changed = False

            for i, t in enumerate(targets):
                if t not in items:
                    continue
                t_obb = item_obb(t)
                if not t_obb:
                    continue

                for other in targets[i + 1:]:
                    if other not in items:
                        continue
                    o_obb = item_obb(other)
                    if not o_obb:
                        continue

                    t_is_paper = t.item_type in (
                        ItemType.PAPER_TARGET, ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
                        ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
                    other_is_paper = other.item_type in (
                        ItemType.PAPER_TARGET, ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
                        ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
                    if t_is_paper and other_is_paper:
                        continue

                    d = obb_distance(t_obb, o_obb)
                    if d < engine.MIN_TARGET_TO_TARGET - 0.03:
                        to_move = t if t.id < other.id else other
                        dx = to_move.x - (t.x if t.id < other.id else other.x)
                        dy = to_move.y - (t.y if t.id < other.id else other.y)
                        dist = math.hypot(dx, dy)
                        if dist < 0.1:
                            dx, dy = 0.5, 0.5
                            dist = math.hypot(dx, dy)
                        nx, ny = dx / dist, dy / dist
                        to_move.x += nx * 0.15
                        to_move.y += ny * 0.15
                        to_move.x = max(margin, min(self._stage.width - margin, to_move.x))
                        to_move.y = max(margin, min(self._stage.depth - margin, to_move.y))
                        changed = True
                        t_obb = item_obb(t)

                for w in walls:
                    if w not in items:
                        continue
                    w_obb = item_obb(w)
                    if not w_obb:
                        continue
                    d = obb_distance(t_obb, w_obb)
                    if d < engine.MIN_TARGET_TO_WALL - 0.03:
                        dx = t.x - w.x
                        dy = t.y - w.y
                        dist = math.hypot(dx, dy)
                        if dist < 0.1:
                            dx, dy = 0.5, 0.5
                            dist = 0.5
                        t.x += (dx / dist) * 0.2
                        t.y += (dy / dist) * 0.2
                        t.x = max(margin, min(self._stage.width - margin, t.x))
                        t.y = max(margin, min(self._stage.depth - margin, t.y))
                        changed = True
                        t_obb = item_obb(t)

            if not changed:
                break

        return items

    # ── Rotation refinement ─────────────────────────────────────────────

    def refine_target_rotations(self, items: List[StageItem]) -> None:
        """Refine target rotations toward the nearest shooting position."""
        positions = [(sp.x, sp.y) for sp in self._stage.shooting_positions]
        if not positions:
            return

        for it in items:
            if not is_scoring_target(it.item_type):
                continue
            nearest = min(
                positions,
                key=lambda pos: math.hypot(pos[0] - it.x, pos[1] - it.y),
            )
            it.rotation = compute_target_rotation(
                it.x, it.y, nearest[0], nearest[1], it.width, it.height,
            )

    # ── Shooting positions ──────────────────────────────────────────────

    def generate_shooting_positions(self) -> List[ShootingPosition]:
        """Generate shooting positions for the stage.

        Creates:
        1. A start position at the front edge of the shooting area
        2. Optionally an intermediate position for complex shapes (H, X, F, ...)
        """
        p = self._perimeter_poly
        if not p or len(p) < 3:
            return []

        positions: list[ShootingPosition] = []
        poly_cx = sum(v[0] for v in p) / len(p)

        front_y = min(v[1] for v in p)
        front_x = sum(v[0] for v in p if abs(v[1] - front_y) < 0.5) / max(
            1, sum(1 for v in p if abs(v[1] - front_y) < 0.5))

        start = ShootingPosition(
            id=1,
            x=round(front_x, 2),
            y=round(front_y + 0.5, 2),
            label="Start",
            is_start=True,
            angle=90.0,
        )
        positions.append(start)

        complex_shapes = {"H", "X", "F", "E", "N", "M", "S", "Z"}
        letter = getattr(self._config, 'letter_shape', 'random')
        if letter in complex_shapes or (letter == "random" and len(p) > 6):
            mid_y = sum(v[1] for v in p) / len(p)
            intermediate = ShootingPosition(
                id=2,
                x=round(poly_cx, 2),
                y=round(mid_y, 2),
                label="Intermediate",
                is_start=False,
                angle=90.0,
            )
            positions.append(intermediate)

        return positions

    def generate_fault_lines(self, existing: List[StageItem]) -> List[StageItem]:
        """Generate strategic fault lines in front of targets."""
        fault_lines: list[StageItem] = []
        targets = [
            it for it in existing
            if it.item_type in (
                ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
                ItemType.POPPER, ItemType.METAL_PLATE,
                ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
            )
        ]
        for target in targets:
            angle = math.radians(target.rotation)
            dist = random.uniform(3.0, 5.0)
            fx = target.x + math.cos(angle) * dist
            fy = target.y + math.sin(angle) * dist
            if self._perimeter_poly and not point_in_polygon(fx, fy, self._perimeter_poly):
                continue
            length = random.uniform(2.0, 4.0)
            rot = target.rotation + random.uniform(-15, 15)
            fl = StageItem(0, ItemType.FAULT_LINE, fx, fy, length, 0.0, rot,
                           TARGET_COLORS.get("fault_line", "#dc2626"), "Fault Line")
            margin = IPSCRulesEngine.MIN_TARGET_TO_EDGE
            if (margin <= fx <= self._stage.width - margin and
                    margin <= fy <= self._stage.depth - margin):
                fault_lines.append(fl)
        return fault_lines
