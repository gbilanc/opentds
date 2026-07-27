"""
Generatore procedurale di stage con vincoli IPSC — Orchestratore.

Modulo orchestratore che coordina:
- core/shapes.py: forme alfabetiche, poligoni, perimetri
- core/placement.py: PlacementEngine (posizionamento bersagli/ostacoli)
- core/visibility.py: VisibilityEngine (linea di vista)
- core/repair.py: RepairEngine (riparazione violazioni)
- core/scoring.py: scoring, metadati, attivatori
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

from core.constants import (
    MIN_TARGET_TO_EDGE,
    MIN_TARGET_TO_WALL,
    MIN_TARGET_TO_TARGET,
    MIN_TARGET_TO_BARRIER,
    MIN_BACKSTOP_DEPTH,
    MIN_STEEL_DISTANCE,
    MIN_STEEL_PLACEMENT_DISTANCE,
    MIN_POLY_DIM,
    FRONT_OPEN_GAP,
    INTERIOR_SAMPLE_COUNT,
    MAX_ACTIVATOR_DISTANCE,
    MAX_ACTIVATOR_MOVING_DISTANCE,
    MAX_ACTIVATED_PER_ACTIVATOR,
    MAX_HITS_PER_POSITION,
    COURSE_TARGET_DISTRIBUTION,
    TARGET_DIMENSIONS,
    TARGET_COLORS,
    SAME_LINE_OF_FIRE_THRESHOLD_DEG,
    ACTIVATOR_SECTOR_ANGLE_DEG,
)
from core.models import Stage, StageItem, ItemType, CourseType
from core.ipsc_rules import IPSCRulesEngine
from core.geometry import (
    point_in_polygon,
    polygon_center,
    segments_intersect,
    line_intersects_rect,
    euclidean_distance,
    angle_between_points,
    validate_polygon,
)
from core.collision import item_obb, min_distance_between as obb_distance
from core.shapes import (
    LETTER_SHAPES,
    generate_perimeter_polygon as _generate_perimeter_polygon,
    perimeter_to_items as _perimeter_to_items,
    polygon_to_shapely as _perimeter_to_shapely_polygon,
)
from shapely.geometry import Polygon as ShapelyPolygon, Point as ShapelyPoint
from core.scoring import (
    is_paper_like as _is_paper_like,
    is_steel_like as _is_steel_like,
    is_scoring_target as _is_scoring_target,
    is_obstacle as _is_obstacle,
    is_blocking_wall as _is_blocking_wall,
    resolve_target_counts as _resolve_target_counts,
    create_activator_relationships as _create_activator_relationships,
    populate_stage_metadata as _populate_stage_metadata,
    score_stage as _score_stage,
)
from core.placement import PlacementEngine, compute_target_rotation
from core.visibility import (
    get_blocking_walls,
    is_target_visible,
    ensure_target_visibility,
    sample_interior_points,
)
from core.repair import RepairEngine


# ── Helper per estrarre poligono dalle properties ──────────────────────────

def _get_perimeter_poly(stage: Stage) -> list[tuple[float, float]] | None:
    """Recupera il poligono dell'area di tiro dalle properties dello stage.

    Usa prima `perimeter_poly` salvato dal generatore, poi tenta
    la ricostruzione dalle fault-line perimetrali.
    """
    poly = stage.properties.get("perimeter_poly")
    if poly:
        return [(round(x, 2), round(y, 2)) for x, y in poly]
    # Tentativo di ricostruzione dalle fault-line perimetrali
    # Nota: import ritardato per evitare dipendenza circolare core→ui→core
    try:
        from ui.editor.stage_scene import _build_polygon_from_fault_lines
        return _build_polygon_from_fault_lines(stage.items)
    except ImportError:
        return None


def _assign_ids(items: list[StageItem]) -> None:
    """Assegna ID univoci progressivi a tutti gli item."""
    next_id = max((it.id for it in items if it.id > 0), default=0) + 1
    for it in items:
        if it.id == 0:
            it.id = next_id
            next_id += 1


# ── Dataclass di configurazione ──────────────────────────────────────────

@dataclass
class GeneratorConfig:
    stage_width: float = 20.0
    stage_depth: float = 15.0
    num_targets: int = 8
    num_steel: int = 2          # backward compat: ripartito tra poppers e plates
    num_poppers: int = 0        # 0 = auto-da-num_steel (60%)
    num_plates: int = 0         # 0 = auto-da-num_steel (40%)
    num_moving: int = 1         # swinger / drop_turner / mover
    num_mini: int = 0           # mini target cartacei (App. B3)
    num_walls: int = 1
    num_barriers: int = 4
    include_fault_lines: bool = True
    include_no_shoots: bool = True
    include_activators: bool = True  # poppers/plates che attivano bersagli
    difficulty: str = "medium"  # easy | medium | hard
    delimitation: str = "fault_lines"  # fault_lines | barriers | walls | mixed
    seed: Optional[int] = None
    max_attempts: int = 500
    discipline: str = "ipsc_pistol"  # ipsc_pistol | mini_rifle | shotgun
    letter_shape: str = "random"  # random | Q (quadrato) | O (rettangolo) | T | U | W | X | Y | Z
    course_type: str = ""  # "short" | "medium" | "long" | "" = non classificato
    auto_distribution: bool = True  # se True, calcola bersagli da course_type


@dataclass
class Phase1Config:
    """Configurazione per la Fase 1: generazione dell'area di tiro."""
    stage_width: float = 20.0
    stage_depth: float = 15.0
    letter_shape: str = "random"  # random | Q | O | T | U | W | X | Y | Z
    rotation: float = 0.0       # gradi 0-360
    delimitation: str = "fault_lines"  # fault_lines | barriers | walls | mixed
    seed: Optional[int] = None
    discipline: str = "ipsc_pistol"


