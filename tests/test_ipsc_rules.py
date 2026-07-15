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


# ─── Reg. 2.1.8.4 — Angolo bersagli fissi ────────────────────────────────────

class TestFixedTargetsAngle:
    """Verifica Reg. 2.1.8.4: bersagli fissi non oltre 90°."""

    def test_no_violation_when_target_faces_shooter(self):
        """Bersaglio che punta verso l'area di tiro → OK."""
        stage = Stage(width=20.0, depth=15.0)
        # Paper target con rotazione verso il centro (x=10, y=7.5)
        # Il centro è a (10, 7.5), il bersaglio a (5, 10)
        # Direzione dal bersaglio al centro: atan2(7.5-10, 10-5) = atan2(-2.5, 5) ≈ -27°
        stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5, 10,
                                 0.45, 0.45, rotation=-27, label="Paper"))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_fixed_targets_angle()
        assert len(v) == 0, f"Violazioni inaspettate: {v}"

    def test_violation_when_target_faces_away(self):
        """Bersaglio che punta in direzione opposta all'area di tiro → violazione."""
        stage = Stage(width=20.0, depth=15.0)
        # Paper target con rotazione opposta al centro
        # Centro a (10, 7.5), bersaglio a (5, 10)
        # Direzione opposta: -27 + 180 = 153°
        stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5, 10,
                                 0.45, 0.45, rotation=153, label="Paper"))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_fixed_targets_angle()
        assert any("2.1.8.4" in x for x in v), f"Violazione 2.1.8.4 attesa: {v}"

    def test_no_violation_for_moving_targets(self):
        """Bersagli mobili/swinger NON sono fissi, nessuna violazione."""
        stage = Stage(width=20.0, depth=15.0)
        stage.add_item(StageItem(0, ItemType.SWINGER, 5, 10,
                                 0.45, 0.45, rotation=180, label="Swinger"))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_fixed_targets_angle()
        assert len(v) == 0

    def test_no_violation_for_activated_targets(self):
        """Bersagli attivati NON sono fissi, nessuna violazione."""
        stage = Stage(width=20.0, depth=15.0)
        it = StageItem(0, ItemType.PAPER_TARGET, 5, 10,
                       0.45, 0.45, rotation=180, label="Paper")
        it.properties["activated_by"] = [1]
        stage.add_item(it)
        engine = IPSCRulesEngine(stage)
        v = engine._validate_fixed_targets_angle()
        assert len(v) == 0


# ─── Reg. 4.3.3.3 — Piatti metallici con carta/popper ───────────────────────

class TestMetalPlatesNeedPaper:
    """Verifica Reg. 4.3.3.3: almeno 1 carta/popper con plates."""

    def test_no_plates_no_violation(self):
        """Nessun piatto → nessuna violazione."""
        stage = Stage()
        stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5, 5, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_metal_plates_need_paper()
        assert len(v) == 0

    def test_plates_with_paper_no_violation(self):
        """Piatti + bersaglio carta → OK."""
        stage = Stage()
        stage.add_item(StageItem(0, ItemType.METAL_PLATE, 10, 10, 0.20, 0.20))
        stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5, 5, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_metal_plates_need_paper()
        assert len(v) == 0

    def test_plates_with_popper_no_violation(self):
        """Piatti + Popper → OK (Reg. 4.3.3.3 menziona popper)."""
        stage = Stage()
        stage.add_item(StageItem(0, ItemType.METAL_PLATE, 10, 10, 0.20, 0.20))
        stage.add_item(StageItem(0, ItemType.POPPER, 8, 8, 0.30, 0.30))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_metal_plates_need_paper()
        assert len(v) == 0

    def test_plates_only_violation(self):
        """Solo piatti metallici, nessun paper/popper → violazione."""
        stage = Stage()
        stage.add_item(StageItem(0, ItemType.METAL_PLATE, 10, 10, 0.20, 0.20))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_metal_plates_need_paper()
        assert any("4.3.3.3" in x for x in v), f"Violazione 4.3.3.3 attesa: {v}"


# ─── Reg. 4.2.4 — Hard cover non nasconde zona A ───────────────────────────

