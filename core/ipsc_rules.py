"""
Motore di vincoli IPSC per la generazione e validazione stage.

Usa Shapely per collision detection OBB (oriented bounding box),
con regole IPSC 2025: minimi/massimi bersagli, no-shoot, shooting
positions, fault line closure, dimensioni stage.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List

from core.models import Stage, StageItem, ItemType
from core.collision import (
    make_stage_boundary,
    item_obb,
    min_distance_between,
    contains,
)
from shapely.geometry import Point


@dataclass
class ConstraintResult:
    ok: bool
    violations: List[str] = None

    def __post_init__(self):
        if self.violations is None:
            self.violations = []


class IPSCRulesEngine:
    """Validatore e generatore constraint-based per stage IPSC.

    Utilizza Shapely per calcoli geometrici precisi (OBB, distanza minima,
    point-in-polygon).

    Regole validate:
    - Distanze minime (bordo, muri, bersagli, barriere)
    - Numero bersagli (min 8, max 32 per stage standard)
    - Numero steel (max 40% del totale)
    - No-shoot consigliati (almeno 1 ogni 8 bersagli)
    - Dimensioni stage (min 10×8m, max 40×30m)
    - Backstop minimo 3m dietro i bersagli
    """

    # Distanze minime in metri
    MIN_TARGET_TO_EDGE = 1.0
    MIN_TARGET_TO_WALL = 0.8
    MIN_TARGET_TO_TARGET = 0.8
    MIN_TARGET_TO_BARRIER = 0.5
    MIN_WALL_TO_EDGE = 0.3
    MIN_OBSTACLE_GAP = 0.1  # distanza minima tra ostacoli (muri, barriere, porte)
    MIN_BACKSTOP_DEPTH = 3.0

    # Limiti IPSC
    MIN_TARGETS = 8
    MAX_STEEL_PCT = 0.4        # max 40% steel
    MAX_STAGE_WIDTH = 40.0
    MAX_STAGE_DEPTH = 30.0
    RECOMMENDED_NO_SHOOT_INTERVAL = 8  # 1 no-shoot ogni 8 paper

    def __init__(self, stage: Stage, discipline: str = "ipsc_pistol"):
        self.stage = stage
        self._discipline = discipline

    def set_discipline(self, discipline: str):
        """Cambia la disciplina (ipsc_pistol | mini_rifle | shotgun).
        Regola i limiti di conseguenza."""
        self._discipline = discipline

    @property
    def MIN_STAGE_WIDTH(self) -> float:
        if self._discipline == "mini_rifle":
            return 15.0
        elif self._discipline == "shotgun":
            return 8.0
        return 10.0

    @property
    def MIN_STAGE_DEPTH(self) -> float:
        if self._discipline == "mini_rifle":
            return 10.0
        elif self._discipline == "shotgun":
            return 8.0
        return 8.0

    @property
    def MAX_TARGETS(self) -> int:
        if self._discipline == "mini_rifle":
            return 40
        elif self._discipline == "shotgun":
            return 32
        return 32

    # ── Validazione completa ──────────────────────────────────────────────

    def validate(self) -> ConstraintResult:
        """Valida l'intero stage corrente."""
        violations: List[str] = []

        violations.extend(self._validate_dimensions())
        violations.extend(self._validate_target_counts())
        violations.extend(self._validate_spatial())
        violations.extend(self._validate_shooting_positions())

        return ConstraintResult(ok=len(violations) == 0, violations=violations)

    # ── Validazioni di conteggio ──────────────────────────────────────────

    def _validate_dimensions(self) -> List[str]:
        """Verifica dimensioni stage entro i limiti IPSC."""
        v = []
        w, d = self.stage.width, self.stage.depth

        if w < self.MIN_STAGE_WIDTH:
            v.append(f"Stage troppo stretto: {w}m (min {self.MIN_STAGE_WIDTH}m)")
        if d < self.MIN_STAGE_DEPTH:
            v.append(f"Stage troppo corto: {d}m (min {self.MIN_STAGE_DEPTH}m)")
        if w > self.MAX_STAGE_WIDTH:
            v.append(f"Stage troppo largo: {w}m (max {self.MAX_STAGE_WIDTH}m)")
        if d > self.MAX_STAGE_DEPTH:
            v.append(f"Stage troppo profondo: {d}m (max {self.MAX_STAGE_DEPTH}m)")

        # Backstop minimo
        deepest_target = max(
            (it.y + it.height / 2 for it in self.stage.items
             if it.item_type in (ItemType.PAPER_TARGET, ItemType.STEEL_TARGET)),
            default=0,
        )
        backstop_space = d - deepest_target
        if 0 < backstop_space < self.MIN_BACKSTOP_DEPTH and deepest_target > 0:
            v.append(
                f"Spazio dietro bersagli insufficiente: {backstop_space:.1f}m "
                f"(min {self.MIN_BACKSTOP_DEPTH}m)")

        return v

    def _validate_target_counts(self) -> List[str]:
        """Verifica conteggi bersagli secondo regole IPSC."""
        v: List[str] = []

        paper = [it for it in self.stage.items
                 if it.item_type == ItemType.PAPER_TARGET]
        steel = [it for it in self.stage.items
                 if it.item_type == ItemType.STEEL_TARGET]
        no_shoots = [it for it in self.stage.items
                     if it.item_type == ItemType.NO_SHOOT]
        moving = [it for it in self.stage.items
                  if it.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER,
                                      ItemType.MOVER)]

        total_scoring = len(paper) + len(steel)

        if total_scoring < self.MIN_TARGETS:
            v.append(
                f"Bersagli insufficienti: {total_scoring} "
                f"(min {self.MIN_TARGETS})")
        if total_scoring > self.MAX_TARGETS:
            v.append(
                f"Troppi bersagli: {total_scoring} "
                f"(max {self.MAX_TARGETS})")

        if len(paper) > 0 and len(steel) / total_scoring > self.MAX_STEEL_PCT:
            v.append(
                f"Troppi bersagli steel: {len(steel)}/{total_scoring} "
                f"(max {self.MAX_STEEL_PCT:.0%})")

        # No-shoot consigliati
        if len(paper) >= self.RECOMMENDED_NO_SHOOT_INTERVAL:
            expected_ns = max(1, len(paper) // self.RECOMMENDED_NO_SHOOT_INTERVAL)
            if len(no_shoots) < expected_ns:
                v.append(
                    f"No-shoot insufficienti: {len(no_shoots)} "
                    f"(consigliati almeno {expected_ns} per {len(paper)} paper)")

        return v

    def _validate_spatial(self) -> List[str]:
        """Verifica vincoli spaziali con OBB Shapely."""
        violations: List[str] = []

        targets = [it for it in self.stage.items if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET, ItemType.NO_SHOOT)]
        walls = [it for it in self.stage.items if it.item_type in (
            ItemType.WALL, ItemType.DOOR)]
        barriers = [it for it in self.stage.items
                    if it.item_type == ItemType.BARRIER]

        for t in targets:
            t_obb = item_obb(t)
            if t_obb is None:
                continue

            # Bordo stage
            edge_margin = make_stage_boundary(
                self.stage.width, self.stage.depth,
                margin=self.MIN_TARGET_TO_EDGE)
            if not contains(edge_margin, t_obb.centroid):
                violations.append(
                    f"Bersaglio #{t.id} troppo vicino al bordo stage "
                    f"(min {self.MIN_TARGET_TO_EDGE}m)")

            # Distanza da muri/porte
            for w in walls:
                w_obb = item_obb(w)
                if w_obb and min_distance_between(t_obb, w_obb) < self.MIN_TARGET_TO_WALL:
                    violations.append(
                        f"Bersaglio #{t.id} troppo vicino a muro #{w.id} "
                        f"({self.MIN_TARGET_TO_WALL}m)")

            # Distanza da barriere
            for b in barriers:
                b_obb = item_obb(b)
                if b_obb and min_distance_between(t_obb, b_obb) < self.MIN_TARGET_TO_BARRIER:
                    violations.append(
                        f"Bersaglio #{t.id} troppo vicino a barriera #{b.id} "
                        f"({self.MIN_TARGET_TO_BARRIER}m)")

            # Distanza da altri bersagli
            for other in targets:
                if other.id == t.id:
                    continue
                other_obb = item_obb(other)
                if other_obb and min_distance_between(t_obb, other_obb) < self.MIN_TARGET_TO_TARGET:
                    violations.append(
                        f"Bersaglio #{t.id} troppo vicino a bersaglio #{other.id} "
                        f"({self.MIN_TARGET_TO_TARGET}m)")

        # Ostacoli non devono sovrapporsi (muri, barriere, porte)
        obstacles = walls + barriers
        for i, a in enumerate(obstacles):
            a_obb = item_obb(a)
            if a_obb is None:
                continue
            for b in obstacles[i + 1:]:
                b_obb = item_obb(b)
                if b_obb and min_distance_between(a_obb, b_obb) < self.MIN_OBSTACLE_GAP:
                    violations.append(
                        f"Ostacolo #{a.id} ({a.label}) troppo vicino a #{b.id} ({b.label}) "
                        f"(gap min {self.MIN_OBSTACLE_GAP}m)")

        return violations

    # ── Validazione posizione candidato ───────────────────────────────────

    def is_valid_position(self, item: StageItem, existing: List[StageItem]) -> bool:
        """Verifica se un nuovo item può essere posizionato validamente."""
        item_obb_geom = item_obb(item)
        if item_obb_geom is None:
            return True

        # Bordo stage
        edge_margin = make_stage_boundary(
            self.stage.width, self.stage.depth, margin=self.MIN_TARGET_TO_EDGE)
        if not contains(edge_margin, item_obb_geom.centroid):
            return False

        is_obstacle = item.item_type in (ItemType.WALL, ItemType.BARRIER, ItemType.DOOR)

        # Collisioni con item esistenti
        for other in existing:
            other_obb_geom = item_obb(other)
            if other_obb_geom is None:
                continue

            # Ostacolo vs ostacolo: non possono sovrapporsi
            if is_obstacle and other.item_type in (ItemType.WALL, ItemType.BARRIER, ItemType.DOOR):
                if min_distance_between(item_obb_geom, other_obb_geom) < self.MIN_OBSTACLE_GAP:
                    return False
            elif other.item_type in (ItemType.WALL, ItemType.DOOR):
                if min_distance_between(item_obb_geom, other_obb_geom) < self.MIN_TARGET_TO_WALL:
                    return False
            elif other.item_type in (ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
                                      ItemType.NO_SHOOT):
                if min_distance_between(item_obb_geom, other_obb_geom) < self.MIN_TARGET_TO_TARGET:
                    return False
            elif other.item_type == ItemType.BARRIER:
                if min_distance_between(item_obb_geom, other_obb_geom) < self.MIN_TARGET_TO_BARRIER:
                    return False

        return True

    # ── Helpers ───────────────────────────────────────────────────────────

    def _validate_shooting_positions(self) -> List[str]:
        """Verifica che le posizioni di tiro siano valide."""
        v = []
        boundary = make_stage_boundary(self.stage.width, self.stage.depth)

        for sp in self.stage.shooting_positions:
            if not contains(boundary, Point(sp.x, sp.y)):
                v.append(f"Posizione di tiro #{sp.id} fuori dallo stage")

            # Verifica accessibilità (non dentro un muro)
            for item in self.stage.items:
                if item.item_type in (ItemType.WALL, ItemType.BARRIER, ItemType.DOOR):
                    obb = item_obb(item)
                    if obb and contains(obb, Point(sp.x, sp.y)):
                        v.append(f"Posizione di tiro #{sp.id} dentro {item.label} #{item.id}")
                        break

        # Deve esserci almeno una posizione di partenza
        starts = [sp for sp in self.stage.shooting_positions if sp.is_start]
        if not starts and self.stage.shooting_positions:
            v.append("Nessuna posizione di partenza (is_start=True) definita")

        return v

    def count_targets(self) -> dict:
        """Conta i bersagli per tipo."""

        paper = [it for it in self.stage.items
                 if it.item_type == ItemType.PAPER_TARGET]
        steel = [it for it in self.stage.items
                 if it.item_type == ItemType.STEEL_TARGET]
        moving = [it for it in self.stage.items
                  if it.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER,
                                      ItemType.MOVER)]
        no_shoots = [it for it in self.stage.items
                     if it.item_type == ItemType.NO_SHOOT]
        return {
            "paper": len(paper),
            "steel": len(steel),
            "moving": len(moving),
            "no_shoots": len(no_shoots),
            "total_scoring": len(paper) + len(steel),
        }
