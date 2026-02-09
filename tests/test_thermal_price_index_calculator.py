"""Unit tests for ThermalPriceIndexCalculator."""

import pytest
from src.thermal_price_index_calculator import (
    ThermalPriceIndexCalculator,
    CoalPriceAdjustment,
    BlendedIndexResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _on_spec_quality():
    """Quality matching GAR5500 reference spec exactly."""
    return {
        "calorific_value_kcal_gar": 5500.0,
        "total_moisture_pct": 20.0,
        "ash_pct": 8.0,
        "total_sulphur_pct": 0.5,
    }


@pytest.fixture
def calc():
    return ThermalPriceIndexCalculator(reference_spec="GAR5500")


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------

class TestInstantiation:
    def test_default_init(self):
        c = ThermalPriceIndexCalculator()
        assert c is not None

    def test_gar5000_init(self):
        c = ThermalPriceIndexCalculator(reference_spec="GAR5000")
        assert c is not None

    def test_nar6000_init(self):
        c = ThermalPriceIndexCalculator(reference_spec="NAR6000")
        assert c is not None

    def test_invalid_spec_raises(self):
        with pytest.raises(ValueError, match="Unknown reference_spec"):
            ThermalPriceIndexCalculator(reference_spec="GAR9999")


# ---------------------------------------------------------------------------
# calculate_adjustment() — basic
# ---------------------------------------------------------------------------

class TestCalculateAdjustmentBasic:
    def test_returns_price_adjustment(self, calc):
        adj = calc.calculate_adjustment("C1", 85.0, _on_spec_quality())
        assert isinstance(adj, CoalPriceAdjustment)

    def test_on_spec_zero_cv_adjustment(self, calc):
        adj = calc.calculate_adjustment("C1", 85.0, _on_spec_quality())
        assert abs(adj.cv_adjustment_usd) < 0.001

    def test_on_spec_zero_moisture_adjustment(self, calc):
        adj = calc.calculate_adjustment("C1", 85.0, _on_spec_quality())
        assert abs(adj.moisture_adjustment_usd) < 0.001

    def test_on_spec_zero_total_adjustment(self, calc):
        adj = calc.calculate_adjustment("C1", 85.0, _on_spec_quality())
        assert abs(adj.total_quality_adjustment_usd) < 0.001

    def test_on_spec_realised_equals_reference(self, calc):
        adj = calc.calculate_adjustment("C1", 85.0, _on_spec_quality())
        assert abs(adj.realised_price_usd_per_tonne - 85.0) < 0.001

    def test_cargo_id_preserved(self, calc):
        adj = calc.calculate_adjustment("BV-2026-001", 85.0, _on_spec_quality())
        assert adj.cargo_id == "BV-2026-001"

    def test_reference_spec_preserved(self, calc):
        adj = calc.calculate_adjustment("C1", 85.0, _on_spec_quality())
        assert adj.reference_spec == "GAR5500"

    def test_zero_reference_price_raises(self, calc):
        with pytest.raises(ValueError, match="reference_price_usd_per_tonne"):
            calc.calculate_adjustment("C1", 0, _on_spec_quality())

    def test_negative_reference_price_raises(self, calc):
        with pytest.raises(ValueError):
            calc.calculate_adjustment("C1", -85.0, _on_spec_quality())


# ---------------------------------------------------------------------------
# CV adjustment
# ---------------------------------------------------------------------------

class TestCVAdjustment:
    def test_higher_cv_positive_adjustment(self, calc):
        quality = _on_spec_quality()
        quality["calorific_value_kcal_gar"] = 5700.0  # above reference 5500
        adj = calc.calculate_adjustment("C1", 85.0, quality)
        assert adj.cv_adjustment_usd > 0

    def test_lower_cv_negative_adjustment(self, calc):
        quality = _on_spec_quality()
        quality["calorific_value_kcal_gar"] = 5300.0  # below reference 5500
        adj = calc.calculate_adjustment("C1", 85.0, quality)
        assert adj.cv_adjustment_usd < 0

    def test_cv_adjustment_proportional(self, calc):
        quality = _on_spec_quality()
        quality["calorific_value_kcal_gar"] = 5500.0 * 1.1  # 10% above
        adj = calc.calculate_adjustment("C1", 100.0, quality)
        expected = 100.0 * 0.1  # 10% of reference price
        assert abs(adj.cv_adjustment_usd - expected) < 0.01

    def test_missing_cv_no_adjustment(self, calc):
        quality = {"total_moisture_pct": 20.0, "ash_pct": 8.0, "total_sulphur_pct": 0.5}
        adj = calc.calculate_adjustment("C1", 85.0, quality)
        assert adj.cv_adjustment_usd == 0.0


# ---------------------------------------------------------------------------
# Quality adjustments
# ---------------------------------------------------------------------------

class TestQualityAdjustments:
    def test_higher_moisture_penalty(self, calc):
        quality = _on_spec_quality()
        quality["total_moisture_pct"] = 22.0  # 2% above 20% spec
        adj = calc.calculate_adjustment("C1", 85.0, quality)
        assert adj.moisture_adjustment_usd < 0

    def test_lower_moisture_bonus(self, calc):
        quality = _on_spec_quality()
        quality["total_moisture_pct"] = 18.0  # 2% below spec
        adj = calc.calculate_adjustment("C1", 85.0, quality)
        assert adj.moisture_adjustment_usd > 0

    def test_higher_ash_penalty(self, calc):
        quality = _on_spec_quality()
        quality["ash_pct"] = 10.0  # 2% above 8% spec
        adj = calc.calculate_adjustment("C1", 85.0, quality)
        assert adj.ash_adjustment_usd < 0

    def test_lower_ash_bonus(self, calc):
        quality = _on_spec_quality()
        quality["ash_pct"] = 6.0  # 2% below spec
        adj = calc.calculate_adjustment("C1", 85.0, quality)
        assert adj.ash_adjustment_usd > 0

    def test_higher_sulphur_penalty(self, calc):
        quality = _on_spec_quality()
        quality["total_sulphur_pct"] = 0.7  # 0.2% above 0.5% spec
        adj = calc.calculate_adjustment("C1", 85.0, quality)
        assert adj.sulphur_adjustment_usd < 0

    def test_lower_sulphur_bonus(self, calc):
        quality = _on_spec_quality()
        quality["total_sulphur_pct"] = 0.3  # 0.2% below spec
        adj = calc.calculate_adjustment("C1", 85.0, quality)
        assert adj.sulphur_adjustment_usd > 0

    def test_total_adjustment_sums_correctly(self, calc):
        quality = _on_spec_quality()
        quality["total_moisture_pct"] = 22.0
        quality["ash_pct"] = 9.0
        adj = calc.calculate_adjustment("C1", 85.0, quality)
        expected = (adj.cv_adjustment_usd + adj.moisture_adjustment_usd
                    + adj.ash_adjustment_usd + adj.sulphur_adjustment_usd)
        assert abs(adj.total_quality_adjustment_usd - expected) < 0.001

    def test_realised_price_equals_reference_plus_adjustments(self, calc):
        quality = _on_spec_quality()
        quality["ash_pct"] = 10.0
        adj = calc.calculate_adjustment("C1", 85.0, quality)
        assert abs(adj.realised_price_usd_per_tonne
                   - (85.0 + adj.total_quality_adjustment_usd)) < 0.001

    def test_missing_quality_param_zero_adjustment(self, calc):
        quality = {"calorific_value_kcal_gar": 5500.0}
        adj = calc.calculate_adjustment("C1", 85.0, quality)
        assert adj.moisture_adjustment_usd == 0.0
        assert adj.ash_adjustment_usd == 0.0


# ---------------------------------------------------------------------------
# blend_indices()
# ---------------------------------------------------------------------------

class TestBlendIndices:
    def test_returns_blended_result(self, calc):
        result = calc.blend_indices({"newcastle": 95.0, "ici3": 72.0})
        assert isinstance(result, BlendedIndexResult)

    def test_equal_weights_average(self, calc):
        result = calc.blend_indices({"A": 100.0, "B": 80.0})
        assert abs(result.blended_price_usd_per_tonne - 90.0) < 0.001

    def test_custom_weights_applied(self, calc):
        result = calc.blend_indices(
            {"newcastle": 100.0, "ici3": 80.0},
            weights={"newcastle": 0.7, "ici3": 0.3},
        )
        expected = 100.0 * 0.7 + 80.0 * 0.3
        assert abs(result.blended_price_usd_per_tonne - expected) < 0.001

    def test_single_index_returns_same_price(self, calc):
        result = calc.blend_indices({"newcastle": 92.5})
        assert abs(result.blended_price_usd_per_tonne - 92.5) < 0.001

    def test_empty_indices_raises(self, calc):
        with pytest.raises(ValueError, match="index_prices must not be empty"):
            calc.blend_indices({})

    def test_negative_price_raises(self, calc):
        with pytest.raises(ValueError, match="must be > 0"):
            calc.blend_indices({"A": -10.0})


# ---------------------------------------------------------------------------
# convert_price_basis()
# ---------------------------------------------------------------------------

class TestConvertPriceBasis:
    def test_gar_to_nar_reduces_price(self, calc):
        nar_price = calc.convert_price_basis(100.0, "GAR", "NAR")
        assert nar_price < 100.0

    def test_nar_to_gar_increases_price(self, calc):
        gar_price = calc.convert_price_basis(90.0, "NAR", "GAR")
        assert gar_price > 90.0

    def test_same_basis_no_change(self, calc):
        result = calc.convert_price_basis(90.0, "GAR", "GAR")
        assert result == 90.0

    def test_invalid_basis_raises(self, calc):
        with pytest.raises(ValueError, match="basis must be"):
            calc.convert_price_basis(90.0, "FOB", "NAR")

    def test_negative_price_raises(self, calc):
        with pytest.raises(ValueError, match="price must be > 0"):
            calc.convert_price_basis(-10.0, "GAR", "NAR")


# ---------------------------------------------------------------------------
# batch operations
# ---------------------------------------------------------------------------

class TestBatchOperations:
    def test_batch_adjustments_count(self, calc):
        cargoes = [
            {"cargo_id": f"C{i}", "reference_price_usd_per_tonne": 85.0,
             "actual_quality": _on_spec_quality()}
            for i in range(5)
        ]
        results = calc.batch_adjustments(cargoes)
        assert len(results) == 5

    def test_batch_summary_count(self, calc):
        cargoes = [
            {"cargo_id": f"C{i}", "reference_price_usd_per_tonne": 85.0,
             "actual_quality": _on_spec_quality()}
            for i in range(3)
        ]
        results = calc.batch_adjustments(cargoes)
        summary = calc.batch_summary(results)
        assert summary["count"] == 3

    def test_empty_batch_summary_returns_empty(self, calc):
        summary = calc.batch_summary([])
        assert summary == {}