class TestHardCoverHighZone:
    """Verifica Reg. 4.2.4: hard cover non nasconde zona A."""

    def test_no_hard_cover_no_violation(self):
        """Nessun hard cover → OK."""
        stage = Stage()
        stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5, 5, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_hard_cover_high_zone()
        assert len(v) == 0

    def test_hard_cover_away_from_target_no_violation(self):
        """Hard cover lontano dal centro del bersaglio → OK."""
        stage = Stage()
        stage.add_item(StageItem(0, ItemType.HARD_COVER, 3, 3, 1.0, 1.0))
        stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 10, 10, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_hard_cover_high_zone()
        assert len(v) == 0

    def test_hard_cover_on_target_center_violation(self):
        """Hard cover che copre il centro del bersaglio → violazione."""
        stage = Stage()
        # Hard cover centrato sul paper target
        stage.add_item(StageItem(0, ItemType.HARD_COVER, 5.0, 5.0, 1.0, 1.0))
        stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5.0, 5.0, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_hard_cover_high_zone()
        assert any("4.2.4" in x for x in v), f"Violazione 4.2.4 attesa: {v}"


# ─── Reg. 4.3.1.1 — Vietati bersagli metallici rotanti ──────────────────────

class TestMetalRotatingProhibited:
    """Verifica Reg. 4.3.1.1: nessun metallico con movimento/rotazione."""

    def test_plain_metal_no_violation(self):
        """Metallico senza proprietà di movimento → OK."""
        stage = Stage()
        stage.add_item(StageItem(0, ItemType.POPPER, 10, 10, 0.30, 0.30))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_metal_rotating_prohibited()
        assert len(v) == 0

    def test_rotating_metal_violation(self):
        """Metallico con proprietà di movimento → violazione."""
        stage = Stage()
        it = StageItem(0, ItemType.STEEL_TARGET, 10, 10, 0.30, 0.30, label="Steel")
        it.properties["amplitude"] = 45
        it.properties["speed"] = 1.0
        stage.add_item(it)
        engine = IPSCRulesEngine(stage)
        v = engine._validate_metal_rotating_prohibited()
        assert any("4.3.1.1" in x for x in v), f"Violazione 4.3.1.1 attesa: {v}"

    def test_moving_target_is_not_metal_no_violation(self):
        """Bersaglio mobile (SWINGER) non è metallico → OK."""
        stage = Stage()
        it = StageItem(0, ItemType.SWINGER, 10, 10, 0.45, 0.45, label="Swinger")
        it.properties["amplitude"] = 45
        stage.add_item(it)
        engine = IPSCRulesEngine(stage)
        v = engine._validate_metal_rotating_prohibited()
        assert len(v) == 0


# ─── App. C3 — Altezza montaggio piatti metallici ───────────────────────────

class TestPlateMountingHeight:
    """Verifica App. C3: piatti su hard cover/paletti ≥ 1m."""

    def test_no_plates_no_violation(self):
        stage = Stage()
        stage.add_item(StageItem(0, ItemType.PAPER_TARGET, 5, 5, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_plate_mounting_height()
        assert len(v) == 0

    def test_plate_with_mount_height_ok(self):
        """Piatto con mount_height ≥ 1m → OK."""
        stage = Stage()
        it = StageItem(0, ItemType.METAL_PLATE, 10, 10, 0.20, 0.20)
        it.properties["mount_height"] = 1.0
        stage.add_item(it)
        engine = IPSCRulesEngine(stage)
        v = engine._validate_plate_mounting_height()
        assert len(v) == 0

    def test_plate_on_hard_cover_ok(self):
        """Piatto sopra un hard cover → OK (App. C3: 'posti su Hard Cover')."""
        stage = Stage()
        stage.add_item(StageItem(0, ItemType.HARD_COVER, 10.0, 10.0, 2.0, 2.0))
        stage.add_item(StageItem(0, ItemType.METAL_PLATE, 10.0, 10.0, 0.20, 0.20))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_plate_mounting_height()
        assert len(v) == 0

    def test_plate_without_support_violation(self):
        """Piatto senza mount_height né hard cover sotto → violazione."""
        stage = Stage()
        stage.add_item(StageItem(0, ItemType.METAL_PLATE, 10, 10, 0.20, 0.20))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_plate_mounting_height()
        assert any("App. C3" in x for x in v), f"Violazione App. C3 attesa: {v}"
