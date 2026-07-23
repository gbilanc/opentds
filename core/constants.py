"""
Costanti regolamentari IPSC centralizzate.

Tutte le distanze sono in metri, angoli in gradi.
Riferimenti: Regolamento IPSC Handgun 2025 (https://www.ipsc.org).
"""
from __future__ import annotations

from typing import Final

# ═══════════════════════════════════════════════════════════════════════════════
#  Distanze minime (Cap. 2 — Sicurezza e Regole Generali)
# ═══════════════════════════════════════════════════════════════════════════════

# Distanza tra bersaglio e bordo stage / fault line (Reg. 2.1.4)
MIN_TARGET_TO_EDGE: Final = 1.0

# Distanza tra bersaglio e muro/porta (Reg. 2.2.1)
MIN_TARGET_TO_WALL: Final = 0.8

# Distanza tra due bersagli che assegnano punti (Reg. 2.1.5)
MIN_TARGET_TO_TARGET: Final = 0.8

# Distanza tra bersaglio e barriera (Reg. 2.2.3)
MIN_TARGET_TO_BARRIER: Final = 0.5

# Distanza tra muro/barriera e bordo stage
MIN_WALL_TO_EDGE: Final = 0.3

# Gap minimo tra ostacoli (muri, barriere, porte) — non perimetrali
MIN_OBSTACLE_GAP: Final = 0.1

# Backstop minimo dietro i bersagli (Reg. 2.1.6)
MIN_BACKSTOP_DEPTH: Final = 3.0

# Distanza minima tiratore → bersaglio metallico
# IPSC Reg. 2.1.3: il tiratore non deve trovarsi a meno di 7m da un
# bersaglio metallico quando spara. Con fault lines a 8m, il RO può
# fermarlo prima della violazione.
MIN_STEEL_DISTANCE: Final = 7.0

# Distanza di posizionamento bersagli steel dal poligono area di tiro
# = MIN_STEEL_DISTANCE + margine di sicurezza (1m)
MIN_STEEL_PLACEMENT_DISTANCE: Final = 8.0

# ═══════════════════════════════════════════════════════════════════════════════
#  Angoli (Cap. 2 — Sicurezza)
# ═══════════════════════════════════════════════════════════════════════════════

# Angolo di sicurezza di default (Reg. 2.1.2)
SAFETY_ANGLE_DEFAULT: Final = 90.0

# Angolo massimo bersagli fissi rispetto alla verticale (Reg. 2.1.8.4)
MAX_FIXED_TARGET_ANGLE: Final = 90.0

# Soglia per considerare due bersagli sulla stessa linea di tiro (gradi)
# Dal centro dell'area di tiro, se l'angolo tra due bersagli è < di questo
# valore, sono considerati allineati sulla stessa linea di tiro.
SAME_LINE_OF_FIRE_THRESHOLD_DEG: Final = 3.0

# Angolo massimo per considerare un bersaglio "nello stesso settore"
# dell'attivatore per le relazioni di attivazione
ACTIVATOR_SECTOR_ANGLE_DEG: Final = 45.0

# ═══════════════════════════════════════════════════════════════════════════════
#  Altezze (Cap. 2 — Ostacoli e App. C3)
# ═══════════════════════════════════════════════════════════════════════════════

# Altezza massima ostacoli (Reg. 2.2.2)
MAX_OBSTACLE_HEIGHT: Final = 2.0

# Altezza minima barriere (Reg. 2.2.3)
MIN_BARRIER_HEIGHT: Final = 1.8

# Altezza minima montaggio piatti metallici (App. C3)
MIN_PLATE_MOUNT_HEIGHT: Final = 1.0

# ═══════════════════════════════════════════════════════════════════════════════
#  Conteggi bersagli (Cap. 1 — Struttura gara)
# ═══════════════════════════════════════════════════════════════════════════════

# Numero minimo di bersagli per stage (Reg. 1.2.1)
MIN_TARGETS: Final = 8

# Percentuale massima di bersagli steel (Reg. 1.2.1.5)
MAX_STEEL_PCT: Final = 0.4

# Rapporto consigliato no-shoot: 1 ogni N bersagli carta
RECOMMENDED_NO_SHOOT_INTERVAL: Final = 8

# Massimo colpi conteggiabili da singola posizione (Reg. 1.2.1)
MAX_HITS_PER_POSITION: Final = 9

# Numero minimo di no-shoot per stage
MIN_NO_SHOOTS: Final = 1

# ═══════════════════════════════════════════════════════════════════════════════
#  Dimensioni stage (Cap. 1 — Regole Generali)
# ═══════════════════════════════════════════════════════════════════════════════

# Dimensioni massime stage
MAX_STAGE_WIDTH: Final = 40.0
MAX_STAGE_DEPTH: Final = 30.0

# Dimensioni minime per disciplina
MIN_STAGE_DIMENSIONS: Final[dict[str, tuple[float, float]]] = {
    "ipsc_pistol": (10.0, 8.0),
    "mini_rifle":  (15.0, 10.0),
    "shotgun":      (8.0, 8.0),
}

# Massimo numero bersagli per disciplina
MAX_TARGETS_BY_DISCIPLINE: Final[dict[str, int]] = {
    "ipsc_pistol": 32,
    "mini_rifle":  40,
    "shotgun":     32,
}

# ═══════════════════════════════════════════════════════════════════════════════
#  Colpi per tipo di corso (Reg. 1.2.1.1-3)
# ═══════════════════════════════════════════════════════════════════════════════

