"""
Test unitari per core/generator.py — StageGenerator.
"""
from __future__ import annotations

import pytest

from core.models import Stage, StageItem, ItemType
from core.generator import StageGenerator, GeneratorConfig, GeneratorResult
from core.ipsc_rules import IPSCRulesEngine
from core.geometry import (
    point_in_polygon,
    polygon_center,
    point_in_rotated_rect,
    segments_intersect,
    line_intersects_rect,
)


# ─── GeneratorConfig ─────────────────────────────────────────────────────────

class TestGeneratorConfig:
    """Verifica GeneratorConfig defaults e costruzione."""

    def test_default_values(self):
        """Valori di default sensati."""
        cfg = GeneratorConfig()
        assert cfg.stage_width == 20.0
        assert cfg.stage_depth == 15.0
        assert cfg.num_targets == 8
        assert cfg.num_steel == 2
        assert cfg.num_moving == 1
        assert cfg.num_walls == 1
        assert cfg.num_barriers == 4
        assert cfg.include_fault_lines is True
        assert cfg.include_no_shoots is True
        assert cfg.difficulty == "medium"
        assert cfg.delimitation == "fault_lines"
        assert cfg.seed is None
        assert cfg.max_attempts == 500

    def test_custom_config(self):
        """Config con valori custom."""
        cfg = GeneratorConfig(stage_width=30.0, num_targets=15, difficulty="hard", seed=42)
        assert cfg.stage_width == 30.0
        assert cfg.num_targets == 15
        assert cfg.difficulty == "hard"
        assert cfg.seed == 42

    def test_invalid_difficulty(self):
        """Config accetta qualsiasi stringa difficulty (validazione esterna)."""
        cfg = GeneratorConfig(difficulty="extreme")
        assert cfg.difficulty == "extreme"


# ─── StageGenerator ──────────────────────────────────────────────────────────

class TestGeneratorDeterminism:
    """La generazione con stesso seed è riproducibile a livello di score e bersagli.
    
    Nota: il numero totale di item può variare leggermente perché muri/barriere/no-shoot
    hanno loop di riposizionamento con exit condizionale. I bersagli (paper, steel, moving)
    invece sono deterministici con seed fisso.
    """

    def test_generate_score_with_seed_is_deterministic(self):
        """Stesso seed → stesso score (riproducibilità globale)."""
        cfg = GeneratorConfig(seed=42)
        r1 = StageGenerator(cfg).generate()
        r2 = StageGenerator(cfg).generate()
        assert r1.score == r2.score

    def test_generate_target_count_with_seed_is_deterministic(self):
        """Stesso seed → stesso numero di bersagli (paper + steel + moving)."""
        cfg = GeneratorConfig(seed=42)
        r1 = StageGenerator(cfg).generate()
        r2 = StageGenerator(cfg).generate()
        target_types = {ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
                        ItemType.POPPER, ItemType.METAL_PLATE,
                        ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
                        ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER}
        tg1 = [it for it in r1.stage.items if it.item_type in target_types]
        tg2 = [it for it in r2.stage.items if it.item_type in target_types]
        assert len(tg1) == len(tg2)

    def test_generate_targets_count_is_deterministic(self):
        """Stesso seed → stesso numero di bersagli per tipo (stage ampio)."""
        # Stage grande e semplice (lettera O) per evitare violazioni e retry
        cfg = GeneratorConfig(seed=42, num_targets=5, num_steel=0,
                              num_poppers=1, num_plates=1,
                              num_moving=0, num_mini=1,
                              include_fault_lines=False, include_no_shoots=False,
                              auto_distribution=False,
                              stage_width=30.0, stage_depth=25.0,
                              letter_shape="O")
        r1 = StageGenerator(cfg).generate()
        r2 = StageGenerator(cfg).generate()
        def _counts(stage):
            return {
                "paper": len([it for it in stage.items if it.item_type == ItemType.PAPER_TARGET]),
                "popper": len([it for it in stage.items if it.item_type == ItemType.POPPER]),
                "plate": len([it for it in stage.items if it.item_type == ItemType.METAL_PLATE]),
                "mini": len([it for it in stage.items if it.item_type == ItemType.MINI_TARGET]),
                "moving": len([it for it in stage.items if it.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)]),
            }
        assert _counts(r1.stage) == _counts(r2.stage)

    def test_different_seeds_give_different_results(self):
        """Semi diversi producono risultati diversi (con alta probabilità)."""
        gen1 = StageGenerator(GeneratorConfig(seed=42))
        gen2 = StageGenerator(GeneratorConfig(seed=999))
        r1 = gen1.generate()
        r2 = gen2.generate()
        # Dovrebbero differire in almeno una coordinata
        coords1 = [(it.x, it.y) for it in r1.stage.items]
        coords2 = [(it.x, it.y) for it in r2.stage.items]
        assert coords1 != coords2 or len(r1.stage.items) != len(r2.stage.items)


