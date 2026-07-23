"""
Motore di vincoli IPSC per la generazione e validazione stage.

Usa Shapely per collision detection OBB (oriented bounding box),
con regole IPSC 2025: minimi/massimi bersagli, no-shoot, shooting
positions, fault line closure, dimensioni stage.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List

from core.constants import (
    MIN_TARGET_TO_EDGE,
    MIN_TARGET_TO_WALL,
    MIN_TARGET_TO_TARGET,
    MIN_TARGET_TO_BARRIER,
    MIN_WALL_TO_EDGE,
    MIN_OBSTACLE_GAP,
    MIN_BACKSTOP_DEPTH,
    MIN_STEEL_DISTANCE,
    SAFETY_ANGLE_DEFAULT,
    MAX_FIXED_TARGET_ANGLE,
    MAX_OBSTACLE_HEIGHT,
    MIN_BARRIER_HEIGHT,
    MIN_PLATE_MOUNT_HEIGHT,
    MIN_TARGETS,
    MAX_STEEL_PCT,
    MAX_STAGE_WIDTH,
    MAX_STAGE_DEPTH,
    RECOMMENDED_NO_SHOOT_INTERVAL,
    MAX_HITS_PER_POSITION,
    COURSE_MAX_ROUNDS,
    MAX_TARGETS_BY_DISCIPLINE,
    MIN_STAGE_DIMENSIONS,
    DIVISION_MAG_CAPACITY,
    DIVISION_ALLOW_OPTICS,
    DIVISION_ALLOW_COMP,
    DIVISION_MAX_BARREL_LENGTH,
    DIVISION_MIN_TRIGGER_WEIGHT,
    RATIO_SHORT,
    RATIO_MEDIUM,
    RATIO_LONG,
    MATCH_MIN_STAGES,
    MATCH_MIN_ROUNDS,
    SAME_LINE_OF_FIRE_THRESHOLD_DEG,
)
from core.models import Stage, StageItem, ItemType, CourseType, Division
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

    # Costanti centralizzate da core.constants
    MIN_TARGET_TO_EDGE = MIN_TARGET_TO_EDGE
    MIN_TARGET_TO_WALL = MIN_TARGET_TO_WALL
    MIN_TARGET_TO_TARGET = MIN_TARGET_TO_TARGET
    MIN_TARGET_TO_BARRIER = MIN_TARGET_TO_BARRIER
    MIN_WALL_TO_EDGE = MIN_WALL_TO_EDGE
    MIN_OBSTACLE_GAP = MIN_OBSTACLE_GAP
    MIN_BACKSTOP_DEPTH = MIN_BACKSTOP_DEPTH
    MIN_STEEL_DISTANCE = MIN_STEEL_DISTANCE
    SAFETY_ANGLE_DEFAULT = SAFETY_ANGLE_DEFAULT
    MAX_FIXED_TARGET_ANGLE = MAX_FIXED_TARGET_ANGLE
    MAX_OBSTACLE_HEIGHT = MAX_OBSTACLE_HEIGHT
    MIN_BARRIER_HEIGHT = MIN_BARRIER_HEIGHT
    MIN_PLATE_MOUNT_HEIGHT = MIN_PLATE_MOUNT_HEIGHT
    MIN_TARGETS = MIN_TARGETS
    MAX_STEEL_PCT = MAX_STEEL_PCT
    MAX_STAGE_WIDTH = MAX_STAGE_WIDTH
    MAX_STAGE_DEPTH = MAX_STAGE_DEPTH
    RECOMMENDED_NO_SHOOT_INTERVAL = RECOMMENDED_NO_SHOOT_INTERVAL
    MAX_HITS_PER_POSITION = MAX_HITS_PER_POSITION
    COURSE_MAX_ROUNDS: dict[str, int] = COURSE_MAX_ROUNDS
    DIVISION_MAG_CAPACITY: dict[str, int | None] = DIVISION_MAG_CAPACITY
    DIVISION_ALLOW_OPTICS: dict[str, bool] = DIVISION_ALLOW_OPTICS
    DIVISION_ALLOW_COMP: dict[str, bool] = DIVISION_ALLOW_COMP
    DIVISION_MAX_BARREL_LENGTH: dict[str, float | None] = DIVISION_MAX_BARREL_LENGTH
    DIVISION_MIN_TRIGGER_WEIGHT: dict[str, float | None] = DIVISION_MIN_TRIGGER_WEIGHT
    RATIO_SHORT = RATIO_SHORT
    RATIO_MEDIUM = RATIO_MEDIUM
    RATIO_LONG = RATIO_LONG

    def __init__(self, stage: Stage, discipline: str = "ipsc_pistol"):
        self.stage = stage
        self._discipline = discipline

    def set_discipline(self, discipline: str):
        """Cambia la disciplina (ipsc_pistol | mini_rifle | shotgun).
        Regola i limiti di conseguenza."""
        self._discipline = discipline

    @property
    def MIN_STAGE_WIDTH(self) -> float:
        dims = MIN_STAGE_DIMENSIONS.get(self._discipline, MIN_STAGE_DIMENSIONS["ipsc_pistol"])
        return dims[0]

    @property
    def MIN_STAGE_DEPTH(self) -> float:
        dims = MIN_STAGE_DIMENSIONS.get(self._discipline, MIN_STAGE_DIMENSIONS["ipsc_pistol"])
        return dims[1]

    @property
    def MAX_TARGETS(self) -> int:
        return MAX_TARGETS_BY_DISCIPLINE.get(self._discipline, 32)

    # ── Validazione completa ──────────────────────────────────────────────

    def validate(self) -> ConstraintResult:
        """Valida l'intero stage corrente."""
        violations: List[str] = []

        violations.extend(self._validate_dimensions())
        violations.extend(self._validate_target_counts())
        violations.extend(self._validate_spatial())
        violations.extend(self._validate_shooting_positions())
        violations.extend(self._validate_steel_distance())
        violations.extend(self._validate_max_hits_per_position())
        violations.extend(self._validate_safety_angles())
        violations.extend(self._validate_course_type())
        violations.extend(self._validate_division())
        violations.extend(self._validate_fixed_targets_angle())
        violations.extend(self._validate_metal_plates_need_paper())
        violations.extend(self._validate_hard_cover_high_zone())
        violations.extend(self._validate_metal_rotating_prohibited())
        violations.extend(self._validate_plate_mounting_height())
        violations.extend(self._validate_same_line_of_fire())

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

        paper_targets = [it for it in self.stage.items if it.item_type in (
            ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
            ItemType.MINI_TARGET, ItemType.MICRO_TARGET)]
        no_shoots = [it for it in self.stage.items
                     if it.item_type == ItemType.NO_SHOOT]
        walls = [it for it in self.stage.items if it.item_type in (
            ItemType.WALL, ItemType.DOOR)]
        barriers = [it for it in self.stage.items
                    if it.item_type == ItemType.BARRIER]
        all_targets = paper_targets + no_shoots

        for t in all_targets:
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

        # Distanza tra bersagli che assegnano punti (esclude no-shoot)
        # Regola: i bersagli cartacei (PAPER_TARGET, MINI_TARGET, MICRO_TARGET,
        # SWINGER, DROP_TURNER, MOVER) possono essere affiancati o sovrapposti
        # tra loro. Solo metallici (STEEL_TARGET, POPPER, METAL_PLATE) devono
        # mantenere distanza minima e solo da altri metallici.
        eps = 0.05
        for i, a in enumerate(paper_targets):
            a_obb = item_obb(a)
            if not a_obb:
                continue
            a_is_paper = a.item_type in (
                ItemType.PAPER_TARGET, ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
                ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
            for b in paper_targets[i + 1:]:
                b_obb = item_obb(b)
                if not b_obb:
                    continue
                b_is_paper = b.item_type in (
                    ItemType.PAPER_TARGET, ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
                    ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
                # Bersagli cartacei possono essere affiancati/sovrapposti
                if a_is_paper and b_is_paper:
                    continue
                if min_distance_between(a_obb, b_obb) < self.MIN_TARGET_TO_TARGET - eps:
                    violations.append(
                        f"Bersaglio #{a.id} troppo vicino a bersaglio #{b.id} "
                        f"({self.MIN_TARGET_TO_TARGET}m)")

        # Ostacoli non devono sovrapporsi (muri, barriere, porte)
        # Esonero: ostacoli perimetrali (fanno parte del confine) possono toccarsi
        obstacles = walls + barriers
        for i, a in enumerate(obstacles):
            a_obb = item_obb(a)
            if a_obb is None:
                continue
            for b in obstacles[i + 1:]:
                # Se entrambi sono perimetrali, si possono toccare
                if a.properties.get("perimeter") and b.properties.get("perimeter"):
                    continue
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
                # Bersagli cartacei possono essere affiancati/sovrapposti
                item_is_paper = item.item_type in (
                    ItemType.PAPER_TARGET, ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
                    ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
                other_is_paper = other.item_type in (
                    ItemType.PAPER_TARGET, ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
                    ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
                if item_is_paper and other_is_paper:
                    continue  # carta-carta: nessuna distanza minima
                if min_distance_between(item_obb_geom, other_obb_geom) < self.MIN_TARGET_TO_TARGET - 0.05:
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

    # ── Validazione distanza metallici ────────────────────────────────────────

    def _validate_steel_distance(self) -> List[str]:
        """Verifica distanza minima 7m tiratore-bersaglio metallico (Reg. 2.1.3).

        I bersagli metallici devono distare almeno 7m dal tiratore quando questi
        sta effettivamente sparando. Se sono presenti fault lines a 8m, il RO
        può fermare il tiratore prima della violazione.
        """
        v = []
        steel = [it for it in self.stage.items
                 if it.item_type in (ItemType.STEEL_TARGET,)]
        if not steel:
            return v

        # Usa le posizioni di tiro come riferimento; se non definite,
        # usa il centro dell'area di tiro approssimato dal centro stage
        positions = []
        if self.stage.shooting_positions:
            for sp in self.stage.shooting_positions:
                positions.append(Point(sp.x, sp.y))
        else:
            positions.append(Point(self.stage.width / 2, 1.0))

        for s in steel:
            s_point = Point(s.x, s.y)
            min_dist = min(s_point.distance(p) for p in positions)
            if min_dist < self.MIN_STEEL_DISTANCE:
                v.append(
                    f"Bersaglio metallico #{s.id} troppo vicino a posizione di tiro: "
                    f"{min_dist:.1f}m (min {self.MIN_STEEL_DISTANCE}m, Reg. 2.1.3)")

        return v

    # ── Validazione max colpi per posizione ───────────────────────────────────

    def _validate_max_hits_per_position(self) -> List[str]:
        """Verifica max 9 colppi conteggiabili da una singola posizione (Reg. 1.2.1).

        Da qualsiasi singola posizione di tiro, il tiratore non deve poter
        mettere a segno più di 9 colpi su bersagli che assegnano punti.
        Per i bersagli carta si contano 2 colpi ciascuno (default),
        per i metallici 1 colpo ciascuno (devono cadere).
        """
        v = []
        targets = [it for it in self.stage.items
                   if it.item_type in (ItemType.PAPER_TARGET, ItemType.STEEL_TARGET)]
        if not targets:
            return v

        positions = []
        if self.stage.shooting_positions:
            for sp in self.stage.shooting_positions:
                positions.append(Point(sp.x, sp.y))
        else:
            # Se non ci sono shooting positions, campiona punti nell'area di tiro
            cx, cy = self.stage.width / 2, self.stage.depth / 2
            positions = [
                Point(cx, cy),
                Point(cx - 2, cy),
                Point(cx + 2, cy),
                Point(cx, cy + 2),
            ]

        # Costruisce OBB per ogni bersaglio
        target_obbs = {}
        for t in targets:
            obb = item_obb(t)
            if obb:
                target_obbs[t.id] = obb

        from shapely.geometry import LineString as ShapelyLineString

        for pos in positions:
            hits = 0
            # Per ogni bersaglio, verifica se è visibile dalla posizione
            # (linea di vista non ostruita da muri/barriere)
            walls = [it for it in self.stage.items
                     if it.item_type in (ItemType.WALL, ItemType.BARRIER, ItemType.DOOR)]
            wall_obbs = []
            for w in walls:
                wob = item_obb(w)
                if wob:
                    wall_obbs.append(wob)

            for t in targets:
                obb = target_obbs.get(t.id)
                if obb is None:
                    continue

                # Linea di vista dalla posizione al centro del bersaglio
                line = ShapelyLineString([(pos.x, pos.y), (t.x, t.y)])

                # Verifica se la linea interseca muri/barriere
                blocked = False
                for wob in wall_obbs:
                    if line.intersects(wob):
                        blocked = True
                        break

                if not blocked:
                    # Carta: 2 colpi, metallo: 1 colpo
                    hits += 2 if t.item_type == ItemType.PAPER_TARGET else 1

            if hits > self.MAX_HITS_PER_POSITION:
                v.append(
                    f"Posizione ({pos.x:.1f}, {pos.y:.1f}): {hits} colpi "
                    f"conteggiabili (max {self.MAX_HITS_PER_POSITION}, Reg. 1.2.1)")

        return v

    # ── Validazione angoli di sicurezza ───────────────────────────────────────

    def _validate_safety_angles(self) -> List[str]:
        """Verifica angoli di sicurezza 90° (Reg. 2.1.2).

        L'angolo di sicurezza massimo di default è 90° in ogni direzione,
        misurato dal tiratore posto frontalmente rispetto al centro frontale
        dell'area di tiro. I bersagli non devono richiedere al tiratore di
        superare questi angoli per essere ingaggiati.

        Nota: questa è una validazione geometrica semplificata. Verifica che
        i bersagli non siano posizionati a un angolo >90° rispetto alla
        direzione frontale (verso il parapalle di fondo) dalle posizioni di tiro.
        """
        v = []
        targets = [it for it in self.stage.items
                   if it.item_type in (ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
                                       ItemType.SWINGER, ItemType.DROP_TURNER,
                                       ItemType.MOVER)]
        if not targets:
            return v

        positions = []
        if self.stage.shooting_positions:
            for sp in self.stage.shooting_positions:
                positions.append(Point(sp.x, sp.y))
        else:
            positions.append(Point(self.stage.width / 2, self.stage.depth * 0.2))

        # Direzione frontale = verso il parapalle di fondo (y crescente)
        forward = (0.0, 1.0)

        for pos in positions:
            for t in targets:
                dx = t.x - pos.x
                dy = t.y - pos.y
                dist = math.hypot(dx, dy)
                if dist < 0.1:
                    continue

                # Angolo tra vettore posizione→bersaglio e direzione frontale
                angle_rad = math.acos(
                    (dx * forward[0] + dy * forward[1]) / dist
                )
                angle_deg = math.degrees(angle_rad)

                # L'angolo di sicurezza di default è 90° a sinistra e destra
                # = il bersaglio deve essere entro ±90° dalla direzione frontale
                # Tolleranza 20° per tenere conto di forme poligonali complesse
                if angle_deg > self.SAFETY_ANGLE_DEFAULT + 20:  # tolleranza 20°
                    v.append(
                        f"Bersaglio #{t.id} a {angle_deg:.0f}° dalla posizione "
                        f"({pos.x:.1f}, {pos.y:.1f}) — "
                        f"supera angolo sicurezza default {self.SAFETY_ANGLE_DEFAULT}° "
                        f"(Reg. 2.1.2)")

        return v

    # ── Validazione tipo corso (Short/Medium/Long) ───────────────────────────

    def _validate_course_type(self) -> List[str]:
        """Verifica che lo stage rispetti i limiti del tipo di corso (Reg. 1.2.1).

        Short ≤12 colpi, Medium ≤24, Long ≤32.
        Inoltre: max 9 colpi da singola posizione per tutti i tipi;
        Medium/Long non devono permettere di ingaggiare tutti i bersagli
        da una singola posizione.
        """
        v = []
        if not self.stage.course_type:
            return v  # nessun tipo dichiarato → nessuna validazione

        ct = self.stage.course_type.value
        max_rounds = self.COURSE_MAX_ROUNDS.get(ct)
        if max_rounds is None:
            v.append(f"Tipo corso sconosciuto: {ct}")
            return v

        # Calcola il numero di colpi richiesti dallo stage
        # (default: 2 per paper, 1 per metallo/swinger/drop/mover)
        total_rounds = 0
        paper_like = (ItemType.PAPER_TARGET, ItemType.MINI_TARGET,
                      ItemType.MICRO_TARGET, ItemType.SWINGER,
                      ItemType.DROP_TURNER, ItemType.MOVER)
        steel_like = (ItemType.STEEL_TARGET, ItemType.POPPER,
                      ItemType.METAL_PLATE)

        for it in self.stage.items:
            if it.item_type in paper_like:
                total_rounds += 2  # default: 2 colpi per bersaglio carta
            elif it.item_type in steel_like:
                total_rounds += 1  # 1 colpo per metallico

        if total_rounds > max_rounds:
            v.append(
                f"Stage {ct}: {total_rounds} colpi richiesti "
                f"(max {max_rounds}, Reg. 1.2.1.{['',1,2,3][['short','medium','long'].index(ct)]})")

        # Medium/Long: non tutti i bersagli ingaggiabili da una posizione
        if ct in ("medium", "long"):
            targets = [it for it in self.stage.items
                       if it.item_type in paper_like or it.item_type in steel_like]
            if targets:
                positions = self._get_sample_positions()
                walls = [it for it in self.stage.items
                         if it.item_type in (ItemType.WALL, ItemType.BARRIER,
                                             ItemType.DOOR, ItemType.HARD_COVER)]
                from shapely.geometry import LineString as SLine

                for pos in positions:
                    visible_count = 0
                    for t in targets:
                        line = SLine([(pos.x, pos.y), (t.x, t.y)])
                        blocked = False
                        for w in walls:
                            wob = item_obb(w)
                            if wob and line.intersects(wob):
                                blocked = True
                                break
                        if not blocked:
                            visible_count += 1

                    if visible_count >= len(targets):
                        v.append(
                            f"Stage {ct}: tutti i {len(targets)} bersagli sono "
                            f"ingaggiabili dalla posizione ({pos.x:.1f},{pos.y:.1f}) "
                            f"(viola Reg. 1.2.1.{['',1,2,3][['short','medium','long'].index(ct)]})")
                        break

        return v

    def _get_sample_positions(self) -> List[Point]:
        """Restituisce posizioni di tiro di esempio per validazione."""
        if self.stage.shooting_positions:
            return [Point(sp.x, sp.y) for sp in self.stage.shooting_positions]
        # Fallback: campiona punti nell'area di tiro
        cx, cy = self.stage.width / 2, self.stage.depth / 2
        return [
            Point(cx, cy),
            Point(cx - 2, cy),
            Point(cx + 2, cy),
            Point(cx, cy + 2),
        ]

    # ── Validazione Divisione ───────────────────────────────────────────────────

    def _validate_division(self) -> List[str]:
        """Verifica che lo stage sia compatibile con la Divisione (Appendici D1-D5).

        Controlli:
        - Capacità massima caricatori
        - Presenza ottiche (vietate/obbligatorie)
        - Presenza compensatori (vietati)
        - Dimensioni massime canna (Production/PO)
        NOTE: Questa è una validazione semplificata a livello di stage.
        La verifica puntuale dell'equipaggiamento va fatta dal Range Officer.
        """
        v = []
        if not self.stage.division:
            return v

        div = self.stage.division.value

        # Verifica presenza ottiche (se vietate o obbligatorie)
        allow_optics = self.DIVISION_ALLOW_OPTICS.get(div, True)
        has_optics = any(
            "optic" in it.properties or "scope" in it.label.lower()
            for it in self.stage.items
        )
        if not allow_optics and has_optics:
            v.append(f"Divisione {div}: ottiche non permesse (App. D{self._div_index(div)})")

        # Verifica presenza compensatori (se vietati)
        allow_comp = self.DIVISION_ALLOW_COMP.get(div, True)
        has_comp = any(
            "comp" in it.label.lower() or "compensator" in str(it.properties)
            for it in self.stage.items
        )
        if not allow_comp and has_comp:
            v.append(f"Divisione {div}: compensatori non permessi (App. D{self._div_index(div)})")

        # Verifica lunghezza canna
        max_barrel = self.DIVISION_MAX_BARREL_LENGTH.get(div)
        if max_barrel:
            for it in self.stage.items:
                barrel_len = it.properties.get("barrel_length", 0)
                if barrel_len > max_barrel:
                    v.append(
                        f"Divisione {div}: canna {barrel_len*1000:.0f}mm "
                        f"supera max {max_barrel*1000:.0f}mm (App. D{self._div_index(div)})")

        # Capacità caricatori
        max_cap = self.DIVISION_MAG_CAPACITY.get(div)
        if max_cap is not None:
            for it in self.stage.items:
                mag_cap = it.properties.get("mag_capacity", 0)
                if mag_cap > max_cap:
                    v.append(
                        f"Divisione {div}: caricatore da {mag_cap} colpi "
                        f"supera max {max_cap} (App. D{self._div_index(div)})")

        return v

    def _div_index(self, div: str) -> str:
        """Mappa nome divisione a numero appendice."""
        mapping = {
            "open": "1", "standard": "2", "classic": "3",
            "production": "4", "production_optics": "4a", "revolver": "5",
        }
        return mapping.get(div, "?")

    # ── Reg. 2.1.8.4 — Angolo bersagli fissi ────────────────────────────

    def _validate_fixed_targets_angle(self) -> List[str]:
        """Verifica che i bersagli fissi (non attivati) non siano presentati
        ad un angolo superiore a 90° verticali (Reg. 2.1.8.4).

        Un bersaglio fisso (paper, mini, micro, popper, plate che NON è
        attivato/animato) non deve essere ruotato in modo da presentarsi
        edge-on (>90° dalla linea di mira) rispetto all'area di tiro.
        """
        v = []

        # Identifica i bersagli fissi: NON mobili/swinger/drop/mover e
        # NON attivati da altri bersagli
        fixed_targets = [
            it for it in self.stage.items
            if it.item_type in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET,
                                ItemType.MICRO_TARGET, ItemType.POPPER,
                                ItemType.METAL_PLATE, ItemType.STEEL_TARGET)
            and "activated_by" not in it.properties
            and "is_activator" not in it.properties
        ]
        if not fixed_targets:
            return v

        # Centro dell'area di tiro (o shooting position se definita)
        if self.stage.shooting_positions:
            cx = sum(sp.x for sp in self.stage.shooting_positions) / len(self.stage.shooting_positions)
            cy = sum(sp.y for sp in self.stage.shooting_positions) / len(self.stage.shooting_positions)
        else:
            cx = self.stage.width / 2
            cy = self.stage.depth * 0.3

        for t in fixed_targets:
            # Vettore dal bersaglio all'area di tiro (dove guarda il tiratore)
            dx = cx - t.x
            dy = cy - t.y
            dist = math.hypot(dx, dy)
            if dist < 0.3:
                continue

            # Direzione verso l'area di tiro (normalizzata)
            to_shooter_angle = math.degrees(math.atan2(dy, dx)) % 360

            # Rotazione del bersaglio: per IPSC la rotation rappresenta
            # l'orientamento della faccia del bersaglio (normale uscente)
            target_facing = t.rotation % 360

            # Differenza angolare tra dove punta il bersaglio e dove
            # si trova l'area di tiro
            diff = abs(target_facing - to_shooter_angle)
            diff = min(diff, 360 - diff)

            if diff > self.MAX_FIXED_TARGET_ANGLE:
                v.append(
                    f"Bersaglio fisso #{t.id} ({t.label}) presentato a "
                    f"{diff:.0f}° rispetto all'area di tiro "
                    f"(max {self.MAX_FIXED_TARGET_ANGLE}°, Reg. 2.1.8.4)")

        return v

    # ── Reg. 4.3.3.3 — Piatti metallici necessitano carta/popper ────────

    def _validate_metal_plates_need_paper(self) -> List[str]:
        """Verifica che quando ci sono piatti metallici, sia presente almeno
        un bersaglio carta o popper che assegni punti (Reg. 4.3.3.3).

        'I piatti metallici non devono essere impiegati come unico tipo di
        bersaglio in nessun esercizio. Deve essere incluso in ciascun esercizio
        almeno un bersaglio di carta o Popper che assegni punti'
        """
        v = []

        has_metal_plates = any(
            it.item_type == ItemType.METAL_PLATE
            for it in self.stage.items
        )
        if not has_metal_plates:
            return v

        has_paper_or_popper = any(
            it.item_type in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET,
                             ItemType.MICRO_TARGET, ItemType.POPPER)
            for it in self.stage.items
        )
        if not has_paper_or_popper:
            v.append(
                "Sono presenti piatti metallici ma nessun bersaglio carta o "
                "Popper che assegni punti (Reg. 4.3.3.3)")

        return v

    # ── Reg. 4.2.4 — Hard cover non nasconde zona A ─────────────────────

    def _validate_hard_cover_high_zone(self) -> List[str]:
        """Verifica che l'Hard Cover non nasconda totalmente la zona a
        punteggio più alto (A) dei bersagli carta (Reg. 4.2.4).

        Controllo geometrico semplificato: se un hard cover è posizionato
        direttamente davanti a un paper target e ne copre il centro
        (dove si trova la zona A), viene segnalato.
        """
        v = []

        hard_covers = [
            it for it in self.stage.items
            if it.item_type == ItemType.HARD_COVER
        ]
        paper_targets = [
            it for it in self.stage.items
            if it.item_type in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET,
                                ItemType.MICRO_TARGET)
        ]
        if not hard_covers or not paper_targets:
            return v

        for hc in hard_covers:
            hc_obb = item_obb(hc)
            if hc_obb is None:
                continue
            for pt in paper_targets:
                # Il centro del paper target (zona A) è circa al suo centro
                pt_center = Point(pt.x, pt.y)
                # Se il centro del bersaglio è dentro l'hard cover o molto
                # vicino, la zona A potrebbe essere coperta
                if hc_obb.contains(pt_center):
                    v.append(
                        f"Hard Cover #{hc.id} copre il centro del bersaglio "
                        f"#{pt.id} (possibile occultamento zona A, Reg. 4.2.4)")
                else:
                    # Verifica distanza: se hard cover è molto vicino al centro
                    from shapely import distance as sh_dist
                    d = sh_dist(hc_obb, pt_center)
                    if d < 0.15:
                        v.append(
                            f"Hard Cover #{hc.id} a {d*100:.0f}cm dal centro "
                            f"del bersaglio #{pt.id} "
                            f"(possibile occultamento zona A, Reg. 4.2.4)")

        return v

    # ── Reg. 4.3.1.1 — Vietati bersagli metallici rotanti ───────────────

    def _validate_metal_rotating_prohibited(self) -> List[str]:
        """Verifica che non ci siano bersagli metallici (popper, plate,
        steel) che possano ruotare o porsi di taglio quando colpiti
        (Reg. 4.3.1.1).

        'Sono espressamente proibiti i bersagli metallici che assegnano
        punti o penalità che possano ruotare o porsi di taglio a seguito
        di un colpo andato a segno.'

        Il controllo rileva proprietà come "swinger", "rotating",
        "drop_turner" su item di tipo metallico.
        """
        v = []

        metal_items = [
            it for it in self.stage.items
            if it.item_type in (ItemType.STEEL_TARGET, ItemType.POPPER,
                                ItemType.METAL_PLATE)
        ]
        for it in metal_items:
            props = it.properties or {}
            # Cerca proprietà che indicano movimento/rotazione
            moving_props = [k for k in props if k in (
                "amplitude", "speed", "trigger", "fall_time",
                "distance", "direction", "rotating", "swing",
            )]
            if moving_props:
                v.append(
                    f"Bersaglio metallico #{it.id} ({it.label}) ha proprietà "
                    f"di movimento ({', '.join(moving_props)}) che sono "
                    f"vietate per i metallici (Reg. 4.3.1.1)")

        # Inoltre, i tipi SWINGER, DROP_TURNER, MOVER non dovrebbero
        # MAI essere di tipo metallico (sono inherently carta)
        for it in self.stage.items:
            if it.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER,
                                ItemType.MOVER):
                if "metal" in it.label.lower() or "steel" in it.label.lower():
                    v.append(
                        f"Bersaglio mobile #{it.id} ({it.label}) è marcato "
                        f"come metallico ma i mobili devono essere cartacei "
                        f"(Reg. 4.3.1.1)")

        return v

    # ── App. C3 — Altezza montaggio piatti metallici ────────────────────

    def _validate_plate_mounting_height(self) -> List[str]:
        """Verifica che i piatti metallici siano montati su Hard Cover o
        paletti di almeno 1m di altezza (App. C3).

        'Nelle gare di pistola i piatti metallici dovrebbero essere posti
        su Hard Cover o paletti di almeno 1 m di altezza.'

        Rileva se un METAL_PLATE non ha un HARD_COVER sottostante o
        la proprietà mount_height < 1m.
        """
        v = []

        plates = [
            it for it in self.stage.items
            if it.item_type == ItemType.METAL_PLATE
        ]
        if not plates:
            return v

        hard_covers = [
            it for it in self.stage.items
            if it.item_type == ItemType.HARD_COVER
        ]

        for pl in plates:
            mount_height = pl.properties.get("mount_height", 0.0)

            # Verifica 1: proprietà esplicita mount_height
            if mount_height >= self.MIN_PLATE_MOUNT_HEIGHT:
                continue

            # Verifica 2: c'è un hard cover sotto il piatto?
            has_support = False
            pl_point = Point(pl.x, pl.y)
            for hc in hard_covers:
                hc_obb = item_obb(hc)
                if hc_obb and hc_obb.contains(pl_point):
                    has_support = True
                    break
                # Oppure hard cover a meno di 0.3m sotto
                from shapely import distance as sh_dist
                if hc_obb and sh_dist(hc_obb, pl_point) < 0.3:
                    # Verifica che l'hard cover sia sotto (y minore)
                    if hc.y + hc.height / 2 < pl.y:
                        has_support = True
                        break

            if not has_support:
                v.append(
                    f"Piatto metallico #{pl.id} non montato su Hard Cover o "
                    f"paletto ≥ {self.MIN_PLATE_MOUNT_HEIGHT}m "
                    f"(mount_height={mount_height}m, App. C3)")

        return v

    def _validate_same_line_of_fire(self) -> List[str]:
        """Verifica che non ci siano due bersagli sulla stessa linea di tiro.

        Dal centro dell'area di tiro, se due bersagli che assegnano punti
        hanno un angolo inferiore a SAME_LINE_OF_FIRE_THRESHOLD_DEG,
        sono considerati sulla stessa linea di tiro.

        Questo evita che un singolo colpo possa colpire due bersagli
        e garantisce distribuzione angolare degli ingaggi.
        """
        v = []
        targets = [
            it for it in self.stage.items
            if it.item_type in (
                ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
                ItemType.POPPER, ItemType.METAL_PLATE,
                ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
                ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER,
            )
        ]
        if len(targets) < 2:
            return v

        # Centro dell'area di tiro approssimato
        cx = self.stage.width / 2
        cy = self.stage.depth * 0.3
        if self.stage.shooting_positions:
            cx = sum(sp.x for sp in self.stage.shooting_positions) / len(self.stage.shooting_positions)
            cy = sum(sp.y for sp in self.stage.shooting_positions) / len(self.stage.shooting_positions)

        threshold = SAME_LINE_OF_FIRE_THRESHOLD_DEG
        for i, a in enumerate(targets):
            a_angle = math.degrees(math.atan2(a.y - cy, a.x - cx))
            for b in targets[i + 1:]:
                if a.id == b.id:
                    continue
                b_angle = math.degrees(math.atan2(b.y - cy, b.x - cx))
                diff = abs(a_angle - b_angle)
                diff = min(diff, 360 - diff)
                if diff < threshold:
                    v.append(
                        f"Bersagli #{a.id} e #{b.id} sulla stessa linea di tiro "
                        f"(angolo {diff:.1f}°, soglia {threshold}°)"
                    )

        return v

    def count_targets(self) -> dict:
        """Conta i bersagli per tipo."""

        def _is_paper(it):
            return it.item_type in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET,
                                    ItemType.MICRO_TARGET)
        def _is_steel(it):
            return it.item_type in (ItemType.STEEL_TARGET, ItemType.POPPER,
                                    ItemType.METAL_PLATE)
        def _is_moving(it):
            return it.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER,
                                    ItemType.MOVER)

        paper = [it for it in self.stage.items if _is_paper(it)]
        steel = [it for it in self.stage.items if _is_steel(it)]
        moving = [it for it in self.stage.items if _is_moving(it)]
        no_shoots = [it for it in self.stage.items
                     if it.item_type == ItemType.NO_SHOOT]
        return {
            "paper": len(paper),
            "steel": len(steel),
            "moving": len(moving),
            "no_shoots": len(no_shoots),
            "total_scoring": len(paper) + len(steel),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  MatchValidator — validazione a livello di gara (multi-stage)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class MatchValidationResult:
    ok: bool
    violations: List[str] = None

    def __post_init__(self):
        if self.violations is None:
            self.violations = []


class MatchValidator:
    """Validatore a livello di gara IPSC (multi-stage).

    Verifica:
    - Rapporto 3:2:1 Short:Medium:Long (Appendice A4)
    - Numero minimo esercizi per livello (Appendice A1)
    - Distribuzione coerente
    """

    def __init__(self, stages: List[Stage], match_level: int = 1):
        self.stages = stages
        self.match_level = match_level

    def validate(self) -> MatchValidationResult:
        violations: List[str] = []

        violations.extend(self._validate_ratio_3_2_1())
        violations.extend(self._validate_min_stages())
        violations.extend(self._validate_min_rounds())

        return MatchValidationResult(
            ok=len(violations) == 0, violations=violations)

    def _validate_ratio_3_2_1(self) -> List[str]:
        """Verifica il rapporto 3:2:1 tra Short:Medium:Long (App. A4)."""
        v = []
        if not self.stages:
            return v

        short = sum(1 for s in self.stages
                    if s.course_type == CourseType.SHORT)
        medium = sum(1 for s in self.stages
                     if s.course_type == CourseType.MEDIUM)
        long_ = sum(1 for s in self.stages
                    if s.course_type == CourseType.LONG)

        # Rapporto approssimato: per ogni Long, ci devono essere
        # circa 3 Short e 2 Medium
        if long_ > 0:
            expected_short = long_ * 3
            expected_medium = long_ * 2

            # Tolleranza: ±1 sul rapporto
            if abs(short - expected_short) > 1 and short > 0:
                v.append(
                    f"Rapporto 3:2:1: {short} Short, {medium} Medium, {long_} Long. "
                    f"Attesi ~{expected_short} Short per {long_} Long (App. A4)")
            if abs(medium - expected_medium) > 1 and medium > 0:
                v.append(
                    f"Rapporto 3:2:1: {short} Short, {medium} Medium, {long_} Long. "
                    f"Attesi ~{expected_medium} Medium per {long_} Long (App. A4)")

        return v

    def _validate_min_stages(self) -> List[str]:
        """Verifica il numero minimo di esercizi per livello (App. A1)."""
        v = []
        min_stages = MATCH_MIN_STAGES.get(self.match_level, 3)
        if len(self.stages) < min_stages:
            v.append(
                f"Gara livello {self.match_level}: {len(self.stages)} esercizi "
                f"(min {min_stages}, App. A1)")
        return v

    def _validate_min_rounds(self) -> List[str]:
        """Verifica il numero minimo di colpi totali per livello (App. A1)."""
        v = []
        min_rounds = MATCH_MIN_ROUNDS.get(self.match_level, 40)
        total = 0
        for s in self.stages:
            for it in s.items:
                if it.item_type in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET,
                                    ItemType.MICRO_TARGET, ItemType.SWINGER,
                                    ItemType.DROP_TURNER, ItemType.MOVER):
                    total += 2
                elif it.item_type in (ItemType.STEEL_TARGET, ItemType.POPPER,
                                      ItemType.METAL_PLATE):
                    total += 1
        if total < min_rounds:
            v.append(
                f"Gara livello {self.match_level}: {total} colpi totali "
                f"(min {min_rounds}, App. A1)")
        return v

