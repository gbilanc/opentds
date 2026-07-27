"""
Models for the shooting path editor.

Represents the shooter's movement path through the stage as an ordered
sequence of waypoints, each with associated target engagements.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


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
        # Renumber
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
    ) -> ShootingPath:
        """Create a ShootingPath from Stage.shooting_positions.

        Optionally pre-compute visible targets for each waypoint.
        """
        path = ShootingPath()
        for i, sp in enumerate(positions):
            engaged = []
            visible = []
            if targets:
                for t in targets:
                    # Simple proximity-based engagement assignment
                    dx = t.x - sp.x
                    dy = t.y - sp.y
                    dist = (dx * dx + dy * dy) ** 0.5
                    if dist < 15.0:  # within reasonable range
                        visible.append(t.id)
            wp = PathWaypoint(
                id=sp.id,
                x=sp.x,
                y=sp.y,
                label=sp.label or f"P{sp.id}",
                is_start=sp.is_start,
                order=i,
                engaged_target_ids=engaged,
                visible_target_ids=visible,
            )
            path.add_waypoint(wp)
        return path