@dataclass
class Phase2Config:
    """Configurazione per la Fase 2: posizionamento bersagli e ostacoli."""
    shooting_positions: list[tuple[float, float, bool]] = None  # (x, y, is_start)
    num_targets: int = 8
    num_poppers: int = 1
    num_plates: int = 1
    num_mini: int = 0
    num_moving: int = 1
    num_walls: int = 1
    num_barriers: int = 4
    include_no_shoots: bool = True
    include_activators: bool = True
    difficulty: str = "medium"
    course_type: str = ""
    auto_distribution: bool = True
    seed: Optional[int] = None
    max_attempts: int = 500
    placed_walls: list[dict] = None  # [{x, y, width, rotation}, ...]
    placed_barriers: list[dict] = None  # [{x, y, width, rotation}, ...]

    def __post_init__(self):
        if self.shooting_positions is None:
            self.shooting_positions = []
        if self.placed_walls is None:
            self.placed_walls = []
        if self.placed_barriers is None:
            self.placed_barriers = []


@dataclass
class GeneratorResult:
    stage: Stage
    score: float
    attempts: int


# ── StageGenerator: Orchestratore ─────────────────────────────────────────

class StageGenerator:
    """Generatore procedurale constraint-based per stage IPSC.

    Coordina PlacementEngine, VisibilityEngine, RepairEngine e Scoring
    per produrre stage completi e validati.
    """

    def __init__(self, config: GeneratorConfig):
        self.config = config
        if config.seed is not None:
            random.seed(config.seed)
        self._perimeter_poly: list[tuple[float, float]] = []
        self._interior_samples: list[tuple[float, float]] = []
        self._obb_cache: dict[int, object] = {}

    # ── Fase 1: Generazione perimetro area di tiro ─────────────────────

    @staticmethod
    def generate_perimeter(phase1: Phase1Config) -> tuple[Stage, list[tuple[float, float]]]:
        """Genera solo il perimetro dell'area di tiro (Fase 1).

        Crea uno Stage con le dimensioni specificate, genera il poligono
        dell'area di tiro a forma di lettera, e produce gli item perimetrali
        (fault lines o barriere). Non posiziona bersagli né ostacoli.

        Returns:
            (stage, perimeter_poly) — stage con solo perimetro popolato
        """
        stage = Stage(
            name="Stage - Fase 1",
            width=phase1.stage_width,
            depth=phase1.stage_depth,
        )

        poly = _generate_perimeter_polygon(
            stage,
            letter_shape=phase1.letter_shape,
            rotation=phase1.rotation,
        )
        stage.properties["perimeter_poly"] = [
            (round(x, 2), round(y, 2)) for x, y in poly
        ]
        items = _perimeter_to_items(
            poly,
            style=phase1.delimitation,
            stage_width=phase1.stage_width,
            stage_depth=phase1.stage_depth,
        )

        _assign_ids(items)
        stage.items = items
        stage._next_id = max((it.id for it in items), default=0) + 1
        return stage, poly

    # ── Fase 2: Posizionamento bersagli e ostacoli ─────────────────────

    @staticmethod
    def place_targets_and_obstacles(
        stage: Stage,
        phase2: Phase2Config,
        perimeter_poly: list[tuple[float, float]] | None = None,
    ) -> GeneratorResult:
        """Posiziona bersagli, ostacoli, no-shoot e shooting positions
        in uno stage che ha già un perimetro area di tiro definito (Fase 2).

        Il poligono del perimetro viene recuperato da:
        1. `perimeter_poly` passato direttamente
        2. `stage.properties["perimeter_poly"]`

        Returns:
            GeneratorResult con stage completo e score
        """
        poly = perimeter_poly
        if poly is None:
            poly = _get_perimeter_poly(stage)
        if not poly:
            raise ValueError(
                "Nessun perimetro area di tiro definito. "
                "Esegui prima la Fase 1 (generate_perimeter)."
            )

        cfg = phase2
        if cfg.seed is not None:
            random.seed(cfg.seed)

        # Inizializza engine
        gen_config = GeneratorConfig(
            stage_width=stage.width,
            stage_depth=stage.depth,
            num_walls=cfg.num_walls,
            num_barriers=cfg.num_barriers,
            max_attempts=cfg.max_attempts,
            seed=cfg.seed,
        )
        placement = PlacementEngine(poly, gen_config, stage)
        interior = sample_interior_points(poly, 20)
        repair = RepairEngine(placement)

        engine = IPSCRulesEngine(stage)
        engine.set_discipline("ipsc_pistol")
        items = list(stage.items)
        attempts = 0

        # Risoluzione conteggi
        has_explicit_counts = (
            cfg.num_targets > 0 or cfg.num_poppers > 0 or cfg.num_plates > 0
            or cfg.num_mini > 0 or cfg.num_moving > 0
        )
        use_auto = cfg.auto_distribution and cfg.course_type and not has_explicit_counts

        resolved = _resolve_target_counts(
            cfg.num_targets, 0, cfg.num_poppers, cfg.num_plates,
            cfg.num_mini, cfg.num_moving,
            use_auto, cfg.course_type if use_auto else "",
        )
        num_paper = resolved["paper"]
        num_poppers = resolved["poppers"]
        num_plates = resolved["plates"]
        num_mini = resolved["mini"]
        num_moving = resolved["moving"]
        include_activators = cfg.include_activators and (num_poppers > 0 or num_plates > 0)

        # 1a. Mini targets
        mini_placed = 0
        for _ in range(max(num_mini * 5, 20)):
            if mini_placed >= num_mini:
                break
            it = placement.place_target_around(
                items, ItemType.MINI_TARGET, engine)
            if it:
                items.append(it)
                mini_placed += 1
            attempts += 1

        # 1b. Paper targets
        paper_placed = 0
        for _ in range(max(num_paper * 5, 30)):
            if paper_placed >= num_paper:
                break
            it = placement.place_target_around(
                items, ItemType.PAPER_TARGET, engine)
            if it:
                items.append(it)
                paper_placed += 1
            attempts += 1

        # 2. Poppers
        poppers_placed = 0
        for _ in range(max(num_poppers * 5, 30)):
            if poppers_placed >= num_poppers:
                break
            it = placement.place_target_around(
                items, ItemType.POPPER, engine,
                override_min_dist=MIN_STEEL_PLACEMENT_DISTANCE,
            )
            if it:
                it.properties["calibrated"] = True
                it.properties["calibration_pf"] = 125
                items.append(it)
                poppers_placed += 1
            attempts += 1
        # Fallback: reduced distance, then edge placement
        if poppers_placed < num_poppers:
            for reduced in [5.0, 3.0]:
                if poppers_placed >= num_poppers:
                    break
                for _ in range(30):
                    if poppers_placed >= num_poppers:
                        break
                    it = placement.place_target_around(
                        items, ItemType.POPPER, engine,
                        override_min_dist=reduced,
                    )
                    if it:
                        it.properties["calibrated"] = True
                        it.properties["calibration_pf"] = 125
                        items.append(it)
                        poppers_placed += 1
                    attempts += 1
        if poppers_placed < num_poppers:
            for _ in range(50):
                if poppers_placed >= num_poppers:
                    break
                it = placement.place_steel_fallback(
                    items, ItemType.POPPER, engine, min_dist_from_shooter=7.0)
                if it:
                    it.properties["calibrated"] = True
                    it.properties["calibration_pf"] = 125
                    items.append(it)
                    poppers_placed += 1
                attempts += 1

        # 3. Metal plates
        plates_placed = 0
        for _ in range(max(num_plates * 5, 30)):
            if plates_placed >= num_plates:
                break
            it = placement.place_target_around(
                items, ItemType.METAL_PLATE, engine,
                override_min_dist=MIN_STEEL_PLACEMENT_DISTANCE,
            )
            if it:
                items.append(it)
                plates_placed += 1
            attempts += 1
        if plates_placed < num_plates:
            for reduced in [5.0, 3.0]:
                if plates_placed >= num_plates:
                    break
                for _ in range(30):
                    if plates_placed >= num_plates:
                        break
                    it = placement.place_target_around(
                        items, ItemType.METAL_PLATE, engine,
                        override_min_dist=reduced,
                    )
                    if it:
                        items.append(it)
                        plates_placed += 1
                    attempts += 1
        if plates_placed < num_plates:
            for _ in range(50):
                if plates_placed >= num_plates:
                    break
                it = placement.place_steel_fallback(
                    items, ItemType.METAL_PLATE, engine, min_dist_from_shooter=7.0)
                if it:
                    items.append(it)
                    plates_placed += 1
                attempts += 1

        # 4. Reg. 4.3.3.3
        has_plates = any(it.item_type == ItemType.METAL_PLATE for it in items)
        has_paper_or_popper = any(
            it.item_type in (ItemType.PAPER_TARGET, ItemType.POPPER)
            for it in items)
        if has_plates and not has_paper_or_popper:
            for _ in range(5):
                it = placement.place_target_around(
                    items, ItemType.PAPER_TARGET, engine)
                if it:
                    items.append(it)
                    break
                attempts += 1

        # 5. Reach minimum targets
        min_targets = IPSCRulesEngine.MIN_TARGETS
        while len([x for x in items if _is_scoring_target(x.item_type)]) < min_targets:
            it = placement.place_target_around(
                items, ItemType.PAPER_TARGET, engine)
            if it:
                items.append(it)
            attempts += 1
            if attempts > 50:
                break

        # 6. Activators
        _assign_ids(items)
        if include_activators:
            activator_items = [it for it in items
                               if it.item_type in (ItemType.POPPER, ItemType.METAL_PLATE)]
            if activator_items:
                _create_activator_relationships(stage, items, activator_items, poly)

        # 7. Moving targets
        moving_types = [ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER]
        moving_placed = 0
        for _ in range(max(num_moving * 5, 25)):
            if moving_placed >= num_moving:
                break
            mtype = moving_types[moving_placed % len(moving_types)]
            it = placement.place_target_around(items, mtype, engine, is_moving=True)
            if it:
                items.append(it)
                moving_placed += 1
            attempts += 1

        # 8. User-placed walls/barriers (from Fase 2 UI)
        for w_data in cfg.placed_walls:
            w_item = StageItem(
                0, ItemType.WALL,
                w_data["x"], w_data["y"],
                width=w_data.get("width", 3.0),
                height=0.2,
                rotation=w_data.get("rotation", 0.0),
                color=TARGET_COLORS.get("wall", "#475569"),
                label="Muro (utente)",
                properties={"user_placed": True},
            )
            items.append(w_item)

        for b_data in cfg.placed_barriers:
            b_item = StageItem(
                0, ItemType.BARRIER,
                b_data["x"], b_data["y"],
                width=b_data.get("width", 2.0),
                height=0.15,
                rotation=b_data.get("rotation", 0.0),
                color=TARGET_COLORS.get("barrier", "#fbbf24"),
                label="Barriera (utente)",
                properties={"user_placed": True},
            )
            items.append(b_item)

        # 8b. Auto-generated walls/barriers
        walls_before = len(items)
        items.extend(placement.generate_walls(items))
        items.extend(placement.generate_barriers(items))

        # 9. Restrictive walls
        items.extend(repair.add_restrictive_walls(stage, items, engine))

        # 10. No-shoots
        if cfg.include_no_shoots:
            ns_count = max(1, len([x for x in items if _is_scoring_target(x.item_type)]) // 4)
            ns_placed = 0
            for _ in range(ns_count * 3):
                if ns_placed >= ns_count:
                    break
                it = placement.place_no_shoot(items, engine)
                if it:
                    items.append(it)
                    ns_placed += 1
                attempts += 1
            if ns_placed < ns_count and poly:
                papers = [x for x in items
                          if x.item_type in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET)]
                if papers:
                    for _ in range(ns_count - ns_placed):
                        p = random.choice(papers)
                        nx = p.x + 0.4
                        ny = p.y
                        margin = IPSCRulesEngine.MIN_TARGET_TO_EDGE
                        if (margin <= nx <= stage.width - margin and
                            margin <= ny <= stage.depth - margin):
                            ns = StageItem(0, ItemType.NO_SHOOT, nx, ny,
                                           0.45, 0.45, 0,
                                           TARGET_COLORS.get("no_shoot", "#eab308"), "No-Shoot")
                            items.append(ns)
                            ns_placed += 1

        # 11. Separation
        items = placement.separate_overlapping(items, engine)

        _assign_ids(items)
        stage.items = items
        stage._next_id = max((it.id for it in items), default=0) + 1

        # 12. Shooting positions
        if cfg.shooting_positions:
            from core.models import ShootingPosition
            stage.shooting_positions = [
                ShootingPosition(
                    id=i + 1, x=x, y=y,
                    label="Start" if is_start else f"Pos {i + 1}",
                    is_start=is_start, angle=90.0,
                )
                for i, (x, y, is_start) in enumerate(cfg.shooting_positions)
            ]
        else:
            stage.shooting_positions = placement.generate_shooting_positions()

        placement.refine_target_rotations(items)

        _populate_stage_metadata(
            stage, cfg.difficulty, num_poppers, num_plates, num_moving)

        score = _score_stage(
            stage, items,
            perimeter_poly=poly,
            interior_samples=interior,
            get_blocking_walls_fn=lambda: get_blocking_walls(items),
            is_target_visible_fn=lambda t, b: is_target_visible(t, b, interior),
            config_difficulty=cfg.difficulty,
        )

        return GeneratorResult(stage=stage, score=score, attempts=attempts)

    # ── Generazione completa (Fase 1 + 2) ──────────────────────────────

    def generate(self) -> GeneratorResult:
        """Genera uno stage IPSC completo (Fase 1 + 2).

        Mantenuto per retrocompatibilità. Per il nuovo flusso a 2 fasi,
        usa `generate_perimeter()` e `place_targets_and_obstacles()`.
        """
        cfg = self.config
        disc = cfg.discipline

        for retry in range(3):
            phase1 = Phase1Config(
                stage_width=cfg.stage_width,
                stage_depth=cfg.stage_depth,
                letter_shape=cfg.letter_shape,
                delimitation=cfg.delimitation,
                seed=cfg.seed,
                discipline=disc,
            )
            stage, poly = self.generate_perimeter(phase1)
            self._perimeter_poly = poly
            self._interior_samples = sample_interior_points(poly, 20)

            has_steel = (
                cfg.num_steel > 0 or cfg.num_poppers > 0 or cfg.num_plates > 0
                or (cfg.auto_distribution and cfg.course_type)
            )
            phase2 = Phase2Config(
                num_targets=cfg.num_targets,
                num_poppers=cfg.num_poppers,
                num_plates=cfg.num_plates,
                num_mini=cfg.num_mini,
                num_moving=cfg.num_moving,
                num_walls=cfg.num_walls,
                num_barriers=cfg.num_barriers,
                include_no_shoots=cfg.include_no_shoots,
                include_activators=cfg.include_activators,
                difficulty=cfg.difficulty,
                course_type=cfg.course_type,
                auto_distribution=cfg.auto_distribution,
                seed=cfg.seed,
                max_attempts=cfg.max_attempts,
            )
            result = self.place_targets_and_obstacles(stage, phase2, poly)

            engine = IPSCRulesEngine(result.stage)
            engine.set_discipline(disc)
            v = engine.validate()

            if not v.violations:
                return result

            critical = [x for x in v.violations if "no-shoot" not in x.lower()]
            if not critical:
                return result

            if cfg.seed is not None:
                random.seed(cfg.seed + retry + 1)
            else:
                random.seed()

        return result

    # ── Metodo legacy (mantenuto per retrocompatibilità) ───────────────

    def _generate_once(self, cfg: GeneratorConfig, disc: str) -> GeneratorResult:
        """Esegue una singola generazione wrapper (retrocompatibilità)."""
        phase1 = Phase1Config(
            stage_width=cfg.stage_width,
            stage_depth=cfg.stage_depth,
            letter_shape=cfg.letter_shape,
            delimitation=cfg.delimitation,
            seed=cfg.seed,
            discipline=disc,
        )
        stage, poly = self.generate_perimeter(phase1)
        self._perimeter_poly = poly
        self._interior_samples = sample_interior_points(poly, 20)

        phase2 = Phase2Config(
            num_targets=cfg.num_targets,
            num_poppers=cfg.num_poppers,
            num_plates=cfg.num_plates,
            num_mini=cfg.num_mini,
            num_moving=cfg.num_moving,
            num_walls=cfg.num_walls,
            num_barriers=cfg.num_barriers,
            include_no_shoots=cfg.include_no_shoots,
            include_activators=cfg.include_activators,
            difficulty=cfg.difficulty,
            course_type=cfg.course_type,
            auto_distribution=cfg.auto_distribution,
            seed=cfg.seed,
            max_attempts=cfg.max_attempts,
        )
        return self.place_targets_and_obstacles(stage, phase2, poly)
