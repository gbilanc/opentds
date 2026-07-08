# core/generator.py
"""Generatore procedurale di stage con vincoli IPSC."""
from __future__ import annotations
import random
import math
from typing import List, Tuple, Optional
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

from core.models import Stage, StageItem, ItemType
from core.ipsc_rules import IPSCRulesEngine


@dataclass
class GeneratorConfig:
    stage_width: float = 20.0
    stage_depth: float = 15.0
    num_targets: int = 8
    num_steel: int = 2
    num_moving: int = 1  # swinger / drop_turner / mover
    num_walls: int = 4
    num_barriers: int = 2
    include_fault_lines: bool = True
    include_no_shoots: bool = True
    difficulty: str = "medium"  # easy | medium | hard
    seed: Optional[int] = None
    max_attempts: int = 500


@dataclass
class GeneratorResult:
    stage: Stage
    score: float
    attempts: int


class StageGenerator:
    """Generatore procedurale constraint-based."""

    def __init__(self, config: GeneratorConfig):
        self.config = config
        if config.seed is not None:
            random.seed(config.seed)

    def generate(self) -> GeneratorResult:
        stage = Stage(name="Stage Generato", width=self.config.stage_width,
                      depth=self.config.stage_depth)
        engine = IPSCRulesEngine(stage)
        items: List[StageItem] = []
        attempts = 0

        # 1. Genera muri/barriere procedurali (scheletro dello stage)
        items.extend(self._generate_walls(stage))
        items.extend(self._generate_barriers(stage))

        # 2. Posiziona bersagli con rejection sampling
        paper_count = self.config.num_targets - self.config.num_steel
        for _ in range(paper_count):
            it = self._place_target(stage, items, ItemType.PAPER_TARGET, engine)
            if it:
                items.append(it)
            attempts += 1

        for _ in range(self.config.num_steel):
            it = self._place_target(stage, items, ItemType.STEEL_TARGET, engine)
            if it:
                items.append(it)
            attempts += 1

        # 3. Bersagli mobili
        moving_types = [ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER]
        for i in range(self.config.num_moving):
            mtype = moving_types[i % len(moving_types)]
            it = self._place_moving_target(stage, items, mtype, engine)
            if it:
                items.append(it)
            attempts += 1

        # 4. No-shoots (opzionali)
        if self.config.include_no_shoots:
            ns_count = max(1, self.config.num_targets // 4)
            for _ in range(ns_count):
                it = self._place_no_shoot(stage, items, engine)
                if it:
                    items.append(it)
                attempts += 1

        # 4. Fault lines (post-processing, vicino a bersagli per creare zone di tiro)
        if self.config.include_fault_lines:
            items.extend(self._generate_fault_lines(stage, items))

        # Assegna tutti gli item allo stage
        for it in items:
            stage.add_item(it)

        score = self._score_stage(stage, items)
        return GeneratorResult(stage=stage, score=score, attempts=attempts)

    def _generate_walls(self, stage: Stage) -> List[StageItem]:
        """Genera muri come coperture e corridoi."""
        walls = []
        count = self.config.num_walls
        # Difficoltà influenza lunghezza e disposizione
        if self.config.difficulty == "easy":
            avg_len = 3.0
        elif self.config.difficulty == "hard":
            avg_len = 5.0
        else:
            avg_len = 4.0

        for _ in range(count):
            # Posizione casuale, evitando il centro come corridoi principali
            x = random.uniform(1.5, stage.width - 1.5)
            y = random.uniform(1.5, stage.depth - 1.5)
            length = random.uniform(avg_len * 0.7, avg_len * 1.3)
            rotation = random.choice([0, 90, 45, -45])
            w = StageItem(0, ItemType.WALL, x, y, length, 0.2, rotation, "#475569", "Muro")
            walls.append(w)
        return walls

    def _generate_barriers(self, stage: Stage) -> List[StageItem]:
        """Genera barriere (obstacles bassi da superare)."""
        barriers = []
        for _ in range(self.config.num_barriers):
            x = random.uniform(1.5, stage.width - 1.5)
            y = random.uniform(1.5, stage.depth - 1.5)
            w = random.uniform(1.5, 3.0)
            rot = random.choice([0, 90])
            b = StageItem(0, ItemType.BARRIER, x, y, w, 0.15, rot, "#fbbf24", "Barriera")
            barriers.append(b)
        return barriers

    def _place_target(self, stage: Stage, existing: List[StageItem],
                      ttype: ItemType, engine: IPSCRulesEngine) -> Optional[StageItem]:
        """Rejection sampling per posizionare un bersaglio valido."""
        for _ in range(self.config.max_attempts):
            x = random.uniform(engine.MIN_TARGET_TO_EDGE, stage.width - engine.MIN_TARGET_TO_EDGE)
            y = random.uniform(engine.MIN_TARGET_TO_EDGE, stage.depth - engine.MIN_TARGET_TO_EDGE)
            rot = random.uniform(-30, 30)
            if ttype == ItemType.STEEL_TARGET:
                w, h = 0.30, 0.30
                color = "#3b82f6"
                label = "Steel"
            else:
                w, h = 0.45, 0.45
                color = "#ef4444"
                label = "Paper"
            it = StageItem(0, ttype, x, y, w, h, rot, color, label)
            if engine.is_valid_position(it, existing):
                return it
        return None

    def _place_moving_target(self, stage: Stage, existing: List[StageItem],
                             mtype: ItemType, engine: IPSCRulesEngine) -> Optional[StageItem]:
        for _ in range(self.config.max_attempts):
            x = random.uniform(engine.MIN_TARGET_TO_EDGE, stage.width - engine.MIN_TARGET_TO_EDGE)
            y = random.uniform(engine.MIN_TARGET_TO_EDGE, stage.depth - engine.MIN_TARGET_TO_EDGE)
            rot = random.uniform(-30, 30)
            if mtype == ItemType.SWINGER:
                w, h = 0.45, 0.45
                color = "#a855f7"
                label = "Swinger"
                props = {"amplitude": random.uniform(30, 60), "speed": random.uniform(0.5, 2.0)}
            elif mtype == ItemType.DROP_TURNER:
                w, h = 0.45, 0.45
                color = "#14b8a6"
                label = "Drop Turner"
                props = {"trigger": "hit", "fall_time": random.uniform(0.3, 1.0)}
            else:  # MOVER
                w, h = 0.45, 0.45
                color = "#f97316"
                label = "Mover"
                props = {"distance": random.uniform(2.0, 5.0), "speed": random.uniform(0.5, 2.0)}
            it = StageItem(0, mtype, x, y, w, h, rot, color, label, properties=props)
            if engine.is_valid_position(it, existing):
                return it
        return None

    def _place_no_shoot(self, stage: Stage, existing: List[StageItem],
                        engine: IPSCRulesEngine) -> Optional[StageItem]:
        """Posiziona un no-shoot vicino a un bersaglio esistente."""
        targets = [it for it in existing if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET)]
        if not targets:
            return None
        for _ in range(self.config.max_attempts):
            # Vicino a un bersaglio casuale
            target = random.choice(targets)
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(1.2, 2.5)
            x = target.x + math.cos(angle) * dist
            y = target.y + math.sin(angle) * dist
            it = StageItem(0, ItemType.NO_SHOOT, x, y, 0.45, 0.45, 0, "#f87171", "No-Shoot")
            if engine.is_valid_position(it, existing):
                return it
        return None

    def _generate_fault_lines(self, stage: Stage, existing: List[StageItem]) -> List[StageItem]:
        """Genera fault lines strategiche davanti ai bersagli."""
        fault_lines = []
        targets = [it for it in existing if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET)]
        for target in targets:
            # Fault line ~3-5m davanti al bersaglio (assumendo direzione verso stage)
            angle = math.radians(target.rotation)
            dist = random.uniform(3.0, 5.0)
            fx = target.x + math.cos(angle) * dist
            fy = target.y + math.sin(angle) * dist
            length = random.uniform(2.0, 4.0)
            rot = target.rotation + random.uniform(-15, 15)
            fl = StageItem(0, ItemType.FAULT_LINE, fx, fy, length, 0.0, rot, "#dc2626", "Fault Line")
            # Verifica bounds
            half = length / 2
            margin = IPSCRulesEngine.MIN_TARGET_TO_EDGE
            if (margin <= fx and fx <= stage.width - margin and
                    margin <= fy and fy <= stage.depth - margin):
                fault_lines.append(fl)
        return fault_lines

    def _score_stage(self, stage: Stage, items: List[StageItem]) -> float:
        """Valuta la qualità dello stage (più alto = migliore)."""
        score = 0.0
        targets = [it for it in items if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET)]
        walls = [it for it in items if it.item_type in (
            ItemType.WALL, ItemType.BARRIER)]

        # Più bersagli = più colpi possibili
        score += len(targets) * 10

        # Steel varietà
        steel = [it for it in targets if it.item_type == ItemType.STEEL_TARGET]
        score += len(steel) * 5

        # Bersagli mobili = difficoltà extra
        moving = [it for it in items if it.item_type in (ItemType.SWINGER, ItemType.MOVER, ItemType.DROP_TURNER)]
        score += len(moving) * 15

        # Distanza media tra bersagli (diversità angolazioni)
        if len(targets) >= 2:
            total_dist = 0.0
            count = 0
            for i, a in enumerate(targets):
                for b in targets[i + 1:]:
                    total_dist += IPSCRulesEngine._distance(a, b)
                    count += 1
            if count > 0:
                avg_dist = total_dist / count
                # Premia distanze medie 2-5m
                score += max(0, 20 - abs(avg_dist - 3.5) * 5)

        # Uso area (copertura)
        if len(walls) > 0:
            score += len(walls) * 3

        # Difficoltà bonus
        if self.config.difficulty == "hard":
            score *= 1.2

        return round(score, 2)
