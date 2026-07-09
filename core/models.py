# core/models.py
"""Modelli dati per il Stage Generator."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Any


class ItemType(Enum):
    WALL = auto()
    PAPER_TARGET = auto()
    STEEL_TARGET = auto()      # generico (backward compat)
    POPPER = auto()            # bersaglio metallico calibrato (App. C1-C2)
    METAL_PLATE = auto()       # piatto metallico non calibrato (App. C3)
    MINI_TARGET = auto()       # bersaglio cartaceo ridotto (App. B3)
    MICRO_TARGET = auto()      # bersaglio cartaceo micro
    FAULT_LINE = auto()
    NO_SHOOT = auto()
    BARRIER = auto()
    DOOR = auto()
    HARD_COVER = auto()        # copertura impenetrabile (Reg. 4.1.4.1)
    SOFT_COVER = auto()        # copertura visiva (Reg. 4.1.4.2)
    SWINGER = auto()           # bersaglio oscillante
    DROP_TURNER = auto()       # bersaglio che cade/gira
    MOVER = auto()             # bersaglio su rotaia


class CourseType(Enum):
    SHORT = "short"       # ≤12 colpi, max 9 da posizione (Reg. 1.2.1.1)
    MEDIUM = "medium"     # ≤24 colpi, max 9 da posizione (Reg. 1.2.1.2)
    LONG = "long"         # ≤32 colpi, max 9 da posizione (Reg. 1.2.1.3)


class Division(Enum):
    OPEN = "open"
    STANDARD = "standard"
    CLASSIC = "classic"
    PRODUCTION = "production"
    PRODUCTION_OPTICS = "production_optics"
    REVOLVER = "revolver"


@dataclass
class StageItem:
    """Elemento generico posizionato sullo stage."""
    id: int
    item_type: ItemType
    x: float = 0.0        # centro (metri)
    y: float = 0.0        # centro (metri)
    width: float = 1.0    # metri
    height: float = 2.0   # metri
    rotation: float = 0.0   # gradi, 0 = allineato asse X
    color: str = "#808080"
    label: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    # ── properties per bersagli mobili ────────────────────────────
    #   swinger:      { "amplitude": 45, "speed": 1.0, "axis": "y" }
    #   drop_turner:  { "trigger": "hit", "fall_time": 0.5 }
    #   mover:        { "distance": 3.0, "speed": 1.5, "direction": 0 }
    #
    # ── properties per metallici ──────────────────────────────────
    #   popper:       { "calibrated": true, "calibration_pf": 125 }
    #   metal_plate:  { "diameter": 0.2 }
    #
    # ── properties per attivatori (popper/plate → bersagli) ────────
    #   attivatore:   { "activates": [id1, id2, ...] }
    #   bersaglio:    { "activated_by": [id_attivatore],
    #                    "activation_visible": true }
    #
    # ── properties per mini target ────────────────────────────────
    #   mini_target:  { "scale": 0.75 }
    #   micro_target: { "scale": 0.50 }
    #
    # ── properties per coperture ──────────────────────────────────
    #   cover:        { "height": 2.0, "impenetrable": true }


@dataclass
class ShootingPosition:
    """Posizione di tiro del tiratore all'interno dello stage.
    
    Uno stage IPSC può avere una posizione di partenza (start) e
    posizioni intermedie opzionali dove il tiratore deve
    fermarsi per ingaggiare bersagli.
    """
    id: int
    x: float = 0.0
    y: float = 0.0
    label: str = ""
    is_start: bool = False  # True = posizione di partenza
    angle: float = 0.0       # direzione di ingaggio preferita (gradi)
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Stage:
    """Contenitore dello stage.
    
    `properties` contiene metadati di briefing (non posizionali):
        start_signal: str          — "Acustico"
        start_position: str        — "Ovunque nella shooting area"
        ready_condition_handgun: str
        ready_condition_pcc: str
        procedure: str             — testo della procedura
        max_points: int            — massimo punteggio possibile
        activator_descs: list[str] — descrizioni attivazioni per briefing
    """
    name: str = "Nuovo Stage"
    width: float = 20.0   # metri
    depth: float = 15.0   # metri
    course_type: Optional[CourseType] = None  # Short/Medium/Long
    division: Optional[Division] = None        # Divisione di riferimento
    items: List[StageItem] = field(default_factory=list)
    shooting_positions: List[ShootingPosition] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    _next_id: int = 1

    def add_item(self, item: StageItem) -> StageItem:
        item.id = self._next_id
        self._next_id += 1
        self.items.append(item)
        return item

    def remove_item(self, item_id: int) -> bool:
        for i, it in enumerate(self.items):
            if it.id == item_id:
                self.items.pop(i)
                return True
        return False

    def get_item(self, item_id: int) -> Optional[StageItem]:
        for it in self.items:
            if it.id == item_id:
                return it
        return None
