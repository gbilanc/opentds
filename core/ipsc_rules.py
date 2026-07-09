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

    # Distanze minime in metri
    MIN_TARGET_TO_EDGE = 1.0
    MIN_TARGET_TO_WALL = 0.8
    MIN_TARGET_TO_TARGET = 0.8
    MIN_TARGET_TO_BARRIER = 0.5
    MIN_WALL_TO_EDGE = 0.3
    MIN_OBSTACLE_GAP = 0.1  # distanza minima tra ostacoli (muri, barriere, porte)
    MIN_BACKSTOP_DEPTH = 3.0
    MIN_STEEL_DISTANCE = 7.0    # IPSC Reg. 2.1.3: distanza minima tiratore-bersaglio metallico
    SAFETY_ANGLE_DEFAULT = 90.0  # IPSC Reg. 2.1.2: angolo di sicurezza default

    # Limiti IPSC
    MIN_TARGETS = 8
    MAX_STEEL_PCT = 0.4        # max 40% steel
    MAX_STAGE_WIDTH = 40.0
    MAX_STAGE_DEPTH = 30.0
    RECOMMENDED_NO_SHOOT_INTERVAL = 8  # 1 no-shoot ogni 8 paper
    MAX_HITS_PER_POSITION = 9   # IPSC Reg. 1.2.1: max 9 colppi conteggiabili da singola posizione

    # Limiti per tipo di corso (Regola 1.2.1)
    COURSE_MAX_ROUNDS: dict[str, int] = {
        "short": 12,
        "medium": 24,
        "long": 32,
    }

    # Limiti Divisione (Appendici D1-D5)
    DIVISION_MAG_CAPACITY: dict[str, int | None] = {
        "open": None,
        "standard": None,  # limitato da lunghezza 170mm
        "classic": 8,       # 8 Major / 10 Minor
        "production": 15,
        "production_optics": 15,
        "revolver": 6,      # 6 colpi, 7+ solo Minor
    }
    DIVISION_ALLOW_OPTICS: dict[str, bool] = {
        "open": True,
        "standard": False,
        "classic": False,
        "production": False,
        "production_optics": True,
        "revolver": False,
    }
    DIVISION_ALLOW_COMP: dict[str, bool] = {
        "open": True,
        "standard": False,
        "classic": False,
        "production": False,
        "production_optics": False,
        "revolver": False,
    }
    DIVISION_BOX_TEST: dict[str, tuple[float, float, float]] = {
        "standard": (0.225, 0.150, 0.045),
        "classic": (0.225, 0.150, 0.045),
    }
    DIVISION_MAX_BARREL_LENGTH: dict[str, float | None] = {
        "production": 0.127,
        "production_optics": 0.127,
    }
    DIVISION_MIN_TRIGGER_WEIGHT: dict[str, float | None] = {
        "production": 2.27,     # kg primo colpo
        "production_optics": 2.27,
    }

    # Rapporto 3:2:1 (Appendice A4)
    RATIO_SHORT = 3
    RATIO_MEDIUM = 2
    RATIO_LONG = 1

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
        violations.extend(self._validate_steel_distance())
        violations.extend(self._validate_max_hits_per_position())
        violations.extend(self._validate_safety_angles())
        violations.extend(self._validate_course_type())
        violations.extend(self._validate_division())

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
        eps = 0.05
        for i, a in enumerate(paper_targets):
            a_obb = item_obb(a)
            if not a_obb:
                continue
            for b in paper_targets[i + 1:]:
                b_obb = item_obb(b)
                if not b_obb:
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

    # Match level requirements (Appendice A1)
    MATCH_MIN_STAGES: dict[int, int] = {
        1: 3, 2: 6, 3: 12, 4: 24, 5: 30,
    }
    MATCH_MIN_ROUNDS: dict[int, int] = {
        1: 40, 2: 80, 3: 150, 4: 300, 5: 450,
    }

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
        min_stages = self.MATCH_MIN_STAGES.get(self.match_level, 3)
        if len(self.stages) < min_stages:
            v.append(
                f"Gara livello {self.match_level}: {len(self.stages)} esercizi "
                f"(min {min_stages}, App. A1)")
        return v

    def _validate_min_rounds(self) -> List[str]:
        """Verifica il numero minimo di colpi totali per livello (App. A1)."""
        v = []
        min_rounds = self.MATCH_MIN_ROUNDS.get(self.match_level, 40)
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

