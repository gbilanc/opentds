"""
Test per shooting positions: modello, validazione, serializzazione.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.models import Stage, ShootingPosition, StageItem, ItemType
from core.ipsc_rules import IPSCRulesEngine
from services.serializer import save_stage, load_stage, stage_to_dict, dict_to_stage


class TestShootingPositionModel:
    """Verifica modello ShootingPosition."""

    def test_default_values(self):
        sp = ShootingPosition(id=1)
        assert sp.x == 0.0
        assert sp.y == 0.0
        assert sp.label == ""
        assert sp.is_start is False
        assert sp.angle == 0.0

    def test_start_position(self):
        sp = ShootingPosition(id=1, x=5.0, y=3.0, label="Start", is_start=True)
        assert sp.x == 5.0
        assert sp.is_start is True


class TestShootingPositionsInStage:
    """Verifica integrazione ShootingPosition in Stage."""

    def test_stage_with_positions(self, empty_stage):
        sp = ShootingPosition(id=1, x=5.0, y=3.0, label="Start", is_start=True)
        empty_stage.shooting_positions.append(sp)
        assert len(empty_stage.shooting_positions) == 1

    def test_position_separate_from_items(self, empty_stage):
        """Le shooting positions sono separate dagli items."""
        empty_stage.shooting_positions.append(
            ShootingPosition(id=1, x=3.0, y=3.0, is_start=True))
        empty_stage.add_item(StageItem(0, ItemType.WALL, 5.0, 5.0, 2.0, 0.2))
        assert len(empty_stage.shooting_positions) == 1
        assert len(empty_stage.items) == 1


class TestShootingPositionValidation:
    """Verifica validazione shooting positions."""

    def test_valid_position_passes(self, empty_stage):
        empty_stage.shooting_positions.append(
            ShootingPosition(id=1, x=5.0, y=3.0, label="Start", is_start=True))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_shooting_positions()
        assert len(v) == 0

    def test_position_outside_boundary(self, empty_stage):
        empty_stage.shooting_positions.append(
            ShootingPosition(id=1, x=25.0, y=30.0, label="Fuori"))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_shooting_positions()
        assert any("fuori" in x.lower() for x in v)

    def test_position_inside_wall(self, empty_stage):
        empty_stage.add_item(StageItem(0, ItemType.WALL, 5.0, 5.0, 3.0, 0.2))
        empty_stage.shooting_positions.append(
            ShootingPosition(id=1, x=5.0, y=5.0, label="Dentro muro"))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_shooting_positions()
        assert any("dentro" in x.lower() for x in v)

    def test_missing_start_flag(self, empty_stage):
        empty_stage.shooting_positions.append(
            ShootingPosition(id=1, x=5.0, y=3.0, label="Posizione"))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_shooting_positions()
        assert any("partenza" in x.lower() for x in v)


class TestShootingPositionSerializer:
    """Verifica round-trip JSON delle shooting positions."""

    def test_round_trip_preserves_positions(self, empty_stage):
        empty_stage.shooting_positions.append(
            ShootingPosition(id=1, x=3.0, y=2.0, label="Start",
                             is_start=True, angle=90.0))
        empty_stage.shooting_positions.append(
            ShootingPosition(id=2, x=8.0, y=6.0, label="Posizione 2",
                             is_start=False, angle=45.0,
                             properties={"cover": "barrier"}))

        data = stage_to_dict(empty_stage)
        assert data["version"] == 2
        assert len(data["shooting_positions"]) == 2
        assert data["shooting_positions"][0]["is_start"] is True
        assert data["shooting_positions"][1]["properties"]["cover"] == "barrier"

        stage2 = dict_to_stage(data)
        assert len(stage2.shooting_positions) == 2
        assert stage2.shooting_positions[0].is_start is True
        assert stage2.shooting_positions[0].label == "Start"
        assert stage2.shooting_positions[1].properties["cover"] == "barrier"

    def test_round_trip_file(self, empty_stage):
        empty_stage.shooting_positions.append(
            ShootingPosition(id=1, x=5.0, y=3.0, label="Start", is_start=True))

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp_path = Path(f.name)
        try:
            save_stage(empty_stage, tmp_path)
            loaded = load_stage(tmp_path)
            assert len(loaded.shooting_positions) == 1
            assert loaded.shooting_positions[0].is_start is True
            assert loaded.shooting_positions[0].x == 5.0
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_backward_compat_no_positions(self):
        """JSON v1 senza shooting_positions non causa errori."""
        data = {"version": 1, "name": "Test", "width": 20.0, "depth": 15.0, "items": []}
        stage = dict_to_stage(data)
        assert len(stage.shooting_positions) == 0
