"""Tests for src.blend_ratio_optimizer.

Covers:
* CoalSource / BlendTarget validation (edge cases: moisture > 100%, negative
  ash, CV out of [1000, 8000], non-string id, duplicate source ids).
* Closed-form binary blend math (hand-checked mixing values).
* N-source LP solver feasibility + cap enforcement.
* BlendResult immutability (dataclass frozen=True) and as_dict() output.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.blend_ratio_optimizer import (  # noqa: E402
    BlendResult,
    BlendTarget,
    CoalSource,
    optimize_binary_blend,
    optimize_blend,
)


# --------------------------------------------------------------------------- #
# CoalSource validation
# --------------------------------------------------------------------------- #


class TestCoalSourceValidation:
    def test_valid_source_constructs(self) -> None:
        s = CoalSource("PIT-A", 6000.0, 10.0, 0.5, 12.0)
        assert s.source_id == "PIT-A"
        assert s.cv_kcal_kg == 6000.0

    def test_empty_source_id_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            CoalSource("", 6000.0, 10.0, 0.5, 12.0)

    def test_whitespace_source_id_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            CoalSource("   ", 6000.0, 10.0, 0.5, 12.0)

    def test_cv_below_physical_range_raises(self) -> None:
        # Below 1000 kcal/kg is not combustible coal
        with pytest.raises(ValueError, match="cv_kcal_kg"):
            CoalSource("PIT-A", 500.0, 10.0, 0.5, 12.0)

    def test_cv_above_physical_range_raises(self) -> None:
        # Above 8000 kcal/kg exceeds meta-anthracite
        with pytest.raises(ValueError, match="cv_kcal_kg"):
            CoalSource("PIT-A", 9000.0, 10.0, 0.5, 12.0)

    def test_negative_ash_raises(self) -> None:
        with pytest.raises(ValueError, match="ash_pct"):
            CoalSource("PIT-A", 6000.0, -1.0, 0.5, 12.0)

    def test_ash_above_100_raises(self) -> None:
        with pytest.raises(ValueError, match="ash_pct"):
            CoalSource("PIT-A", 6000.0, 110.0, 0.5, 12.0)

    def test_moisture_above_100_raises(self) -> None:
        with pytest.raises(ValueError, match="moisture_pct"):
            CoalSource("PIT-A", 6000.0, 10.0, 0.5, 101.0)

    def test_negative_moisture_raises(self) -> None:
        with pytest.raises(ValueError, match="moisture_pct"):
            CoalSource("PIT-A", 6000.0, 10.0, 0.5, -0.1)

    def test_sulfur_above_10_raises(self) -> None:
        with pytest.raises(ValueError, match="total_sulfur_pct"):
            CoalSource("PIT-A", 6000.0, 10.0, 15.0, 12.0)

    def test_negative_available_tonnes_raises(self) -> None:
        with pytest.raises(ValueError, match="available_tonnes"):
            CoalSource("PIT-A", 6000.0, 10.0, 0.5, 12.0, available_tonnes=-1.0)

    def test_immutable(self) -> None:
        s = CoalSource("PIT-A", 6000.0, 10.0, 0.5, 12.0)
        with pytest.raises(Exception):
            s.ash_pct = 20.0  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# BlendTarget validation
# --------------------------------------------------------------------------- #


class TestBlendTargetValidation:
    def test_valid_target(self) -> None:
        t = BlendTarget(target_cv_kcal_kg=6000.0)
        assert t.max_ash_pct == 15.0
        assert t.max_sulfur_pct == 0.8
        assert t.cv_tolerance_kcal_kg == 50.0

    def test_cv_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="target_cv_kcal_kg"):
            BlendTarget(target_cv_kcal_kg=500.0)
        with pytest.raises(ValueError, match="target_cv_kcal_kg"):
            BlendTarget(target_cv_kcal_kg=9000.0)

    def test_ash_cap_above_100_raises(self) -> None:
        with pytest.raises(ValueError, match="max_ash_pct"):
            BlendTarget(target_cv_kcal_kg=6000.0, max_ash_pct=105.0)

    def test_moisture_cap_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="max_moisture_pct"):
            BlendTarget(target_cv_kcal_kg=6000.0, max_moisture_pct=-1.0)

    def test_negative_tolerance_raises(self) -> None:
        with pytest.raises(ValueError, match="cv_tolerance_kcal_kg"):
            BlendTarget(target_cv_kcal_kg=6000.0, cv_tolerance_kcal_kg=-10.0)


# --------------------------------------------------------------------------- #
# Binary blend — closed-form math
# --------------------------------------------------------------------------- #


class TestBinaryBlend:
    def test_hits_target_exactly_on_midpoint(self) -> None:
        """Target halfway between two sources → 50/50 blend."""
        a = CoalSource("A", 6400.0, 10.0, 0.50, 12.0)
        b = CoalSource("B", 5200.0, 12.0, 0.90, 20.0)
        target = BlendTarget(target_cv_kcal_kg=5800.0)
        result = optimize_binary_blend(a, b, target)

        # w_a = (5800 - 5200) / (6400 - 5200) = 600 / 1200 = 0.5
        assert math.isclose(result.ratios[0], 0.5, abs_tol=1e-6)
        assert math.isclose(result.ratios[1], 0.5, abs_tol=1e-6)
        # Blended CV = 0.5 * 6400 + 0.5 * 5200 = 5800
        assert math.isclose(result.blended_cv_kcal_kg, 5800.0, abs_tol=0.01)
        # Blended ash = 0.5 * 10 + 0.5 * 12 = 11
        assert math.isclose(result.blended_ash_pct, 11.0, abs_tol=1e-4)
        # Blended sulfur = 0.5 * 0.50 + 0.5 * 0.90 = 0.70
        assert math.isclose(result.blended_sulfur_pct, 0.70, abs_tol=1e-4)
        # Blended moisture = 0.5 * 12 + 0.5 * 20 = 16
        assert math.isclose(result.blended_moisture_pct, 16.0, abs_tol=1e-4)
        assert result.feasible is True
        assert result.method == "closed_form_binary"

    def test_target_at_source_a_yields_pure_a(self) -> None:
        a = CoalSource("A", 6400.0, 10.0, 0.50, 12.0)
        b = CoalSource("B", 5200.0, 12.0, 0.90, 20.0)
        target = BlendTarget(target_cv_kcal_kg=6400.0)
        result = optimize_binary_blend(a, b, target)
        assert math.isclose(result.ratios[0], 1.0, abs_tol=1e-6)
        assert math.isclose(result.ratios[1], 0.0, abs_tol=1e-6)

    def test_target_above_both_clips_to_higher_source(self) -> None:
        """Target beyond the higher source CV is clipped (raw w > 1 → w=1)."""
        a = CoalSource("A", 6400.0, 10.0, 0.50, 12.0)
        b = CoalSource("B", 5200.0, 12.0, 0.90, 20.0)
        target = BlendTarget(target_cv_kcal_kg=7000.0, cv_tolerance_kcal_kg=20.0)
        result = optimize_binary_blend(a, b, target)
        assert math.isclose(result.ratios[0], 1.0, abs_tol=1e-6)
        # CV deviation = 6400 - 7000 = -600 → fails tolerance
        assert result.meets_specification is False
        assert any("cv" in v for v in result.violations)

    def test_ash_cap_violation_detected(self) -> None:
        # Both sources above ash cap; blend always > cap
        a = CoalSource("A", 6000.0, 18.0, 0.50, 12.0)
        b = CoalSource("B", 6000.0, 20.0, 0.50, 12.0)
        target = BlendTarget(target_cv_kcal_kg=6000.0, max_ash_pct=15.0)
        result = optimize_binary_blend(a, b, target)
        assert result.meets_specification is False
        assert any("ash" in v for v in result.violations)

    def test_sulfur_cap_violation_detected(self) -> None:
        a = CoalSource("A", 6000.0, 10.0, 1.5, 12.0)
        b = CoalSource("B", 6000.0, 10.0, 1.2, 12.0)
        target = BlendTarget(target_cv_kcal_kg=6000.0, max_sulfur_pct=0.8)
        result = optimize_binary_blend(a, b, target)
        assert result.meets_specification is False
        assert any("sulfur" in v for v in result.violations)

    def test_identical_cv_sources(self) -> None:
        a = CoalSource("A", 6000.0, 8.0, 0.40, 10.0)
        b = CoalSource("B", 6000.0, 12.0, 0.60, 14.0)
        target = BlendTarget(target_cv_kcal_kg=6000.0)
        result = optimize_binary_blend(a, b, target)
        # Any mix yields CV = 6000; implementation picks 50/50
        assert math.isclose(result.blended_cv_kcal_kg, 6000.0, abs_tol=0.01)
        assert result.meets_specification is True

    def test_same_source_id_raises(self) -> None:
        a = CoalSource("DUP", 6000.0, 10.0, 0.50, 12.0)
        b = CoalSource("DUP", 5500.0, 12.0, 0.60, 14.0)
        with pytest.raises(ValueError, match="distinct source_ids"):
            optimize_binary_blend(a, b, BlendTarget(6000.0))

    def test_wrong_type_raises(self) -> None:
        a = CoalSource("A", 6000.0, 10.0, 0.50, 12.0)
        with pytest.raises(TypeError):
            optimize_binary_blend(a, "not a source", BlendTarget(6000.0))  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            optimize_binary_blend(a, a, "not a target")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# N-source LP solver
# --------------------------------------------------------------------------- #


class TestOptimizeBlend:
    def test_delegates_to_binary_for_two_sources(self) -> None:
        a = CoalSource("A", 6400.0, 10.0, 0.50, 12.0)
        b = CoalSource("B", 5200.0, 12.0, 0.90, 20.0)
        target = BlendTarget(target_cv_kcal_kg=5800.0)
        result = optimize_blend([a, b], target)
        assert result.method == "closed_form_binary"
        assert math.isclose(result.ratios[0], 0.5, abs_tol=1e-6)

    def test_single_source(self) -> None:
        a = CoalSource("A", 6000.0, 10.0, 0.50, 12.0)
        target = BlendTarget(target_cv_kcal_kg=6000.0)
        result = optimize_blend([a], target)
        assert result.ratios == (1.0,)
        assert result.method == "single_source"
        assert result.meets_specification is True

    def test_three_source_lp_hits_target(self) -> None:
        sources = [
            CoalSource("A", 6400.0, 9.0, 0.40, 10.0),
            CoalSource("B", 5800.0, 11.0, 0.65, 14.0),
            CoalSource("C", 5200.0, 14.0, 0.90, 20.0),
        ]
        target = BlendTarget(
            target_cv_kcal_kg=6000.0,
            max_ash_pct=12.0,
            max_sulfur_pct=0.8,
            max_moisture_pct=18.0,
            cv_tolerance_kcal_kg=10.0,
        )
        result = optimize_blend(sources, target)
        assert result.feasible is True
        # Ratios sum to ~1
        assert math.isclose(sum(result.ratios), 1.0, abs_tol=1e-4)
        # CV should hit within tolerance
        assert abs(result.cv_deviation_kcal_kg) <= target.cv_tolerance_kcal_kg
        # Caps respected
        assert result.blended_ash_pct <= target.max_ash_pct + 1e-6
        assert result.blended_sulfur_pct <= target.max_sulfur_pct + 1e-6
        assert result.blended_moisture_pct <= target.max_moisture_pct + 1e-6

    def test_infeasible_returns_diagnostic(self) -> None:
        # All sources above ash cap → LP infeasible
        sources = [
            CoalSource("A", 6000.0, 20.0, 0.50, 12.0),
            CoalSource("B", 5800.0, 22.0, 0.55, 13.0),
            CoalSource("C", 5900.0, 21.0, 0.60, 14.0),
        ]
        target = BlendTarget(
            target_cv_kcal_kg=5900.0,
            max_ash_pct=15.0,
        )
        result = optimize_blend(sources, target)
        assert result.feasible is False
        assert result.meets_specification is False
        assert any("infeasible" in v for v in result.violations)
        # Diagnostic fallback is 1/n uniform
        assert all(math.isclose(r, 1.0 / 3.0, abs_tol=1e-6) for r in result.ratios)

    def test_empty_sources_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            optimize_blend([], BlendTarget(6000.0))

    def test_duplicate_source_ids_raises(self) -> None:
        a = CoalSource("SAME", 6000.0, 10.0, 0.5, 12.0)
        b = CoalSource("SAME", 5500.0, 12.0, 0.6, 14.0)
        c = CoalSource("OTHER", 5800.0, 11.0, 0.55, 13.0)
        with pytest.raises(ValueError, match="Duplicate source_id"):
            optimize_blend([a, b, c], BlendTarget(6000.0))

    def test_non_coalsource_raises(self) -> None:
        with pytest.raises(TypeError):
            optimize_blend(["not a source"], BlendTarget(6000.0))  # type: ignore[list-item]

    def test_non_blendtarget_raises(self) -> None:
        a = CoalSource("A", 6000.0, 10.0, 0.5, 12.0)
        b = CoalSource("B", 5500.0, 12.0, 0.6, 14.0)
        c = CoalSource("C", 5800.0, 11.0, 0.55, 13.0)
        with pytest.raises(TypeError):
            optimize_blend([a, b, c], "not a target")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# BlendResult structural guarantees
# --------------------------------------------------------------------------- #


class TestBlendResult:
    def test_as_dict_roundtrip(self) -> None:
        a = CoalSource("A", 6400.0, 10.0, 0.50, 12.0)
        b = CoalSource("B", 5200.0, 12.0, 0.90, 20.0)
        result = optimize_binary_blend(a, b, BlendTarget(5800.0))
        d = result.as_dict()
        assert set(d.keys()) == {
            "ratios",
            "blended_cv_kcal_kg",
            "blended_ash_pct",
            "blended_sulfur_pct",
            "blended_moisture_pct",
            "cv_deviation_kcal_kg",
            "feasible",
            "meets_specification",
            "violations",
            "method",
        }
        assert isinstance(d["ratios"], list)
        assert isinstance(d["violations"], list)

    def test_result_is_immutable(self) -> None:
        a = CoalSource("A", 6400.0, 10.0, 0.50, 12.0)
        b = CoalSource("B", 5200.0, 12.0, 0.90, 20.0)
        result = optimize_binary_blend(a, b, BlendTarget(5800.0))
        with pytest.raises(Exception):
            result.ratios = (0.1, 0.9)  # type: ignore[misc]
