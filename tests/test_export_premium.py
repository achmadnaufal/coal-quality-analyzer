"""
Unit tests for CoalQualityAnalyzer export premium and compliance methods.
"""
import pytest
from quality_metrics import CoalQualityAnalyzer


class TestExportPremium:
    """Tests for calculate_export_premium method."""

    def test_at_benchmark_returns_base_price(self):
        """Coal exactly at benchmark spec should return base price (no GCV adj)."""
        result = CoalQualityAnalyzer.calculate_export_premium(
            gcv_mj_kg=25.0, ash_pct=10.0, sulfur_pct=0.8,
            moisture_pct=12.0, benchmark_price_usd=100.0, benchmark_gcv=25.0,
        )
        assert result["total_adjustment_usd"] == 0.0
        assert result["adjusted_price_usd_per_tonne"] == 100.0

    def test_high_gcv_gives_premium(self):
        """Coal with GCV above benchmark should yield premium."""
        result = CoalQualityAnalyzer.calculate_export_premium(
            gcv_mj_kg=27.0, ash_pct=8.0, sulfur_pct=0.5,
            moisture_pct=8.0, benchmark_price_usd=100.0, benchmark_gcv=25.0,
        )
        assert result["premium_or_discount"] == "premium"
        assert result["adjusted_price_usd_per_tonne"] > 100.0

    def test_low_quality_gives_discount(self):
        """Coal with poor specs (high ash/sulfur) should be discounted."""
        result = CoalQualityAnalyzer.calculate_export_premium(
            gcv_mj_kg=20.0, ash_pct=18.0, sulfur_pct=2.0,
            moisture_pct=18.0, benchmark_price_usd=100.0, benchmark_gcv=25.0,
        )
        assert result["premium_or_discount"] == "discount"
        assert result["adjusted_price_usd_per_tonne"] < 100.0

    def test_invalid_gcv_raises(self):
        """Zero or negative GCV must raise ValueError."""
        with pytest.raises(ValueError, match="gcv_mj_kg must be positive"):
            CoalQualityAnalyzer.calculate_export_premium(
                gcv_mj_kg=0.0, ash_pct=10.0, sulfur_pct=0.8, moisture_pct=10.0
            )

    def test_invalid_benchmark_price_raises(self):
        """Zero benchmark price must raise ValueError."""
        with pytest.raises(ValueError, match="benchmark_price_usd must be positive"):
            CoalQualityAnalyzer.calculate_export_premium(
                gcv_mj_kg=25.0, ash_pct=10.0, sulfur_pct=0.8,
                moisture_pct=10.0, benchmark_price_usd=0.0,
            )

    def test_returns_all_keys(self):
        """Result dict must contain all expected keys."""
        result = CoalQualityAnalyzer.calculate_export_premium(
            gcv_mj_kg=24.5, ash_pct=9.2, sulfur_pct=0.7, moisture_pct=11.5
        )
        expected_keys = {
            "adjusted_price_usd_per_tonne", "benchmark_price_usd_per_tonne",
            "total_adjustment_usd", "premium_or_discount",
            "quality_adjustments", "calorific_ratio",
        }
        assert expected_keys.issubset(set(result.keys()))


class TestSpecificationCompliance:
    """Tests for check_specification_compliance method."""

    def test_fully_compliant(self):
        params = {"gcv": 25.0, "ash": 10.0, "sulfur": 0.7}
        spec = {"gcv": {"min": 23.0}, "ash": {"max": 12.0}, "sulfur": {"max": 1.0}}
        result = CoalQualityAnalyzer.check_specification_compliance(params, spec)
        assert result["compliant"] is True
        assert result["compliance_rate"] == 100.0

    def test_fails_on_high_ash(self):
        params = {"gcv": 25.0, "ash": 15.0, "sulfur": 0.7}
        spec = {"gcv": {"min": 23.0}, "ash": {"max": 12.0}, "sulfur": {"max": 1.0}}
        result = CoalQualityAnalyzer.check_specification_compliance(params, spec)
        assert result["compliant"] is False
        assert result["parameters"]["ash"]["compliant"] is False

    def test_empty_params_raises(self):
        with pytest.raises(ValueError, match="params dict cannot be empty"):
            CoalQualityAnalyzer.check_specification_compliance({}, {"ash": {"max": 12}})

    def test_empty_spec_raises(self):
        with pytest.raises(ValueError, match="spec dict cannot be empty"):
            CoalQualityAnalyzer.check_specification_compliance({"ash": 10.0}, {})

    def test_missing_parameter_marked(self):
        params = {"gcv": 25.0}
        spec = {"gcv": {"min": 23.0}, "ash": {"max": 12.0}}
        result = CoalQualityAnalyzer.check_specification_compliance(params, spec)
        assert result["parameters"]["ash"]["status"] == "missing"
        assert result["compliant"] is False
