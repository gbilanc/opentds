# core/generator.py
"""Generatore procedurale di stage con vincoli IPSC."""
from __future__ import annotations
import random
import math
import time
from typing import List, Tuple, Optional
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

from core.models import Stage, StageItem, ItemType, CourseType
from core.ipsc_rules import IPSCRulesEngine
from core.geometry import (
    point_in_polygon,
    polygon_center,
    segments_intersect,
    line_intersects_rect,
    euclidean_distance,
)
from core.collision import item_obb, min_distance_between as obb_distance


# ── Helper functions per classificazione tipi IPSC ─────────────────────────

def _is_paper_like(t: "ItemType") -> bool:
    """True per tipi bersaglio cartaceo."""
    return t in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET, ItemType.MICRO_TARGET)

def _is_steel_like(t: "ItemType") -> bool:
    """True per tipi bersaglio metallico."""
    return t in (ItemType.STEEL_TARGET, ItemType.POPPER, ItemType.METAL_PLATE)

def _is_scoring_target(t: "ItemType") -> bool:
    """True per tutti i bersagli che assegnano punti."""
    return _is_paper_like(t) or _is_steel_like(t) or t in (
        ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)

def _is_obstacle(t: "ItemType") -> bool:
    """True per ostacoli/barriere/muri/coperture."""
    return t in (ItemType.WALL, ItemType.BARRIER, ItemType.DOOR,
                  ItemType.HARD_COVER, ItemType.SOFT_COVER)


@dataclass
class GeneratorConfig:
    stage_width: float = 20.0
    stage_depth: float = 15.0
    num_targets: int = 8
    num_steel: int = 2
    num_moving: int = 1  # swinger / drop_turner / mover
    num_walls: int = 1
    num_barriers: int = 4
    include_fault_lines: bool = True
    include_no_shoots: bool = True
    difficulty: str = "medium"  # easy | medium | hard
    delimitation: str = "fault_lines"  # fault_lines | barriers | walls | mixed
    seed: Optional[int] = None
    max_attempts: int = 500
    discipline: str = "ipsc_pistol"  # ipsc_pistol | mini_rifle | shotgun
    letter_shape: str = "random"  # random (lettera casuale) | L | T | U | C | H | F | O | Z | S | X | Y | M | N | E
    course_type: str = ""  # "short" | "medium" | "long" | "" = non classificato


@dataclass
class GeneratorResult:
    stage: Stage
    score: float
    attempts: int


# ── Forme alfabetiche per l'area di tiro ──────────────────────────────
# Ogni forma è definita come lista di vertici in coordinate normalizzate (0-1)
# in senso antiorario. (0,0) = angolo basso-sinistra dello stage.
# La forma viene scalata alle dimensioni dello stage e perturbata.

