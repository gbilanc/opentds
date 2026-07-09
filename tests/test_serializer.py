"""
Test unitari per services/serializer.py — round-trip JSON.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from core.models import Stage, StageItem, ItemType
from services.serializer import stage_to_dict, dict_to_stage, save_stage, load_stage


# ─── stage_to_dict ───────────────────────────────────────────────────────────

class TestStageToDict:
    """Conversione Stage → dizionario."""

    def test_empty_stage_to_dict(self, empty_stage):
        """Stage vuoto produce dizionario minimale."""
        data = stage_to_dict(empty_stage)
        assert data["version"] == 2
        assert data["name"] == "Test Stage"
        assert data["width"] == 20.0
        assert data["depth"] == 15.0
        assert data["items"] == []

    def test_stage_with_items_to_dict(self, sample_stage):
        """Stage con item produce lista items completa."""
        data = stage_to_dict(sample_stage)
        assert len(data["items"]) == 7
        first = data["items"][0]
        assert "id" in first
        assert "type" in first
        assert "x" in first
        assert "y" in first
        assert "width" in first
        assert "height" in first
        assert "rotation" in first
        assert "color" in first
        assert "label" in first
        assert "properties" in first

    def test_dict_contains_item_types(self, sample_stage):
        """I tipi di item sono salvati come stringhe (nome enum)."""
        data = stage_to_dict(sample_stage)
        types = {it["type"] for it in data["items"]}
        assert "WALL" in types
        assert "PAPER_TARGET" in types
        assert "STEEL_TARGET" in types
        assert "FAULT_LINE" in types
        assert "NO_SHOOT" in types
        assert "BARRIER" in types
        assert "DOOR" in types

    def test_dict_serializes_moving_properties(self, empty_stage):
        """Proprietà di bersagli mobili sono preservate."""
        swinger = StageItem(0, ItemType.SWINGER, 10.0, 10.0, 0.45, 0.45,
                            properties={"amplitude": 45, "speed": 1.0, "axis": "y"})
        empty_stage.add_item(swinger)
        data = stage_to_dict(empty_stage)
        assert data["items"][0]["type"] == "SWINGER"
        assert data["items"][0]["properties"]["amplitude"] == 45.0
        assert data["items"][0]["properties"]["speed"] == 1.0
        assert data["items"][0]["properties"]["axis"] == "y"

    def test_dict_is_json_serializable(self, empty_stage):
        """Il dizionario è serializzabile in JSON senza errori."""
        empty_stage.add_item(StageItem(0, ItemType.MOVER, 5.0, 5.0,
                                        properties={"distance": 3.0, "speed": 1.5}))
        data = stage_to_dict(empty_stage)
        json_str = json.dumps(data, indent=2)
        assert isinstance(json_str, str)
        # Re-load
        parsed = json.loads(json_str)
        assert parsed["items"][0]["properties"]["distance"] == 3.0


# ─── dict_to_stage ───────────────────────────────────────────────────────────

class TestDictToStage:
    """Conversione dizionario → Stage."""

    def test_dict_to_empty_stage(self):
        """Dizionario vuoto produce stage con default."""
        data = {"name": "Empty", "width": 10.0, "depth": 10.0, "items": []}
        stage = dict_to_stage(data)
        assert stage.name == "Empty"
        assert stage.width == 10.0
        assert stage.depth == 10.0
        assert stage.items == []

    def test_dict_to_stage_with_items(self):
        """Dizionario con item produce stage popolato."""
        data = {
            "name": "Test",
            "width": 20.0,
            "depth": 15.0,
            "items": [
                {"id": 1, "type": "WALL", "x": 5.0, "y": 5.0, "width": 3.0,
                 "height": 0.2, "rotation": 0.0, "color": "#475569",
                 "label": "Muro", "properties": {}},
                {"id": 2, "type": "PAPER_TARGET", "x": 10.0, "y": 10.0,
                 "width": 0.45, "height": 0.45, "rotation": 15.0,
                 "color": "#ef4444", "label": "Paper", "properties": {}},
            ]
        }
        stage = dict_to_stage(data)
        assert len(stage.items) == 2
        assert stage.items[0].item_type == ItemType.WALL
        assert stage.items[0].x == 5.0
        assert stage.items[1].item_type == ItemType.PAPER_TARGET
        assert stage.items[1].rotation == 15.0

    def test_dict_to_stage_with_moving_items(self):
        """Item mobili con properties sono ricostruiti correttamente."""
        data = {
            "name": "Moving",
            "width": 20.0,
            "depth": 15.0,
            "items": [
                {"id": 1, "type": "SWINGER", "x": 5.0, "y": 5.0, "width": 0.45,
                 "height": 0.45, "rotation": 0.0, "color": "#a855f7",
                 "label": "Swinger", "properties": {"amplitude": 60, "speed": 1.5}},
            ]
        }
        stage = dict_to_stage(data)
        assert stage.items[0].item_type == ItemType.SWINGER
        assert stage.items[0].properties["amplitude"] == 60
        assert stage.items[0].properties["speed"] == 1.5

    def test_next_id_from_max(self):
        """_next_id parte dal max id + 1."""
        data = {
            "name": "Test",
            "width": 20.0,
            "depth": 15.0,
            "items": [
                {"id": 10, "type": "WALL", "x": 1.0, "y": 1.0, "width": 2.0,
                 "height": 0.2, "rotation": 0.0, "color": "#475569",
                 "label": "", "properties": {}},
            ]
        }
        stage = dict_to_stage(data)
        assert stage._next_id == 11


# ─── Round-trip ──────────────────────────────────────────────────────────────

class TestRoundTrip:
    """Test di round-trip: Stage → dict → Stage deve conservare tutto."""

    def test_round_trip_preserves_items(self, sample_stage):
        """Tutti gli item sopravvivono a round-trip."""
        data = stage_to_dict(sample_stage)
        stage2 = dict_to_stage(data)
        assert len(stage2.items) == len(sample_stage.items)
        for original, restored in zip(sample_stage.items, stage2.items):
            assert original.id == restored.id
            assert original.item_type == restored.item_type
            assert original.x == restored.x
            assert original.y == restored.y
            assert original.width == restored.width
            assert original.height == restored.height
            assert original.rotation == restored.rotation
            assert original.color == restored.color
            assert original.label == restored.label
            assert original.properties == restored.properties

    def test_round_trip_preserves_stage_metadata(self, sample_stage):
        """Metadati dello stage (nome, dimensioni) sono preservati."""
        data = stage_to_dict(sample_stage)
        stage2 = dict_to_stage(data)
        assert stage2.name == sample_stage.name
        assert stage2.width == sample_stage.width
        assert stage2.depth == sample_stage.depth

    def test_round_trip_with_moving_targets(self, empty_stage):
        """Proprietà bersagli mobili sopravvivono a round-trip."""
        empty_stage.add_item(StageItem(0, ItemType.SWINGER, 5.0, 5.0, 0.45, 0.45,
                                        properties={"amplitude": 45, "speed": 2.0}))
        empty_stage.add_item(StageItem(0, ItemType.MOVER, 10.0, 10.0, 0.45, 0.45,
                                        properties={"distance": 5.0, "speed": 1.0}))
        empty_stage.add_item(StageItem(0, ItemType.DROP_TURNER, 15.0, 5.0, 0.45, 0.45,
                                        properties={"trigger": "hit", "fall_time": 0.8}))
        data = stage_to_dict(empty_stage)
        stage2 = dict_to_stage(data)
        assert len(stage2.items) == 3
        assert stage2.items[0].properties["amplitude"] == 45
        assert stage2.items[0].properties["speed"] == 2.0
        assert stage2.items[1].properties["distance"] == 5.0
        assert stage2.items[2].properties["fall_time"] == 0.8

    def test_round_trip_new_ids_are_unique(self, sample_stage):
        """Dopo round-trip, nuovi item hanno id univoci (next_id corretto)."""
        data = stage_to_dict(sample_stage)
        stage2 = dict_to_stage(data)
        new_item = stage2.add_item(StageItem(0, ItemType.WALL, 1.0, 1.0, 2.0, 0.2))
        assert new_item.id not in {it.id for it in sample_stage.items}

    def test_round_trip_json_file(self, sample_stage):
        """Salvataggio e caricamento da file JSON preserva i dati."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp_path = Path(f.name)
        try:
            save_stage(sample_stage, tmp_path)
            loaded = load_stage(tmp_path)
            assert loaded.name == sample_stage.name
            assert len(loaded.items) == len(sample_stage.items)
            for orig, loaded_it in zip(sample_stage.items, loaded.items):
                assert orig.x == loaded_it.x
                assert orig.y == loaded_it.y
                assert orig.item_type == loaded_it.item_type
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_json_file_is_valid_json(self, sample_stage):
        """Il file salvato è JSON valido."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp_path = Path(f.name)
        try:
            save_stage(sample_stage, tmp_path)
            with open(tmp_path, encoding="utf-8") as f:
                parsed = json.load(f)
            assert parsed["version"] == 2
            assert len(parsed["items"]) == 7
        finally:
            tmp_path.unlink(missing_ok=True)


# ─── Casi limite ─────────────────────────────────────────────────────────────

class TestSerializerEdgeCases:
    """Casi limite per la serializzazione."""

    def test_unknown_type_raises_key_error(self):
        """Tipo sconosciuto solleva KeyError."""
        data = {
            "name": "Bad", "width": 20.0, "depth": 15.0,
            "items": [{"id": 1, "type": "UNKNOWN_TYPE", "x": 0, "y": 0,
                        "width": 1, "height": 1, "rotation": 0,
                        "color": "#000", "label": "", "properties": {}}]
        }
        with pytest.raises(KeyError):
            dict_to_stage(data)

    def test_missing_fields_use_defaults(self):
        """Campi mancanti nel JSON usano valori di default."""
        data = {
            "name": "Minimal",
            "width": 20.0,
            "depth": 15.0,
            "items": [
                {"id": 1, "type": "WALL"}  # Solo campi obbligatori
            ]
        }
        stage = dict_to_stage(data)
        assert stage.items[0].x == 0.0
        assert stage.items[0].y == 0.0
        assert stage.items[0].width == 1.0
        assert stage.items[0].height == 2.0
        assert stage.items[0].rotation == 0.0
        assert stage.items[0].color == "#808080"
        assert stage.items[0].label == ""

    def test_empty_items_list(self):
        """Lista items vuota non causa errori."""
        data = {"name": "Empty", "width": 10.0, "depth": 10.0, "items": []}
        stage = dict_to_stage(data)
        assert len(stage.items) == 0
