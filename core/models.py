# core/models.py
"""Modelli dati per il Stage Generator."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Any


class ItemType(Enum):
    WALL = auto()
    PAPER_TARGET = auto()
    STEEL_TARGET = auto()
    FAULT_LINE = auto()
    NO_SHOOT = auto()
    BARRIER = auto()
    DOOR = auto()
    SWINGER = auto()        # bersaglio oscillante
    DROP_TURNER = auto()    # bersaglio che cade/gira
    MOVER = auto()          # bersaglio su rotaia


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
    # properties per bersagli mobili:
    #   swinger: { "amplitude": 45, "speed": 1.0, "axis": "y" }
    #   drop_turner: { "trigger": "hit", "fall_time": 0.5 }
    #   mover: { "distance": 3.0, "speed": 1.5, "direction": 0 }


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
    """Contenitore dello stage."""
    name: str = "Nuovo Stage"
    width: float = 20.0   # metri
    depth: float = 15.0   # metri
    items: List[StageItem] = field(default_factory=list)
    shooting_positions: List[ShootingPosition] = field(default_factory=list)
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
