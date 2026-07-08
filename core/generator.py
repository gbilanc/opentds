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
    delimitation: str = "fault_lines"  # fault_lines | barriers | walls | mixed
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
        self._perimeter_poly: List[Tuple[float, float]] = []  # vertici poligono area di tiro
        self._interior_samples: List[Tuple[float, float]] = []  # punti interni per visibility check

    def generate(self) -> GeneratorResult:
        stage = Stage(name="Stage Generato", width=self.config.stage_width,
                      depth=self.config.stage_depth)
        engine = IPSCRulesEngine(stage)
        items: List[StageItem] = []
        attempts = 0

        # 1. Posiziona bersagli PRIMA (verso il fondale)
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

        # 2. Bersagli mobili
        moving_types = [ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER]
        for i in range(self.config.num_moving):
            mtype = moving_types[i % len(moving_types)]
            it = self._place_moving_target(stage, items, mtype, engine)
            if it:
                items.append(it)
            attempts += 1

        # 3. Genera perimetro AREA DI TIRO DAVANTI ai bersagli
        #    Il perimetro non si estende oltre la posizione dei bersagli
        items.extend(self._generate_perimeter_from_targets(stage, items))

        # 4. Pre-calcola punti di osservazione interni
        self._interior_samples = self._sample_interior_points(20)

        # 5. Genera muri/barriere FUORI dall'area di tiro (tra area e bersagli)
        #    Solo se ostacolano l'acquisizione (nascondono bersagli in modo mirato)
        items.extend(self._generate_walls(stage, items))
        items.extend(self._generate_barriers(stage, items))

        # 6. No-shoots (opzionali)
        if self.config.include_no_shoots:
            ns_count = max(1, self.config.num_targets // 4)
            for _ in range(ns_count):
                it = self._place_no_shoot(stage, items, engine)
                if it:
                    items.append(it)
                attempts += 1

        # 7. Fault lines tattiche (post-processing, vicino a bersagli)
        if self.config.include_fault_lines:
            items.extend(self._generate_fault_lines(stage, items))

        # Assegna tutti gli item allo stage
        for it in items:
            stage.add_item(it)

        score = self._score_stage(stage, items)
        return GeneratorResult(stage=stage, score=score, attempts=attempts)

    def _generate_walls(self, stage: Stage, existing: List[StageItem]) -> List[StageItem]:
        """Genera muri FUORI dal perimetro (tra area e bersagli).
        Ogni muro deve oscurare almeno 1 bersaglio (serve a nascondere)."""
        walls = []
        count = self.config.num_walls
        avg_len = 3.0 if self.config.difficulty == "easy" else 5.0 if self.config.difficulty == "hard" else 4.0

        targets = [it for it in existing if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
            ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)]
        if not targets or not self._perimeter_poly or not self._interior_samples:
            return walls

        min_visible = max(1, math.ceil(len(targets) * 0.7))
        poly_max_y = max(p[1] for p in self._perimeter_poly)
        min_target_y = min(t.y for t in targets)

        # Zona valida: fuori perimetro ma davanti ai bersagli
        zone_lo = poly_max_y + 0.5
        zone_hi = min_target_y - 0.5
        if zone_lo >= zone_hi:
            return walls

        for _ in range(count):
            placed = False
            for _ in range(100):
                # Scegli un target e un punto di osservazione casuali
                t = random.choice(targets)
                ox, oy = random.choice(self._interior_samples)

                # Calcola la frazione lungo la linea che cade nella zona valida
                dy = t.y - oy
                t_frac_lo = (zone_lo - oy) / dy if abs(dy) > 1e-6 else 0.5
                t_frac_hi = (zone_hi - oy) / dy if abs(dy) > 1e-6 else 0.5
                t_frac_lo = max(0.2, min(t_frac_lo, t_frac_hi))
                t_frac_hi = min(0.8, max(t_frac_lo, t_frac_hi))
                if t_frac_lo >= t_frac_hi:
                    continue
                t_frac = random.uniform(t_frac_lo, t_frac_hi)

                x = ox + (t.x - ox) * t_frac
                y = oy + dy * t_frac
                x = max(1.5, min(stage.width - 1.5, x))

                # Deve essere FUORI dal perimetro
                if self._point_in_polygon(x, y, self._perimeter_poly):
                    continue

                # Rotazione perpendicolare alla linea di vista
                angle_to_target = math.degrees(math.atan2(t.y - oy, t.x - ox))
                rotation = angle_to_target + random.choice([-90, 90])

                length = random.uniform(avg_len * 0.7, avg_len * 1.3)
                w = StageItem(0, ItemType.WALL, x, y, length, 0.2, rotation, "#475569", "Muro")

                # Deve bloccare ALMENO 1 bersaglio
                blocks_any = False
                for t2 in targets:
                    for ox2, oy2 in self._interior_samples:
                        if self._line_intersects_rect(
                            (ox2, oy2), (t2.x, t2.y),
                            w.x, w.y, w.width, w.height, w.rotation
                        ):
                            blocks_any = True
                            break
                    if blocks_any:
                        break
                if not blocks_any:
                    continue

                # Non deve nascondere TROPPI bersagli
                test_items = existing + walls + [w]
                test_blockers = self._get_blocking_walls(test_items)
                visible_now = sum(1 for t2 in targets
                                  if self._is_target_visible(t2, test_blockers))
                if visible_now >= min_visible:
                    walls.append(w)
                    placed = True
                    break
            if not placed:
                break
        return walls

    def _generate_barriers(self, stage: Stage, existing: List[StageItem]) -> List[StageItem]:
        """Genera barriere FUORI dal perimetro (tra area e bersagli).
        Posizionate sulla linea di vista tra campione e target."""
        barriers = []
        targets = [it for it in existing if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
            ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)]
        if not targets or not self._perimeter_poly or not self._interior_samples:
            return barriers

        min_visible = max(1, math.ceil(len(targets) * 0.7))
        poly_max_y = max(p[1] for p in self._perimeter_poly)
        min_target_y = min(t.y for t in targets)

        zone_lo = poly_max_y + 0.5
        zone_hi = min_target_y - 0.5
        if zone_lo >= zone_hi:
            return barriers

        for _ in range(self.config.num_barriers):
            placed = False
            for _ in range(100):
                t = random.choice(targets)
                ox, oy = random.choice(self._interior_samples)

                dy = t.y - oy
                t_frac_lo = (zone_lo - oy) / dy if abs(dy) > 1e-6 else 0.5
                t_frac_hi = (zone_hi - oy) / dy if abs(dy) > 1e-6 else 0.5
                t_frac_lo = max(0.2, min(t_frac_lo, t_frac_hi))
                t_frac_hi = min(0.8, max(t_frac_lo, t_frac_hi))
                if t_frac_lo >= t_frac_hi:
                    continue
                t_frac = random.uniform(t_frac_lo, t_frac_hi)

                x = ox + (t.x - ox) * t_frac
                y = oy + dy * t_frac
                x = max(1.5, min(stage.width - 1.5, x))

                if self._point_in_polygon(x, y, self._perimeter_poly):
                    continue

                angle_to_target = math.degrees(math.atan2(t.y - oy, t.x - ox))
                rot = angle_to_target + random.choice([-90, 90])

                bw = random.uniform(1.5, 3.0)
                b = StageItem(0, ItemType.BARRIER, x, y, bw, 0.15, rot, "#fbbf24", "Barriera")

                # Deve bloccare almeno 1 bersaglio
                blocks_any = False
                for t2 in targets:
                    for ox2, oy2 in self._interior_samples:
                        if self._line_intersects_rect(
                            (ox2, oy2), (t2.x, t2.y),
                            b.x, b.y, b.width, b.height, b.rotation
                        ):
                            blocks_any = True
                            break
                    if blocks_any:
                        break
                if not blocks_any:
                    continue

                test_items = existing + barriers + [b]
                test_blockers = self._get_blocking_walls(test_items)
                visible_now = sum(1 for t in targets
                                  if self._is_target_visible(t, test_blockers))
                if visible_now >= min_visible:
                    barriers.append(b)
                    placed = True
                    break
            if not placed:
                break
        return barriers

    def _place_target(self, stage: Stage, existing: List[StageItem],
                      ttype: ItemType, engine: IPSCRulesEngine) -> Optional[StageItem]:
        """Posiziona bersaglio nel fondale (55-100% profondità)."""
        margin = engine.MIN_TARGET_TO_EDGE
        back_start = stage.depth * 0.55
        for _ in range(self.config.max_attempts):
            x = random.uniform(margin, stage.width - margin)
            y = random.uniform(back_start, stage.depth - margin)
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
        margin = engine.MIN_TARGET_TO_EDGE
        back_start = stage.depth * 0.55
        for _ in range(self.config.max_attempts):
            x = random.uniform(margin, stage.width - margin)
            y = random.uniform(back_start, stage.depth - margin)
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
            target = random.choice(targets)
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(1.2, 2.5)
            x = target.x + math.cos(angle) * dist
            y = target.y + math.sin(angle) * dist
            it = StageItem(0, ItemType.NO_SHOOT, x, y, 0.45, 0.45, 0, "#f87171", "No-Shoot")
            if engine.is_valid_position(it, existing):
                return it
        return None

    # ─── Utilità geometriche ───

    @staticmethod
    def _point_in_polygon(px: float, py: float,
                          poly: List[Tuple[float, float]]) -> bool:
        """Ray casting: True se (px,py) è dentro il poligono convesso."""
        inside = False
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            if ((y1 > py) != (y2 > py)) and \
               (px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-9) + x1):
                inside = not inside
        return inside

    @staticmethod
    def _polygon_center(poly: List[Tuple[float, float]]) -> Tuple[float, float]:
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        return cx, cy

    @staticmethod
    def _point_in_rotated_rect(px: float, py: float,
                                cx: float, cy: float,
                                w: float, h: float,
                                angle_deg: float) -> bool:
        """True se (px,py) è dentro il rettangolo ruotato."""
        angle = math.radians(angle_deg)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        dx = px - cx
        dy = py - cy
        local_x = dx * cos_a + dy * sin_a
        local_y = -dx * sin_a + dy * cos_a
        return abs(local_x) <= w / 2 + 1e-6 and abs(local_y) <= h / 2 + 1e-6

    @staticmethod
    def _segments_intersect(a: Tuple[float, float],
                             b: Tuple[float, float],
                             c: Tuple[float, float],
                             d: Tuple[float, float]) -> bool:
        """True se il segmento a-b interseca c-d (esclusi estremi coincidenti)."""
        def orient(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        o1 = orient(a, b, c)
        o2 = orient(a, b, d)
        o3 = orient(c, d, a)
        o4 = orient(c, d, b)
        # Caso collineare: controlla se si sovrappongono
        if abs(o1) < 1e-9 and abs(o2) < 1e-9 and abs(o3) < 1e-9 and abs(o4) < 1e-9:
            # Proietta su asse x per sovrapposizione
            def between(v, s1, s2):
                return min(s1, s2) - 1e-6 <= v <= max(s1, s2) + 1e-6
            return (between(a[0], c[0], d[0]) or between(b[0], c[0], d[0]) or
                    between(c[0], a[0], b[0]) or between(d[0], a[0], b[0]))
        return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)

    @staticmethod
    def _line_intersects_rect(p1: Tuple[float, float],
                               p2: Tuple[float, float],
                               cx: float, cy: float,
                               w: float, h: float,
                               angle_deg: float) -> bool:
        """True se il segmento p1-p2 interseca il rettangolo ruotato."""
        # Se un estremo è dentro il rettangolo → interseca
        if StageGenerator._point_in_rotated_rect(p1[0], p1[1], cx, cy, w, h, angle_deg):
            return True
        if StageGenerator._point_in_rotated_rect(p2[0], p2[1], cx, cy, w, h, angle_deg):
            return True
        # Controlla intersezione con ogni lato del rettangolo
        angle = math.radians(angle_deg)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        hw, hh = w / 2, h / 2
        # 4 angoli del rettangolo
        corners = []
        for dx, dy in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]:
            x = cx + dx * cos_a - dy * sin_a
            y = cy + dx * sin_a + dy * cos_a
            corners.append((x, y))
        n = len(corners)
        for i in range(n):
            if StageGenerator._segments_intersect(p1, p2, corners[i], corners[(i + 1) % n]):
                return True
        return False

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
            if self._point_in_polygon(x, y, self._perimeter_poly):
                points.append((x, y))
        return points[:count] if points else [(self._polygon_center(self._perimeter_poly))]

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
                if self._line_intersects_rect(
                    (obs_x, obs_y), target_pos,
                    wall.x, wall.y, wall.width, wall.height, wall.rotation
                ):
                    visible = False
                    break
            if visible:
                return True
        return False

    def _generate_perimeter_polygon(self, stage: Stage,
                                     back_y: Optional[float] = None) -> List[Tuple[float, float]]:
        """Genera i vertici di un poligono chiuso che delimita l'area di tiro.
        back_y limita la profondità: il poligono non si estende oltre."""
        margin = IPSCRulesEngine.MIN_TARGET_TO_EDGE
        w = stage.width
        d_eff = back_y if back_y is not None else stage.depth
        lo, hi = margin + 0.5, margin + 0.5

        # 1. Quattro angoli base (d_eff = profondità massima = back_y)
        fl = (lo + random.uniform(0, 1.0), lo + random.uniform(0, 1.0))
        fr = (w - hi - random.uniform(0, 1.0), lo + random.uniform(0, 1.0))
        br = (w - hi - random.uniform(0, 1.0), d_eff - hi - random.uniform(0, 1.0))
        bl = (lo + random.uniform(0, 1.0), d_eff - hi - random.uniform(0, 1.0))

        base = [fl, fr, br, bl]

        # 2. Trasformazioni: skew, indent, chamfer
        transforms = []
        if random.random() < 0.6:
            transforms.append('skew')
        if random.random() < 0.5:
            transforms.append('indent')
        if random.random() < 0.35:
            transforms.append('chamfer')

        if 'skew' in transforms:
            side = random.randint(0, 3)
            shift = random.uniform(1.0, 3.0) * random.choice([-1, 1])
            if side == 0:
                base[0] = (base[0][0] + shift, base[0][1])
                base[1] = (base[1][0] + shift, base[1][1])
            elif side == 1:
                base[1] = (base[1][0], base[1][1] + shift)
                base[2] = (base[2][0], base[2][1] + shift)
            elif side == 2:
                base[2] = (base[2][0] + shift, base[2][1])
                base[3] = (base[3][0] + shift, base[3][1])
            else:
                base[0] = (base[0][0], base[0][1] + shift)
                base[3] = (base[3][0], base[3][1] + shift)

        if 'indent' in transforms:
            side = random.randint(0, 3)
            if side == 0:  # frontale → rientra verso fondale
                cut_x = random.uniform(w * 0.25, w * 0.6)
                cut_depth = random.uniform(1.5, d_eff * 0.35)
                idx = 1
                base.insert(idx, (base[idx][0], base[idx][1] + cut_depth))
                base.insert(idx, (cut_x, base[0][1]))
            elif side == 1:  # destra → rientra verso sinistra
                cut_y = random.uniform(d_eff * 0.2, d_eff * 0.6)
                cut_depth = random.uniform(1.5, w * 0.3)
                idx = 3
                base.insert(idx, (base[idx][0] - cut_depth, base[idx][1]))
                base.insert(idx, (base[2][0], cut_y))
            elif side == 2:  # fondale → rientra verso fronte
                cut_x = random.uniform(w * 0.25, w * 0.6)
                cut_depth = random.uniform(1.5, d_eff * 0.35)
                idx = len(base) - 1
                base.insert(idx, (base[idx][0], base[idx][1] - cut_depth))
                base.insert(idx, (cut_x, base[-1][1]))
            else:  # sinistra → rientra verso destra
                cut_y = random.uniform(d_eff * 0.2, d_eff * 0.6)
                cut_depth = random.uniform(1.5, w * 0.3)
                idx = 1
                base.insert(idx, (base[0][0] + cut_depth, cut_y))
                base.insert(idx, (base[0][0], cut_y))

        if 'chamfer' in transforms:
            corner = random.randint(0, 3)
            p = base[corner]
            p_prev = base[(corner - 1) % len(base)]
            p_next = base[(corner + 1) % len(base)]
            inset = random.uniform(0.5, 1.5)
            dx1 = p_next[0] - p[0]
            dy1 = p_next[1] - p[1]
            len1 = math.hypot(dx1, dy1) or 1
            dx2 = p_prev[0] - p[0]
            dy2 = p_prev[1] - p[1]
            len2 = math.hypot(dx2, dy2) or 1
            p1 = (p[0] + dx1 / len1 * inset, p[1] + dy1 / len1 * inset)
            p2 = (p[0] + dx2 / len2 * inset, p[1] + dy2 / len2 * inset)
            base[corner] = p1
            base.insert(corner + 1, p2)

        # 3. Perturba e clamp
        poly = []
        for px, py in base:
            nx = px + random.uniform(-0.4, 0.4)
            ny = py + random.uniform(-0.4, 0.4)
            nx = max(margin, min(w - margin, nx))
            ny = max(margin, min(d_eff - margin, ny))
            poly.append((round(nx, 2), round(ny, 2)))

        # 4. Rimuovi duplicati ravvicinati
        cleaned = [poly[0]]
        for p in poly[1:]:
            if math.hypot(p[0] - cleaned[-1][0], p[1] - cleaned[-1][1]) > 0.6:
                cleaned.append(p)
        if len(cleaned) > 2 and math.hypot(cleaned[-1][0] - cleaned[0][0], cleaned[-1][1] - cleaned[0][1]) < 0.4:
            cleaned.pop()
        if len(cleaned) < 3:
            cleaned = base[:4]
        return cleaned

    def _generate_perimeter_from_targets(self, stage: Stage,
                                          existing: List[StageItem]) -> List[StageItem]:
        """Genera il perimetro dell'area di tiro DAVANTI ai bersagli."""
        targets = [it for it in existing if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
            ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)]
        if not targets:
            self._perimeter_poly = [
                (1.0, 1.0), (stage.width - 1.0, 1.0),
                (stage.width - 1.0, stage.depth - 1.0), (1.0, stage.depth - 1.0)
            ]
            return self._materialize_perimeter(stage, self._perimeter_poly, stage.depth)

        # Bersaglio più avanzato (min Y) = bordo posteriore del perimetro
        min_target_y = min(t.y for t in targets)
        margin = IPSCRulesEngine.MIN_TARGET_TO_EDGE
        back_y = min_target_y - random.uniform(0.5, 1.5)
        back_y = max(margin + 1.0, back_y)

        poly = self._generate_perimeter_polygon(stage, back_y)
        self._perimeter_poly = poly

        return self._materialize_perimeter(stage, poly, back_y)

    def _materialize_perimeter(self, stage: Stage,
                                poly: List[Tuple[float, float]],
                                back_y: float) -> List[StageItem]:
        """Converte un poligono in item Stage (fault lines/barriere/walls)."""
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
                if abs(cy - back_y / 2) > abs(cx - stage.width / 2):
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
        """Rimuove muri/barriere finché ≥70% dei bersagli è visibile.
        Prova a rimuovere ogni bloccante e sceglie quello che libera piú target."""
        targets = [it for it in items if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
            ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)]
        if not targets or not self._interior_samples:
            return items

        min_visible = max(1, math.ceil(len(targets) * 0.7))

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
                            if self._line_intersects_rect(
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
            if self._perimeter_poly and not self._point_in_polygon(fx, fy, self._perimeter_poly):
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
                    total_dist += IPSCRulesEngine._distance(a, b)
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
