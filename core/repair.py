"""
Repair strategies for IPSC rule violations.

Provides targeted fixes for common validation violations:
- Target too close to wall → remove wall
- Too many hits per position → add blocking walls
- Insufficient targets → add paper targets
- Backstop too shallow → push targets forward
- Medium/Long: all targets visible from one position → add dividers
"""

from __future__ import annotations

import math
import random
import re
from typing import List

from shapely.geometry import LineString as SLine

from core.collision import item_obb
from core.constants import TARGET_COLORS
from core.geometry import line_intersects_rect, point_in_polygon
from core.ipsc_rules import IPSCRulesEngine
from core.models import ItemType, Stage, StageItem
from core.placement import PlacementEngine
from core.scoring import is_paper_like, is_scoring_target
from core.visibility import get_blocking_walls, is_target_visible


class RepairEngine:
    """Applies targeted repairs to eliminate IPSC rule violations.

    Injected with a PlacementEngine to place new items when needed.
    """

    def __init__(self, placement_engine: PlacementEngine):
        self._placement = placement_engine

    def repair_violations(
        self,
        stage: Stage,
        violations: List[str],
        engine: IPSCRulesEngine,
    ) -> bool:
        """Apply targeted repairs for each violation.

        Returns True if at least one repair was applied.
        """
        repaired = False

        for v_text in violations:
            v_lower = v_text.lower()

            # 1. Target too close to wall → remove the offending wall
            if "troppo vicino a muro" in v_lower:
                if self._repair_target_too_close_to_wall(stage, v_text, engine):
                    repaired = True

            # 2. Too many hits per position → block excess targets
            elif "colpi conteggiabili" in v_lower and "max 9" in v_lower:
                if self._repair_too_many_hits(stage, v_text, engine):
                    repaired = True

            # 3. Insufficient targets → add paper targets
            elif "bersagli insufficienti" in v_lower:
                if self._repair_insufficient_targets(stage, engine):
                    repaired = True

            # 4. Backstop too shallow → push targets forward
            elif "dietro bersagli insufficiente" in v_lower:
                if self._repair_backstop(stage, engine):
                    repaired = True

            # 5. Obstacles too close → remove the second one
            elif "ostacolo" in v_lower and "vicino" in v_lower:
                if self._repair_obstacles_too_close(stage, v_text):
                    repaired = True

            # 6. Medium/long: all targets visible from one position
            elif "tutti i" in v_lower and "bersagli sono" in v_lower:
                if self._repair_all_visible(stage, v_text, engine):
                    repaired = True

        return repaired

    def add_restrictive_walls(
        self,
        stage: Stage,
        existing: List[StageItem],
        engine: IPSCRulesEngine,
    ) -> List[StageItem]:
        """Add walls to enforce max 9 hits per position (Reg. 1.2.1).

        Medium/Long courses must not allow engaging all targets from one position.
        Walls are placed to selectively block line of sight to excess targets.
        """
        interior_samples = self._placement._interior_samples
        perimeter_poly = self._placement._perimeter_poly

        if not interior_samples or not perimeter_poly:
            return []

        targets = [it for it in existing if is_scoring_target(it.item_type)]
        if not targets:
            return []

        max_hits = IPSCRulesEngine.MAX_HITS_PER_POSITION
        new_walls: list[StageItem] = []
        max_walls = max(2, len(targets) // 2)

        if stage.shooting_positions:
            positions = [(sp.x, sp.y) for sp in stage.shooting_positions]
        else:
            cx, cy = stage.width / 2, stage.depth / 2
            positions = [(cx, cy), (cx - 2, cy), (cx + 2, cy), (cx, cy + 2)]

        for obs_x, obs_y in positions:
            if len(new_walls) >= max_walls:
                break

            all_blockers = get_blocking_walls(existing) + new_walls
            visible_targets = []
            for t in targets:
                visible = True
                for w in all_blockers:
                    if line_intersects_rect(
                        (obs_x, obs_y),
                        (t.x, t.y),
                        w.x,
                        w.y,
                        w.width,
                        w.height,
                        w.rotation,
                    ):
                        visible = False
                        break
                if visible:
                    visible_targets.append(t)

            total_hits = sum(
                2
                if is_paper_like(t.item_type)
                or t.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
                else 1
                for t in visible_targets
            )

            if total_hits <= max_hits:
                continue

            visible_targets.sort(
                key=lambda t: math.hypot(t.x - obs_x, t.y - obs_y),
                reverse=True,
            )

            for t in visible_targets:
                if len(new_walls) >= max_walls:
                    break

                hits_this = (
                    2
                    if (
                        is_paper_like(t.item_type)
                        or t.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
                    )
                    else 1
                )
                if total_hits - hits_this < max_hits:
                    continue

                dx = t.x - obs_x
                dy = t.y - obs_y
                dist = math.hypot(dx, dy)
                if dist < 2.0:
                    continue
                nx, ny = dx / dist, dy / dist

                wall_dist = dist * random.uniform(0.35, 0.65)
                wx = obs_x + nx * wall_dist
                wy = obs_y + ny * wall_dist

                if point_in_polygon(wx, wy, perimeter_poly):
                    continue

                margin = IPSCRulesEngine.MIN_TARGET_TO_EDGE
                if not (
                    margin <= wx <= stage.width - margin and margin <= wy <= stage.depth - margin
                ):
                    continue

                wall_angle = math.degrees(math.atan2(ny, nx)) + 90
                wall_len = random.uniform(1.5, 3.0)

                new_wall = StageItem(
                    0,
                    ItemType.BARRIER,
                    wx,
                    wy,
                    wall_len,
                    0.2,
                    wall_angle,
                    TARGET_COLORS.get("barrier", "#fbbf24"),
                    "Barriera ristr.",
                )

                test_items = existing + new_walls
                if not engine.is_valid_position(new_wall, test_items):
                    continue

                test_blockers = all_blockers + [new_wall]
                still_visible = False
                for ox2, oy2 in positions:
                    vis = True
                    for w in test_blockers:
                        if line_intersects_rect(
                            (ox2, oy2),
                            (t.x, t.y),
                            w.x,
                            w.y,
                            w.width,
                            w.height,
                            w.rotation,
                        ):
                            vis = False
                            break
                    if vis:
                        still_visible = True
                        break

                if still_visible and not self._placement.blocks_entrance_corridor(
                    new_wall, stage.width
                ):
                    new_walls.append(new_wall)
                    total_hits -= hits_this
                    all_blockers = get_blocking_walls(existing) + new_walls

        return new_walls

    # ── Repair implementations ──────────────────────────────────────────

    def _repair_target_too_close_to_wall(
        self,
        stage: Stage,
        v_text: str,
        engine: IPSCRulesEngine,
    ) -> bool:
        m = re.search(r"#(\d+)", v_text)
        if not m:
            return False
        target_id = int(m.group(1))
        target = stage.get_item(target_id)
        if not target:
            return False

        walls = [
            it
            for it in stage.items
            if it.item_type in (ItemType.WALL, ItemType.BARRIER, ItemType.DOOR, ItemType.HARD_COVER)
        ]
        for w in walls:
            t_obb = item_obb(target)
            w_obb = item_obb(w)
            if t_obb and w_obb:
                from core.collision import min_distance_between

                dist = min_distance_between(t_obb, w_obb)
                if dist < engine.MIN_TARGET_TO_WALL:
                    stage.remove_item(w.id)
                    return True
        return False

    def _repair_too_many_hits(
        self,
        stage: Stage,
        v_text: str,
        engine: IPSCRulesEngine,
    ) -> bool:
        m = re.search(r"\(([\d.]+),\s*([\d.]+)\)", v_text)
        if not m:
            return False
        px, py = float(m.group(1)), float(m.group(2))

        targets = [it for it in stage.items if is_scoring_target(it.item_type)]
        visible_targets: list[StageItem] = []
        for t in targets:
            t_obb = item_obb(t)
            if t_obb is None:
                continue
            walls_check = get_blocking_walls(stage.items)
            line = SLine([(px, py), (t.x, t.y)])
            blocked = False
            for w in walls_check:
                wob = item_obb(w)
                if wob and line.intersects(wob):
                    blocked = True
                    break
            if not blocked:
                visible_targets.append(t)

        total_hits = sum(
            2
            if is_paper_like(t.item_type)
            or t.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
            else 1
            for t in visible_targets
        )

        if total_hits <= 9:
            return False

        visible_targets.sort(
            key=lambda t: math.hypot(t.x - px, t.y - py),
            reverse=True,
        )

        repaired = False
        for t_block in visible_targets:
            if total_hits <= 9:
                break
            dx = t_block.x - px
            dy = t_block.y - py
            dist = math.hypot(dx, dy)
            if dist < 1.5:
                continue
            nx, ny = dx / dist, dy / dist
            wx = px + nx * dist * 0.4
            wy = py + ny * dist * 0.4
            margin = engine.MIN_TARGET_TO_EDGE
            if not (margin <= wx <= stage.width - margin and margin <= wy <= stage.depth - margin):
                continue

            wall = StageItem(
                0,
                ItemType.BARRIER,
                wx,
                wy,
                1.5,
                0.2,
                math.degrees(math.atan2(ny, nx)),
                TARGET_COLORS.get("barrier", "#fbbf24"),
                "Barriera ripar.",
            )
            test_blockers = get_blocking_walls(stage.items + [wall])
            if is_target_visible(t_block, test_blockers, self._placement._interior_samples):
                stage.add_item(wall)
                repaired = True
                hits_blocked = (
                    2
                    if (
                        is_paper_like(t_block.item_type)
                        or t_block.item_type
                        in (ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
                    )
                    else 1
                )
                total_hits -= hits_blocked

        return repaired

    def _repair_insufficient_targets(
        self,
        stage: Stage,
        engine: IPSCRulesEngine,
    ) -> bool:
        min_t = IPSCRulesEngine.MIN_TARGETS
        current = len([it for it in stage.items if is_scoring_target(it.item_type)])
        needed = min_t - current

        repaired = False
        for _ in range(needed * 2):
            it = self._placement.place_target_around(stage.items, ItemType.PAPER_TARGET, engine)
            if it:
                stage.add_item(it)
                repaired = True
                current += 1
                if current >= min_t:
                    break
        return repaired

    def _repair_backstop(
        self,
        stage: Stage,
        engine: IPSCRulesEngine,
    ) -> bool:
        targets = [it for it in stage.items if is_scoring_target(it.item_type)]
        max_allowed_y = stage.depth - IPSCRulesEngine.MIN_BACKSTOP_DEPTH + 0.3
        repaired = False
        for t in targets:
            if t.y + t.height / 2 > max_allowed_y:
                t.y = max_allowed_y - t.height / 2
                repaired = True
        return repaired

    def _repair_obstacles_too_close(
        self,
        stage: Stage,
        v_text: str,
    ) -> bool:
        m = re.findall(r"#(\d+)", v_text)
        if len(m) >= 2:
            id2 = int(m[1])
            item2 = stage.get_item(id2)
            if item2 and not item2.properties.get("perimeter"):
                stage.remove_item(id2)
                return True
        return False

    def _repair_all_visible(
        self,
        stage: Stage,
        v_text: str,
        engine: IPSCRulesEngine,
    ) -> bool:
        m = re.search(r"\(([\d.]+),\s*([\d.]+)\)", v_text)
        if not m:
            return False
        px, py = float(m.group(1)), float(m.group(2))

        targets = [it for it in stage.items if is_scoring_target(it.item_type)]
        if not targets:
            return False

        farthest = max(targets, key=lambda t: math.hypot(t.x - px, t.y - py))
        dx = farthest.x - px
        dy = farthest.y - py
        dist = math.hypot(dx, dy)
        if dist <= 2.0:
            return False

        nx, ny = dx / dist, dy / dist
        wx = px + nx * dist * 0.4
        wy = py + ny * dist * 0.4
        margin = engine.MIN_TARGET_TO_EDGE
        if not (margin <= wx <= stage.width - margin and margin <= wy <= stage.depth - margin):
            return False

        wall = StageItem(
            0,
            ItemType.BARRIER,
            wx,
            wy,
            2.0,
            0.2,
            math.degrees(math.atan2(ny, nx)),
            TARGET_COLORS.get("barrier", "#fbbf24"),
            "Barriera div.",
        )
        stage.add_item(wall)
        return True
