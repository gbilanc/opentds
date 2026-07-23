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
    letter_shape: str = "random"  # random (lettera casuale) | L | T | U | C | H | F | O | Z | S | X | Y | M | N | E
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

    def _place_blocking_items(self, stage: Stage, existing: List[StageItem],
                               count: int, item_type: ItemType,
                               base_width: callable, base_height: float,
                               color: str, label: str) -> List[StageItem]:
        """Piazza item (muri/barriere) fuori dall'area di tiro, tra area e bersagli.

        Tenta prima di posizionare item che bloccano almeno 1 bersaglio.
        Se fallisce, posiziona item in punti validi qualsiasi (fallback).

        Regola: barriere NON possono essere posizionate all'interno dell'area
        di tiro. Il controllo usa l'OBB completo dell'item (non solo il centro)
        per verificare che non intersechi il poligono dell'area di tiro.
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

                # VERIFICA OBB: l'item non deve intersecare l'area di tiro
                item_obb_geom = item_obb(item)
                if item_obb_geom is not None and area_poly is not None:
                    if shapely_intersects(item_obb_geom, area_poly):
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

            # Passata 2 (fallback): piazza in qualsiasi posizione valida
            if not placed:
                for _ in range(100):
                    wx = random.uniform(margin + 1, stage.width - margin - 1)
                    wy = random.uniform(margin + 1, stage.depth - margin - 1)

                    item = StageItem(0, item_type, wx, wy,
                                     base_width(), base_height,
                                     random.uniform(0, 360),
                                     color, label)

                    # VERIFICA OBB: non deve intersecare area di tiro
                    item_obb_geom = item_obb(item)
                    if item_obb_geom is not None and area_poly is not None:
                        if shapely_intersects(item_obb_geom, area_poly):
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
            # Backward compat: generico
            w, h = 0.30, 0.30
            color = "#d1d5db"
            label = "Steel"
            min_dist_from_edge = 8.0
        elif ttype == ItemType.POPPER:
            # Popper calibrato IPSC (App. C1-C2): bianco, ~30cm
            w, h = 0.30, 0.30
            color = "#d1d5db"
            label = "Popper"
            min_dist_from_edge = 8.0
            # I popper NON devono avere proprietà di movimento (Reg. 4.3.1.1)
        elif ttype == ItemType.METAL_PLATE:
            # Piatto metallico IPSC (App. C3): bianco, ~20cm
            w, h = 0.20, 0.20
            color = "#e5e7eb"
            label = "Plate"
            min_dist_from_edge = 8.0
        elif is_moving:
            # Bersagli mobili su supporto cartaceo → marrone
            colors = {
                ItemType.SWINGER: ("#A0522D", "Swinger"),
                ItemType.DROP_TURNER: ("#8B6914", "Drop Turner"),
                ItemType.MOVER: ("#CD853F", "Mover"),
            }
            color, label = colors.get(ttype, ("#808080", ""))
            w, h = 0.45, 0.45
            min_dist_from_edge = 1.0
        elif ttype == ItemType.MINI_TARGET:
            # Mini target IPSC (App. B3): marrone, 75% scala
            w, h = 0.34, 0.34
            color = "#A0522D"
            label = "Mini"
            min_dist_from_edge = 1.0
        elif ttype == ItemType.MICRO_TARGET:
            # Micro target: ancora più piccolo
            w, h = 0.23, 0.23
            color = "#8B4513"
            label = "Micro"
            min_dist_from_edge = 1.0
        else:
            # Paper target standard IPSC
            w, h = 0.45, 0.45
            color = "#8B4513"
            label = "Paper"
            min_dist_from_edge = 1.0

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

        for _ in range(self.config.max_attempts):
            edge_idx = random.choice(candidate_edges)
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

            # Distanza dal lato: calcola lo spazio disponibile nella
            # direzione della normale e adatta la distanza massima
            backstop_margin = IPSCRulesEngine.MIN_BACKSTOP_DEPTH
            half_h = (h if not is_moving else 0.45) / 2
            max_y = stage.depth - backstop_margin - half_h - 0.2

            # Calcola lo spazio massimo nella direzione della normale
            # che mantiene il bersaglio dentro lo stage
            if nx > 0:
                max_dist_x = (stage.width - margin - ex) / max(nx, 0.001)
            elif nx < 0:
                max_dist_x = (ex - margin) / max(-nx, 0.001)
            else:
                max_dist_x = float('inf')

            if ny > 0:
                max_dist_y = (max_y - ey) / max(ny, 0.001)
            elif ny < 0:
                max_dist_y = (ey - margin) / max(-ny, 0.001)
            else:
                max_dist_y = float('inf')

            max_dist = min(max_dist_x, max_dist_y)
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

    def _generate_perimeter_polygon(self, stage: Stage,
                                     back_y: Optional[float] = None,
                                     rotation: Optional[float] = None) -> List[Tuple[float, float]]:
        """Genera il poligono dell'area di tiro a forma di lettera dell'alfabeto.

        La lettera viene scalata alle dimensioni dello stage, ruotata
        casualmente di 0/90/180/270 gradi, e leggermente perturbata.
        Il perimetro è completamente chiuso, accessibile dalla parte
        opposta al parapalle (fronte up-range). I bersagli vengono
        posizionati INTORNO, mai dietro.

        Il poligono risultato è validato con validate_polygon() per
        garantire: area > 0, nessuna auto-intersezione, vertici non coincidenti.
        """
        margin = MIN_TARGET_TO_EDGE
        w = stage.width
        # Riserva MIN_BACKSTOP_DEPTH metri tra area di tiro e parapalle
        backstop_margin = MIN_BACKSTOP_DEPTH
        d_eff = back_y if back_y is not None else stage.depth - backstop_margin

        def _clamp(poly: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
            result = []
            for px, py in poly:
                nx = max(margin + 0.1, min(w - margin - 0.1, px))
                ny = max(margin + 0.1, min(d_eff - margin - 0.1, py))
                result.append((round(nx, 2), round(ny, 2)))
            return result

        def _rotate_poly(poly: List[Tuple[float, float]], angle_deg: float,
                          cx: float, cy: float) -> List[Tuple[float, float]]:
            angle = math.radians(angle_deg)
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            result = []
            for px, py in poly:
                dx = px - cx
                dy = py - cy
                nx = cx + dx * cos_a - dy * sin_a
                ny = cy + dx * sin_a + dy * cos_a
                result.append((round(nx, 2), round(ny, 2)))
            return result

        def _perturb(poly: List[Tuple[float, float]], amount: float = 0.3) -> List[Tuple[float, float]]:
            result = []
            for px, py in poly:
                nx = px + random.uniform(-amount, amount)
                ny = py + random.uniform(-amount, amount)
                result.append((round(nx, 2), round(ny, 2)))
            return result

        # Sceglie la lettera
        shape_type = self.config.letter_shape
        if shape_type in LETTER_SHAPES:
            letter = shape_type
        else:
            letter = random.choice(list(LETTER_SHAPES.keys()))
        norm_verts = LETTER_SHAPES[letter]

        # Calcola margine dinamico in base ai tipi di bersaglio:
        # - bersagli steel (popper, plate) richiedono MIN_STEEL_PLACEMENT_DISTANCE
        #   dal perimetro + 1m dal bordo stage
        # - bersagli carta richiedono 1m dal perimetro + 1m dal bordo = 2m
        # Usa il massimo tra le esigenze dei bersagli configurati
        has_steel = (
            self.config.num_steel > 0 or
            self.config.num_poppers > 0 or
            self.config.num_plates > 0 or
            (self.config.auto_distribution and self.config.course_type)
        )
        if has_steel:
            # Per steel: MIN_STEEL_PLACEMENT_DISTANCE + 2m (range random) + 1m (bordo stage)
            dynamic_inset = max(margin + 1.0, MIN_STEEL_PLACEMENT_DISTANCE + 3.0)
        else:
            dynamic_inset = margin + 1.0
        # Limita l'inset per non rendere l'area di tiro troppo piccola
        max_inset_w = (w - MIN_POLY_DIM) / 2
        max_inset_d = (d_eff - MIN_POLY_DIM) / 2
        inset = min(dynamic_inset, max_inset_w, max_inset_d)
        scale_x = w - 2 * inset
        scale_y = d_eff - 2 * inset
        # Se lo stage è troppo piccolo per ospitare steel, scala tutto
        # e posiziona i bersagli più vicini (con avviso)
        if scale_x < MIN_POLY_DIM or scale_y < MIN_POLY_DIM:
            # Fallback: usa margine minimo
            inset = margin + 1.0
            scale_x = w - 2 * inset
            scale_y = d_eff - 2 * inset

        poly = []
        for nx, ny in norm_verts:
            x = inset + nx * scale_x
            y = inset + ny * scale_y
            poly.append((x, y))

        # Rotazione casuale
        if rotation is None:
            rotation = random.choice([0, 90, 180, 270])
        if rotation != 0:
            cx, cy = w / 2, d_eff / 2
            poly = _rotate_poly(poly, rotation, cx, cy)
            poly = _clamp(poly)

        # Tentativo con perturbazione: se invalido, usa poligono pulito
        for attempt in range(5):
            test_poly = _perturb(poly, amount=0.3)
            clamped = _clamp(test_poly)
            valid, errors = validate_polygon(clamped, min_vertices=4)
            if valid:
                return clamped

        # Fallback: poligono pulito senza perturbazione
        valid, errors = validate_polygon(poly, min_vertices=4)
        if not valid:
            # Ultima risorsa: lettera O semplice
            norm_verts = LETTER_SHAPES["O"]
            poly = [(inset + nx * scale_x, inset + ny * scale_y) for nx, ny in norm_verts]
            return _clamp(poly)
        return _clamp(poly)

    def _generate_perimeter_items(self, stage: Stage,
                                   poly: List[Tuple[float, float]]) -> List[StageItem]:
        """Converte il poligono del perimetro in item Stage.

        Per fault lines: genera tutti i segmenti (linee a terra non bloccano).
        Per barriere/walls: lascia un'apertura di FRONT_OPEN_GAP sul fronte
        (lato up-range) identificando il segmento orizzontale frontale più
        lungo e accorciandolo.

        Tutti gli item perimetrali ricevono `properties["perimeter"] = True`
        e `properties["closed_chain"] = True` per indicare che formano un
        ciclo chiuso.
        """
        items = []
        style = self.config.delimitation
        n = len(poly)

        if n < 3:
            return items

        is_blocking = style in ("barriers", "walls", "mixed")
        skip_idx = -1

        # Per barriere/walls: trova il segmento frontale (y minima) da accorciare
        if is_blocking:
            best_idx = -1
            best_y = float('inf')
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                mid_y = (y1 + y2) / 2
                seg_len = math.hypot(x2 - x1, y2 - y1)
                angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180)
                is_horizontal = angle < 30 or angle > 150
                if is_horizontal and seg_len >= FRONT_OPEN_GAP and mid_y < best_y:
                    best_y = mid_y
                    best_idx = i

            if best_idx >= 0:
                x1, y1 = poly[best_idx]
                x2, y2 = poly[(best_idx + 1) % n]
                seg_len = math.hypot(x2 - x1, y2 - y1)
                # Due segmenti con gap centrale di FRONT_OPEN_GAP
                gap_half = max(0.05, (seg_len - FRONT_OPEN_GAP) / 2 / seg_len)
                for (sx1, sy1, sx2, sy2) in [
                    (x1, y1,
                     x1 + (x2 - x1) * gap_half, y1 + (y2 - y1) * gap_half),
                    (x1 + (x2 - x1) * (1 - gap_half), y1 + (y2 - y1) * (1 - gap_half),
                     x2, y2)
                ]:
                    cx = (sx1 + sx2) / 2
                    cy = (sy1 + sy2) / 2
                    seg_len = math.hypot(sx2 - sx1, sy2 - sy1)
                    if seg_len < 0.3:
                        continue
                    angle = math.degrees(math.atan2(sy2 - sy1, sx2 - sx1))
                    if style == "mixed":
                        itype, thick, color, label = ItemType.FAULT_LINE, 0.0, TARGET_COLORS["fault_line"], "Fault Line"
                    elif style == "barriers":
                        itype, thick, color, label = ItemType.BARRIER, 0.15, TARGET_COLORS["barrier"], "Barriera"
                    else:
                        itype, thick, color, label = ItemType.WALL, 0.2, TARGET_COLORS["wall"], "Muro"
                    item = StageItem(0, itype, cx, cy, seg_len, thick, angle, color, label)
                    item.properties["perimeter"] = True
                    item.properties["closed_chain"] = True
                    items.append(item)
                skip_idx = best_idx

        # Genera i segmenti rimanenti
        style_map = {
            "fault_lines": (ItemType.FAULT_LINE, 0.0, TARGET_COLORS["fault_line"], "Fault Line"),
            "barriers":    (ItemType.BARRIER, 0.15, TARGET_COLORS["barrier"], "Barriera"),
            "walls":       (ItemType.WALL, 0.2, TARGET_COLORS["wall"], "Muro"),
        }

        for i in range(n):
            if i == skip_idx:
                continue
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            length = math.hypot(x2 - x1, y2 - y1)
            if length < 0.3:
                continue
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))

            if style == "mixed":
                if abs(cy - stage.depth / 2) > abs(cx - stage.width / 2):
                    itype, thick, color, label = ItemType.BARRIER, 0.15, TARGET_COLORS["barrier"], "Barriera"
                else:
                    itype, thick, color, label = ItemType.FAULT_LINE, 0.0, TARGET_COLORS["fault_line"], "Fault Line"
            else:
                itype, thick, color, label = style_map.get(style, style_map["fault_lines"])

            item = StageItem(0, itype, cx, cy, length, thick, angle, color, label)
            item.properties["perimeter"] = True
            item.properties["closed_chain"] = True
            items.append(item)

        return items

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

                if still_visible:
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

    def _resolve_target_counts(self, cfg: GeneratorConfig) -> dict:
        """Calcola i conteggi bersagli in base al course_type e ai parametri.

        Se auto_distribution \u00e8 True e course_type \u00e8 impostato, usa le
        distribuzioni tipiche dai PDF reali (Short=5+1+1, Medium=11+1+2, Long=15+2+2).
        Altrimenti usa i valori letterali della configurazione.
        """
        if not cfg.auto_distribution or not cfg.course_type:
            # Calcola poppers/plates da num_steel se non specificati
            if cfg.num_poppers > 0 or cfg.num_plates > 0:
                poppers = cfg.num_poppers
                plates = cfg.num_plates
            else:
                poppers = max(1, round(cfg.num_steel * 0.6)) if cfg.num_steel > 0 else 1
                plates = max(0, cfg.num_steel - poppers) if cfg.num_steel > 0 else 1
            # Se num_steel==0 ma user ha specificato poppers/plates
            if cfg.num_steel == 0 and cfg.num_poppers == 0 and cfg.num_plates == 0:
                poppers = 0
                plates = 0
            return {
                "paper": cfg.num_targets,
                "poppers": poppers,
                "plates": plates,
                "mini": cfg.num_mini,
                "moving": cfg.num_moving,
            }

        # Auto-distribution per course type (basata su PDF reali)
        ct = cfg.course_type
        if ct == "short":
            base = {"paper": 5, "poppers": 1, "plates": 1, "mini": 0, "moving": 0}
        elif ct == "medium":
            base = {"paper": 11, "poppers": 1, "plates": 2, "mini": 1, "moving": 1}
        elif ct == "long":
            base = {"paper": 15, "poppers": 2, "plates": 2, "mini": 1, "moving": 2}
        else:
            base = {"paper": 8, "poppers": 1, "plates": 1, "mini": 0, "moving": 1}

        # Sovrascrivi con valori espliciti dell'utente
        if cfg.num_targets > 0:
            base["paper"] = cfg.num_targets
        has_explicit_steel = cfg.num_poppers > 0 or cfg.num_plates > 0
        if cfg.num_poppers > 0:
            base["poppers"] = cfg.num_poppers
        elif cfg.num_steel > 0 and not has_explicit_steel:
            base["poppers"] = max(1, round(cfg.num_steel * 0.6))
        if cfg.num_plates > 0:
            base["plates"] = cfg.num_plates
        elif cfg.num_steel > 0 and not has_explicit_steel:
            base["plates"] = max(0, cfg.num_steel - base["poppers"])
        if cfg.num_mini > 0:
            base["mini"] = cfg.num_mini
        if cfg.num_moving > 0:
            base["moving"] = cfg.num_moving

        return base

    def _create_activator_relationships(
        self, stage: Stage, items: List[StageItem],
        activators: List[StageItem]
    ) -> None:
        """Collega poppers/plates a bersagli attivati (mobili o paper).

        Priorità: bersagli MOBILI (swinger, drop_turner, mover) > paper target.

        Per ogni attivatore (popper/plate), trova bersagli nelle immediate
        vicinanze (distanza < MAX_ACTIVATOR_MOVING_DISTANCE per mobili,
        < MAX_ACTIVATOR_DISTANCE per paper) nello stesso settore
        (angolo ≤ ACTIVATOR_SECTOR_ANGLE_DEG) e li marca come attivati.

        I bersagli mobili devono essere attivati da bersagli metallici
        posti nelle immediate vicinanze (Req. 6).

        Genera descrizioni testuali per il briefing alla IPSC:
            'P1 attiva S1 (Swinger) che resterà visibile al termine del movimento'
        """
        if not activators or not self._perimeter_poly:
            return

        # Centro area di tiro
        cx = sum(p[0] for p in self._perimeter_poly) / len(self._perimeter_poly)
        cy = sum(p[1] for p in self._perimeter_poly) / len(self._perimeter_poly)

        # Tutti i bersagli attivabili (non ancora attivati)
        # Priorità 1: bersagli MOBILI (swinger, drop_turner, mover)
        moving_targets = [it for it in items
                          if it.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
                          and "activated_by" not in it.properties]
        # Priorità 2: paper target (fallback)
        papers = [it for it in items
                  if it.item_type in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET)
                  and "activated_by" not in it.properties]

        if not moving_targets and not papers:
            return

        # Ordina attivatori per distanza dal centro (più vicini prima)
        activators.sort(key=lambda a: euclidean_distance(a.x, a.y, cx, cy))

        used_targets = set()
        descs = []

        # --- Passata 1: attiva bersagli MOBILI (distanza ravvicinata) ---
        for act_idx, activator in enumerate(activators):
            if not moving_targets:
                break

            act_angle = math.atan2(activator.y - cy, activator.x - cx)
            nearby = []
            for mt in moving_targets:
                if mt.id in used_targets:
                    continue
                mt_angle = math.atan2(mt.y - cy, mt.x - cx)
                angle_diff = abs(act_angle - mt_angle)
                if angle_diff > math.pi:
                    angle_diff = 2 * math.pi - angle_diff
                dist = euclidean_distance(activator.x, activator.y, mt.x, mt.y)
                if angle_diff < math.radians(ACTIVATOR_SECTOR_ANGLE_DEG) and dist < MAX_ACTIVATOR_MOVING_DISTANCE:
                    nearby.append((dist, mt))

            if not nearby:
                continue

            nearby.sort(key=lambda x: x[0])
            selected = [mt for _, mt in nearby[:MAX_ACTIVATED_PER_ACTIVATOR]]
            sel_ids = [s.id for s in selected]

            activator.properties["activates"] = sel_ids
            activator.properties["is_activator"] = True
            label_prefix = "P" if activator.item_type == ItemType.POPPER else "MP"
            activator.label = f"{label_prefix}{act_idx + 1}"

            type_labels = {
                ItemType.SWINGER: "Swinger",
                ItemType.DROP_TURNER: "Drop Turner",
                ItemType.MOVER: "Mover",
            }
            for s in selected:
                s.properties["activated_by"] = [activator.id]
                s.properties["activation_visible"] = True
                used_targets.add(s.id)

            label = activator.label
            target_strs = []
            for sid in sel_ids:
                s_item = next((x for x in items if x.id == sid), None)
                if s_item:
                    tlabel = type_labels.get(s_item.item_type, "")
                    if not s_item.label or s_item.label in ("Paper", "Mini", "Popper", "Plate"):
                        s_item.label = f"S{sid}"
                    target_strs.append(f"{s_item.label} ({tlabel})" if tlabel else s_item.label)
                else:
                    target_strs.append(f"S{sid}")
            congiunzione = " e " if len(target_strs) > 1 else ""
            vis = "resteranno visibili" if len(target_strs) > 1 else "resterà visibile"
            desc = f"{label} attiva {congiunzione.join(target_strs)} che {vis} al termine del movimento"
            descs.append(desc)

        # --- Passata 2: attiva PAPER TARGET (fallback, distanza maggiore) ---
        for act_idx, activator in enumerate(activators):
            if "is_activator" in activator.properties:
                continue  # già usato per un mobile
            if not papers:
                continue

            act_angle = math.atan2(activator.y - cy, activator.x - cx)
            nearby = []
            for p in papers:
                if p.id in used_targets:
                    continue
                p_angle = math.atan2(p.y - cy, p.x - cx)
                angle_diff = abs(act_angle - p_angle)
                if angle_diff > math.pi:
                    angle_diff = 2 * math.pi - angle_diff
                dist = euclidean_distance(activator.x, activator.y, p.x, p.y)
                if angle_diff < math.radians(ACTIVATOR_SECTOR_ANGLE_DEG) and dist < MAX_ACTIVATOR_DISTANCE:
                    nearby.append((dist, p))

            if not nearby:
                continue

            nearby.sort(key=lambda x: x[0])
            selected = [p for _, p in nearby[:MAX_ACTIVATED_PER_ACTIVATOR]]
            sel_ids = [s.id for s in selected]

            existing_activates = activator.properties.get("activates", [])
            sel_ids = existing_activates + [sid for sid in sel_ids if sid not in existing_activates]

            activator.properties["activates"] = sel_ids
            activator.properties["is_activator"] = True
            if not activator.properties.get("_labeled"):
                label_prefix = "P" if activator.item_type == ItemType.POPPER else "MP"
                activator.label = f"{label_prefix}{act_idx + 1}"
                activator.properties["_labeled"] = True

            for s in selected:
                s.properties["activated_by"] = s.properties.get("activated_by", []) + [activator.id]
                s.properties["activation_visible"] = True
                used_targets.add(s.id)

            label = activator.label or f"{activator.item_type.name}#{activator.id}"
            target_strs = []
            for sid in sel_ids:
                s_item = next((x for x in items if x.id == sid), None)
                if s_item:
                    if not s_item.label or s_item.label in ("Paper", "Mini", "Popper", "Plate"):
                        s_item.label = f"T{sid}"
                    target_strs.append(s_item.label)
                else:
                    target_strs.append(f"T{sid}")
            congiunzione = " e " if len(target_strs) > 1 else ""
            vis = "resteranno visibili" if len(target_strs) > 1 else "resterà visibile"
            desc = f"{label} attiva {congiunzione.join(target_strs)} che {vis} al termine del movimento"
            descs.append(desc)

        if descs:
            stage.properties["activator_descs"] = descs
            stage.properties["procedure"] = (
                "Al segnale di partenza ingaggiare tutti i bersagli. "
                + " ".join(descs) + "."
            )

    def _populate_stage_metadata(
        self, stage: Stage, cfg: GeneratorConfig,
        num_poppers: int, num_plates: int, num_moving: int
    ) -> None:
        """Popola i metadati di briefing nello stage."""
        # Non sovrascrivere se gi\u00e0 popolati (es. da caricamento file)
        if stage.properties.get("start_signal"):
            return

        stage.properties["start_signal"] = "Acustico"

        # Posizione di partenza in base alla difficolt\u00e0
        if cfg.difficulty == "hard":
            stage.properties["start_position"] = "Talloni che toccano i segni come mostrato"
        elif cfg.difficulty == "easy":
            stage.properties["start_position"] = "Ovunque nella shooting area"
        else:
            stage.properties["start_position"] = "In piedi nella shooting area"

        # Condizione pronto arma
        stage.properties["ready_condition_handgun"] = (
            "In piedi come da regolamento IPSC Handgun punto 8.2.2 (Appendice E2), come mostrato"
        )
        stage.properties["ready_condition_pcc"] = (
            "In piedi come da regolamento IPSC PCC punto 8.2.2 (Appendice E1), come mostrato"
        )
        if cfg.difficulty == "hard":
            stage.properties["handgun_condition"] = "Arma scarica in fondina"
            stage.properties["pcc_condition"] = "Scarico Option 3"
        else:
            stage.properties["handgun_condition"] = "Arma in fondina caricatore inserito colpo non camerato"
            stage.properties["pcc_condition"] = "Carico Option 1"

        # Procedura (se non gi\u00e0 generata dagli attivatori)
        if "procedure" not in stage.properties:
            stage.properties["procedure"] = "Al segnale di partenza ingaggiare tutti i bersagli."

        # Calcolo punti massimi (default: 5 per paper, 5 per popper/plate)
        paper_count = sum(1 for it in stage.items
                          if it.item_type in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET))
        steel_count = sum(1 for it in stage.items
                          if it.item_type in (ItemType.POPPER, ItemType.METAL_PLATE))
        # IPSC: ogni paper vale max 5 punti (10 per double), ogni popper 5, ogni plate 5
        # Per semplicit\u00e0: 5 per paper (2 colpi) + 5 per steel (1 colpo)
        stage.properties["max_points"] = paper_count * 10 + steel_count * 5

        # Metadati aggiuntivi
        stage.properties["angoli_sicurezza"] = "90\u00b0 laterali e parapalle in verticale"
        stage.properties["hard_cover"] = "Le strutture sono hard cover"
        stage.properties["note"] = (
            "Il punteggio verr\u00e0 conteggiato durante l'esecuzione dell'esercizio. "
            "Il tiratore potr\u00e0 delegare un altro tiratore alla verifica del punteggio."
        )

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

    def _score_stage(self, stage: Stage, items: List[StageItem]) -> float:
        """Valuta la qualità dello stage (più alto = migliore)."""
        score = 0.0
        targets = [it for it in items if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
            ItemType.POPPER, ItemType.METAL_PLATE,
            ItemType.MINI_TARGET, ItemType.MICRO_TARGET)]
        walls = [it for it in items if it.item_type in (
            ItemType.WALL, ItemType.BARRIER)]

        # Più bersagli = più colpi possibili
        score += len(targets) * 10

        # Steel varietà (poppers + plates)
        steel = [it for it in targets if it.item_type in (
            ItemType.STEEL_TARGET, ItemType.POPPER, ItemType.METAL_PLATE)]
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
                    total_dist += euclidean_distance(a.x, a.y, b.x, b.y)
                    count += 1
            if count > 0:
                avg_dist = total_dist / count
                score += max(0, 20 - abs(avg_dist - 3.5) * 5)

        # Uso area (copertura)
        if len(walls) > 0:
            score += len(walls) * 3

        # Perimetro poligonale
        perim_items = [it for it in items if it.item_type in (
            ItemType.FAULT_LINE, ItemType.WALL, ItemType.BARRIER)]
        score += len(perim_items) * 2
        if len(self._perimeter_poly) >= 5:
            score += 5
        if len(self._perimeter_poly) >= 6:
            score += 5

        # Bonus per visibilità bersagli (tutti visibili = stage ben progettato)
        visible_count = 0
        blockers = self._get_blocking_walls(items)
        for t in targets:
            if self._is_target_visible(t, blockers):
                visible_count += 1
        if targets:
            visibility_pct = visible_count / len(targets)
            if visibility_pct >= 0.9:
                score += 15
            elif visibility_pct >= 0.7:
                score += 8

        # Difficoltà bonus
        if self.config.difficulty == "hard":
            score *= 1.2

        return round(score, 2)
