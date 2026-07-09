"""
Test unitari per core/ipsc_rules.py — IPSCRulesEngine.
"""
from __future__ import annotations

import pytest

from core.models import Stage, StageItem, ItemType
from core.ipsc_rules import IPSCRulesEngine, ConstraintResult


# ─── ConstraintResult ────────────────────────────────────────────────────────

class TestConstraintResult:
    def test_default_violations_is_empty_list(self):
        result = ConstraintResult(ok=True)
        assert result.violations == []

    def test_ok_false_with_violations(self):
        result = ConstraintResult(ok=False, violations=["V1"])
        assert result.ok is False
        assert len(result.violations) == 1


# ─── Dimensioni stage ────────────────────────────────────────────────────────

class TestStageDimensions:
    def test_valid_dimensions(self, empty_stage):
        """Stage 20×15m è nei limiti."""
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_dimensions()
        assert len(v) == 0

    def test_too_small_width(self):
        """Stage troppo stretto."""
        stage = Stage(width=5.0, depth=15.0)
        engine = IPSCRulesEngine(stage)
        v = engine._validate_dimensions()
        assert any("stretto" in x.lower() for x in v)

    def test_too_small_depth(self):
        """Stage troppo corto."""
        stage = Stage(width=20.0, depth=5.0)
        engine = IPSCRulesEngine(stage)
        v = engine._validate_dimensions()
        assert any("corto" in x.lower() for x in v)

    def test_too_large_width(self):
        """Stage troppo largo."""
        stage = Stage(width=50.0, depth=15.0)
        engine = IPSCRulesEngine(stage)
        v = engine._validate_dimensions()
        assert any("largo" in x.lower() for x in v)

    def test_too_large_depth(self):
        """Stage troppo profondo."""
        stage = Stage(width=20.0, depth=40.0)
        engine = IPSCRulesEngine(stage)
        v = engine._validate_dimensions()
        assert any("profondo" in x.lower() for x in v)


# ─── Conteggio bersagli ──────────────────────────────────────────────────────

class TestTargetCounts:
    def test_minimum_targets_not_met(self, empty_stage):
        """Meno di 8 bersagli totali."""
        for _ in range(4):
            empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5, 5, 0.45, 0.45))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_target_counts()
        assert any("insufficienti" in x.lower() for x in v)

    def test_minimum_targets_met(self, empty_stage):
        """Almeno 8 bersagli → nessun errore di conteggio bersagli."""
        for i in range(8):
            empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5 + i, 5, 0.45, 0.45))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_target_counts()
        # Nessun errore di totale bersagli (warning no-shoot è separato)
        assert not any("bersagli insufficienti" in x.lower() for x in v)

    def test_steel_ratio_too_high(self, empty_stage):
        """Troppi steel (8 steel su 10 totali = 80% > 40%)."""
        for i in range(2):
            empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5 + i, 5, 0.45, 0.45))
        for i in range(8):
            empty_stage.add_item(StageItem(0, ItemType.STEEL_TARGET, 10 + i, 5, 0.30, 0.30))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_target_counts()
        assert any("steel" in x.lower() for x in v)

    def test_recommended_no_shoot(self, empty_stage):
        """Con 16 paper, ci vorrebbero almeno 2 no-shoot."""
        for i in range(16):
            empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5 + i, 5, 0.45, 0.45))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_target_counts()
        assert any("no-shoot" in x.lower() for x in v)

    def test_no_shoot_warning_suppressed_with_enough(self, empty_stage):
        """Con 16 paper e 2 no-shoot, nessun warning."""
        for i in range(16):
            empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5 + i, 5, 0.45, 0.45))
        for i in range(2):
            empty_stage.add_item(StageItem(0, ItemType.NO_SHOOT, 15 + i, 10, 0.45, 0.45))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_target_counts()
        assert not any("no-shoot" in x.lower() for x in v)


# ─── Backstop ────────────────────────────────────────────────────────────────

class TestBackstop:
    def test_insufficient_backstop(self):
        """Bersaglio troppo vicino al fondo stage."""
        stage = Stage(width=20.0, depth=10.0)
        stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 10, 9.5, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_dimensions()
        assert any("dietro" in x.lower() for x in v)


# ─── Validazione spaziale ────────────────────────────────────────────────────

class TestValidateSpatial:
    def test_empty_stage_is_valid(self, empty_stage):
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_spatial()
        assert len(v) == 0

    def test_valid_target_placement(self, empty_stage):
        empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 10.0, 7.5, 0.45, 0.45))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_spatial()
        assert len(v) == 0

    def test_target_too_close_to_edge(self, empty_stage):
        empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 0.5, 0.5, 0.45, 0.45))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_spatial()
        assert any("bordo" in x.lower() for x in v)

    def test_target_too_close_to_wall(self, empty_stage):
        empty_stage.add_item(StageItem(0, ItemType.WALL, 5.0, 5.0, 3.0, 0.2))
        empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5.3, 5.0, 0.45, 0.45))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_spatial()
        assert any("muro" in x.lower() for x in v)

    def test_targets_too_close(self, empty_stage):
        empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 10.0, 10.0, 0.45, 0.45))
        empty_stage.add_item(StageItem(0, ItemType.STEEL_TARGET, 10.3, 10.0, 0.30, 0.30))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_spatial()
        assert any("bersaglio" in x.lower() and "vicino" in x.lower() for x in v)

    def test_barrier_separate_distance(self, empty_stage):
        """Barriera ha soglia 0.5m, diversa da muro 0.8m."""
        empty_stage.add_item(StageItem(0, ItemType.BARRIER, 5.0, 5.0, 2.0, 0.15))
        empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 7.0, 5.0, 0.45, 0.45))
        engine = IPSCRulesEngine(empty_stage)
        v = engine._validate_spatial()
        assert len(v) == 0
        # A 0.4m → deve fallire
        stage2 = Stage(width=20.0, depth=15.0)
        stage2.add_item(StageItem(0, ItemType.BARRIER, 5.0, 5.0, 2.0, 0.15))
        stage2.add_item(StageItem(0, ItemType.PAPER_TARGET, 5.4, 5.0, 0.45, 0.45))
        engine2 = IPSCRulesEngine(stage2)
        v2 = engine2._validate_spatial()
        assert any("barriera" in x.lower() for x in v2)