COURSE_MAX_ROUNDS: Final[dict[str, int]] = {
    "short":  12,
    "medium": 24,
    "long":   32,
}

# Colpi per bersaglio (default per calcolo punteggio)
HITS_PER_PAPER: Final = 2
HITS_PER_STEEL: Final = 1
HITS_PER_MOVING: Final = 2  # i mobili sono su supporto cartaceo

# ═══════════════════════════════════════════════════════════════════════════════
#  Dimensioni bersagli (App. B — Specifiche Bersagli)
# ═══════════════════════════════════════════════════════════════════════════════

# Dimensioni standard IPSC per bersagli (larghezza, altezza in metri)
TARGET_DIMENSIONS: Final[dict[str, tuple[float, float]]] = {
    "paper":        (0.45, 0.45),
    "mini":         (0.34, 0.34),
    "micro":        (0.23, 0.23),
    "popper":       (0.30, 0.30),
    "metal_plate":  (0.20, 0.20),
    "steel_generic":(0.30, 0.30),
    "swinger":      (0.45, 0.45),
    "drop_turner":  (0.45, 0.45),
    "mover":        (0.45, 0.45),
}

# Colori IPSC standard
TARGET_COLORS: Final[dict[str, str]] = {
    "paper":       "#8B4513",  # marrone — bersaglio carta
    "mini":        "#A0522D",
    "micro":       "#8B4513",
    "popper":      "#d1d5db",  # grigio chiaro — acciaio
    "metal_plate": "#e5e7eb",
    "steel_generic":"#d1d5db",
    "swinger":     "#A0522D",
    "drop_turner": "#8B6914",
    "mover":       "#CD853F",
    "no_shoot":    "#eab308",  # giallo — penalità
    "wall":        "#475569",
    "barrier":     "#fbbf24",
    "fault_line":  "#dc2626",  # rosso — linea di fallo
}

# ═══════════════════════════════════════════════════════════════════════════════
#  Generazione automatica — distribuzione bersagli per course_type
# ═══════════════════════════════════════════════════════════════════════════════

# Distribuzione tipica per tipo di corso (paper, poppers, plates, mini, moving)
COURSE_TARGET_DISTRIBUTION: Final[dict[str, dict[str, int]]] = {
    "short":  {"paper": 5,  "poppers": 1, "plates": 1, "mini": 0, "moving": 0},
    "medium": {"paper": 11, "poppers": 1, "plates": 2, "mini": 1, "moving": 1},
    "long":   {"paper": 15, "poppers": 2, "plates": 2, "mini": 1, "moving": 2},
}

# ═══════════════════════════════════════════════════════════════════════════════
#  Generazione — parametri geometrici
# ═══════════════════════════════════════════════════════════════════════════════

# Dimensione minima del poligono dell'area di tiro (m)
MIN_POLY_DIM: Final = 4.0

# Apertura sul fronte per accesso (m) — per delimitazione barriers/walls
FRONT_OPEN_GAP: Final = 2.0

# Numero di punti interni da campionare per visibility check
INTERIOR_SAMPLE_COUNT: Final = 20

# ═══════════════════════════════════════════════════════════════════════════════
#  Generazione — relazioni attivatore-attivato
# ═══════════════════════════════════════════════════════════════════════════════

# Distanza massima tra attivatore (popper/plate) e bersaglio attivato (m)
MAX_ACTIVATOR_DISTANCE: Final = 6.0

# Distanza massima per "immediate vicinanze" tra metallico e bersaglio mobile (m)
MAX_ACTIVATOR_MOVING_DISTANCE: Final = 3.0

# Massimo bersagli attivabili da un singolo attivatore
MAX_ACTIVATED_PER_ACTIVATOR: Final = 3

# ═══════════════════════════════════════════════════════════════════════════════
#  Validazione — Divisioni (App. D1-D5)
# ═══════════════════════════════════════════════════════════════════════════════

DIVISION_MAG_CAPACITY: Final[dict[str, int | None]] = {
    "open":              None,
    "standard":          None,
    "classic":            8,
    "production":         15,
    "production_optics":  15,
    "revolver":            6,
}

DIVISION_ALLOW_OPTICS: Final[dict[str, bool]] = {
    "open":              True,
    "standard":          False,
    "classic":           False,
    "production":        False,
    "production_optics": True,
    "revolver":          False,
}

DIVISION_ALLOW_COMP: Final[dict[str, bool]] = {
    "open":              True,
    "standard":          False,
    "classic":           False,
    "production":        False,
    "production_optics": False,
    "revolver":          False,
}

DIVISION_MAX_BARREL_LENGTH: Final[dict[str, float | None]] = {
    "production":        0.127,
    "production_optics": 0.127,
}

DIVISION_MIN_TRIGGER_WEIGHT: Final[dict[str, float | None]] = {
    "production":        2.27,
    "production_optics": 2.27,
}

# ═══════════════════════════════════════════════════════════════════════════════
#  Match — rapporto 3:2:1 (App. A4) e minimi per livello (App. A1)
# ═══════════════════════════════════════════════════════════════════════════════

RATIO_SHORT: Final = 3
RATIO_MEDIUM: Final = 2
RATIO_LONG: Final = 1

MATCH_MIN_STAGES: Final[dict[int, int]] = {
    1: 3, 2: 6, 3: 12, 4: 24, 5: 30,
}

MATCH_MIN_ROUNDS: Final[dict[int, int]] = {
    1: 40, 2: 80, 3: 150, 4: 300, 5: 450,
}
