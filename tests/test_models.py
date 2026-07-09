"""
Test unitari per core/models.py — Stage, StageItem, ItemType.
"""
from __future__ import annotations

import pytest

from core.models import Stage, StageItem, ItemType


# ─── ItemType ────────────────────────────────────────────────────────────────

class TestItemType:
    """ItemType enum: 10 tipi previsti."""

    def test_all_types_present(self):
        assert len(ItemType) == 10
        assert ItemType.WALL in ItemType
        assert ItemType.PAPER_TARGET in ItemType
        assert ItemType.STEEL_TARGET in ItemType
        assert ItemType.FAULT_LINE in ItemType
        assert ItemType.NO_SHOOT in ItemType
        assert ItemType.BARRIER in ItemType
        assert ItemType.DOOR in ItemType
        assert ItemType.SWINGER in ItemType
        assert ItemType.DROP_TURNER in ItemType
        assert ItemType.MOVER in ItemType

    def test_types_are_unique(self):
        names = [t.name for t in ItemType]
        assert len(names) == len(set(names))


# ─── StageItem ───────────────────────────────────────────────────────────────

class TestStageItemCreation:
    """Verifica creazione e valori di default di StageItem."""

    def test_default_values(self):
        """Item creato con solo id e tipo ha valori predefiniti sensati."""
        item = StageItem(1, ItemType.WALL)
        assert item.id == 1
        assert item.item_type == ItemType.WALL
        assert item.x == 0.0
        assert item.y == 0.0
        assert item.width == 1.0
        assert item.height == 2.0
        assert item.rotation == 0.0
        assert item.color == "#808080"
        assert item.label == ""
        assert item.properties == {}

    def test_full_construction(self, sample_items):
        """Costruzione con tutti i parametri."""
        item = sample_items["swinger"]
        assert item.id == 8
        assert item.item_type == ItemType.SWINGER
        assert item.x == 10.0
        assert item.y == 12.0
        assert item.properties["amplitude"] == 45.0

    def test_mutable_properties(self):
        """Le proprietà sono mutabili dopo la creazione."""
        item = StageItem(1, ItemType.MOVER)
        item.x = 7.5
        item.y = 3.2
        item.rotation = 45.0
        item.properties["distance"] = 5.0
        assert item.x == 7.5
        assert item.y == 3.2
        assert item.rotation == 45.0
        assert item.properties["distance"] == 5.0


# ─── Stage ───────────────────────────────────────────────────────────────────

class TestStageCreation:
    """Verifica creazione Stage e gestione items."""

    def test_default_stage(self):
        """Stage vuoto con default ragionevoli."""
        stage = Stage()
        assert stage.name == "Nuovo Stage"
        assert stage.width == 20.0
        assert stage.depth == 15.0
        assert stage.items == []
        assert stage._next_id == 1

    def test_custom_stage(self):
        """Stage con parametri custom."""
        stage = Stage(name="Custom", width=30.0, depth=25.0)
        assert stage.name == "Custom"
        assert stage.width == 30.0
        assert stage.depth == 25.0

    def test_add_item_assigns_id(self, empty_stage):
        """add_item assegna id progressivo e restituisce l'item."""
        item = StageItem(0, ItemType.WALL)
        returned = empty_stage.add_item(item)
        assert returned is item
        assert item.id == 1
        assert len(empty_stage.items) == 1

    def test_add_item_increments_next_id(self, empty_stage):
        """L'id incrementa a ogni aggiunta."""
        i1 = empty_stage.add_item(StageItem(0, ItemType.WALL))
        i2 = empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET))
        i3 = empty_stage.add_item(StageItem(0, ItemType.STEEL_TARGET))
        assert i1.id == 1
        assert i2.id == 2
        assert i3.id == 3
        assert empty_stage._next_id == 4

    def test_remove_item_existing(self, empty_stage):
        """Rimuovere un item esistente restituisce True."""
        item = empty_stage.add_item(StageItem(0, ItemType.WALL))
        assert empty_stage.remove_item(item.id) is True
        assert len(empty_stage.items) == 0

    def test_remove_item_non_existing(self, empty_stage):
        """Rimuovere un id inesistente restituisce False."""
        assert empty_stage.remove_item(999) is False

    def test_remove_item_shifts_ids_properly(self, empty_stage):
        """La rimozione non lascia buchi nella lista."""
        i1 = empty_stage.add_item(StageItem(0, ItemType.WALL))
        i2 = empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET))
        empty_stage.remove_item(i1.id)
        assert len(empty_stage.items) == 1
        assert empty_stage.items[0].id == i2.id

    def test_get_item_existing(self, sample_stage):
        """get_item trova un item esistente per id."""
        item = sample_stage.get_item(1)
        assert item is not None
        assert item.id == 1

    def test_get_item_non_existing(self, sample_stage):
        """get_item restituisce None per id inesistente."""
        assert sample_stage.get_item(999) is None

    def test_added_items_are_independent(self, empty_stage):
        """Ogni item aggiunto è un oggetto distinto."""
        i1 = empty_stage.add_item(StageItem(0, ItemType.WALL))
        i2 = empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET))
        assert i1 is not i2
        assert len(empty_stage.items) == len(set(id(it) for it in empty_stage.items))


class TestStageWithSample:
    """Test su sample_stage pre-popolato."""

    def test_sample_has_correct_item_count(self, sample_stage):
        """Lo stage di esempio ha 7 item."""
        assert len(sample_stage.items) == 7

    def test_sample_item_types(self, sample_stage):
        """Tipi di item corretti nello stage di esempio."""
        types = {it.item_type for it in sample_stage.items}
        assert ItemType.WALL in types
        assert ItemType.PAPER_TARGET in types
        assert ItemType.STEEL_TARGET in types
        assert ItemType.FAULT_LINE in types
        assert ItemType.NO_SHOOT in types
        assert ItemType.BARRIER in types
        assert ItemType.DOOR in types

    def test_sample_no_duplicate_ids(self, sample_stage):
        """Tutti gli item hanno id univoci."""
        ids = [it.id for it in sample_stage.items]
        assert len(ids) == len(set(ids))

    def test_remove_from_sample(self, sample_stage):
        """Rimozione da stage popolato."""
        initial_len = len(sample_stage.items)
        sample_stage.remove_item(1)
        assert len(sample_stage.items) == initial_len - 1
        assert sample_stage.get_item(1) is None