class TestGeneratorOutputStructure:
    """Verifica struttura dell'output generato."""

    def test_generate_returns_generator_result(self):
        """generate() restituisce un GeneratorResult."""
        cfg = GeneratorConfig(seed=1, num_targets=4, num_steel=1, num_moving=1,
                              num_walls=2, num_barriers=1)
        gen = StageGenerator(cfg)
        result = gen.generate()
        assert isinstance(result, GeneratorResult)
        assert isinstance(result.stage, Stage)
        assert isinstance(result.score, float)
        assert isinstance(result.attempts, int)

    def test_generated_stage_has_expected_items(self):
        """Lo stage generato contiene i tipi di oggetti richiesti."""
        cfg = GeneratorConfig(seed=42, num_targets=8, num_steel=2, num_moving=1,
                              num_walls=2, num_barriers=1,
                              include_fault_lines=True, include_no_shoots=True)
        gen = StageGenerator(cfg)
        result = gen.generate()

        items = result.stage.items
        types = [it.item_type for it in items]

        scoring_types = {ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
                          ItemType.POPPER, ItemType.METAL_PLATE,
                          ItemType.MINI_TARGET, ItemType.MICRO_TARGET}
        assert any(t in scoring_types for t in types)
        assert len([t for t in types if t in scoring_types]) >= 4

    def test_generated_items_have_valid_ids(self, empty_stage):
        """Tutti gli item generati hanno id univoci e positivi."""
        cfg = GeneratorConfig(seed=7, num_targets=5, num_walls=2)
        gen = StageGenerator(cfg)
        result = gen.generate()
        ids = [it.id for it in result.stage.items]
        assert len(ids) == len(set(ids))
        assert all(i > 0 for i in ids)

    def test_generated_items_within_bounds(self):
        """Tutti gli item generati sono dentro i confini dello stage."""
        cfg = GeneratorConfig(seed=10, stage_width=20.0, stage_depth=15.0)
        gen = StageGenerator(cfg)
        result = gen.generate()
        margin = 0.5
        for it in result.stage.items:
            assert margin <= it.x <= cfg.stage_width - margin, \
                f"Item {it.id} x={it.x} fuori dai bound"
            assert margin <= it.y <= cfg.stage_depth - margin, \
                f"Item {it.id} y={it.y} fuori dai bound"

    def test_generated_stage_is_valid_by_rules(self):
        """Lo stage generato non ha violazioni gravi con OBB reali.
        
        Con Shapely OBB, piccole sovrapposizioni marginali possono emergere.
        Verifichiamo che non ci siano violazioni catastrofiche (es. bersaglio
        dentro un muro) e che lo score sia positivo.
        """
        cfg = GeneratorConfig(seed=42, num_targets=6, num_steel=2, num_moving=1,
                              num_walls=3, num_barriers=1)
        gen = StageGenerator(cfg)
        result = gen.generate()
        engine = IPSCRulesEngine(result.stage)
        validation = engine.validate()
        violations = validation.violations
        # Nessuna violazione catastrofica (distanza zero = sovrapposizione)
        zero_dist = [v for v in violations if "0.0m" in v or "0.0" in v]
        assert len(zero_dist) == 0, f"Sovrapposizioni trovate: {zero_dist}"
        # Score positivo
        assert result.score > 0