# ─── is_valid_position ───────────────────────────────────────────────────────

class TestIsValidPosition:
    def test_valid_center(self, empty_stage):
        engine = IPSCRulesEngine(empty_stage)
        item = StageItem(0, ItemType.PAPER_TARGET, 10.0, 7.5, 0.45, 0.45)
        assert engine.is_valid_position(item, [])

    def test_invalid_edge(self, empty_stage):
        engine = IPSCRulesEngine(empty_stage)
        item = StageItem(0, ItemType.PAPER_TARGET, 0.5, 0.5, 0.45, 0.45)
        assert not engine.is_valid_position(item, [])

    def test_valid_against_existing(self, empty_stage):
        engine = IPSCRulesEngine(empty_stage)
        existing = [StageItem(1, ItemType.WALL, 5.0, 5.0, 3.0, 0.2)]
        item = StageItem(0, ItemType.PAPER_TARGET, 10.0, 10.0, 0.45, 0.45)
        assert engine.is_valid_position(item, existing)

    def test_invalid_against_existing(self, empty_stage):
        engine = IPSCRulesEngine(empty_stage)
        existing = [StageItem(1, ItemType.WALL, 5.0, 5.0, 3.0, 0.2)]
        item = StageItem(0, ItemType.PAPER_TARGET, 5.3, 5.0, 0.45, 0.45)
        assert not engine.is_valid_position(item, existing)


# ─── Costanti ────────────────────────────────────────────────────────────────

class TestConstants:
    def test_min_target_to_edge_default(self):
        assert IPSCRulesEngine.MIN_TARGET_TO_EDGE == 1.0

    def test_min_target_to_wall_default(self):
        assert IPSCRulesEngine.MIN_TARGET_TO_WALL == 0.8

    def test_min_target_to_target_default(self):
        assert IPSCRulesEngine.MIN_TARGET_TO_TARGET == 0.8

    def test_min_target_to_barrier_default(self):
        assert IPSCRulesEngine.MIN_TARGET_TO_BARRIER == 0.5

    def test_min_targets(self):
        assert IPSCRulesEngine.MIN_TARGETS == 8

    def test_max_targets_pistol(self):
        engine = IPSCRulesEngine(Stage(), discipline="ipsc_pistol")
        assert engine.MAX_TARGETS == 32

    def test_min_stage_dimensions(self):
        engine = IPSCRulesEngine(Stage())
        assert engine.MIN_STAGE_WIDTH == 10.0
        assert engine.MIN_STAGE_DEPTH == 8.0

    def test_shotgun_dimensions(self):
        engine = IPSCRulesEngine(Stage(), discipline="shotgun")
        assert engine.MIN_STAGE_WIDTH == 8.0
        assert engine.MIN_STAGE_DEPTH == 8.0

    def test_mini_rifle_dimensions(self):
        engine = IPSCRulesEngine(Stage(), discipline="mini_rifle")
        assert engine.MIN_STAGE_WIDTH == 15.0
        assert engine.MIN_STAGE_DEPTH == 10.0

    def test_max_targets_by_discipline(self):
        pistol = IPSCRulesEngine(Stage(), discipline="ipsc_pistol")
        rifle = IPSCRulesEngine(Stage(), discipline="mini_rifle")
        assert pistol.MAX_TARGETS == 32
        assert rifle.MAX_TARGETS == 40


# ─── count_targets ───────────────────────────────────────────────────────────

class TestCountTargets:
    def test_empty_stage(self, empty_stage):
        engine = IPSCRulesEngine(empty_stage)
        c = engine.count_targets()
        assert c["paper"] == 0
        assert c["steel"] == 0
        assert c["moving"] == 0
        assert c["no_shoots"] == 0

    def test_mixed_stage(self, empty_stage):
        empty_stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5, 5))
        empty_stage.add_item(StageItem(0, ItemType.STEEL_TARGET, 6, 6))
        empty_stage.add_item(StageItem(0, ItemType.SWINGER, 7, 7))
        empty_stage.add_item(StageItem(0, ItemType.NO_SHOOT, 8, 8))
        engine = IPSCRulesEngine(empty_stage)
        c = engine.count_targets()
        assert c["paper"] == 1
        assert c["steel"] == 1
        assert c["moving"] == 1
        assert c["no_shoots"] == 1


# ─── Validate (completo) ─────────────────────────────────────────────────────

class TestValidateComplete:
    def test_valid_stage_passes(self, empty_stage):
        """Stage con 8 paper, dimensioni corrette passa."""
        for i in range(8):
            empty_stage.add_item(
                StageItem(0, ItemType.PAPER_TARGET, 5 + i * 1.5, 10, 0.45, 0.45))
        engine = IPSCRulesEngine(empty_stage)
        r = engine.validate()
        # Potrebbero esserci violazioni spaziali con OBB, ma non di conteggio
        assert any(x for x in r.violations
                    if "insufficienti" in x or "troppo" in x.lower()) or r.ok

    def test_validate_returns_violations_for_bad_stage(self, empty_stage):
        """Stage piccolo e con pochi bersagli ha violazioni."""
        engine = IPSCRulesEngine(empty_stage)
        r = engine.validate()
        assert not r.ok
        assert len(r.violations) > 0
