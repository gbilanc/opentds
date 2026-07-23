"""
Test unitari per core/scoring.py — scoring, metadati, attivatori, conteggi.
"""
from __future__ import annotations

import pytest

from core.models import Stage, StageItem, ItemType
from core.scoring import (
    is_paper_like,
    is_steel_like,
    is_scoring_target,
    is_obstacle,
    resolve_target_counts,
    score_stage,
)


class TestTypeHelpers:
    def test_is_paper_like(self):
        assert is_paper_like(ItemType.PAPER_TARGET)
        assert is_paper_like(ItemType.MINI_TARGET)
        assert is_paper_like(ItemType.MICRO_TARGET)
        assert not is_paper_like(ItemType.POPPER)
        assert not is_paper_like(ItemType.WALL)

    def test_is_steel_like(self):
        assert is_steel_like(ItemType.POPPER)
        assert is_steel_like(ItemType.METAL_PLATE)
        assert is_steel_like(ItemType.STEEL_TARGET)
        assert not is_steel_like(ItemType.PAPER_TARGET)
        assert not is_steel_like(ItemType.SWINGER)

    def test_is_scoring_target(self):
        assert is_scoring_target(ItemType.PAPER_TARGET)
        assert is_scoring_target(ItemType.POPPER)
        assert is_scoring_target(ItemType.SWINGER)
        assert is_scoring_target(ItemType.DROP_TURNER)
        assert not is_scoring_target(ItemType.WALL)
        assert not is_scoring_target(ItemType.FAULT_LINE)
        assert not is_scoring_target(ItemType.NO_SHOOT)

    def test_is_obstacle(self):
        assert is_obstacle(ItemType.WALL)
        assert is_obstacle(ItemType.BARRIER)
        assert is_obstacle(ItemType.DOOR)
        assert is_obstacle(ItemType.HARD_COVER)
        assert not is_obstacle(ItemType.PAPER_TARGET)
        assert not is_obstacle(ItemType.FAULT_LINE)


class TestResolveTargetCounts:
    def test_auto_distribution_short(self):
        result = resolve_target_counts(
            num_targets=0, num_steel=0, num_poppers=0, num_plates=0,
            num_mini=0, num_moving=0,
            auto_distribution=True, course_type="short",
        )
        assert result["paper"] == 5
        assert result["poppers"] == 1
        assert result["plates"] == 1
        assert result["mini"] == 0
        assert result["moving"] == 0

    def test_auto_distribution_medium(self):
        result = resolve_target_counts(
            0, 0, 0, 0, 0, 0, True, "medium",
        )
        assert result["paper"] == 11
        assert result["poppers"] == 1
        assert result["plates"] == 2
        assert result["moving"] == 1

    def test_auto_distribution_long(self):
        result = resolve_target_counts(
            0, 0, 0, 0, 0, 0, True, "long",
        )
        assert result["paper"] == 15
        assert result["poppers"] == 2
        assert result["plates"] == 2

    def test_explicit_values_override_auto(self):
        result = resolve_target_counts(
            num_targets=8, num_steel=0, num_poppers=3, num_plates=4,
            num_mini=2, num_moving=3,
            auto_distribution=True, course_type="short",
        )
        assert result["paper"] == 8
        assert result["poppers"] == 3
        assert result["plates"] == 4
        assert result["mini"] == 2
        assert result["moving"] == 3

    def test_no_auto_distribution(self):
        result = resolve_target_counts(
            10, 2, 0, 0, 1, 2, False, "",
        )
        assert result["paper"] == 10
        assert result["poppers"] >= 1  # 60% di 2
        assert result["plates"] >= 0
        assert result["mini"] == 1
        assert result["moving"] == 2

    def test_explicit_steel_without_auto(self):
        result = resolve_target_counts(
            6, 0, 2, 3, 0, 0, False, "",
        )
        assert result["paper"] == 6
        assert result["poppers"] == 2
        assert result["plates"] == 3

    def test_zero_steel(self):
        result = resolve_target_counts(
            5, 0, 0, 0, 0, 0, False, "",
        )
        assert result["poppers"] == 0
        assert result["plates"] == 0

    def test_unknown_course_type_fallsback_to_default(self):
        result = resolve_target_counts(
            0, 0, 0, 0, 0, 0, True, "unknown",
        )
        # Fallback: default distribution
        assert result["paper"] >= 5


class TestScoreStage:
    def test_empty_stage_score_zero(self):
        stage = Stage()
        score = score_stage(
            stage, [],
            perimeter_poly=None,
            interior_samples=[],
            get_blocking_walls_fn=lambda: [],
            is_target_visible_fn=lambda t, b: True,
            config_difficulty="easy",
        )
        assert score == 0.0

    def test_score_increases_with_targets(self):
        stage = Stage(width=20.0, depth=15.0)
        items = [
            StageItem(1, ItemType.PAPER_TARGET, 5, 5),
            StageItem(2, ItemType.PAPER_TARGET, 8, 5),
        ]
        score = score_stage(
            stage, items,
            perimeter_poly=[(2, 2), (18, 2), (18, 13), (2, 13)],
            interior_samples=[(10, 7)],
            get_blocking_walls_fn=lambda: [],
            is_target_visible_fn=lambda t, b: True,
            config_difficulty="easy",
        )
        assert score > 0

    def test_hard_difficulty_multiplier(self):
        stage = Stage(width=20.0, depth=15.0)
        items = [
            StageItem(1, ItemType.PAPER_TARGET, 5, 5),
            StageItem(2, ItemType.POPPER, 10, 5),
        ]
        score_easy = score_stage(
            stage, items,
            perimeter_poly=None, interior_samples=[],
            get_blocking_walls_fn=lambda: [],
            is_target_visible_fn=lambda t, b: True,
            config_difficulty="easy",
        )
        score_hard = score_stage(
            stage, items,
            perimeter_poly=None, interior_samples=[],
            get_blocking_walls_fn=lambda: [],
            is_target_visible_fn=lambda t, b: True,
            config_difficulty="hard",
        )
        assert score_hard > score_easy

    def test_visibility_bonus(self):
        stage = Stage(width=20.0, depth=15.0)
        items = [
            StageItem(1, ItemType.PAPER_TARGET, 5, 5),
            StageItem(2, ItemType.PAPER_TARGET, 10, 5),
        ]
        score_all_visible = score_stage(
            stage, items,
            perimeter_poly=None, interior_samples=[],
            get_blocking_walls_fn=lambda: [],
            is_target_visible_fn=lambda t, b: True,
            config_difficulty="easy",
        )
        score_none_visible = score_stage(
            stage, items,
            perimeter_poly=None, interior_samples=[],
            get_blocking_walls_fn=lambda: [],
            is_target_visible_fn=lambda t, b: False,
            config_difficulty="easy",
        )
        assert score_all_visible > score_none_visible