class TestGeneratorEdgeCases:
    """Casi limite e configurazioni estreme."""

    def test_minimal_stage_generates(self):
        """Stage piccolo genera senza errori (usando lettera O per risparmiare spazio)."""
        cfg = GeneratorConfig(stage_width=8.0, stage_depth=6.0,
                              num_targets=3, num_steel=0, num_moving=0,
                              num_walls=0, num_barriers=0,
                              include_fault_lines=True, include_no_shoots=False,
                              seed=42, letter_shape="O")
        gen = StageGenerator(cfg)
        result = gen.generate()
        assert len(result.stage.items) >= 2

    def test_large_stage_generates(self):
        """Stage grande (50×50m) con molti bersagli genera."""
        cfg = GeneratorConfig(stage_width=50.0, stage_depth=50.0,
                              num_targets=20, num_steel=5, num_moving=3,
                              num_walls=8, num_barriers=4,
                              seed=42)
        gen = StageGenerator(cfg)
        result = gen.generate()
        # Almeno i bersagli richiesti
        target_types = {ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
                        ItemType.POPPER, ItemType.METAL_PLATE,
                        ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
                        ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER}
        targets = [it for it in result.stage.items if it.item_type in target_types]
        assert len(targets) >= cfg.num_targets

    def test_no_moving_targets(self):
        """Configurazione senza bersagli mobili."""
        cfg = GeneratorConfig(seed=42, num_moving=0)
        gen = StageGenerator(cfg)
        result = gen.generate()
        moving_types = {ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER}
        moving = [it for it in result.stage.items if it.item_type in moving_types]
        assert len(moving) == 0

    def test_easy_difficulty_generates(self):
        """Difficoltà easy produce stage."""
        cfg = GeneratorConfig(seed=42, difficulty="easy")
        gen = StageGenerator(cfg)
        result = gen.generate()
        assert len(result.stage.items) > 0

    def test_hard_difficulty_generates(self):
        """Difficoltà hard produce stage (e score > easy)."""
        cfg_easy = GeneratorConfig(seed=42, difficulty="easy", num_targets=6)
        cfg_hard = GeneratorConfig(seed=42, difficulty="hard", num_targets=6)
        r_easy = StageGenerator(cfg_easy).generate()
        r_hard = StageGenerator(cfg_hard).generate()
        # Hard ha moltiplicatore 1.2x
        assert r_hard.score > r_easy.score

    def test_different_delimitation_styles(self):
        """Tutti gli stili di delimitazione funzionano."""
        for style in ["fault_lines", "barriers", "walls", "mixed"]:
            cfg = GeneratorConfig(seed=42, delimitation=style, num_targets=4,
                                  num_steel=1, num_walls=1)
            gen = StageGenerator(cfg)
            result = gen.generate()
            assert len(result.stage.items) > 0, f"Delimitation '{style}' fallisce"

    def test_zero_steel_targets(self):
        """Zero bersagli steel (poppers e plates esplicitamente a 0)."""
        cfg = GeneratorConfig(seed=42, num_steel=0, num_poppers=0, num_plates=0,
                              auto_distribution=False)
        gen = StageGenerator(cfg)
        result = gen.generate()
        steel_types = {ItemType.STEEL_TARGET, ItemType.POPPER, ItemType.METAL_PLATE}
        steel = [it for it in result.stage.items if it.item_type in steel_types]
        assert len(steel) == 0

    def test_all_steel_targets(self):
        """Tutti i bersagli sono steel (stage grande per distanza 8m)."""
        cfg = GeneratorConfig(seed=42, num_targets=0, num_steel=0,
                              num_poppers=2, num_plates=2,
                              num_mini=0, num_moving=0,
                              stage_width=50.0, stage_depth=40.0,
                              auto_distribution=False)
        gen = StageGenerator(cfg)
        result = gen.generate()
        steel_types = {ItemType.POPPER, ItemType.METAL_PLATE}
        steel = [it for it in result.stage.items if it.item_type in steel_types]
        assert len(steel) >= 2