LETTER_SHAPES: dict[str, List[Tuple[float, float]]] = {
    "L": [
        (0.00, 0.00), (1.00, 0.00), (1.00, 0.35),
        (0.35, 0.35), (0.35, 1.00), (0.00, 1.00),
    ],
    "T": [
        (0.00, 0.65), (0.35, 0.65), (0.35, 0.00),
        (0.65, 0.00), (0.65, 0.65), (1.00, 0.65),
        (1.00, 1.00), (0.00, 1.00),
    ],
    "U": [
        (0.00, 0.00), (1.00, 0.00), (1.00, 1.00),
        (0.70, 1.00), (0.70, 0.25), (0.30, 0.25),
        (0.30, 1.00), (0.00, 1.00),
    ],
    "C": [
        (0.00, 0.00), (1.00, 0.00), (1.00, 0.20),
        (0.20, 0.20), (0.20, 0.80), (1.00, 0.80),
        (1.00, 1.00), (0.00, 1.00),
    ],
    "H": [
        (0.00, 0.00), (0.30, 0.00), (0.30, 0.35),
        (0.70, 0.35), (0.70, 0.00), (1.00, 0.00),
        (1.00, 1.00), (0.70, 1.00), (0.70, 0.65),
        (0.30, 0.65), (0.30, 1.00), (0.00, 1.00),
    ],
    "F": [
        (0.25, 0.00), (1.00, 0.00), (1.00, 0.25),
        (0.55, 0.25), (0.55, 0.50), (1.00, 0.50),
        (1.00, 0.75), (0.55, 0.75), (0.55, 1.00),
        (0.25, 1.00), (0.25, 0.00),
    ],
    "O": [
        (0.00, 0.00), (1.00, 0.00), (1.00, 1.00), (0.00, 1.00),
    ],
    "Z": [
        (0.00, 0.65), (0.65, 0.65), (0.00, 0.00),
        (1.00, 0.00), (0.35, 0.65), (1.00, 0.65),
        (1.00, 1.00), (0.00, 1.00),
    ],
    "S": [
        (0.00, 0.00), (1.00, 0.00), (1.00, 0.20),
        (0.25, 0.20), (0.25, 0.40), (1.00, 0.40),
        (1.00, 0.60), (0.25, 0.60), (0.25, 0.80),
        (1.00, 0.80), (1.00, 1.00), (0.00, 1.00),
    ],
    # ── Nuove forme ──────────────────────────────────────────────────────
    "X": [
        # Plus / croce: quattro bracci che si incontrano al centro
        (0.35, 0.00), (0.65, 0.00), (0.65, 0.35),
        (1.00, 0.35), (1.00, 0.65), (0.65, 0.65),
        (0.65, 1.00), (0.35, 1.00), (0.35, 0.65),
        (0.00, 0.65), (0.00, 0.35), (0.35, 0.35),
    ],
    "Y": [
        # Stelo centrale in basso, biforcazione in alto a V
        (0.40, 0.00), (0.60, 0.00), (0.60, 0.40),
        (1.00, 0.70), (1.00, 1.00), (0.00, 1.00),
        (0.00, 0.70), (0.40, 0.40),
    ],
    "M": [
        # Due gambe in basso, V centrale in alto
        (0.00, 0.00), (0.25, 0.00), (0.25, 1.00),
        (0.50, 0.50), (0.75, 1.00), (0.75, 0.00),
        (1.00, 0.00), (1.00, 1.00), (0.00, 1.00),
    ],
    "N": [
        # Due barre verticali collegate da diagonale
        (0.00, 0.00), (0.25, 0.00), (0.25, 0.70),
        (0.75, 0.00), (1.00, 0.00), (1.00, 1.00),
        (0.75, 1.00), (0.75, 0.30), (0.25, 1.00),
        (0.00, 1.00),
    ],
    "E": [
        # Tre ripiani orizzontali a destra, barra verticale a sinistra
        (0.00, 0.00), (1.00, 0.00), (1.00, 0.25),
        (0.30, 0.25), (0.30, 0.40), (1.00, 0.40),
        (1.00, 0.60), (0.30, 0.60), (0.30, 0.75),
        (1.00, 0.75), (1.00, 1.00), (0.00, 1.00),
    ],
}


