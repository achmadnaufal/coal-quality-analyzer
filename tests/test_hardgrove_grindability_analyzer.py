"""
Tests for src/hardgrove_grindability_analyzer.py

Covers: happy path (typical bituminous coal), HGI moisture correction,
classification boundaries, Bond Work Index, mill specific energy,
capacity de-rate, batch processing, buyer spec screening, and edge cases
(zero/negative HGI, ash > 100%, negative moisture, division-by-zero
guarded behavior, empty batch, type validation).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hardgrove_grindability_analyzer import (
    GrindabilityClass,
    HGIAnalysis,
    HGISample,
    analyze_batch,
    analyze_sample,
    bond_work_index,
    capacity_derate_percent,
    classify_grindability,
    correct_hgi_for_moisture,
    meets_specification,
    mill_specific_energy,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def standard_sample() -> HGISample:
    """Typical Indonesian sub-bituminous coal sample."""
    return HGISample(
        sample_id="KAL-001",
        hgi=52.0,
        surface_moisture_pct=3.0,
        ash_pct=12.5,
    )


@pytest.fixture()
def reference_sample() -> HGISample:
    """Sample at exact reference moisture so no correction is applied."""
    return HGISample(
        sample_id="REF-50",
        hgi=50.0,
        surface_moisture_pct=1.0,
        ash_pct=10.0,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_analyze_sample_returns_immutable_result(standard_sample: HGISample) -> None:
    result = analyze_sample(standard_sample)
    assert isinstance(result, HGIAnalysis)
    assert result.sample_id == "KAL-001"
    # frozen dataclass — must reject mutation
    with pytest.raises(Exception):
        result.hgi_corrected = 99.0  # type: ignore[misc]


def test_analyze_sample_typical_medium_class(standard_sample: HGISample) -> None:
    result = analyze_sample(standard_sample)
    # 52 HGI - 1.3*(3-1) = 49.4 -> hard
    assert result.grindability_class == GrindabilityClass.HARD
    assert 48.0 < result.hgi_corrected < 50.0
    assert result.bond_work_index_kwh_per_short_ton > 0
    assert result.mill_specific_energy_kwh_per_t > 0
    assert result.warning == ""


def test_reference_sample_has_no_moisture_correction(
    reference_sample: HGISample,
) -> None:
    result = analyze_sample(reference_sample)
    assert math.isclose(result.hgi_corrected, 50.0, abs_tol=1e-9)
    assert math.isclose(
        result.mill_specific_energy_kwh_per_t, 12.0, abs_tol=1e-9
    )
    assert math.isclose(result.capacity_derate_pct, 0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Moisture correction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hgi, moisture, expected",
    [
        (50.0, 1.0, 50.0),       # at reference, no change
        (55.0, 5.0, 49.8),       # 55 - 1.3*4 = 49.8
        (60.0, 10.0, 48.3),      # 60 - 1.3*9 = 48.3
        (50.0, 0.0, 51.3),       # below reference, slight bump
    ],
)
def test_correct_hgi_for_moisture_parametrized(
    hgi: float, moisture: float, expected: float
) -> None:
    assert math.isclose(
        correct_hgi_for_moisture(hgi, moisture), expected, abs_tol=1e-6
    )


def test_correct_hgi_clamps_to_minimum_one() -> None:
    # Extreme moisture would push HGI below zero — must clamp at 1.0
    corrected = correct_hgi_for_moisture(10.0, 100.0)
    assert corrected == 1.0


# ---------------------------------------------------------------------------
# Classification boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hgi, expected",
    [
        (35.0, GrindabilityClass.VERY_HARD),
        (40.0, GrindabilityClass.HARD),
        (49.999, GrindabilityClass.HARD),
        (50.0, GrindabilityClass.MEDIUM),
        (69.999, GrindabilityClass.MEDIUM),
        (70.0, GrindabilityClass.SOFT),
        (89.999, GrindabilityClass.SOFT),
        (90.0, GrindabilityClass.VERY_SOFT),
        (105.0, GrindabilityClass.VERY_SOFT),
    ],
)
def test_classify_grindability_boundaries(
    hgi: float, expected: GrindabilityClass
) -> None:
    assert classify_grindability(hgi) == expected


# ---------------------------------------------------------------------------
# Mill physics
# ---------------------------------------------------------------------------


def test_bond_work_index_decreases_with_higher_hgi() -> None:
    # Softer coal (higher HGI) should require less work
    assert bond_work_index(40) > bond_work_index(60) > bond_work_index(90)


def test_mill_energy_baseline_at_hgi_50() -> None:
    assert math.isclose(mill_specific_energy(50.0), 12.0, abs_tol=1e-9)


def test_capacity_derate_negative_for_softer_coal() -> None:
    # HGI > 50 → softer → should yield capacity gain (negative de-rate)
    assert capacity_derate_percent(70) < 0
    # HGI < 50 → harder → capacity loss (positive de-rate)
    assert capacity_derate_percent(30) > 0


# ---------------------------------------------------------------------------
# Buyer spec screening
# ---------------------------------------------------------------------------


def test_meets_specification_default_window(reference_sample: HGISample) -> None:
    result = analyze_sample(reference_sample)
    assert meets_specification(result) is True


def test_fails_specification_if_too_hard() -> None:
    sample = HGISample("HARD-1", hgi=35.0)
    result = analyze_sample(sample)
    assert meets_specification(result) is False


def test_meets_specification_invalid_window_raises() -> None:
    sample = HGISample("X", hgi=55.0)
    result = analyze_sample(sample)
    with pytest.raises(ValueError, match="must be <"):
        meets_specification(result, min_hgi=70, max_hgi=50)
    with pytest.raises(ValueError, match="must be positive"):
        meets_specification(result, min_hgi=-1, max_hgi=50)


# ---------------------------------------------------------------------------
# Edge cases — input validation
# ---------------------------------------------------------------------------


def test_zero_hgi_raises() -> None:
    # HGISample is a plain frozen dataclass; validation runs at analyze time
    with pytest.raises(ValueError, match="hgi must be > 0"):
        analyze_sample(HGISample("Z", hgi=0.0))


def test_negative_hgi_raises() -> None:
    with pytest.raises(ValueError, match="hgi must be > 0"):
        analyze_sample(HGISample("N", hgi=-5.0))


def test_negative_surface_moisture_raises() -> None:
    with pytest.raises(ValueError, match="surface_moisture_pct must be >= 0"):
        analyze_sample(HGISample("M", hgi=55, surface_moisture_pct=-1.0))


def test_ash_above_100_raises() -> None:
    with pytest.raises(ValueError, match="ash_pct must be <= 100"):
        analyze_sample(HGISample("A", hgi=55, ash_pct=150.0))


def test_negative_ash_raises() -> None:
    with pytest.raises(ValueError, match="ash_pct must be >= 0"):
        analyze_sample(HGISample("A", hgi=55, ash_pct=-3.0))


def test_out_of_range_hgi_warns_but_does_not_raise() -> None:
    result = analyze_sample(HGISample("WARN", hgi=120.0))
    assert "outside typical range" in result.warning
    assert result.grindability_class == GrindabilityClass.VERY_SOFT


def test_high_ash_warns() -> None:
    result = analyze_sample(HGISample("ASHY", hgi=55, ash_pct=60.0))
    assert "atypical for power coal" in result.warning


def test_wrong_type_raises() -> None:
    with pytest.raises(TypeError, match="Expected HGISample"):
        analyze_sample("not-a-sample")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


def test_analyze_batch_preserves_order() -> None:
    batch = [
        HGISample("A", 45),
        HGISample("B", 55),
        HGISample("C", 75),
    ]
    results = analyze_batch(batch)
    assert [r.sample_id for r in results] == ["A", "B", "C"]


def test_empty_batch_returns_empty_list() -> None:
    assert analyze_batch([]) == []


def test_batch_propagates_validation_error() -> None:
    batch = [HGISample("A", 55), HGISample("BAD", -1)]
    with pytest.raises(ValueError):
        analyze_batch(batch)


# ---------------------------------------------------------------------------
# Numerical sanity
# ---------------------------------------------------------------------------


def test_bond_wi_division_by_zero_guard() -> None:
    # hgi=0 must raise rather than divide by zero silently
    with pytest.raises(ValueError):
        bond_work_index(0.0)
    with pytest.raises(ValueError):
        mill_specific_energy(0.0)
    with pytest.raises(ValueError):
        classify_grindability(0.0)
