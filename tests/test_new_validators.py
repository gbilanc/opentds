"""
Test per nuovi validatori IPSC aggiunti nel refactoring.

Copre:
- _validate_same_line_of_fire()
- _validate_steel_distance()
- _validate_max_hits_per_position()
- _validate_safety_angles()
- _validate_course_type()
"""
from __future__ import annotations

import pytest

from core.models import Stage, StageItem, ItemType, CourseType
from core.ipsc_rules import IPSCRulesEngine


class TestValidateSameLineOfFire:
    """Verifica che due bersagli non siano sulla stessa linea di tiro."""

    def test_no_violation_with_separate_targets(self):
        """Due bersagli a diverso angolo dal centro."""
        stage = Stage(width=20.0, depth=15.0)
        stage.add_item(StageItem(1, ItemType.PAPER_TARGET, 5, 10, 0.45, 0.45))
        stage.add_item(StageItem(2, ItemType.PAPER_TARGET, 15, 10, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_same_line_of_fire()
        assert len(v) == 0, f"Violazioni inaspettate: {v}"

    def test_violation_with_aligned_targets(self):
        """Due bersagli allineati dal centro (stesso angolo)."""
        stage = Stage(width=20.0, depth=15.0)
        # Entrambi lungo la stessa direzione dal centro (10, 4.5)
        stage.add_item(StageItem(1, ItemType.PAPER_TARGET, 10, 8, 0.45, 0.45))
        stage.add_item(StageItem(2, ItemType.PAPER_TARGET, 10, 12, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_same_line_of_fire()
        assert len(v) > 0, "Violazione attesa per bersagli allineati"

    def test_paper_and_steel_aligned_violation(self):
        """Paper e steel allineati → violazione."""
        stage = Stage(width=20.0, depth=15.0)
        stage.add_item(StageItem(1, ItemType.PAPER_TARGET, 10, 8, 0.45, 0.45))
        stage.add_item(StageItem(2, ItemType.POPPER, 10, 12, 0.30, 0.30))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_same_line_of_fire()
        assert len(v) > 0, "Violazione attesa per paper+steel allineati"

    def test_single_target_no_violation(self):
        """Un solo bersaglio → nessuna violazione."""
        stage = Stage(width=20.0, depth=15.0)
        stage.add_item(StageItem(1, ItemType.PAPER_TARGET, 10, 10, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_same_line_of_fire()
        assert len(v) == 0


class TestValidateSteelDistance:
    """Verifica distanza minima 7m tiratore-bersaglio metallico (Reg. 2.1.3)."""

    def test_steel_far_enough(self):
        """Bersaglio metallico a >7m dalla posizione di tiro."""
        stage = Stage(width=20.0, depth=15.0)
        stage.add_item(StageItem(1, ItemType.STEEL_TARGET, 10, 12, 0.30, 0.30))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_steel_distance()
        # Nessuna shooting position definita, usa fallback centro → distanza
        # deve essere sufficiente
        assert len(v) == 0 or "distanza" not in v[0].lower(), f"Violazione inaspettata: {v}"

    def test_no_steel_no_violation(self):
        """Nessun bersaglio metallico → OK."""
        stage = Stage(width=20.0, depth=15.0)
        stage.add_item(StageItem(1, ItemType.PAPER_TARGET, 10, 10, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_steel_distance()
        assert len(v) == 0


class TestValidateMaxHitsPerPosition:
    """Verifica max 9 colpi per posizione (Reg. 1.2.1)."""

    def test_few_targets_no_violation(self):
        """Pochi bersagli → max 9 colpi non superato."""
        stage = Stage(width=20.0, depth=15.0)
        for i in range(3):
            stage.add_item(StageItem(i + 1, ItemType.PAPER_TARGET, 5 + i * 2, 10, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_max_hits_per_position()
        assert len(v) == 0, f"Violazioni inaspettate: {v}"

    def test_many_targets_violation(self):
        """Molti bersagli → possibile violazione max 9 colpi."""
        stage = Stage(width=30.0, depth=20.0)
        # 5 paper = 10 colpi, supera 9
        for i in range(5):
            stage.add_item(StageItem(i + 1, ItemType.PAPER_TARGET, 5 + i * 3, 15, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_max_hits_per_position()
        # Con 5 paper visibili = 10 colpi, deve violare
        # Ma dipende dalla visibilità: se muri bloccano, potrebbe non violare
        # Test relativo: se non ci sono muri, ci sarà violazione
        if not any(it.item_type in (ItemType.WALL, ItemType.BARRIER) for it in stage.items):
            hits_violations = [x for x in v if "colpi" in x.lower()]
            assert len(hits_violations) > 0, f"Violazione max 9 colpi attesa: {v}"

    def test_no_targets_no_violation(self):
        """Nessun bersaglio → OK."""
        stage = Stage(width=20.0, depth=15.0)
        engine = IPSCRulesEngine(stage)
        v = engine._validate_max_hits_per_position()
        assert len(v) == 0


class TestValidateSafetyAngles:
    """Verifica angoli di sicurezza 90° (Reg. 2.1.2)."""

    def test_default_no_violation(self):
        """Stage vuoto → nessuna violazione."""
        stage = Stage(width=20.0, depth=15.0)
        engine = IPSCRulesEngine(stage)
        v = engine._validate_safety_angles()
        assert len(v) == 0

    def test_target_within_safety_angle(self):
        """Bersaglio entro 90° dalla direzione frontale."""
        stage = Stage(width=20.0, depth=15.0)
        stage.add_item(StageItem(1, ItemType.PAPER_TARGET, 10, 12, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_safety_angles()
        assert len(v) == 0, f"Violazioni inaspettate: {v}"


class TestValidateCourseType:
    """Verifica limite colpi per Short/Medium/Long (Reg. 1.2.1)."""

    def test_short_with_few_targets(self):
        """Short course con pochi bersagli → OK."""
        stage = Stage(width=20.0, depth=15.0, course_type=CourseType.SHORT)
        for i in range(4):
            stage.add_item(StageItem(i + 1, ItemType.PAPER_TARGET, 5 + i * 2, 10, 0.45, 0.45))
        # 4 paper = 8 colpi ≤ 12
        engine = IPSCRulesEngine(stage)
        v = engine._validate_course_type()
        assert len(v) == 0, f"Violazioni inaspettate: {v}"

    def test_short_with_too_many_targets(self):
        """Short course con troppi bersagli → violazione."""
        stage = Stage(width=20.0, depth=15.0, course_type=CourseType.SHORT)
        for i in range(8):
            stage.add_item(StageItem(i + 1, ItemType.PAPER_TARGET, 5 + i * 1.5, 10, 0.45, 0.45))
        # 8 paper = 16 colpi > 12
        engine = IPSCRulesEngine(stage)
        v = engine._validate_course_type()
        colpi_violations = [x for x in v if "colpi" in x.lower()]
        assert len(colpi_violations) > 0, f"Violazione colpi attesa: {v}"

    def test_no_course_type_no_validation(self):
        """Nessun course_type dichiarato → nessuna validazione."""
        stage = Stage(width=20.0, depth=15.0)
        for i in range(10):
            stage.add_item(StageItem(i + 1, ItemType.PAPER_TARGET, 5 + i, 10, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_course_type()
        assert len(v) == 0