class StageGenerator:
    """Generatore procedurale constraint-based."""

    def __init__(self, config: GeneratorConfig):
        self.config = config
        if config.seed is not None:
            random.seed(config.seed)
        self._perimeter_poly: List[Tuple[float, float]] = []  # vertici poligono area di tiro
        self._interior_samples: List[Tuple[float, float]] = []  # punti interni per visibility check

    def generate(self) -> GeneratorResult:
        """Genera uno stage IPSC valido con zero violazioni.

        Strategia:
        1. Genera lo stage una volta
        2. Valida con IPSCRulesEngine
        3. Se ci sono violazioni, applica riparazioni mirate finché
           non sono tutte risolte o scade il timeout
        4. Se timeout, rigenera da capo con seed diverso
        """
        cfg = self.config
        disc = cfg.discipline
        deadline = time.monotonic() + 20.0

        for mega_attempt in range(20):
            if time.monotonic() > deadline:
                break

            if mega_attempt > 0 and cfg.seed is None:
                random.seed()

            result = self._generate_once(cfg, disc)
            stage = result.stage

            engine = IPSCRulesEngine(stage)
            engine.set_discipline(disc)

            # Loop di riparazione: applica fix finché non ci sono più violazioni
            for repair_cycle in range(15):
                if time.monotonic() > deadline:
                    break

                v = engine.validate()
                if not v.violations:
                    return result

                repaired = self._repair_violations(stage, v.violations, engine)
                if not repaired:
                    break  # Nessuna riparazione possibile, rigenera

                # Ricrea engine dopo le modifiche allo stage
                engine = IPSCRulesEngine(stage)
                engine.set_discipline(disc)

        # Fallback: ultimo tentativo senza garanzia
        result = self._generate_once(cfg, disc)
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
        poly = self._generate_perimeter_polygon(stage)
        self._perimeter_poly = poly
        self._interior_samples = self._sample_interior_points(20)
        items.extend(self._generate_perimeter_items(stage, poly))

        # 2. Posiziona bersagli INTORNO all'area di tiro (fuori dal perimetro)
        #    Richiede almeno MIN_TARGETS (8) bersagli totali
        min_targets = IPSCRulesEngine.MIN_TARGETS
        paper_target = max(cfg.num_targets - cfg.num_steel, min_targets - cfg.num_steel)
        paper_target = max(paper_target, 0)

        paper_placed = 0
        for _ in range(paper_target * 2):  # oversample per garantire il minimo
            if paper_placed >= paper_target:
                break
            it = self._place_target_around(stage, items, ItemType.PAPER_TARGET, engine)
            if it:
                items.append(it)
                paper_placed += 1
            attempts += 1

        steel_placed = 0
        for _ in range(cfg.num_steel * 2):
            if steel_placed >= cfg.num_steel:
                break
            it = self._place_target_around(stage, items, ItemType.STEEL_TARGET, engine)
            if it:
                items.append(it)
                steel_placed += 1
            attempts += 1

        # Se non abbiamo abbastanza bersagli, aggiungi altri paper
        # (con limite ragionevole per non stallare)
        fill_attempts = 0
        while len([x for x in items if _is_scoring_target(x.item_type)]) < min_targets:
            it = self._place_target_around(stage, items, ItemType.PAPER_TARGET, engine)
            if it:
                items.append(it)
            attempts += 1
            fill_attempts += 1
            if fill_attempts > 50:
                break

        # 3. Bersagli mobili
        moving_types = [ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER]
        for i in range(cfg.num_moving):
            mtype = moving_types[i % len(moving_types)]
            it = self._place_target_around(stage, items, mtype, engine, is_moving=True)
            if it:
                items.append(it)
            attempts += 1

        # 4. Muri/barriere FUORI dall'area di tiro
        items.extend(self._generate_walls(stage, items))
        items.extend(self._generate_barriers(stage, items))

        # 5. Aggiunge muri restrittivi (con validazione posizioni)
        items.extend(self._add_restrictive_walls(stage, items, engine))

        # 6. No-shoots
        if cfg.include_no_shoots:
            ns_count = max(1, len([x for x in items if _is_scoring_target(x.item_type)]) // 4)
            for _ in range(ns_count):
                it = self._place_no_shoot(stage, items, engine)
                if it:
                    items.append(it)
                attempts += 1

        # 7. Garantisce che TUTTI i bersagli siano visibili
        items = self._ensure_target_visibility(stage, items)

        # Assegna tutti gli item allo stage
        for it in items:
            stage.add_item(it)

        score = self._score_stage(stage, items)
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

        Per ogni item: sceglie un bersaglio casuale e un punto interno all'area
        di tiro, poi piazza l'item sulla linea tra i due, FUORI dal perimetro.
        Ogni item deve bloccare almeno 1 bersaglio senza nasconderne troppi.
        """
        items = []
        targets = [it for it in existing if _is_scoring_target(it.item_type)]
        if not targets or not self._perimeter_poly or not self._interior_samples:
            return items

        min_visible = max(1, math.ceil(len(targets) * 0.7))

        for _ in range(count):
            placed = False
            for _ in range(100):
                t = random.choice(targets)
                ox, oy = random.choice(self._interior_samples)

                # Direzione dal punto interno al bersaglio
                dx = t.x - ox
                dy = t.y - oy
                dist = math.hypot(dx, dy)
                if dist < 2.0:
                    continue
                nx, ny = dx / dist, dy / dist

                # Posiziona l'item a una frazione della distanza (tra area e target)
                t_frac = random.uniform(0.3, 0.7)
                wx = ox + nx * dist * t_frac
                wy = oy + ny * dist * t_frac
                wx = max(1.5, min(stage.width - 1.5, wx))
                wy = max(1.5, min(stage.depth - 1.5, wy))

                # Deve stare FUORI dal perimetro
                if point_in_polygon(wx, wy, self._perimeter_poly):
                    continue

                angle_to_target = math.degrees(math.atan2(dy, dx))
                rotation = angle_to_target + random.choice([-90, 90])

                item = StageItem(0, item_type, wx, wy,
                                 base_width(), base_height,
                                 rotation, color, label)

                # Deve bloccare ALMENO 1 bersaglio (linea di vista interrotta)
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

                # Non deve sovrapporsi ad altri ostacoli (usa is_valid_position)
                from core.ipsc_rules import IPSCRulesEngine
                local_engine = IPSCRulesEngine(stage)
                if not local_engine.is_valid_position(item, existing + items):
                    continue

                # Non deve nascondere TROPPI bersagli
                test_items = existing + items + [item]
                test_blockers = self._get_blocking_walls(test_items)
                visible_now = sum(1 for t2 in targets
                                  if self._is_target_visible(t2, test_blockers))
                if visible_now >= min_visible:
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
            w, h = 0.30, 0.30
            color = "#d1d5db"  # IPSC: bianco (grigio chiaro per visibilità)
            label = "Steel"
            min_dist_from_edge = 8.0  # IPSC: distanza fissa 8m
        elif is_moving:
            # IPSC: bersagli mobili su supporto cartaceo → marrone
            colors = {
                ItemType.SWINGER: ("#A0522D", "Swinger"),
                ItemType.DROP_TURNER: ("#8B6914", "Drop Turner"),
                ItemType.MOVER: ("#CD853F", "Mover"),
            }
            color, label = colors.get(ttype, ("#808080", ""))
            w, h = 0.45, 0.45
            min_dist_from_edge = 1.0
        else:
            w, h = 0.45, 0.45
            color = "#8B4513"  # IPSC: marrone zona punti
            label = "Paper"
            min_dist_from_edge = 1.0

        for _ in range(self.config.max_attempts):
            edge_idx = random.randrange(n)
            x1, y1 = poly[edge_idx]
            x2, y2 = poly[(edge_idx + 1) % n]
            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            if length < 0.3:
                continue

            # Posizione lungo il lato (interpolazione)
            t = random.uniform(0.1, 0.9)
            ex = x1 + dx * t
            ey = y1 + dy * t

            # Normale uscente (per poligono in senso antiorario)
            nx = dy / length
            ny = -dx / length

            # Salta i lati che puntano VERSO L'INGRESSO (ny < -0.3 = componente
            # negativa verso l'entrata). I bersagli devono stare SOLO tra
            # l'area di tiro e il parapalle di fondo/laterali, MAI verso ingresso.
            if ny < -0.3:
                continue

            # Distanza dal lato
            dist = random.uniform(min_dist_from_edge, min_dist_from_edge + 3.0)
            px = ex + nx * dist
            py = ey + ny * dist

            # Deve stare dentro lo stage, con backstop minimo garantito
            # (t.y + t.height/2 <= d - MIN_BACKSTOP_DEPTH)
            backstop_margin = IPSCRulesEngine.MIN_BACKSTOP_DEPTH
            half_h = (h if not is_moving else 0.45) / 2
            max_y = stage.depth - backstop_margin - half_h - 0.2
            if not (margin <= px <= stage.width - margin and
                    margin <= py <= max_y):
                continue

            # Deve stare FUORI dal perimetro
            if point_in_polygon(px, py, poly):
                continue

            # Orientamento VERSO IL PARAPALLE DI FONDO o LATERALE, MAI verso ingresso
            # Calcola tre direzioni candidate: verso il centro del parapalle,
            # verso il parapalle sinistro, verso il parapalle destro.
            # Sceglie quella con la maggior componente down-range (y positiva).
            backstop_cx = stage.width / 2
            backstop_cy = stage.depth
            left_cx = 0.0
            left_cy = stage.depth / 2
            right_cx = stage.width
            right_cy = stage.depth / 2

            candidates = [
                (backstop_cx, backstop_cy),
                (left_cx, left_cy),
                (right_cx, right_cy),
            ]
            best_angle = None
            best_downrange = -float('inf')
            for tcx, tcy in candidates:
                a = math.degrees(math.atan2(tcy - py, tcx - px))
                # La componente down-range è positiva se il bersaglio
                # punta verso y crescenti (verso il fondo dello stage)
                dy_component = math.cos(math.radians(a - 90))
                if dy_component > best_downrange:
                    best_downrange = dy_component
                    best_angle = a

            rot = best_angle + random.uniform(-10, 10)

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

            it = StageItem(0, ttype, px, py, w, h, rot, color, label,
                           properties=props)
            if engine.is_valid_position(it, existing):
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

    def _sample_interior_points(self, count: int = 20) -> List[Tuple[float, float]]:
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

    def _get_blocking_walls(self, items: List[StageItem]) -> List[StageItem]:
        """Ritorna gli item che bloccano la visuale (muri, porte, barriere perimetrali in stile walls)."""
        blockers = []
        for it in items:
            if it.item_type in (ItemType.WALL, ItemType.DOOR):
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
        """
        margin = IPSCRulesEngine.MIN_TARGET_TO_EDGE
        w = stage.width
        # Riserva almeno MIN_BACKSTOP_DEPTH metri tra area di tiro e parapalle
        backstop_margin = IPSCRulesEngine.MIN_BACKSTOP_DEPTH
        d_eff = back_y if back_y is not None else stage.depth - backstop_margin

        def _poly_is_simple(poly: List[Tuple[float, float]]) -> bool:
            n = len(poly)
            for i in range(n):
                a, b = poly[i], poly[(i + 1) % n]
                for j in range(i + 2, n):
                    if (j + 1) % n == i:
                        continue
                    c, d = poly[j], poly[(j + 1) % n]
                    if segments_intersect(a, b, c, d):
                        if (i + 1) % n == j or (j + 1) % n == i:
                            continue
                        return False
            return True

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

        for attempt in range(5):
            test_poly = _perturb(poly, amount=0.3)
            clamped = _clamp(test_poly)
            if len(clamped) >= 3 and _poly_is_simple(clamped):
                return clamped

        return _clamp(poly)

    def _generate_perimeter_items(self, stage: Stage,
                                   poly: List[Tuple[float, float]]) -> List[StageItem]:
        """Converte il poligono del perimetro in item Stage (fault lines/barriere/walls).
        
        Lascia un'apertura di ~2m sul fronte (lato up-range / y min) per
        l'ingresso del tiratore.
        """
        items = []
        style = self.config.delimitation
        n = len(poly)

        style_map = {
            "fault_lines": (ItemType.FAULT_LINE, 0.0, "#dc2626", "Fault Line"),
            "barriers":    (ItemType.BARRIER, 0.15, "#fbbf24", "Barriera"),
            "walls":       (ItemType.WALL, 0.2, "#475569", "Muro"),
        }

        for i in range(n):
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
                    itype, thick, color, label = ItemType.BARRIER, 0.15, "#fbbf24", "Barriera"
                else:
                    itype, thick, color, label = ItemType.FAULT_LINE, 0.0, "#dc2626", "Fault Line"
            else:
                itype, thick, color, label = style_map.get(style, style_map["fault_lines"])

            item = StageItem(0, itype, cx, cy, length, thick, angle, color, label)
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
            blockers = self._get_blocking_walls(items)
            if not blockers:
                break

            visible = sum(1 for t in targets if self._is_target_visible(t, blockers))
            if visible >= min_visible:
                break

            # Per ogni bloccante, simula la rimozione e conta quanti target libera
            best_gain = 0
            best_item = None
            for b in blockers:
                test_items = [it for it in items if it is not b]
                test_blockers = self._get_blocking_walls(test_items)
                test_visible = sum(1 for t in targets
                                   if self._is_target_visible(t, test_blockers))
                gain = test_visible - visible
                if gain > best_gain:
                    best_gain = gain
                    best_item = b

            if best_item is None or best_gain == 0:
                # Se nessun muro libera target da solo, rimuovi quello che appare
                # piú frequente nelle linee bloccate
                wall_hits = {id(w): 0 for w in blockers}
                wall_map = {id(w): w for w in blockers}
                invisible = [t for t in targets
                             if not self._is_target_visible(t, blockers)]
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
                    0, ItemType.WALL, wx, wy,
                    wall_len, 0.2, wall_angle,
                    "#475569", "Muro ristr.")

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
                            wall = StageItem(0, ItemType.WALL, wx, wy,
                                             1.5, 0.2,
                                             math.degrees(math.atan2(ny, nx)),
                                             "#475569", "Muro ripar.")
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

            # 5. Ostacoli troppo vicini → rimuovi il secondo ostacolo
            elif "ostacolo" in v_lower and "vicino" in v_lower:
                m = _re.findall(r'#(\d+)', v_text)
                if len(m) >= 2:
                    # Rimuovi il secondo ostacolo
                    stage.remove_item(int(m[1]))
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
                                wall = StageItem(0, ItemType.WALL, wx, wy,
                                                 2.0, 0.2,
                                                 math.degrees(math.atan2(ny, nx)),
                                                 "#475569", "Muro div.")
                                stage.add_item(wall)
                                repaired = True

        return repaired

    def _generate_fault_lines(self, stage: Stage, existing: List[StageItem]) -> List[StageItem]:
        """Genera fault lines strategiche davanti ai bersagli."""
        fault_lines = []
        targets = [it for it in existing if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET)]
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
