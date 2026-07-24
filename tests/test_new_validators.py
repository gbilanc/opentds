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

    @pytest.mark.parametrize("course_type,paper_count,expect_violation", [
        (CourseType.SHORT, 4, False),   # 4 paper = 8 colpi ≤ 12
        (CourseType.SHORT, 7, True),    # 7 paper = 14 colpi > 12
        (CourseType.MEDIUM, 8, False),  # 8 paper = 16 colpi ≤ 24
        (CourseType.MEDIUM, 15, True),  # 15 paper = 30 colpi > 24
        (CourseType.LONG, 14, False),   # 14 paper = 28 colpi ≤ 32
        (CourseType.LONG, 20, True),    # 20 paper = 40 colpi > 32
    ])
    def test_course_type_round_limits(self, course_type, paper_count, expect_violation):
        """Verifica limite colpi per ogni tipo corso."""
        stage = Stage(width=25.0, depth=20.0, course_type=course_type)
        for i in range(paper_count):
            stage.add_item(StageItem(i + 1, ItemType.PAPER_TARGET,
                                      5 + i * 1.5, 12, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_course_type()
        colpi_violations = [x for x in v if "colpi" in x.lower()]
        if expect_violation:
            assert len(colpi_violations) > 0, (
                f"Violazione attesa per {course_type.value} con {paper_count} paper")
        else:
            assert len(colpi_violations) == 0, (
                f"Violazione inaspettata per {course_type.value} con {paper_count} paper: {v}")

    @pytest.mark.parametrize("discipline", [
        "ipsc_pistol", "mini_rifle", "shotgun",
    ])
    def test_all_disciplines_accept_valid_stage(self, discipline):
        """Stage valido per ogni disciplina non dà violazioni catastrofiche."""
        stage = Stage(width=25.0, depth=20.0)
        for i in range(8):
            stage.add_item(StageItem(i + 1, ItemType.PAPER_TARGET,
                                      5 + i * 1.5, 12, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        engine.set_discipline(discipline)
        v = engine.validate()
        # Verifica che non ci siano violazioni di dimensioni minime
        dim_violations = [x for x in v.violations
                          if "stretto" in x.lower() or "corto" in x.lower()]
        # Per stage 25x20, tutte le discipline hanno dimensioni sufficienti
        assert len(dim_violations) == 0, (
            f"Violazioni dimensioni per {discipline}: {dim_violations}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Test per cono di ingaggio 180°
# ═══════════════════════════════════════════════════════════════════════════════


class TestEngagementConeSafetyAngles:
    """Verifica che i bersagli fuori dal cono 180° siano rilevati."""

    def test_target_in_front_within_cone(self):
        """Bersaglio davanti alla posizione (angolo 90°) → OK."""
        stage = Stage(width=20.0, depth=15.0)
        from core.models import ShootingPosition
        stage.shooting_positions.append(
            ShootingPosition(id=1, x=10.0, y=3.0, angle=90.0, is_start=True))
        # Bersaglio direttamente di fronte (y=12, stesso x)
        stage.add_item(StageItem(1, ItemType.PAPER_TARGET, 10.0, 12.0, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_safety_angles()
        assert len(v) == 0, f"Violazioni inaspettate: {v}"

    def test_target_behind_shooter_violation(self):
        """Bersaglio dietro al tiratore → violazione cono 180°."""
        stage = Stage(width=20.0, depth=15.0)
        from core.models import ShootingPosition
        # Tiratore a (10, 10) con direzione 90° (verso +Y, parapalle)
        stage.shooting_positions.append(
            ShootingPosition(id=1, x=10.0, y=10.0, angle=90.0, is_start=True))
        # Bersaglio dietro al tiratore (y=2, verso -Y)
        stage.add_item(StageItem(1, ItemType.PAPER_TARGET, 10.0, 2.0, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_safety_angles()
        assert len(v) > 0, "Violazione attesa: bersaglio dietro al tiratore"

    def test_target_90_degrees_left_within_cone(self):
        """Bersaglio esattamente a 90° a sinistra → al limite del cono."""
        stage = Stage(width=20.0, depth=15.0)
        from core.models import ShootingPosition
        # Tiratore a (10, 10) con direzione 90° (+Y)
        stage.shooting_positions.append(
            ShootingPosition(id=1, x=10.0, y=10.0, angle=90.0, is_start=True))
        # Bersaglio a sinistra: (-X rispetto al tiratore, stessa Y)
        stage.add_item(StageItem(1, ItemType.PAPER_TARGET, 0.5, 10.0, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_safety_angles()
        # 90° esatti + tolleranza 2° → ancora dentro il cono
        assert len(v) == 0, f"Bersaglio a 90° laterali dovrebbe essere accettato: {v}"

    def test_target_beyond_90_degrees_violation(self):
        """Bersaglio oltre 90° laterali → violazione."""
        stage = Stage(width=20.0, depth=15.0)
        from core.models import ShootingPosition
        stage.shooting_positions.append(
            ShootingPosition(id=1, x=10.0, y=10.0, angle=90.0, is_start=True))
        # Bersaglio molto a sinistra e leggermente dietro (angolo > 90°)
        stage.add_item(StageItem(1, ItemType.PAPER_TARGET, 0.5, 9.0, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_safety_angles()
        assert len(v) > 0, "Violazione attesa: bersaglio oltre 90° laterali"

    def test_multiple_positions_each_checked(self):
        """Ogni shooting position ha il proprio cono di ingaggio."""
        stage = Stage(width=20.0, depth=15.0)
        from core.models import ShootingPosition
        # Posizione 1: guarda verso +Y (90°), bersaglio davanti OK
        stage.shooting_positions.append(
            ShootingPosition(id=1, x=5.0, y=3.0, angle=90.0, is_start=True))
        # Posizione 2: guarda verso +Y (90°), ma il bersaglio è dietro
        stage.shooting_positions.append(
            ShootingPosition(id=2, x=15.0, y=10.0, angle=90.0))
        # Bersaglio a (5, 12): davanti per pos1 (stesso X=5, Y=12 > 3),
        # ma per pos2 (15,10) il bersaglio è a -X e +Y → angolo > 90°
        # Da pos2: dx=-10, dy=2. Forward=(0,1). cos = 2/sqrt(104) ≈ 0.196.
        # acos(0.196) ≈ 78.7° — ancora dentro il cono!
        # Mettiamolo a (0, 3): da pos2 (15,10) dx=-15, dy=-7, forward=(0,1).
        # cos = -7/sqrt(274) ≈ -0.423. acos ≈ 115° > 92° → violazione.
        stage.add_item(StageItem(1, ItemType.PAPER_TARGET, 0.0, 3.0, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_safety_angles()
        # Deve rilevare che dalla pos2 il bersaglio è fuori cono
        violations_pos2 = [x for x in v if "(15.0, 10.0)" in x]
        assert len(violations_pos2) > 0, (
            f"Violazione attesa dalla posizione 2: {v}")


class TestEngagementConeMaxHits:
    """Verifica che il conteggio colpi rispetti il cono 180°."""

    def test_targets_behind_not_counted(self):
        """Bersagli dietro al tiratore non contano per max 9 colpi."""
        stage = Stage(width=20.0, depth=15.0)
        from core.models import ShootingPosition
        stage.shooting_positions.append(
            ShootingPosition(id=1, x=10.0, y=10.0, angle=90.0, is_start=True))
        # 5 bersagli davanti (10 colpi) + 2 dietro (4 colpi ignorati)
        for i in range(5):
            stage.add_item(StageItem(i + 1, ItemType.PAPER_TARGET,
                                      5 + i * 2, 13.0, 0.45, 0.45))
        # Bersagli dietro: non dovrebbero contare
        stage.add_item(StageItem(6, ItemType.PAPER_TARGET, 5.0, 2.0, 0.45, 0.45))
        stage.add_item(StageItem(7, ItemType.PAPER_TARGET, 15.0, 2.0, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_max_hits_per_position()
        # 5 paper davanti = 10 colpi > 9 → violazione, ma non per i 2 dietro
        assert len(v) > 0, "Violazione attesa: 10 colpi davanti > 9"

    def test_few_targets_in_cone_no_violation(self):
        """Pochi bersagli nel cono frontale → nessuna violazione."""
        stage = Stage(width=20.0, depth=15.0)
        from core.models import ShootingPosition
        stage.shooting_positions.append(
            ShootingPosition(id=1, x=10.0, y=3.0, angle=90.0, is_start=True))
        # 3 bersagli davanti = 6 colpi
        for i in range(3):
            stage.add_item(StageItem(i + 1, ItemType.PAPER_TARGET,
                                      5 + i * 3, 12.0, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_max_hits_per_position()
        assert len(v) == 0, f"Violazioni inaspettate: {v}"


class TestEngagementConeCourseType:
    """Verifica cono 180° nella validazione course type."""

    def test_medium_course_all_targets_in_cone_triggers_violation(self):
        """Medium course: se tutti i bersagli sono ingaggiabili da una
        posizione (cono + visibilità) → violazione."""
        stage = Stage(width=20.0, depth=15.0, course_type=CourseType.MEDIUM)
        from core.models import ShootingPosition
        stage.shooting_positions.append(
            ShootingPosition(id=1, x=10.0, y=3.0, angle=90.0, is_start=True))
        # 4 bersagli tutti davanti, nessun muro → tutti ingaggiabili
        for i in range(4):
            stage.add_item(StageItem(i + 1, ItemType.PAPER_TARGET,
                                      5 + i * 3, 12.0, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_course_type()
        # 4 paper = 8 colpi ≤ 24 (ok), ma tutti visibili da 1 posizione
        all_visible_violations = [x for x in v if "tutti" in x.lower()]
        assert len(all_visible_violations) > 0, (
            f"Violazione attesa: tutti bersagli ingaggiabili da una posizione: {v}")

    def test_medium_course_targets_split_by_cone_no_violation(self):
        """Medium course: bersagli divisi tra cono e fuori cono → OK."""
        stage = Stage(width=20.0, depth=15.0, course_type=CourseType.MEDIUM)
        from core.models import ShootingPosition
        stage.shooting_positions.append(
            ShootingPosition(id=1, x=10.0, y=10.0, angle=90.0, is_start=True))
        # 3 davanti (nel cono) + 2 dietro (fuori cono)
        for i in range(3):
            stage.add_item(StageItem(i + 1, ItemType.PAPER_TARGET,
                                      5 + i * 3, 13.0, 0.45, 0.45))
        for i in range(2):
            stage.add_item(StageItem(i + 4, ItemType.PAPER_TARGET,
                                      5 + i * 5, 5.0, 0.45, 0.45))
        engine = IPSCRulesEngine(stage)
        v = engine._validate_course_type()
        # I bersagli dietro non sono ingaggiabili → non tutti da una posizione
        all_visible_violations = [x for x in v if "tutti" in x.lower()]
        assert len(all_visible_violations) == 0, (
            f"Nessuna violazione attesa: bersagli fuori cono non sono ingaggiabili: {v}")
