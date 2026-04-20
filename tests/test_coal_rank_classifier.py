"""
Tests for src/coal_rank_classifier.py — ASTM D388 coal rank classifier.

Covers: happy paths across the full rank spectrum (lignite B through
meta-anthracite), Parr mineral-matter corrections, kcal/kg ↔ Btu/lb
conversion, higher-vs-lower rank branching at FC_dmmf = 69 %, the
agglomerating tie-break band (10 500 – 11 500 Btu/lb), batch order,
empty batch, coking-candidate helper, rank ordinal, and all validation
branches (bad unit, negative numerics, closure failure, non-positive
GCV, wrong type, Parr denominator guard).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from coal_rank_classifier import (  # noqa: E402
    CoalClass,
    CoalRank,
    ProximateSample,
    RankAnalysis,
    class_of,
    classify_batch,
    classify_sample,
    gcv_in_btu_per_lb,
    is_coking_candidate,
    kcal_per_kg_to_btu_per_lb,
    parr_fixed_carbon_dmmf,
    parr_gcv_mmmf_btu_per_lb,
    rank_rank_ordinal,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def kalimantan_sub_bituminous() -> ProximateSample:
    """Typical Kalimantan export thermal coal (sub-bituminous C)."""
    return ProximateSample(
        sample_id="KAL-001",
        moisture_pct=28.0,
        ash_pct=6.0,
        volatile_matter_pct=40.0,
        fixed_carbon_pct=26.0,
        sulfur_pct=0.4,
        gcv=4850.0,
        gcv_unit="kcal_per_kg",
        agglomerating=False,
    )


@pytest.fixture()
def bowen_basin_coking() -> ProximateSample:
    """Australian Bowen Basin low-volatile coking coal (FC_dmmf ~81 %)."""
    return ProximateSample(
        sample_id="BOW-LVB",
        moisture_pct=2.0,
        ash_pct=7.0,
        volatile_matter_pct=18.0,
        fixed_carbon_pct=73.0,
        sulfur_pct=0.5,
        gcv=14_700.0,
        gcv_unit="btu_per_lb",
        agglomerating=True,
    )


@pytest.fixture()
def powder_river_basin() -> ProximateSample:
    """US Powder River Basin sub-bituminous (non-agglomerating)."""
    return ProximateSample(
        sample_id="PRB-01",
        moisture_pct=28.0,
        ash_pct=5.0,
        volatile_matter_pct=34.0,
        fixed_carbon_pct=33.0,
        sulfur_pct=0.4,
        gcv=8600.0,
        gcv_unit="btu_per_lb",
        agglomerating=False,
    )


# ---------------------------------------------------------------------------
# Happy-path classifications
# ---------------------------------------------------------------------------


def test_kalimantan_is_sub_bituminous(
    kalimantan_sub_bituminous: ProximateSample,
) -> None:
    result = classify_sample(kalimantan_sub_bituminous)
    assert result.coal_class is CoalClass.SUB_BITUMINOUS
    assert result.coal_rank is CoalRank.SUB_BITUMINOUS_C
    assert result.classification_axis == "calorific_value"
    assert result.sample_id == "KAL-001"


def test_bowen_basin_is_low_volatile_bituminous(
    bowen_basin_coking: ProximateSample,
) -> None:
    result = classify_sample(bowen_basin_coking)
    assert result.coal_class is CoalClass.BITUMINOUS
    assert result.coal_rank is CoalRank.LOW_VOLATILE_BITUMINOUS
    assert result.classification_axis == "fixed_carbon"
    assert 78.0 <= result.fixed_carbon_dmmf_pct < 86.0


def test_prb_is_sub_bituminous(powder_river_basin: ProximateSample) -> None:
    result = classify_sample(powder_river_basin)
    assert result.coal_class is CoalClass.SUB_BITUMINOUS
    # GCV_mmmf lands in the 8 300 – 9 500 band
    assert result.coal_rank is CoalRank.SUB_BITUMINOUS_C


def test_anthracite_classification() -> None:
    sample = ProximateSample(
        sample_id="PA-ANT",
        moisture_pct=4.0,
        ash_pct=10.0,
        volatile_matter_pct=5.0,
        fixed_carbon_pct=81.0,
        sulfur_pct=0.6,
        gcv=13_000.0,
        gcv_unit="btu_per_lb",
    )
    result = classify_sample(sample)
    assert result.coal_class is CoalClass.ANTHRACITIC
    assert result.coal_rank is CoalRank.ANTHRACITE


def test_lignite_b_very_low_gcv() -> None:
    sample = ProximateSample(
        sample_id="LIG-B",
        moisture_pct=40.0,
        ash_pct=10.0,
        volatile_matter_pct=30.0,
        fixed_carbon_pct=20.0,
        sulfur_pct=0.5,
        gcv=3000.0,
        gcv_unit="kcal_per_kg",  # 5400 Btu/lb
    )
    result = classify_sample(sample)
    assert result.coal_class is CoalClass.LIGNITIC
    assert result.coal_rank is CoalRank.LIGNITE_B


def test_high_volatile_a_bituminous_threshold() -> None:
    # GCV_mmmf target >= 14 000 Btu/lb → hvAb
    sample = ProximateSample(
        sample_id="HVA",
        moisture_pct=3.0,
        ash_pct=6.0,
        volatile_matter_pct=36.0,
        fixed_carbon_pct=55.0,
        sulfur_pct=0.8,
        gcv=14_400.0,
        gcv_unit="btu_per_lb",
        agglomerating=True,
    )
    result = classify_sample(sample)
    assert result.coal_rank is CoalRank.HIGH_VOLATILE_A_BITUMINOUS


# ---------------------------------------------------------------------------
# Agglomerating tie-break band (10 500 – 11 500 Btu/lb mmmf)
# ---------------------------------------------------------------------------


def test_agglomerating_tiebreak_goes_to_hvcb() -> None:
    # gcv=10 000 Btu/lb AR with A=8, S=0.6 → GCV_mmmf ≈ 10 952 Btu/lb,
    # which lands squarely in the 10 500-11 500 agglomeration band.
    sample = ProximateSample(
        sample_id="TIE-AGG",
        moisture_pct=10.0,
        ash_pct=8.0,
        volatile_matter_pct=38.0,
        fixed_carbon_pct=44.0,
        sulfur_pct=0.6,
        gcv=10_000.0,
        gcv_unit="btu_per_lb",
        agglomerating=True,
    )
    result = classify_sample(sample)
    assert 10_500.0 <= result.gcv_mmmf_btu_per_lb < 11_500.0
    assert result.coal_rank is CoalRank.HIGH_VOLATILE_C_BITUMINOUS


def test_nonagglomerating_tiebreak_goes_to_suba() -> None:
    sample = ProximateSample(
        sample_id="TIE-NON",
        moisture_pct=10.0,
        ash_pct=8.0,
        volatile_matter_pct=38.0,
        fixed_carbon_pct=44.0,
        sulfur_pct=0.6,
        gcv=10_000.0,
        gcv_unit="btu_per_lb",
        agglomerating=False,
    )
    result = classify_sample(sample)
    assert 10_500.0 <= result.gcv_mmmf_btu_per_lb < 11_500.0
    assert result.coal_rank is CoalRank.SUB_BITUMINOUS_A


# ---------------------------------------------------------------------------
# Parr mineral-matter corrections
# ---------------------------------------------------------------------------


def test_parr_fixed_carbon_dmmf_known_value() -> None:
    # M=2, A=8, S=0.6, FC=70  → denom = 100 - 2 - 8.64 - 0.33 = 89.03
    # numer = 70 - 0.09 = 69.91  → 78.524 %
    fc_dmmf = parr_fixed_carbon_dmmf(
        fixed_carbon_pct=70.0, moisture_pct=2.0, ash_pct=8.0, sulfur_pct=0.6
    )
    assert fc_dmmf == pytest.approx(78.524, abs=0.01)


def test_parr_gcv_mmmf_known_value() -> None:
    # GCV=14000 Btu/lb, A=8, S=0.6  → denom = 100 - 8.64 - 0.33 = 91.03
    # numer = 14000 - 30 = 13970 → 15 346 Btu/lb
    gcv_mmmf = parr_gcv_mmmf_btu_per_lb(14_000.0, ash_pct=8.0, sulfur_pct=0.6)
    assert gcv_mmmf == pytest.approx(15_346.0, abs=1.0)


def test_parr_denominator_guard_raises() -> None:
    # Totally unphysical inputs collapse the denominator
    with pytest.raises(ValueError, match="Parr denominator"):
        parr_fixed_carbon_dmmf(
            fixed_carbon_pct=1.0, moisture_pct=95.0, ash_pct=20.0, sulfur_pct=1.0
        )


def test_parr_gcv_denominator_guard_raises() -> None:
    with pytest.raises(ValueError, match="Parr GCV denominator"):
        parr_gcv_mmmf_btu_per_lb(10_000.0, ash_pct=95.0, sulfur_pct=1.0)


# ---------------------------------------------------------------------------
# Unit conversions
# ---------------------------------------------------------------------------


def test_kcal_to_btu_conversion() -> None:
    assert kcal_per_kg_to_btu_per_lb(5000.0) == pytest.approx(9000.0, abs=0.5)


def test_kcal_to_btu_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="kcal_per_kg must be > 0"):
        kcal_per_kg_to_btu_per_lb(0.0)


def test_gcv_in_btu_per_lb_passthrough() -> None:
    assert gcv_in_btu_per_lb(10_500.0, "btu_per_lb") == 10_500.0


def test_gcv_in_btu_per_lb_bad_unit_raises() -> None:
    with pytest.raises(ValueError, match="unit must be"):
        gcv_in_btu_per_lb(5000.0, "joules_per_gram")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_classify_rejects_non_sample_type() -> None:
    with pytest.raises(TypeError, match="ProximateSample"):
        classify_sample({"fc": 50})  # type: ignore[arg-type]


def test_classify_rejects_bad_gcv_unit() -> None:
    sample = ProximateSample(
        "X", 5.0, 10.0, 35.0, 50.0, 0.5, 12_000.0, gcv_unit="cal_per_g"
    )
    with pytest.raises(ValueError, match="gcv_unit"):
        classify_sample(sample)


def test_classify_rejects_negative_moisture() -> None:
    sample = ProximateSample("X", -1.0, 10.0, 40.0, 51.0, 0.5, 12_000.0)
    with pytest.raises(ValueError, match="moisture_pct must be >= 0"):
        classify_sample(sample)


def test_classify_rejects_ash_over_100() -> None:
    sample = ProximateSample("X", 5.0, 101.0, 0.0, 0.0, 0.0, 12_000.0)
    with pytest.raises(ValueError, match="ash_pct must be <= 100"):
        classify_sample(sample)


def test_classify_rejects_non_positive_gcv() -> None:
    sample = ProximateSample("X", 5.0, 10.0, 35.0, 50.0, 0.5, 0.0)
    with pytest.raises(ValueError, match="gcv must be > 0"):
        classify_sample(sample)


def test_classify_rejects_closure_failure() -> None:
    # M + A + VM + FC = 50 → well outside 100 ± 3
    sample = ProximateSample("X", 10.0, 10.0, 10.0, 20.0, 0.2, 12_000.0)
    with pytest.raises(ValueError, match="proximate closure failed"):
        classify_sample(sample)


def test_warning_raised_for_high_sulfur() -> None:
    # High but still physical sulfur
    sample = ProximateSample(
        "HI-S",
        moisture_pct=5.0,
        ash_pct=10.0,
        volatile_matter_pct=35.0,
        fixed_carbon_pct=50.0,
        sulfur_pct=6.0,
        gcv=12_500.0,
        gcv_unit="btu_per_lb",
    )
    result = classify_sample(sample)
    assert "sulfur_pct" in result.warning


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


def test_classify_batch_preserves_order(
    kalimantan_sub_bituminous: ProximateSample,
    bowen_basin_coking: ProximateSample,
    powder_river_basin: ProximateSample,
) -> None:
    batch = [kalimantan_sub_bituminous, bowen_basin_coking, powder_river_basin]
    results = classify_batch(batch)
    assert [r.sample_id for r in results] == [
        "KAL-001",
        "BOW-LVB",
        "PRB-01",
    ]


def test_classify_batch_empty_returns_empty_list() -> None:
    assert classify_batch([]) == []


def test_classify_batch_does_not_mutate_inputs(
    kalimantan_sub_bituminous: ProximateSample,
) -> None:
    before = (
        kalimantan_sub_bituminous.moisture_pct,
        kalimantan_sub_bituminous.ash_pct,
        kalimantan_sub_bituminous.gcv,
    )
    _ = classify_batch([kalimantan_sub_bituminous])
    after = (
        kalimantan_sub_bituminous.moisture_pct,
        kalimantan_sub_bituminous.ash_pct,
        kalimantan_sub_bituminous.gcv,
    )
    assert before == after


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_class_of_all_ranks_map() -> None:
    for rank in CoalRank:
        cls = class_of(rank)
        assert isinstance(cls, CoalClass)


def test_rank_rank_ordinal_monotonic() -> None:
    ordered = [
        CoalRank.LIGNITE_B,
        CoalRank.LIGNITE_A,
        CoalRank.SUB_BITUMINOUS_C,
        CoalRank.SUB_BITUMINOUS_B,
        CoalRank.SUB_BITUMINOUS_A,
        CoalRank.HIGH_VOLATILE_C_BITUMINOUS,
        CoalRank.HIGH_VOLATILE_B_BITUMINOUS,
        CoalRank.HIGH_VOLATILE_A_BITUMINOUS,
        CoalRank.MEDIUM_VOLATILE_BITUMINOUS,
        CoalRank.LOW_VOLATILE_BITUMINOUS,
        CoalRank.SEMI_ANTHRACITE,
        CoalRank.ANTHRACITE,
        CoalRank.META_ANTHRACITE,
    ]
    ordinals = [rank_rank_ordinal(r) for r in ordered]
    assert ordinals == list(range(len(ordered)))


def test_is_coking_candidate_true_for_lvb(
    bowen_basin_coking: ProximateSample,
) -> None:
    result = classify_sample(bowen_basin_coking)
    assert is_coking_candidate(result) is True


def test_is_coking_candidate_false_for_sub_bituminous(
    kalimantan_sub_bituminous: ProximateSample,
) -> None:
    result = classify_sample(kalimantan_sub_bituminous)
    assert is_coking_candidate(result) is False


# ---------------------------------------------------------------------------
# Parametrized rank sweep
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("moisture", "ash", "vm", "fc", "s", "gcv_btu", "agglom", "expected_rank"),
    [
        # Meta-anthracite: FC_dmmf >= 98
        (2.0, 5.0, 1.0, 92.0, 0.3, 14_000.0, False, CoalRank.META_ANTHRACITE),
        # Semi-anthracite: 86 <= FC_dmmf < 92
        (3.0, 8.0, 8.0, 81.0, 0.5, 14_500.0, False, CoalRank.SEMI_ANTHRACITE),
        # Medium-volatile bituminous: 69 <= FC_dmmf < 78
        (2.0, 8.0, 25.0, 65.0, 0.6, 14_800.0, True, CoalRank.MEDIUM_VOLATILE_BITUMINOUS),
        # High-volatile B bituminous: 13 000 <= GCV_mmmf < 14 000
        (5.0, 7.0, 37.0, 51.0, 0.7, 12_400.0, True, CoalRank.HIGH_VOLATILE_B_BITUMINOUS),
        # Sub-bituminous B: 9 500 <= GCV_mmmf < 10 500
        (22.0, 6.0, 36.0, 36.0, 0.4, 9_700.0, False, CoalRank.SUB_BITUMINOUS_B),
        # Lignite A: 6 300 <= GCV_mmmf < 8 300
        (35.0, 9.0, 32.0, 24.0, 0.5, 7_000.0, False, CoalRank.LIGNITE_A),
    ],
)
def test_parametrized_rank_spectrum(
    moisture: float,
    ash: float,
    vm: float,
    fc: float,
    s: float,
    gcv_btu: float,
    agglom: bool,
    expected_rank: CoalRank,
) -> None:
    sample = ProximateSample(
        sample_id=f"PAR-{expected_rank.value}",
        moisture_pct=moisture,
        ash_pct=ash,
        volatile_matter_pct=vm,
        fixed_carbon_pct=fc,
        sulfur_pct=s,
        gcv=gcv_btu,
        gcv_unit="btu_per_lb",
        agglomerating=agglom,
    )
    result = classify_sample(sample)
    assert result.coal_rank is expected_rank


# ---------------------------------------------------------------------------
# Immutability (coding-style rule)
# ---------------------------------------------------------------------------


def test_result_is_frozen(
    kalimantan_sub_bituminous: ProximateSample,
) -> None:
    result = classify_sample(kalimantan_sub_bituminous)
    assert isinstance(result, RankAnalysis)
    with pytest.raises((AttributeError, TypeError)):
        result.coal_rank = CoalRank.ANTHRACITE  # type: ignore[misc]


def test_sample_is_frozen(
    kalimantan_sub_bituminous: ProximateSample,
) -> None:
    with pytest.raises((AttributeError, TypeError)):
        kalimantan_sub_bituminous.moisture_pct = 99.0  # type: ignore[misc]
