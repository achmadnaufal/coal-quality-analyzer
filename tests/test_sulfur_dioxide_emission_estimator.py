"""
Tests for src/sulfur_dioxide_emission_estimator.py

Covers: happy path, edge cases (zero sulfur, zero FGD, max FGD, single sample,
empty batch, out-of-range inputs), determinism, parametrized cases, and
regulatory threshold checks.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sulfur_dioxide_emission_estimator import (
    CoalSample,
    EmissionResult,
    estimate_batch,
    estimate_so2_emission,
    exceeds_threshold,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def standard_sample() -> CoalSample:
    """Typical Indonesian sub-bituminous coal sample."""
    return CoalSample(
        sample_id="KAL-001",
        total_sulfur_pct=0.38,
        calorific_value_kcal_kg=4850,
    )


@pytest.fixture()
def high_sulfur_sample() -> CoalSample:
    return CoalSample(
        sample_id="HIGH-S",
        total_sulfur_pct=3.0,
        calorific_value_kcal_kg=6000,
        fgd_efficiency_pct=90.0,
    )


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_basic_emission_returns_emission_result(standard_sample: CoalSample) -> None:
    result = estimate_so2_emission(standard_sample)
    assert isinstance(result, EmissionResult)
    assert result.sample_id == "KAL-001"


def test_so2_per_tonne_positive(standard_sample: CoalSample) -> None:
    result = estimate_so2_emission(standard_sample)
    assert result.so2_kg_per_tonne > 0


def test_so2_per_mwh_positive(standard_sample: CoalSample) -> None:
    result = estimate_so2_emission(standard_sample)
    assert result.so2_kg_per_mwh > 0


def test_raw_emission_factor_matches_stoichiometry(standard_sample: CoalSample) -> None:
    # raw = sulfur_pct/100 * 1000 kg/t * 2 (SO2/S ratio)
    expected_raw = 0.38 / 100 * 1000 * 2
    result = estimate_so2_emission(standard_sample)
    assert math.isclose(result.emission_factor_raw_kg_per_tonne, expected_raw, rel_tol=1e-9)


def test_no_fgd_means_zero_fgd_reduction(standard_sample: CoalSample) -> None:
    result = estimate_so2_emission(standard_sample)
    assert result.fgd_reduction_kg_per_tonne == pytest.approx(0.0)


def test_fgd_reduces_net_emission(high_sulfur_sample: CoalSample) -> None:
    result = estimate_so2_emission(high_sulfur_sample)
    # With 90 % FGD, net should be ~10 % of post-retention raw
    assert result.fgd_reduction_kg_per_tonne > 0
    assert result.so2_kg_per_tonne < result.emission_factor_raw_kg_per_tonne


def test_determinism(standard_sample: CoalSample) -> None:
    r1 = estimate_so2_emission(standard_sample)
    r2 = estimate_so2_emission(standard_sample)
    assert r1.so2_kg_per_tonne == r2.so2_kg_per_tonne
    assert r1.so2_kg_per_mwh == r2.so2_kg_per_mwh


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_zero_sulfur_gives_zero_emissions() -> None:
    sample = CoalSample("ZERO-S", total_sulfur_pct=0.0, calorific_value_kcal_kg=5000)
    result = estimate_so2_emission(sample)
    assert result.so2_kg_per_tonne == pytest.approx(0.0)
    assert result.so2_kg_per_mwh == pytest.approx(0.0)
    assert result.emission_factor_raw_kg_per_tonne == pytest.approx(0.0)


def test_single_sample_batch() -> None:
    sample = CoalSample("SINGLE", total_sulfur_pct=0.5, calorific_value_kcal_kg=4500)
    results = estimate_batch([sample])
    assert len(results) == 1
    assert results[0].sample_id == "SINGLE"


def test_empty_batch_returns_empty_list() -> None:
    results = estimate_batch([])
    assert results == []


def test_invalid_calorific_value_raises() -> None:
    sample = CoalSample("BAD-GCV", total_sulfur_pct=0.5, calorific_value_kcal_kg=0)
    with pytest.raises(ValueError, match="calorific_value_kcal_kg must be > 0"):
        estimate_so2_emission(sample)


def test_negative_calorific_value_raises() -> None:
    sample = CoalSample("NEG-GCV", total_sulfur_pct=0.5, calorific_value_kcal_kg=-100)
    with pytest.raises(ValueError):
        estimate_so2_emission(sample)


def test_out_of_range_sulfur_adds_warning() -> None:
    sample = CoalSample("OOR-S", total_sulfur_pct=12.0, calorific_value_kcal_kg=5000)
    result = estimate_so2_emission(sample)
    assert "total_sulfur_pct" in result.warning


def test_wrong_type_raises() -> None:
    with pytest.raises(TypeError):
        estimate_so2_emission({"sample_id": "bad"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Parametrized tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sulfur_pct, gcv, fgd_eff, expected_raw_so2",
    [
        (0.5, 5000, 0.0, 10.0),   # 0.5/100*1000*2 = 10
        (1.0, 5000, 0.0, 20.0),   # 1.0/100*1000*2 = 20
        (2.0, 6000, 90.0, 40.0),  # raw = 40; net much lower due to FGD
        (0.0, 4500, 50.0, 0.0),   # zero sulfur always zero raw
    ],
)
def test_parametrized_raw_emission(
    sulfur_pct: float, gcv: float, fgd_eff: float, expected_raw_so2: float
) -> None:
    sample = CoalSample(
        sample_id="P", total_sulfur_pct=sulfur_pct,
        calorific_value_kcal_kg=gcv, fgd_efficiency_pct=fgd_eff
    )
    result = estimate_so2_emission(sample)
    assert math.isclose(result.emission_factor_raw_kg_per_tonne, expected_raw_so2, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Regulatory threshold
# ---------------------------------------------------------------------------


def test_exceeds_threshold_true() -> None:
    sample = CoalSample("HIGH", total_sulfur_pct=5.0, calorific_value_kcal_kg=4000)
    result = estimate_so2_emission(sample)
    # High sulfur — so2_kg_per_mwh should exceed a very tight threshold of 0.01 kg/MWh
    assert exceeds_threshold(result, threshold_kg_per_mwh=0.01)


def test_exceeds_threshold_false_zero_sulfur() -> None:
    sample = CoalSample("CLEAN", total_sulfur_pct=0.0, calorific_value_kcal_kg=5000)
    result = estimate_so2_emission(sample)
    assert not exceeds_threshold(result, threshold_kg_per_mwh=2.0)


def test_exceeds_threshold_negative_raises() -> None:
    sample = CoalSample("X", total_sulfur_pct=0.5, calorific_value_kcal_kg=5000)
    result = estimate_so2_emission(sample)
    with pytest.raises(ValueError, match="threshold must be >= 0"):
        exceeds_threshold(result, threshold_kg_per_mwh=-1.0)
