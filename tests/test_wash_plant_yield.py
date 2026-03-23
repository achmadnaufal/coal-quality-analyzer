"""Unit tests for WashPlantYieldCalculator."""
import pytest
from src.wash_plant_yield_calculator import (
    WashPlantYieldCalculator, WashabilityFraction
)


@pytest.fixture
def fractions():
    return [
        WashabilityFraction(sg_float=1.30, mass_pct=12.5, ash_pct=4.2, cv_mj_kg=27.8),
        WashabilityFraction(sg_float=1.40, mass_pct=28.0, ash_pct=6.1, cv_mj_kg=26.9),
        WashabilityFraction(sg_float=1.50, mass_pct=18.5, ash_pct=9.8, cv_mj_kg=25.5),
        WashabilityFraction(sg_float=1.70, mass_pct=10.0, ash_pct=18.5, cv_mj_kg=21.0),
        WashabilityFraction(sg_float=2.00, mass_pct=31.0, ash_pct=68.0, cv_mj_kg=6.2),
    ]


@pytest.fixture
def calc(fractions):
    c = WashPlantYieldCalculator(feed_name="Pit-A ROM", feed_tph=450.0)
    c.load_fractions(fractions)
    return c


# --- WashabilityFraction validation ---

def test_invalid_sg():
    with pytest.raises(ValueError, match="sg_float"):
        WashabilityFraction(sg_float=0.9, mass_pct=10, ash_pct=5, cv_mj_kg=25)

def test_invalid_mass_pct():
    with pytest.raises(ValueError, match="mass_pct"):
        WashabilityFraction(sg_float=1.4, mass_pct=110, ash_pct=5, cv_mj_kg=25)

def test_invalid_ash_pct():
    with pytest.raises(ValueError, match="ash_pct"):
        WashabilityFraction(sg_float=1.4, mass_pct=20, ash_pct=-1, cv_mj_kg=25)

def test_invalid_cv():
    with pytest.raises(ValueError, match="cv_mj_kg"):
        WashabilityFraction(sg_float=1.4, mass_pct=20, ash_pct=5, cv_mj_kg=-10)


# --- WashPlantYieldCalculator setup ---

def test_invalid_feed_tph():
    with pytest.raises(ValueError, match="feed_tph"):
        WashPlantYieldCalculator(feed_tph=0)

def test_add_fraction(fractions):
    c = WashPlantYieldCalculator()
    c.add_fraction(fractions[0])
    assert len(c) == 1

def test_add_duplicate_sg_raises(calc, fractions):
    with pytest.raises(ValueError, match="already exists"):
        calc.add_fraction(fractions[0])

def test_fractions_sorted_by_sg(fractions):
    # Load in reverse order and check they're sorted
    c = WashPlantYieldCalculator()
    for f in reversed(fractions):
        c.add_fraction(f)
    sgs = [f.sg_float for f in c.fractions]
    assert sgs == sorted(sgs)

def test_no_fractions_raises():
    c = WashPlantYieldCalculator()
    with pytest.raises(RuntimeError, match="No washability"):
        c.calculate_yield(1.4)

def test_repr(calc):
    assert "WashPlantYieldCalculator" in repr(calc)
    assert "Pit-A ROM" in repr(calc)


# --- calculate_yield ---

def test_yield_at_sg_140_ideal(calc):
    result = calc.calculate_yield(1.40, separator="ideal")
    # At SG 1.40 ideal: fractions 1.30 + 1.40 = 12.5 + 28.0 = 40.5%
    assert abs(result["yield_pct"] - 40.5) < 1.0

def test_yield_product_discard_sum_to_100(calc):
    for sg in [1.30, 1.40, 1.50, 1.70]:
        result = calc.calculate_yield(sg, separator="ideal")
        assert abs(result["yield_pct"] + result["discard_pct"] - 100.0) < 0.01

def test_higher_sg_higher_yield(calc):
    r1 = calc.calculate_yield(1.40, separator="ideal")
    r2 = calc.calculate_yield(1.50, separator="ideal")
    assert r2["yield_pct"] > r1["yield_pct"]

def test_higher_sg_higher_ash(calc):
    r1 = calc.calculate_yield(1.40, separator="ideal")
    r2 = calc.calculate_yield(1.50, separator="ideal")
    assert r2["product_ash_pct"] > r1["product_ash_pct"]

def test_lower_sg_higher_cv(calc):
    r1 = calc.calculate_yield(1.40, separator="ideal")
    r2 = calc.calculate_yield(1.50, separator="ideal")
    assert r1["product_cv_mj_kg"] > r2["product_cv_mj_kg"]

def test_dmc_yield_vs_ideal(calc):
    r_ideal = calc.calculate_yield(1.50, separator="ideal")
    r_dmc = calc.calculate_yield(1.50, separator="dense_medium_cyclone")
    # DMC has Ep>0 → some misplacement, yield slightly different
    assert r_dmc["yield_pct"] != r_ideal["yield_pct"]

def test_result_keys(calc):
    result = calc.calculate_yield(1.50)
    for key in ["cut_sg", "yield_pct", "product_ash_pct", "product_cv_mj_kg",
                "clean_coal_tph", "discard_tph", "ep"]:
        assert key in result

def test_clean_coal_tph(calc):
    result = calc.calculate_yield(1.50, separator="ideal")
    expected_tph = round(450 * result["yield_pct"] / 100, 1)
    assert result["clean_coal_tph"] == expected_tph

def test_invalid_separator_raises(calc):
    with pytest.raises(ValueError, match="Unknown separator"):
        calc.calculate_yield(1.50, separator="flotation_cell")

def test_ep_override(calc):
    r = calc.calculate_yield(1.50, separator="custom", ep_override=0.05)
    assert r["ep"] == 0.05


# --- theoretical_yield_at_ash ---

def test_theoretical_yield_keys(calc):
    result = calc.theoretical_yield_at_ash(target_ash_pct=10.0)
    for key in ["target_ash_pct", "max_yield_pct", "best_sg", "actual_ash_pct"]:
        assert key in result

def test_lower_ash_target_lower_yield(calc):
    r8 = calc.theoretical_yield_at_ash(8.0)
    r12 = calc.theoretical_yield_at_ash(12.0)
    assert r12["max_yield_pct"] >= r8["max_yield_pct"]

def test_actual_ash_within_target(calc):
    target = 10.0
    result = calc.theoretical_yield_at_ash(target)
    if result["best_sg"] is not None:
        assert result["actual_ash_pct"] <= target


# --- yield_curve ---

def test_yield_curve_length(calc):
    curve = calc.yield_curve()
    assert len(curve) == len(calc.fractions)

def test_yield_curve_sorted_by_sg(calc):
    curve = calc.yield_curve()
    sgs = [r["cut_sg"] for r in curve]
    assert sgs == sorted(sgs)


# --- feed_quality_summary ---

def test_feed_quality_summary_keys(calc):
    summary = calc.feed_quality_summary()
    for key in ["feed_name", "feed_tph", "feed_ash_pct", "feed_cv_mj_kg", "n_fractions"]:
        assert key in summary

def test_feed_total_mass(calc):
    summary = calc.feed_quality_summary()
    assert abs(summary["total_mass_pct"] - 100.0) < 0.01  # fractions sum to 100%
