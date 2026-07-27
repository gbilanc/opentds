"""
Models for the shooting path editor.

Represents the shooter's movement path through the stage as an ordered
sequence of waypoints, each with associated target engagements.

Supports shortest-path ordering and barrier avoidance.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PathWaypoint:
    """A waypoint on the shooter's path.

    Maps to a ShootingPosition but adds engagement metadata and
    ordering information for the path visualization.
    """
    id: int
    x: float = 0.0
    y: float = 0.0
    label: str = ""
    is_start: bool = False
    order: int = 0  # position in the path sequence
    engaged_target_ids: List[int] = field(default_factory=list)
    # targets visible/engageable from this waypoint (auto-computed)
    visible_target_ids: List[int] = field(default_factory=list)


@dataclass
class ShootingPath:
    """The shooter's complete movement path through the stage.

    Stored in Stage.properties["shooting_path"] for serialization.
    """
    waypoints: List[PathWaypoint] = field(default_factory=list)
    color: str = "#3b82f6"  # blue polyline
    visible: bool = True

    @property
    def ordered_waypoints(self) -> List[PathWaypoint]:
        """Return waypoints sorted by their order field."""
        return sorted(self.waypoints, key=lambda w: w.order)

    def add_waypoint(self, wp: PathWaypoint) -> None:
        """Add a waypoint and reassign order."""
        wp.order = len(self.waypoints)
        self.waypoints.append(wp)

    def remove_waypoint(self, wp_id: int) -> bool:
        """Remove a waypoint by ID and renumber order."""
        for i, wp in enumerate(self.waypoints):
            if wp.id == wp_id:
                self.waypoints.pop(i)
                break
        else:
            return False
        for i, wp in enumerate(sorted(self.waypoints, key=lambda w: w.order)):
            wp.order = i
        return True

    def reorder(self, wp_ids: List[int]) -> None:
        """Reorder waypoints to match the given ID sequence."""
        id_to_wp = {wp.id: wp for wp in self.waypoints}
        ordered = [id_to_wp[wid] for wid in wp_ids if wid in id_to_wp]
        for i, wp in enumerate(ordered):
            wp.order = i
        self.waypoints = ordered

    @staticmethod
    def from_shooting_positions(
        positions: list,
        targets: list | None = None,
        blockers: list | None = None,
    ) -> ShootingPath:
        """Create a ShootingPath from Stage.shooting_positions.

        Ordina le posizioni con il percorso pi breve (algoritmo nearest-neighbor)
        ed evita l'attraversamento di barriere/muri.

        Args:
            positions: Lista di ShootingPosition
            targets: Lista di StageItem (bersagli) per calcolo visibilit
            blockers: Lista di StageItem (muri, barriere, hard cover) da evitare
        """
        from core.geometry import line_intersects_rect
        from core.models import ItemType

        if not positions:
            return ShootingPath()

        # Trova la posizione di partenza (start), altrimenti usa la prima
        start_pos = None
        others = []
        for sp in positions:
            if getattr(sp, 'is_start', False) and start_pos is None:
                start_pos = sp
            else:
                others.append(sp)
        if start_pos is None and positions:
            start_pos = positions[0]
            others = list(positions[1:])

        # Blocker types
        blocking_types = {
            ItemType.WALL, ItemType.BARRIER, ItemType.DOOR,
            ItemType.HARD_COVER,
        }

        # Nearest-neighbor ordering con barrier avoidance
        ordered_sp = [start_pos]
        remaining = list(others)

        while remaining:
            last = ordered_sp[-1]
            # Trova il pi vicino tra i rimanenti, evitando barriere
            nearest = None
            nearest_dist = float('inf')
            nearest_path_ok = False

            for sp in remaining:
                dx = sp.x - last.x
                dy = sp.y - last.y
                dist = math.hypot(dx, dy)

                # Verifica se il segmento last -> sp attraversa barriere
                path_blocked = False
                if blockers and dist > 0.5:
                    for wall in blockers:
                        if wall.item_type in blocking_types:
                            if line_intersects_rect(
                                (last.x, last.y), (sp.x, sp.y),
                                wall.x, wall.y, wall.width, wall.height,
                                getattr(wall, 'rotation', 0),
                            ):
                                path_blocked = True
                                break

                # Priorit percorso senza barriere, poi distanza
                if nearest is None:
                    nearest = sp
                    nearest_dist = dist
                    nearest_path_ok = not path_blocked
                elif path_blocked and not nearest_path_ok:
                    # Entrambi bloccati: scegli il pi vicino
                    if dist < nearest_dist:
                        nearest = sp
                        nearest_dist = dist
                elif not path_blocked and nearest_path_ok:
                    # Entrambi liberi: scegli il pi vicino
                    if dist < nearest_dist:
                        nearest = sp
                        nearest_dist = dist
                elif not path_blocked and nearest_path_ok is False:
                    # Questo libero, nearest bloccato: scegli questo
                    nearest = sp
                    nearest_dist = dist
                    nearest_path_ok = True
                # else: nearest libero, questo bloccato: tieni nearest

            if nearest:
                ordered_sp.append(nearest)
                remaining.remove(nearest)

        # Crea ShootingPath con l'ordinamento ottimale
        path = ShootingPath()
        for i, sp in enumerate(ordered_sp):
            engaged = []
            visible = []
            if targets:
                for t in targets:
                    dx = t.x - sp.x
                    dy = t.y - sp.y
                    dist = math.hypot(dx, dy)
                    if dist < 15.0:
                        visible.append(t.id)
            wp = PathWaypoint(
                id=getattr(sp, 'id', i + 1),
                x=getattr(sp, 'x', 0),
                y=getattr(sp, 'y', 0),
                label=getattr(sp, 'label', '') or f"P{getattr(sp, 'id', i + 1)}",
                is_start=getattr(sp, 'is_start', False),
                order=i,
                engaged_target_ids=engaged,
                visible_target_ids=visible,
            )
            path.add_waypoint(wp)
        return path
