# core/generator.py
"""Generatore procedurale di stage con vincoli IPSC.

Modulo orchestratore: delega la logica specializzata a:
- core/shapes.py: forme alfabetiche, poligoni, perimetri
- core/placement.py: posizionamento bersagli/ostacoli
- core/scoring.py: scoring, metadati, attivatori
"""
from __future__ import annotations
import random
import math
import time
from typing import List, Tuple, Optional
from dataclasses import dataclass

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
    letter_shape: str = "random"  # random | Q (quadrato) | O (rettangolo) | X | Y | Z | W
    course_type: str = ""  # "short" | "medium" | "long" | "" = non classificato
    auto_distribution: bool = True  # se True, calcola bersagli da course_type


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
        self._perimeter_poly: List[Tuple[float, float]] = []  # vertici poligono area di tiro
        self._interior_samples: List[Tuple[float, float]] = []  # punti interni per visibility check
        self._obb_cache: dict[int, object] = {}  # cache OBB per item (F2.4)

    def _get_obb(self, item) -> object | None:
        """OBB con cache. Invalida se l'item viene modificato."""
        if item.id not in self._obb_cache:
            self._obb_cache[item.id] = item_obb(item)
        return self._obb_cache[item.id]

    def _invalidate_obb_cache(self, item_id: int | None = None):
        """Invalida la cache OBB. Se item_id è None, invalida tutto."""
        if item_id is None:
            self._obb_cache.clear()
        else:
            self._obb_cache.pop(item_id, None)

    def generate(self) -> GeneratorResult:
        """Genera uno stage IPSC.

        Genera una volta, applica post-processing per ridurre le
        violazioni, e restituisce il risultato.
        """
        cfg = self.config
        disc = cfg.discipline

        # Tenta fino a 3 seed diversi
        for retry in range(3):
            result = self._generate_once(cfg, disc)
            engine = IPSCRulesEngine(result.stage)
            engine.set_discipline(disc)
            v = engine.validate()

            if not v.violations:
                return result

            # Ignora soft violations (no-shoot raccomandati)
            critical = [x for x in v.violations if "no-shoot" not in x.lower()]
            if not critical:
                return result

            # Se abbiamo un seed iniziale, usa incremento deterministico
            # invece di random.seed() (che usa entropia di sistema)
            if cfg.seed is not None:
                random.seed(cfg.seed + retry + 1)
            else:
                random.seed()

        return result

    def _generate_once(self, cfg: GeneratorConfig, disc: str) -> GeneratorResult:
        """Esegue una singola generazione di stage (senza validazione)."""
        if disc == "mini_rifle":
            w = cfg.stage_width or 30.0
            d = cfg.stage_depth or 20.0
        elif disc == "shotgun":
            w = cfg.stage_width or 15.0
            d = cfg.stage_depth or 12.0
        else:
            w = cfg.stage_width
            d = cfg.stage_depth

        # Assicura dimensioni minime per evitare backstop violations
        min_depth_needed = IPSCRulesEngine.MIN_BACKSTOP_DEPTH + 5.0
        if d < min_depth_needed:
            d = min_depth_needed

        ct = None
        if cfg.course_type in ("short", "medium", "long"):
            ct = CourseType(cfg.course_type)
        stage = Stage(name="Stage Generato", width=w, depth=d, course_type=ct)
        engine = IPSCRulesEngine(stage)
        engine.set_discipline(disc)
        items: List[StageItem] = []
        attempts = 0

        # 1. Genera perimetro AREA DI TIRO (lettera dell'alfabeto)
        has_steel = (
            cfg.num_steel > 0 or cfg.num_poppers > 0 or cfg.num_plates > 0
            or (cfg.auto_distribution and cfg.course_type)
        )
        poly = _generate_perimeter_polygon(
            stage,
            letter_shape=cfg.letter_shape,
            has_steel=has_steel,
        )
        self._perimeter_poly = poly
        stage.properties["perimeter_poly"] = [(round(x, 2), round(y, 2)) for x, y in poly]
        self._interior_samples = self._sample_interior_points(20)
        items.extend(_perimeter_to_items(poly, style=cfg.delimitation))

        # ── Risolvi conteggi bersagli da course_type ──
        resolved = _resolve_target_counts(
            cfg.num_targets, cfg.num_steel, cfg.num_poppers, cfg.num_plates,
            cfg.num_mini, cfg.num_moving,
            cfg.auto_distribution, cfg.course_type,
        )
        num_paper = resolved["paper"]
        num_poppers = resolved["poppers"]
        num_plates = resolved["plates"]
        num_mini = resolved["mini"]
        num_moving = resolved["moving"]
        include_activators = cfg.include_activators and (num_poppers > 0 or num_plates > 0)

        # 2. Posiziona bersagli INTORNO all'area di tiro (fuori dal perimetro)
        min_targets = IPSCRulesEngine.MIN_TARGETS

        # 2a. Paper targets + mini targets (mescolati per varietà)
        combined_paper = num_paper + num_mini
        paper_placed = 0
        for _ in range(combined_paper * 3):
            if paper_placed >= combined_paper:
                break
            # Alterna mini e paper
            if paper_placed < num_mini:
                ttype = ItemType.MINI_TARGET if paper_placed % 2 == 0 else ItemType.PAPER_TARGET
            else:
                ttype = ItemType.PAPER_TARGET
            it = self._place_target_around(stage, items, ttype, engine)
            if it:
                items.append(it)
                paper_placed += 1
            attempts += 1

        # 2b. Poppers calibrati (App. C1-C2)
        poppers_placed = 0
        for _ in range(num_poppers * 3):
            if poppers_placed >= num_poppers:
                break
            it = self._place_target_around(stage, items, ItemType.POPPER, engine)
            if it:
                # Proprietà popper calibrato
                it.properties["calibrated"] = True
                it.properties["calibration_pf"] = 125
                items.append(it)
                poppers_placed += 1
            attempts += 1

        # 2c. Metal plates non calibrati (App. C3)
        plates_placed = 0
        for _ in range(num_plates * 3):
            if plates_placed >= num_plates:
                break
            it = self._place_target_around(stage, items, ItemType.METAL_PLATE, engine)
            if it:
                items.append(it)
                plates_placed += 1
            attempts += 1

        # 2d. Reg. 4.3.3.3: se ci sono piatti metallici, serve almeno
        #     un bersaglio carta o Popper che assegni punti
        has_plates = any(it.item_type == ItemType.METAL_PLATE for it in items)
        has_paper_or_popper = any(
            it.item_type in (ItemType.PAPER_TARGET, ItemType.POPPER)
            for it in items)
        if has_plates and not has_paper_or_popper:
            for _ in range(5):
                it = self._place_target_around(
                    stage, items, ItemType.PAPER_TARGET, engine)
                if it:
                    items.append(it)
                    break
                attempts += 1

        # 2e. Se non abbiamo abbastanza bersagli, aggiungi paper
        fill_attempts = 0
        while len([x for x in items if _is_scoring_target(x.item_type)]) < min_targets:
            it = self._place_target_around(stage, items, ItemType.PAPER_TARGET, engine)
            if it:
                items.append(it)
            attempts += 1
            fill_attempts += 1
            if fill_attempts > 50:
                break

        # 2e. Pre-assegna ID a tutti gli item (prima degli attivatori)
        all_ids = {it.id for it in items if it.id > 0}
        next_id = max(all_ids) + 1 if all_ids else 1
        for it in items:
            if it.id == 0:
                it.id = next_id
                next_id += 1

        # 2f. Attivatori: collega poppers/plates a paper target vicini
        if include_activators:
            activator_items = [it for it in items
                               if it.item_type in (ItemType.POPPER, ItemType.METAL_PLATE)]
            if activator_items:
                _create_activator_relationships(stage, items, activator_items, self._perimeter_poly)

        # 3. Bersagli mobili
        moving_types_list = [ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER]
        for i in range(num_moving):
            mtype = moving_types_list[i % len(moving_types_list)]
            it = self._place_target_around(stage, items, mtype, engine, is_moving=True)
            if it:
                items.append(it)
            attempts += 1

        # 4. Muri/barriere FUORI dall'area di tiro
        items.extend(self._generate_walls(stage, items))
        items.extend(self._generate_barriers(stage, items))

        # 5. Aggiunge muri/barriere restrittivi per max 9 colpi/posizione
        items.extend(self._add_restrictive_walls(stage, items, engine))

        # 6. No-shoots (con fallback posizionale)
        if cfg.include_no_shoots:
            ns_count = max(1, len([x for x in items if _is_scoring_target(x.item_type)]) // 4)
            ns_placed = 0
            for _ in range(ns_count * 3):
                if ns_placed >= ns_count:
                    break
                it = self._place_no_shoot(stage, items, engine)
                if it:
                    items.append(it)
                    ns_placed += 1
                attempts += 1
            if ns_placed < ns_count and self._perimeter_poly:
                papers = [x for x in items
                          if x.item_type in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET)]
                if papers:
                    for _ in range(ns_count - ns_placed):
                        p = random.choice(papers)
                        dx, dy = 0.4, 0.0
                        nx = p.x + dx
                        ny = p.y + dy
                        margin = IPSCRulesEngine.MIN_TARGET_TO_EDGE
                        if (margin <= nx <= stage.width - margin and
                            margin <= ny <= stage.depth - margin):
                            ns = StageItem(0, ItemType.NO_SHOOT, nx, ny,
                                           0.45, 0.45, 0, "#eab308", "No-Shoot")
                            items.append(ns)
                            ns_placed += 1

        # 7. Garantisce visibilità (solo per fault lines)
        if cfg.delimitation == "fault_lines":
            items = self._ensure_target_visibility(stage, items)

        # 8. Post-processing
        items = self._separate_overlapping(stage, items, engine)

        # Assegna ID finali a tutti gli item (anche quelli aggiunti dopo muri/no-shoot)
        next_id_final = max((it.id for it in items if it.id > 0), default=0) + 1
        for it in items:
            if it.id == 0:
                it.id = next_id_final
                next_id_final += 1
        stage.items = items
        stage._next_id = max((it.id for it in items), default=0) + 1

        # 9. Genera shooting positions automatiche (F2.1)
        if not stage.shooting_positions:
            stage.shooting_positions = self._generate_shooting_positions(stage, poly)

        # 10. Popola metadati briefing
        _populate_stage_metadata(
            stage, cfg.difficulty, num_poppers, num_plates, num_moving)

        score = _score_stage(
            stage, items,
            perimeter_poly=self._perimeter_poly,
            interior_samples=self._interior_samples,
            get_blocking_walls_fn=lambda: self._get_blocking_walls(items),
            is_target_visible_fn=lambda t, b: self._is_target_visible(t, b),
            config_difficulty=cfg.difficulty,
        )
        return GeneratorResult(stage=stage, score=score, attempts=attempts)

    def _generate_walls(self, stage: Stage, existing: List[StageItem]) -> List[StageItem]:
        """Genera muri FUORI dal perimetro che oscurano bersagli."""
        avg_len = 3.0 if self.config.difficulty == "easy" else 5.0 if self.config.difficulty == "hard" else 4.0
        return self._place_blocking_items(
            stage, existing,
            count=self.config.num_walls,
            item_type=ItemType.WALL,
            base_width=lambda: random.uniform(avg_len * 0.7, avg_len * 1.3),
            base_height=0.2,
            color="#475569",
            label="Muro",
        )

    def _generate_barriers(self, stage: Stage, existing: List[StageItem]) -> List[StageItem]:
        """Genera barriere FUORI dal perimetro che oscurano bersagli."""
        return self._place_blocking_items(
            stage, existing,
            count=self.config.num_barriers,
            item_type=ItemType.BARRIER,
            base_width=lambda: random.uniform(1.5, 3.0),
            base_height=0.15,
            color="#fbbf24",
            label="Barriera",
        )

    def _blocks_entrance_corridor(self, item: StageItem,
                                   stage_width: float = 0) -> bool:
        """True se l'item blocca il corridoio d'ingresso all'area di tiro.

        Il corridoio d'ingresso è lo spazio tra il fronte dello stage (y=0)
        e il bordo frontale dell'area di tiro (y minima del poligono).
        Le barriere NON possono essere posizionate in questo corridoio
        perché isolerebbero l'area di tiro dall'ingresso.
        """
        if not self._perimeter_poly:
            return False
        front_y = min(v[1] for v in self._perimeter_poly)
        if front_y < 0.5:
            return False  # area di tiro arriva quasi al bordo
        item_obb_geom = item_obb(item)
        if item_obb_geom is None:
            return False
        w = stage_width if stage_width > 0 else 40.0
        entrance = ShapelyPolygon([
            (0, 0), (w, 0), (w, front_y), (0, front_y),
        ])
        from shapely import intersects as sh_intersect
        return sh_intersect(item_obb_geom, entrance)

    def _place_blocking_items(self, stage: Stage, existing: List[StageItem],
                               count: int, item_type: ItemType,
                               base_width: callable, base_height: float,
                               color: str, label: str) -> List[StageItem]:
        """Piazza item (muri/barriere) fuori dall'area di tiro, tra area e bersagli.

        Regole:
        - Deve bloccare almeno 1 bersaglio (linea di vista)
        - NON può intersecare l'area di tiro (OBB check)
        - NON può sovrapporsi ad altre barriere/muri (OBB check)
        - NON può bloccare il corridoio d'ingresso all'area di tiro
        """
        from core.ipsc_rules import IPSCRulesEngine as _Engine
        from shapely import intersects as shapely_intersects
        items = []
        targets = [it for it in existing if _is_scoring_target(it.item_type)]
        if not self._perimeter_poly:
            return items

        min_visible = max(1, math.ceil(len(targets) * 0.7)) if targets else 1
        margin = MIN_TARGET_TO_EDGE

        # Poligono area di tiro come shapely Polygon per OBB intersection check
        area_poly = _perimeter_to_shapely_polygon(self._perimeter_poly)

        for _ in range(count):
            placed = False
            # Passata 1: cerca posizione che blocchi almeno 1 bersaglio
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
                wx = max(1.5, min(stage.width - 1.5, wx))
                wy = max(1.5, min(stage.depth - 1.5, wy))

                angle_to_target = math.degrees(math.atan2(dy, dx))
                rotation = angle_to_target + random.choice([-90, 90])

                item = StageItem(0, item_type, wx, wy,
                                 base_width(), base_height,
                                 rotation, color, label)

                # OBB: non deve intersecare l'area di tiro
                item_obb_geom = item_obb(item)
                if item_obb_geom is not None and area_poly is not None:
                    if shapely_intersects(item_obb_geom, area_poly):
                        continue

                # OBB: non deve sovrapporsi ad altre barriere/muri esistenti
                if item_obb_geom is not None:
                    from shapely import intersects as sh_intersect
                    overlaps_obstacle = False
                    for e_it in existing + items:
                        if e_it.item_type in (ItemType.WALL, ItemType.BARRIER,
                                              ItemType.DOOR, ItemType.HARD_COVER):
                            e_obb = item_obb(e_it)
                            if e_obb is not None and sh_intersect(item_obb_geom, e_obb):
                                overlaps_obstacle = True
                                break
                    if overlaps_obstacle:
                        continue

                # NON deve bloccare l'ingresso all'area di tiro
                if self._blocks_entrance_corridor(item, stage.width):
                    continue

                # Deve bloccare ALMENO 1 bersaglio
                blocks_any = False
                for t2 in targets:
                    for ox2, oy2 in self._interior_samples:
                        if line_intersects_rect(
                            (ox2, oy2), (t2.x, t2.y),
                            item.x, item.y, item.width, item.height, item.rotation
                        ):
                            blocks_any = True
                            break
                    if blocks_any:
                        break
                if not blocks_any:
                    continue

                local_engine = _Engine(stage)
                if not local_engine.is_valid_position(item, existing + items):
                    continue

                test_items = existing + items + [item]
                test_blockers = self._get_blocking_walls(test_items)
                visible_now = sum(1 for t2 in targets
                                  if self._is_target_visible(t2, test_blockers))
                if visible_now >= min_visible:
                    item.properties["protected"] = True  # non rimuovere in ensure_visibility
                    items.append(item)
                    placed = True
                    break

            # Passata 2 (fallback): cerca posizione che blocchi ALMENO 1 bersaglio
            if not placed:
                for _ in range(100):
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
                    wx = max(1.5, min(stage.width - 1.5, wx))
                    wy = max(1.5, min(stage.depth - 1.5, wy))
                    angle_to_target = math.degrees(math.atan2(dy, dx))
                    rotation = angle_to_target + random.choice([-90, 90])

                    item = StageItem(0, item_type, wx, wy,
                                     base_width(), base_height,
                                     rotation, color, label)

                    # OBB: non deve intersecare area di tiro
                    item_obb_geom = item_obb(item)
                    if item_obb_geom is not None and area_poly is not None:
                        if shapely_intersects(item_obb_geom, area_poly):
                            continue

                    # NON deve bloccare l'ingresso all'area di tiro
                    if self._blocks_entrance_corridor(item, stage.width):
                        continue

                    # Deve bloccare ALMENO 1 bersaglio (nessuna barriera inutile)
                    blocks_any = False
                    for t2 in targets:
                        for o2x, o2y in self._interior_samples:
                            if line_intersects_rect(
                                (o2x, o2y), (t2.x, t2.y),
                                item.x, item.y, item.width, item.height, item.rotation
                            ):
                                blocks_any = True
                                break
                        if blocks_any:
                            break
                    if not blocks_any:
                        continue

                    local_engine = _Engine(stage)
                    if local_engine.is_valid_position(item, existing + items):
                        item.properties["protected"] = True
                        items.append(item)
                        placed = True
                        break

            if not placed:
                break
        return items

    def _place_target_around(self, stage: Stage, existing: List[StageItem],
                              ttype: ItemType, engine: IPSCRulesEngine,
                              is_moving: bool = False) -> Optional[StageItem]:
        """Posiziona un bersaglio INTORNO all'area di tiro.
        
        Regole:
        - I bersagli sono posizionati FUORI dal perimetro dell'area di tiro
        - SOLO tra area di tiro e parapalle di fondo/laterali
        - MAI dentro l'area di tiro
        - MAI verso l'ingresso (lati con normale uscente ny < -0.3)
        - Bersagli metallici (steel): distanza fissa 8m dal perimetro
        - Tutti i bersagli devono essere visibili dall'area di tiro
        """
        if not self._perimeter_poly or len(self._perimeter_poly) < 3:
            return None

        margin = engine.MIN_TARGET_TO_EDGE
        poly = self._perimeter_poly
        n = len(poly)

        # Parametri bersaglio
        if ttype == ItemType.STEEL_TARGET:
            w, h = 0.30, 0.30; color = "#d1d5db"; label = "Steel"; min_dist_from_edge = MIN_STEEL_PLACEMENT_DISTANCE
        elif ttype == ItemType.POPPER:
            w, h = 0.30, 0.30; color = "#d1d5db"; label = "Popper"; min_dist_from_edge = MIN_STEEL_PLACEMENT_DISTANCE
        elif ttype == ItemType.METAL_PLATE:
            w, h = 0.20, 0.20; color = "#e5e7eb"; label = "Plate"; min_dist_from_edge = MIN_STEEL_PLACEMENT_DISTANCE
        elif is_moving:
            colors = {ItemType.SWINGER: ("#A0522D", "Swinger"), ItemType.DROP_TURNER: ("#8B6914", "Drop Turner"), ItemType.MOVER: ("#CD853F", "Mover")}
            color, label = colors.get(ttype, ("#808080", ""))
            w, h = 0.45, 0.45; min_dist_from_edge = 1.0
        elif ttype == ItemType.MINI_TARGET:
            w, h = 0.34, 0.34; color = "#A0522D"; label = "Mini"; min_dist_from_edge = 1.0
        elif ttype == ItemType.MICRO_TARGET:
            w, h = 0.23, 0.23; color = "#8B4513"; label = "Micro"; min_dist_from_edge = 1.0
        else:
            w, h = 0.45, 0.45; color = "#8B4513"; label = "Paper"; min_dist_from_edge = 1.0

        # Classifica i lati del poligono per posizionamento:
        # I bersagli devono essere posizionati ESCLUSIVAMENTE nel settore
        # compreso tra l'area di tiro e il parapalle di fondo.
        #
        # 1. BACKSTOP ZONE (priorità 100%): lati con normale uscente
        #    che punta verso il backstop (y crescente, ny > 0)
        #    e settore entro 60° dalla perpendicolare al backstop.
        # 2. LATERAL ZONE (fallback): lati laterali (|nx| > 0.7)
        # 3. FRONT (escluso): normale ny < 0 — MAI usati
        #
        # Il posizionamento avviene solo nel settore backstop + laterali.
        # Se non c'è spazio sufficiente, il settore viene allargato
        # progressivamente (60° → 90° → 120°).
        poly_cx = sum(v[0] for v in poly) / n
        poly_cy = sum(v[1] for v in poly) / n

        # Direzione del backstop (y crescente dello stage)
        # Identifica il punto più a fondo del poligono
        back_y = max(v[1] for v in poly)
        backstop_dx = 0.0
        backstop_dy = 1.0

        back_edges = []
        side_edges = []
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            seg_len = math.hypot(x2 - x1, y2 - y1)
            if seg_len < 0.3:
                continue
            # Centro del lato
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2
            # Normale uscente (poligono in senso antiorario)
            nx_seg = (y2 - y1) / seg_len
            ny_seg = -(x2 - x1) / seg_len

            # Angolo tra normale uscente e direzione backstop
            dot_n = nx_seg * backstop_dx + ny_seg * backstop_dy
            angle_n = math.degrees(math.acos(max(-1.0, min(1.0, dot_n))))

            if angle_n < 60.0:  # entro 60° dalla direzione backstop
                back_edges.append(i)
            elif abs(nx_seg) > 0.7 and ny_seg >= -0.3:
                side_edges.append(i)
            # frontali (ny_seg < -0.3) sono esclusi

        # Settore progressivo: inizia con back_edges 100%
        candidate_edges = list(back_edges)
        if not candidate_edges or len(candidate_edges) < 2:
            # Fallback: aggiungi laterali
            candidate_edges.extend(side_edges)
        if not candidate_edges or len(candidate_edges) < 2:
            # Fallback estremo: tutti i lati tranne frontali espliciti
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                seg_len = math.hypot(x2 - x1, y2 - y1)
                if seg_len < 0.3:
                    continue
                ny_seg = -(x2 - x1) / seg_len
                if ny_seg >= -0.3:
                    candidate_edges.append(i)
            if not candidate_edges:
                candidate_edges = list(range(n))

        # ═══ Campionamento guidato (F2.3) ═══
        # Pre-calcola per ogni lato candidato lo spazio massimo disponibile
        # nella direzione della normale. Filtra i lati con spazio insufficiente.
        _backstop_margin = MIN_BACKSTOP_DEPTH
        _half_h = (h if not is_moving else 0.45) / 2
        max_y = stage.depth - _backstop_margin - _half_h - 0.2
        guided_edges: list[tuple[int, float]] = []
        for e_idx in candidate_edges:
            x1, y1 = poly[e_idx]
            x2, y2 = poly[(e_idx + 1) % n]
            seg_len = math.hypot(x2 - x1, y2 - y1)
            if seg_len < 0.3:
                continue
            nx = (y2 - y1) / seg_len
            ny = -(x2 - x1) / seg_len
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2
            if nx > 0:
                md_x = (stage.width - margin - mx) / max(nx, 0.001)
            elif nx < 0:
                md_x = (mx - margin) / max(-nx, 0.001)
            else:
                md_x = float('inf')
            if ny > 0:
                md_y = (max_y - my) / max(ny, 0.001)
            elif ny < 0:
                md_y = (my - margin) / max(-ny, 0.001)
            else:
                md_y = float('inf')
            max_dist_edge = min(md_x, md_y)
            if max_dist_edge >= min_dist_from_edge:
                guided_edges.append((e_idx, max_dist_edge))

        use_guided = len(guided_edges) >= 2

        for _ in range(self.config.max_attempts):
            if use_guided:
                edge_idx, max_dist = random.choice(guided_edges)
            else:
                edge_idx = random.choice(candidate_edges)
                max_dist = max(max_y, stage.width)  # fallback: stima ottimistica

            x1, y1 = poly[edge_idx]
            x2, y2 = poly[(edge_idx + 1) % n]
            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)

            # Posizione lungo il lato (interpolazione)
            t = random.uniform(0.1, 0.9)
            ex = x1 + dx * t
            ey = y1 + dy * t

            # Normale uscente (per poligono in senso antiorario)
            nx = dy / length
            ny = -dx / length
            if max_dist < min_dist_from_edge:
                continue

            dist = random.uniform(
                min_dist_from_edge,
                min(max_dist, min_dist_from_edge + 3.0)
            )
            px = ex + nx * dist
            py = ey + ny * dist

            # Deve stare dentro lo stage, con backstop minimo garantito
            if not (margin <= px <= stage.width - margin and
                    margin <= py <= max_y):
                continue

            # Deve stare FUORI dal perimetro
            if point_in_polygon(px, py, poly):
                continue

            # NON deve essere dietro l'area di tiro (Req. 2)
            if self._is_behind_shooting_area(px, py, poly):
                continue

            # Non deve condividere la linea di tiro con bersagli esistenti (Req. 5)
            if self._targets_on_same_line(px, py, existing,
                                          threshold_deg=SAME_LINE_OF_FIRE_THRESHOLD_DEG):
                continue

            # Orientamento VERSO L'AREA DI TIRO (Reg. 2.1.8.4)
            # I bersagli IPSC devono puntare verso il tiratore, quindi
            # verso l'interno dell'area di tiro.
            # Usa il centro del poligono dell'area di tiro come riferimento.
            poly_cx = sum(p[0] for p in self._perimeter_poly) / len(self._perimeter_poly)
            poly_cy = sum(p[1] for p in self._perimeter_poly) / len(self._perimeter_poly)
            rot = math.degrees(math.atan2(poly_cy - py, poly_cx - px))
            rot += random.uniform(-10, 10)  # leggera variazione per naturalezza

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

            # App. C3: i piatti metallici devono avere mount_height >= 1m
            if ttype == ItemType.METAL_PLATE:
                props["mount_height"] = 1.0

            it = StageItem(0, ttype, px, py, w, h, rot, color, label,
                           properties=props)
            # Usa una tolleranza leggermente maggiore per evitare falsi positivi floating-point
            if engine.is_valid_position(it, existing):
                # Verifica distanza da altri bersagli con margine extra
                it_obb = item_obb(it)
                ok = True
                if it_obb:
                    for other in existing:
                        if other.item_type in (ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
                                               ItemType.NO_SHOOT):
                            # Bersagli cartacei possono essere affiancati/sovrapposti
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

    def _place_no_shoot(self, stage: Stage, existing: List[StageItem],
                        engine: IPSCRulesEngine) -> Optional[StageItem]:
        """Posiziona un no-shoot ATTACCATO DAVANTI a un bersaglio cartaceo.
        
        I no-shoot hanno senso solo se attaccati davanti a bersagli
        cartacei (paper target), per penalizzare tiri imprecisi.
        Sono posizionati sulla linea che dal centro dell'area di tiro
        va verso il paper target, a 0.3-0.8m da quest'ultimo (attaccati).
        """
        papers = [it for it in existing if it.item_type == ItemType.PAPER_TARGET]
        if not papers or not self._perimeter_poly:
            return None
        poly = self._perimeter_poly
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)

        for _ in range(self.config.max_attempts):
            paper = random.choice(papers)
            dx = paper.x - cx
            dy = paper.y - cy
            dist = math.hypot(dx, dy)
            if dist < 0.5:
                continue
            nx = dx / dist
            ny = dy / dist
            # Attaccato davanti al paper (0.3-0.8m)
            ns_dist = random.uniform(0.3, 0.8)
            x = paper.x - nx * ns_dist
            y = paper.y - ny * ns_dist
            if point_in_polygon(x, y, poly):
                continue
            it = StageItem(0, ItemType.NO_SHOOT, x, y, 0.45, 0.45, 0, "#eab308", "No-Shoot")
            if engine.is_valid_position(it, existing):
                return it
        return None

    # ─── Utilità geometriche ───
    # Le funzioni sono state migrate in core/geometry.py

    def _targets_on_same_line(self, target_x: float, target_y: float,
                                existing: List[StageItem],
                                threshold_deg: float = SAME_LINE_OF_FIRE_THRESHOLD_DEG) -> bool:
        """True se il bersaglio è sulla stessa linea di tiro di uno esistente.

        Calcola l'angolo dal centro dell'area di tiro per ogni bersaglio
        esistente. Se la differenza angolare è < threshold_deg, sono
        considerati sulla stessa linea di tiro.

        Regola: non possono essere posizionati più bersagli sulla stessa
        linea di tiro (per evitare che un singolo colpo possa colpire
        due bersagli).
        """
        if not self._perimeter_poly:
            return False

        cx = sum(v[0] for v in self._perimeter_poly) / len(self._perimeter_poly)
        cy = sum(v[1] for v in self._perimeter_poly) / len(self._perimeter_poly)

        # Angolo del nuovo bersaglio rispetto al centro
        new_angle = math.degrees(math.atan2(target_y - cy, target_x - cx))

        for other in existing:
            if not _is_scoring_target(other.item_type):
                continue
            other_angle = math.degrees(math.atan2(other.y - cy, other.x - cx))
            diff = abs(new_angle - other_angle)
            diff = min(diff, 360 - diff)  # gestione wrap-around
            if diff < threshold_deg:
                return True

        return False

    def _sample_interior_points(self, count: int = INTERIOR_SAMPLE_COUNT) -> List[Tuple[float, float]]:
        """Campiona punti casuali dentro il perimetro poligonale."""
        if not self._perimeter_poly:
            return [(5.0, 5.0)]
        # Bounding box del poligono
        xs = [p[0] for p in self._perimeter_poly]
        ys = [p[1] for p in self._perimeter_poly]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        points = []
        for _ in range(count * 5):  # oversample per riempire
            if len(points) >= count:
                break
            x = random.uniform(min_x, max_x)
            y = random.uniform(min_y, max_y)
            if point_in_polygon(x, y, self._perimeter_poly):
                points.append((x, y))
        return points[:count] if points else [(polygon_center(self._perimeter_poly))]

    def _is_behind_shooting_area(self, target_x: float, target_y: float,
                                   poly: list[tuple[float, float]] | None = None) -> bool:
        """True se il bersaglio è nel settore 'dietro' l'area di tiro.

        La direzione di ingaggio principale va dal baricentro dell'area
        verso il backstop (y crescente nello stage, ma dipende dalla
        rotazione della lettera). 'Dietro' = oltre ±90° da questa direzione.

        In pratica: se il bersaglio è dalla parte opposta al backstop
        rispetto all'area di tiro, non è visibile dal tiratore in modo
        sicuro e quindi va scartato.
        """
        p = poly if poly is not None else self._perimeter_poly
        if not p or len(p) < 3:
            return False

        cx = sum(v[0] for v in p) / len(p)
        cy = sum(v[1] for v in p) / len(p)

        # Direzione di ingaggio: dal baricentro verso il backstop.
        # Il backstop è il lato con y maggiore (fondo stage).
        # Identifichiamo il punto medio del lato più a fondo del poligono.
        back_x, back_y = cx, max(v[1] for v in p)
        dx_forward = back_x - cx
        dy_forward = back_y - cy
        forward_len = math.hypot(dx_forward, dy_forward)
        if forward_len < 0.1:
            return False

        # Vettore dal baricentro al bersaglio
        dx_target = target_x - cx
        dy_target = target_y - cy

        # Angolo tra il vettore di ingaggio e il vettore bersaglio
        dot = dx_forward * dx_target + dy_forward * dy_target
        angle = math.degrees(math.acos(
            max(-1.0, min(1.0, dot / (forward_len * math.hypot(dx_target, dy_target) + 1e-9)))
        ))

        # Se l'angolo supera 90°, il bersaglio è dietro l'area di tiro
        return angle > 90.0

    def _get_blocking_walls(self, items: List[StageItem]) -> List[StageItem]:
        """Ritorna gli item che bloccano la visuale (muri, barriere, porte, hard cover)."""
        blockers = []
        for it in items:
            if it.item_type in (ItemType.WALL, ItemType.BARRIER, ItemType.DOOR,
                                ItemType.HARD_COVER):
                blockers.append(it)
        return blockers

    def _is_target_visible(self, target: StageItem,
                            blockers: List[StageItem]) -> bool:
        """Verifica che il bersaglio sia visibile da almeno un punto interno."""
        target_pos = (target.x, target.y)
        for obs_x, obs_y in self._interior_samples:
            visible = True
            for wall in blockers:
                if line_intersects_rect(
                    (obs_x, obs_y), target_pos,
                    wall.x, wall.y, wall.width, wall.height, wall.rotation
                ):
                    visible = False
                    break
            if visible:
                return True
        return False

    def _ensure_target_visibility(self, stage: Stage,
                                    items: List[StageItem]) -> List[StageItem]:
        """Rimuove ostacoli finché TUTTI (100%) i bersagli sono visibili.
        
        Ogni bersaglio deve essere visibile da almeno un punto all'interno
        dell'area di tiro. Se un ostacolo blocca più bersagli di quanti
        ne liberi, viene rimosso.
        """
        targets = [it for it in items if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
            ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)]
        if not targets or not self._interior_samples:
            return items

        min_visible = len(targets)  # 100% visibilità richiesta

        for _ in range(100):
            blockers = [b for b in self._get_blocking_walls(items)
                        if not b.properties.get("protected")]
            if not blockers:
                break

            visible = sum(1 for t in targets if self._is_target_visible(t, blockers))
            if visible >= min_visible:
                break

            # Per ogni bloccante non protetto, simula la rimozione
            best_gain = 0
            best_item = None
            for b in blockers:
                test_items = [it for it in items if it is not b]
                test_blockers = [x for x in self._get_blocking_walls(test_items)
                                 if not x.properties.get("protected")]
                # Include anche i protetti per il calcolo visuale
                all_blockers = test_blockers + [x for x in self._get_blocking_walls(test_items)
                                                if x.properties.get("protected")]
                test_visible = sum(1 for t in targets
                                   if self._is_target_visible(t, all_blockers))
                gain = test_visible - visible
                if gain > best_gain:
                    best_gain = gain
                    best_item = b

            if best_item is None or best_gain == 0:
                # Nessun miglioramento: rimuovi quello che blocca più target
                wall_hits = {id(w): 0 for w in blockers}
                wall_map = {id(w): w for w in blockers}
                invisible = [t for t in targets
                             if not self._is_target_visible(t, [x for x in self._get_blocking_walls(items)
                                                                 if not x.properties.get("protected")])]
                for t in invisible:
                    for ox, oy in self._interior_samples:
                        for w in blockers:
                            if line_intersects_rect(
                                (ox, oy), (t.x, t.y),
                                w.x, w.y, w.width, w.height, w.rotation
                            ):
                                wall_hits[id(w)] = wall_hits.get(id(w), 0) + 1
                if max(wall_hits.values()) == 0:
                    break
                best_id = max(wall_hits, key=wall_hits.get)
                best_item = wall_map[best_id]

            items = [it for it in items if it is not best_item]

        return items

    def _add_restrictive_walls(self, stage: Stage,
                                existing: List[StageItem],
                                engine: IPSCRulesEngine | None = None) -> List[StageItem]:
        """Aggiunge muri per garantire max 9 colpi per posizione (Reg. 1.2.1)
        e che Medium/Long non abbiano tutti i bersagli visibili da una posizione.

        Strategia:
        1. Calcola i colpi visibili da ogni posizione di tiro
        2. Se superano 9, aggiunge muri sulla linea verso i bersagli eccedenti
        3. I muri sono posizionati per non bloccare TUTTA la visuale
        """
        if not self._interior_samples or not self._perimeter_poly:
            return []

        targets = [it for it in existing if _is_scoring_target(it.item_type)]
        if not targets:
            return []

        max_hits = IPSCRulesEngine.MAX_HITS_PER_POSITION  # 9
        new_walls = []
        max_walls = max(2, len(targets) // 2)

        # Ottieni le stesse posizioni usate dal validatore _validate_max_hits_per_position()
        # per garantire che le riparazioni siano efficaci
        if stage.shooting_positions:
            positions = [(sp.x, sp.y) for sp in stage.shooting_positions]
        else:
            cx, cy = stage.width / 2, stage.depth / 2
            positions = [(cx, cy), (cx - 2, cy), (cx + 2, cy), (cx, cy + 2)]

        for obs_x, obs_y in positions:
            if len(new_walls) >= max_walls:
                break

            # Calcola i bersagli visibili da questa posizione
            all_blockers = self._get_blocking_walls(existing) + new_walls
            visible_targets = []
            for t in targets:
                visible = True
                for w in all_blockers:
                    if line_intersects_rect(
                        (obs_x, obs_y), (t.x, t.y),
                        w.x, w.y, w.width, w.height, w.rotation
                    ):
                        visible = False
                        break
                if visible:
                    visible_targets.append(t)

            # Calcola i colpi: 2 per carta, 1 per metallo
            total_hits = sum(
                2 if _is_paper_like(t.item_type) or
                     t.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER,
                                      ItemType.MOVER)
                else 1
                for t in visible_targets
            )

            if total_hits <= max_hits:
                continue

            # Troppi colpi: blocca i bersagli extra (partendo dai più lontani)
            visible_targets.sort(
                key=lambda t: math.hypot(t.x - obs_x, t.y - obs_y),
                reverse=True)

            for t in visible_targets:
                if len(new_walls) >= max_walls:
                    break

                hits_this = 2 if (_is_paper_like(t.item_type) or
                                  t.item_type in (ItemType.SWINGER,
                                                   ItemType.DROP_TURNER,
                                                   ItemType.MOVER)) else 1
                if total_hits - hits_this < max_hits:
                    # Bloccare questo bersaglio ci porterebbe SOTTO il limite
                    # Meglio lasciarlo visibile e bloccarne un altro
                    continue

                dx = t.x - obs_x
                dy = t.y - obs_y
                dist = math.hypot(dx, dy)
                if dist < 2.0:
                    continue
                nx, ny = dx / dist, dy / dist

                # Muro a metà strada, FUORI dal perimetro
                wall_dist = dist * random.uniform(0.35, 0.65)
                wx = obs_x + nx * wall_dist
                wy = obs_y + ny * wall_dist

                if point_in_polygon(wx, wy, self._perimeter_poly):
                    continue

                margin = IPSCRulesEngine.MIN_TARGET_TO_EDGE
                if not (margin <= wx <= stage.width - margin and
                        margin <= wy <= stage.depth - margin):
                    continue

                # Muro perpendicolare alla linea di vista, lungo abbastanza
                wall_angle = math.degrees(math.atan2(ny, nx)) + 90
                wall_len = random.uniform(1.5, 3.0)

                new_wall = StageItem(
                    0, ItemType.BARRIER, wx, wy,
                    wall_len, 0.2, wall_angle,
                    "#fbbf24", "Barriera ristr.")

                # Valida con IPSCRulesEngine (distanza da target, ostacoli, bordo)
                test_items = existing + new_walls
                if not engine.is_valid_position(new_wall, test_items):
                    continue

                # Verifica che il target resti visibile da ALMENO 1 posizione
                test_blockers = all_blockers + [new_wall]
                still_visible = False
                for ox2, oy2 in positions:
                    vis = True
                    for w in test_blockers:
                        if line_intersects_rect(
                            (ox2, oy2), (t.x, t.y),
                            w.x, w.y, w.width, w.height, w.rotation
                        ):
                            vis = False
                            break
                    if vis:
                        still_visible = True
                        break

                # NON deve bloccare l'ingresso all'area di tiro
                if still_visible and not self._blocks_entrance_corridor(new_wall, stage.width):
                    new_walls.append(new_wall)
                    total_hits -= hits_this
                    all_blockers = self._get_blocking_walls(existing) + new_walls

        return new_walls

    # ── Riparazione violazioni ──────────────────────────────────────────────

    def _repair_violations(self, stage: Stage, violations: List[str],
                           engine: IPSCRulesEngine) -> bool:
        """Applica riparazioni mirate per eliminare le violazioni.

        Ritorna True se almeno una riparazione è stata applicata.
        """
        import re as _re
        repaired = False

        for v_text in violations:
            v_lower = v_text.lower()

            # 1. Bersaglio troppo vicino a muro → rimuovi il muro incriminato
            if "troppo vicino a muro" in v_lower:
                m = _re.search(r'#(\d+)', v_text)
                if m:
                    target_id = int(m.group(1))
                    target = stage.get_item(target_id)
                    if target:
                        walls = [it for it in stage.items
                                 if it.item_type in (ItemType.WALL, ItemType.BARRIER,
                                                     ItemType.DOOR, ItemType.HARD_COVER)]
                        for w in walls:
                            t_obb = item_obb(target)
                            w_obb = item_obb(w)
                            if t_obb and w_obb:
                                dist = obb_distance(t_obb, w_obb)
                                if dist < engine.MIN_TARGET_TO_WALL:
                                    stage.remove_item(w.id)
                                    repaired = True
                                    break

            # 2. Troppi colpi da posizione → blocca bersagli eccedenti
            elif "colpi conteggiabili" in v_lower and "max 9" in v_lower:
                m = _re.search(r'\(([\d.]+),\s*([\d.]+)\)', v_text)
                if m:
                    px, py = float(m.group(1)), float(m.group(2))
                    # Conta quanti colpi sono visibili: 2 per paper, 1 per steel
                    targets = [it for it in stage.items if _is_scoring_target(it.item_type)]
                    visible_targets = []
                    for t in targets:
                        t_obb_local = item_obb(t)
                        if t_obb_local is None:
                            continue
                        from shapely.geometry import LineString as SLine
                        walls_check = self._get_blocking_walls(stage.items)
                        line = SLine([(px, py), (t.x, t.y)])
                        blocked = False
                        for w in walls_check:
                            wob_local = item_obb(w)
                            if wob_local and line.intersects(wob_local):
                                blocked = True
                                break
                        if not blocked:
                            visible_targets.append(t)

                    # Calcola colpi totali
                    total_hits = sum(2 if _is_paper_like(t.item_type) or
                                     t.item_type in (ItemType.SWINGER,
                                                      ItemType.DROP_TURNER,
                                                      ItemType.MOVER)
                                     else 1 for t in visible_targets)

                    # Se supera 9, blocca i bersagli extra con muri
                    if total_hits > 9:
                        # Ordina per distanza (blocca i più lontani prima)
                        visible_targets.sort(
                            key=lambda t: math.hypot(t.x - px, t.y - py),
                            reverse=True)
                        # Blocca finché non scendiamo sotto 9
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
                            if not (margin <= wx <= stage.width - margin and
                                    margin <= wy <= stage.depth - margin):
                                continue
                            wall = StageItem(0, ItemType.BARRIER, wx, wy,
                                             1.5, 0.2,
                                             math.degrees(math.atan2(ny, nx)),
                                             "#fbbf24", "Barriera ripar.")
                            # Verifica che il target resti visibile da almeno 1 posizione
                            test_blockers = self._get_blocking_walls(stage.items + [wall])
                            if self._is_target_visible(t_block, test_blockers):
                                stage.add_item(wall)
                                repaired = True
                                hits_blocked = 2 if (_is_paper_like(t_block.item_type) or
                                                     t_block.item_type in (ItemType.SWINGER,
                                                                          ItemType.DROP_TURNER,
                                                                          ItemType.MOVER)) else 1
                                total_hits -= hits_blocked

            # 3. Bersagli insufficienti → aggiungi paper target
            elif "bersagli insufficienti" in v_lower:
                min_t = IPSCRulesEngine.MIN_TARGETS
                current = len([it for it in stage.items if _is_scoring_target(it.item_type)])
                needed = min_t - current
                for _ in range(needed * 2):
                    it = self._place_target_around(
                        stage, stage.items, ItemType.PAPER_TARGET, engine)
                    if it:
                        stage.add_item(it)
                        repaired = True
                        current += 1
                        if current >= min_t:
                            break

            # 4. Backstop insufficiente → sposta bersagli più avanti
            elif "dietro bersagli insufficiente" in v_lower:
                targets = [it for it in stage.items if _is_scoring_target(it.item_type)]
                max_allowed_y = stage.depth - IPSCRulesEngine.MIN_BACKSTOP_DEPTH + 0.3
                for t in targets:
                    if t.y + t.height / 2 > max_allowed_y:
                        t.y = max_allowed_y - t.height / 2
                        repaired = True

            # 5. Ostacoli troppo vicini → rimuovi il secondo (se non è perimetrale)
            elif "ostacolo" in v_lower and "vicino" in v_lower:
                m = _re.findall(r'#(\d+)', v_text)
                if len(m) >= 2:
                    id2 = int(m[1])
                    item2 = stage.get_item(id2)
                    if item2 and not item2.properties.get("perimeter"):
                        stage.remove_item(id2)
                        repaired = True

            # 6. Stage medium/long: tutti bersagli visibili da una posizione
            elif "tutti i" in v_lower and "bersagli sono" in v_lower:
                m = _re.search(r'\(([\d.]+),\s*([\d.]+)\)', v_text)
                if m:
                    px, py = float(m.group(1)), float(m.group(2))
                    targets = [it for it in stage.items if _is_scoring_target(it.item_type)]
                    # Blocca la visuale verso il bersaglio più lontano
                    if targets:
                        farthest = max(targets,
                                       key=lambda t: math.hypot(t.x - px, t.y - py))
                        dx = farthest.x - px
                        dy = farthest.y - py
                        dist = math.hypot(dx, dy)
                        if dist > 2.0:
                            nx, ny = dx / dist, dy / dist
                            wx = px + nx * dist * 0.4
                            wy = py + ny * dist * 0.4
                            margin = engine.MIN_TARGET_TO_EDGE
                            if (margin <= wx <= stage.width - margin and
                                margin <= wy <= stage.depth - margin):
                                wall = StageItem(0, ItemType.BARRIER, wx, wy,
                                                 2.0, 0.2,
                                                 math.degrees(math.atan2(ny, nx)),
                                                 "#fbbf24", "Barriera div.")
                                stage.add_item(wall)
                                repaired = True

        return repaired

    # ── Separazione bersagli ────────────────────────────────────────────────

    def _separate_overlapping(self, stage: Stage, items: List[StageItem],
                              engine: IPSCRulesEngine) -> List[StageItem]:
        """Allontana bersagli troppo vicini tra loro o ai muri.

        Sposta i bersagli per garantire distanza minima. Se non è possibile
        spostare, rimuove il bersaglio in conflitto.
        """
        targets = [it for it in items if _is_scoring_target(it.item_type)]
        walls = [it for it in items if it.item_type in (ItemType.WALL, ItemType.BARRIER,
                                                         ItemType.DOOR, ItemType.HARD_COVER)]
        changed = True
        max_passes = 8
        margin = engine.MIN_TARGET_TO_EDGE

        for _ in range(max_passes):
            changed = False

            for i, t in enumerate(targets):
                if t not in items:
                    continue
                t_obb = item_obb(t)
                if not t_obb:
                    continue

                # Controlla distanza da altri bersagli
                for other in targets[i + 1:]:
                    if other not in items:
                        continue
                    o_obb = item_obb(other)
                    if not o_obb:
                        continue

                    # Bersagli cartacei possono essere affiancati/sovrapposti
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
                        # Allontana: sposta il bersaglio più recente (id maggiore)
                        to_move = t if t.id < other.id else other
                        dx = to_move.x - (t.x if t.id < other.id else other.x)
                        dy = to_move.y - (t.y if t.id < other.id else other.y)
                        dist = math.hypot(dx, dy)
                        if dist < 0.1:
                            dx, dy = 0.5, 0.5
                            dist = math.hypot(dx, dy)
                        nx, ny = dx / dist, dy / dist
                        shift = 0.15  # sposta di 15cm
                        to_move.x += nx * shift
                        to_move.y += ny * shift
                        to_move.x = max(margin, min(stage.width - margin, to_move.x))
                        to_move.y = max(margin, min(stage.depth - margin, to_move.y))
                        changed = True
                        # Ricrea OBB dopo lo spostamento
                        t_obb = item_obb(t)

                # Controlla distanza dai muri
                for w in walls:
                    if w not in items:
                        continue
                    w_obb = item_obb(w)
                    if not w_obb:
                        continue
                    d = obb_distance(t_obb, w_obb)
                    if d < engine.MIN_TARGET_TO_WALL - 0.03:
                        # Sposta il bersaglio lontano dal muro
                        dx = t.x - w.x
                        dy = t.y - w.y
                        dist = math.hypot(dx, dy)
                        if dist < 0.1:
                            dx, dy = 0.5, 0.5
                            dist = 0.5
                        t.x += (dx / dist) * 0.2
                        t.y += (dy / dist) * 0.2
                        t.x = max(margin, min(stage.width - margin, t.x))
                        t.y = max(margin, min(stage.depth - margin, t.y))
                        changed = True
                        t_obb = item_obb(t)

            if not changed:
                break

        return items

    # ═══════════════════════════════════════════════════════════════════════
    #  Nuovi metodi: conteggi, attivatori, metadati
    # ═══════════════════════════════════════════════════════════════════════

    def _generate_shooting_positions(
        self, stage: Stage,
        poly: List[Tuple[float, float]] | None = None
    ) -> List["ShootingPosition"]:
        """Genera shooting positions automatiche per lo stage.

        Crea:
        1. Una posizione di partenza (start) sul lato frontale dell'area di tiro
           (y minima del poligono, centrata x)
        2. Opzionalmente una posizione intermedia per forme complesse
           (es. forma H, X) dove il tiratore può spostarsi

        Returns:
            Lista di ShootingPosition
        """
        from core.models import ShootingPosition
        p = poly if poly is not None else self._perimeter_poly
        if not p or len(p) < 3:
            return []

        positions: list = []
        poly_cx = sum(v[0] for v in p) / len(p)

        # Trova il punto frontale (y minima nel poligono)
        front_y = min(v[1] for v in p)
        front_x = sum(v[0] for v in p if abs(v[1] - front_y) < 0.5) / max(
            1, sum(1 for v in p if abs(v[1] - front_y) < 0.5))

        # Posizione di partenza: appena dentro l'area di tiro, lato frontale
        start = ShootingPosition(
            id=1,
            x=round(front_x, 2),
            y=round(front_y + 0.5, 2),  # mezzo metro dentro l'area
            label="Start",
            is_start=True,
            angle=90.0,  # verso il backstop
        )
        positions.append(start)

        # Per forme complesse (H, X, F, E, N, M), aggiungi posizione intermedia
        complex_shapes = {"H", "X", "F", "E", "N", "M", "S", "Z"}
        letter = self.config.letter_shape
        if letter in complex_shapes or (letter == "random" and len(p) > 6):
            # Posizione intermedia: centro dell'area
            mid_y = sum(v[1] for v in p) / len(p)
            mid_x = poly_cx
            intermediate = ShootingPosition(
                id=2,
                x=round(mid_x, 2),
                y=round(mid_y, 2),
                label="Intermediate",
                is_start=False,
                angle=90.0,
            )
            positions.append(intermediate)

        return positions

    def _generate_fault_lines(self, stage: Stage, existing: List[StageItem]) -> List[StageItem]:
        """Genera fault lines strategiche davanti ai bersagli."""
        fault_lines = []
        targets = [it for it in existing if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
            ItemType.POPPER, ItemType.METAL_PLATE,
            ItemType.MINI_TARGET, ItemType.MICRO_TARGET)]
        for target in targets:
            angle = math.radians(target.rotation)
            dist = random.uniform(3.0, 5.0)
            fx = target.x + math.cos(angle) * dist
            fy = target.y + math.sin(angle) * dist
            # Deve stare dentro il perimetro
            if self._perimeter_poly and not point_in_polygon(fx, fy, self._perimeter_poly):
                continue
            length = random.uniform(2.0, 4.0)
            rot = target.rotation + random.uniform(-15, 15)
            fl = StageItem(0, ItemType.FAULT_LINE, fx, fy, length, 0.0, rot, "#dc2626", "Fault Line")
            margin = IPSCRulesEngine.MIN_TARGET_TO_EDGE
            if (margin <= fx and fx <= stage.width - margin and
                    margin <= fy and fy <= stage.depth - margin):
                fault_lines.append(fl)
        return fault_lines

