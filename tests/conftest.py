"""
Fixtures condivise per i test di OpenTDS.
"""
from __future__ import annotations

import pytest

from core.models import Stage, StageItem, ItemType


@pytest.fixture
def empty_stage() -> Stage:
    """Uno stage vuoto 20×15 m."""
    return Stage(name="Test Stage", width=20.0, depth=15.0)


@pytest.fixture
def sample_stage() -> Stage:
    """Uno stage con alcuni oggetti di esempio."""
    stage = Stage(name="Sample Stage", width=20.0, depth=15.0)
    stage.add_item(StageItem(0, ItemType.WALL, 5.0, 7.0, 4.0, 0.2))
    stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 6.0, 5.0, 0.45, 0.45))
    stage.add_item(StageItem(0, ItemType.STEEL_TARGET, 13.0, 8.0, 0.30, 0.30))
    stage.add_item(StageItem(0, ItemType.FAULT_LINE, 3.0, 10.0, 4.0, 0.0))
    stage.add_item(StageItem(0, ItemType.NO_SHOOT, 6.5, 5.5, 0.45, 0.45))
    stage.add_item(StageItem(0, ItemType.BARRIER, 10.0, 3.0, 2.0, 0.15))
    stage.add_item(StageItem(0, ItemType.DOOR, 8.0, 2.0, 0.9, 0.05))
    return stage


@pytest.fixture
def sample_items() -> dict[str, StageItem]:
    """Item tipici per test di validazione."""
    return {
        "wall": StageItem(1, ItemType.WALL, 5.0, 5.0, 3.0, 0.2, 0, "#475569"),
        "paper": StageItem(2, ItemType.PAPER_TARGET, 10.0, 10.0, 0.45, 0.45, 0, "#ef4444"),
        "steel": StageItem(3, ItemType.STEEL_TARGET, 12.0, 12.0, 0.30, 0.30, 0, "#3b82f6"),
        "fault": StageItem(4, ItemType.FAULT_LINE, 3.0, 3.0, 5.0, 0.0, 0, "#dc2626"),
        "noshoot": StageItem(5, ItemType.NO_SHOOT, 8.0, 8.0, 0.45, 0.45, 0, "#f87171"),
        "barrier": StageItem(6, ItemType.BARRIER, 7.0, 7.0, 2.0, 0.15, 0, "#fbbf24"),
        "door": StageItem(7, ItemType.DOOR, 15.0, 15.0, 0.9, 0.05, 0, "#92400e"),
        "swinger": StageItem(8, ItemType.SWINGER, 10.0, 12.0, 0.45, 0.45, 0, "#a855f7",
                              properties={"amplitude": 45, "speed": 1.0}),
        "drop_turner": StageItem(9, ItemType.DROP_TURNER, 11.0, 13.0, 0.45, 0.45, 0, "#14b8a6",
                                  properties={"trigger": "hit", "fall_time": 0.5}),
        "mover": StageItem(10, ItemType.MOVER, 12.0, 14.0, 0.45, 0.45, 0, "#f97316",
                            properties={"distance": 3.0, "speed": 1.5}),
    }
