# core/ipsc_rules.py
"""Motore di vincoli IPSC per la generazione e validazione stage."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple
import math

from core.models import Stage, StageItem, ItemType


@dataclass
class ConstraintResult:
    ok: bool
    violations: List[str] = None

    def __post_init__(self):
        if self.violations is None:
            self.violations = []


class IPSCRulesEngine:
    """Validatore e generatore constraint-based per stage IPSC."""

    # Distanze minime in metri (valori di default, editabili)
    MIN_TARGET_TO_EDGE = 1.0
    MIN_TARGET_TO_WALL = 0.8
    MIN_TARGET_TO_TARGET = 0.8
    MIN_TARGET_TO_BARRIER = 0.5
    MIN_WALL_TO_EDGE = 0.3
    MIN_BACKSTOP_DEPTH = 3.0  # area sicura dietro bersaglio

    def __init__(self, stage: Stage):
        self.stage = stage

    def validate(self) -> ConstraintResult:
        """Valida l'intero stage corrente."""
        violations = []
        targets = [it for it in self.stage.items if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET, ItemType.NO_SHOOT)]
        walls = [it for it in self.stage.items if it.item_type in (
            ItemType.WALL, ItemType.BARRIER, ItemType.DOOR)]

        for t in targets:
            # Bordo stage
            if not self._in_bounds_with_margin(t, self.MIN_TARGET_TO_EDGE):
                violations.append(f"Bersaglio #{t.id} troppo vicino al bordo stage")
            # Distanza da muri
            for w in walls:
                if self._distance(t, w) < self.MIN_TARGET_TO_WALL:
                    violations.append(f"Bersaglio #{t.id} troppo vicino a muro/barriera #{w.id}")
            # Distanza da altri bersagli
            for other in targets:
                if other.id != t.id and self._distance(t, other) < self.MIN_TARGET_TO_TARGET:
                    violations.append(f"Bersaglio #{t.id} troppo vicino a bersaglio #{other.id}")

        return ConstraintResult(ok=len(violations) == 0, violations=violations)

    def is_valid_position(self, item: StageItem, existing: List[StageItem]) -> bool:
        """Verifica se un nuovo item può essere posizionato validamente."""
        # Bordo stage
        if not self._in_bounds_with_margin(item, self.MIN_TARGET_TO_EDGE):
            return False
        # Collisione con muri esistenti
        for other in existing:
            if other.item_type in (ItemType.WALL, ItemType.BARRIER, ItemType.DOOR):
                if self._distance(item, other) < self.MIN_TARGET_TO_WALL:
                    return False
            elif other.item_type in (ItemType.PAPER_TARGET, ItemType.STEEL_TARGET, ItemType.NO_SHOOT):
                if self._distance(item, other) < self.MIN_TARGET_TO_TARGET:
                    return False
            elif other.item_type == ItemType.BARRIER:
                if self._distance(item, other) < self.MIN_TARGET_TO_BARRIER:
                    return False
        return True

    def _in_bounds_with_margin(self, it: StageItem, margin: float) -> bool:
        half_w = it.width / 2
        half_h = it.height / 2
        cx, cy = it.x, it.y
        # Considera bounding box ruotata semplificata
        r = max(half_w, half_h)
        return (
            cx - r >= margin and cx + r <= self.stage.width - margin and
            cy - r >= margin and cy + r <= self.stage.depth - margin
        )

    @staticmethod
    def _distance(a: StageItem, b: StageItem) -> float:
        """Distanza Euclidea tra centri."""
        dx = a.x - b.x
        dy = a.y - b.y
        return math.hypot(dx, dy)