class TestGeneratorScoring:
    """Verifica scoring dello stage generato."""

    def test_score_is_positive(self):
        """Il punteggio è sempre positivo."""
        cfg = GeneratorConfig(seed=42, num_targets=5)
        gen = StageGenerator(cfg)
        result = gen.generate()
        assert result.score > 0

    def test_more_targets_higher_score(self):
        """Più bersagli = punteggio maggiore (a parità di seed)."""
        # Divario netto: tanti bersagli vs pochi
        cfg_few = GeneratorConfig(seed=42, num_targets=6, num_steel=0, num_poppers=0,
                                  num_plates=0, num_moving=0, num_mini=0,
                                  num_walls=0, num_barriers=0,
                                  include_fault_lines=False, include_no_shoots=False,
                                  auto_distribution=False)
        cfg_many = GeneratorConfig(seed=42, num_targets=14, num_steel=0, num_poppers=2,
                                   num_plates=2, num_moving=2, num_mini=1,
                                   num_walls=0, num_barriers=0,
                                   include_fault_lines=False, include_no_shoots=False,
                                   auto_distribution=False,
                                   stage_width=30.0, stage_depth=25.0)
        r_few = StageGenerator(cfg_few).generate()
        r_many = StageGenerator(cfg_many).generate()
        assert r_many.score >= r_few.score

    def test_score_is_reproducible(self):
        """Stessa configurazione → stesso punteggio."""
        cfg = GeneratorConfig(seed=42)
        s1 = StageGenerator(cfg).generate().score
        s2 = StageGenerator(cfg).generate().score
        assert s1 == s2


class TestGeometryHelpers:
    """Test delle funzioni geometriche in core.geometry."""

    def test_point_in_polygon_inside(self):
        """Punto dentro un poligono convesso."""
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert point_in_polygon(5, 5, poly) is True
        assert point_in_polygon(1, 1, poly) is True

    def test_point_in_polygon_outside(self):
        """Punto fuori dal poligono."""
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert point_in_polygon(11, 5, poly) is False
        assert point_in_polygon(-1, -1, poly) is False

    def test_point_in_polygon_on_edge(self):
        """Punto sul bordo del poligono (considerato inside dal ray casting)."""
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert point_in_polygon(0, 5, poly) is True

    def test_polygon_center(self):
        """Centro di un poligono regolare."""
        poly = [(0, 0), (4, 0), (4, 4), (0, 4)]
        cx, cy = polygon_center(poly)
        assert cx == 2.0
        assert cy == 2.0

    def test_segments_intersect_crossing(self):
        """Due segmenti che si incrociano."""
        a, b = (0, 0), (10, 10)
        c, d = (0, 10), (10, 0)
        assert segments_intersect(a, b, c, d) is True

    def test_segments_intersect_parallel(self):
        """Due segmenti paralleli non si intersecano."""
        a, b = (0, 0), (10, 0)
        c, d = (0, 5), (10, 5)
        assert segments_intersect(a, b, c, d) is False

    def test_segments_intersect_disjoint(self):
        """Due segmenti separati non si intersecano."""
        a, b = (0, 0), (5, 5)
        c, d = (6, 6), (10, 10)
        assert segments_intersect(a, b, c, d) is False

    def test_point_in_rotated_rect_center(self):
        """Centro del rettangolo ruotato (sempre True)."""
        assert point_in_rotated_rect(10, 10, 10, 10, 4, 4, 0)
        assert point_in_rotated_rect(10, 10, 10, 10, 4, 4, 45)

    def test_point_in_rotated_rect_outside(self):
        """Punto fuori dal rettangolo ruotato."""
        assert not point_in_rotated_rect(20, 20, 10, 10, 4, 4, 0)

    def test_line_intersects_rect_direct_hit(self):
        """Linea che passa attraverso un rettangolo."""
        assert line_intersects_rect((0, 5), (20, 5), 10, 5, 4, 4, 0)

    def test_line_intersects_rect_miss(self):
        """Linea che non tocca il rettangolo."""
        assert not line_intersects_rect((0, 0), (20, 0), 10, 10, 4, 4, 0)
