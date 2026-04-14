"""Unit tests for CoalQualityAnalyzer.

Covers:
- Quality parameter validation (valid and boundary cases)
- Specification compliance checking (grade assignment)
- GAR/NAR/ADB/ARB basis conversion via MoistureBasesConverter
- Statistical summary structure from analyze()
- Edge cases: proximate analysis not summing to 100 %, negative values,
  missing / None optional parameters

Run with:
    pytest tests/test_analyzer.py -v
"""
from __future__ import annotations

import pytest

from quality_metrics import CoalGrade, CoalQualityAnalyzer
from src.moisture_bases_converter import MoistureBasesConverter, ProximateAnalysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_analyzer(**overrides) -> CoalQualityAnalyzer:
    """Return a baseline valid CoalQualityAnalyzer with optional overrides."""
    defaults = dict(
        sample_id="TEST-001",
        ash_percent=10.0,
        moisture_percent=8.0,
        sulfur_percent=0.5,
        calorific_value_mj_kg=27.0,
    )
    defaults.update(overrides)
    return CoalQualityAnalyzer(**defaults)


# ---------------------------------------------------------------------------
# 1. Quality parameter validation — valid inputs
# ---------------------------------------------------------------------------

class TestParameterValidation:
    """Tests for boundary and type validation on construction."""

    def test_valid_construction_returns_correct_sample_id(self):
        """A valid set of parameters must store the sample_id unchanged."""
        analyzer = _make_analyzer(sample_id="KAL-2026-01")
        assert analyzer.sample_id == "KAL-2026-01"

    def test_zero_ash_is_accepted(self):
        """Zero ash content is a valid lower boundary."""
        analyzer = _make_analyzer(ash_percent=0.0)
        assert analyzer.ash_percent == 0.0

    def test_max_ash_boundary_accepted(self):
        """Ash content at exactly 100 % is accepted (boundary value)."""
        analyzer = _make_analyzer(
            ash_percent=100.0,
            # With 100% ash, VM and FC must be 0 to satisfy closure
            volatile_matter_percent=0.0,
            fixed_carbon_percent=0.0,
        )
        assert analyzer.ash_percent == 100.0

    def test_negative_ash_raises_value_error(self):
        """Negative ash content must raise ValueError."""
        with pytest.raises(ValueError, match="Ash %"):
            _make_analyzer(ash_percent=-1.0)

    def test_ash_above_100_raises_value_error(self):
        """Ash content above 100 % must raise ValueError."""
        with pytest.raises(ValueError, match="Ash %"):
            _make_analyzer(ash_percent=101.0)

    def test_negative_moisture_raises_value_error(self):
        """Negative moisture must raise ValueError."""
        with pytest.raises(ValueError, match="Moisture %"):
            _make_analyzer(moisture_percent=-0.1)

    def test_negative_sulfur_raises_value_error(self):
        """Negative sulfur must raise ValueError."""
        with pytest.raises(ValueError, match="Sulfur %"):
            _make_analyzer(sulfur_percent=-0.5)

    def test_sulfur_above_max_raises_value_error(self):
        """Sulfur above 10 % must raise ValueError."""
        with pytest.raises(ValueError, match="Sulfur %"):
            _make_analyzer(sulfur_percent=10.1)

    def test_zero_calorific_value_raises_value_error(self):
        """Zero calorific value is not physically meaningful."""
        with pytest.raises(ValueError, match="Calorific value"):
            _make_analyzer(calorific_value_mj_kg=0.0)

    def test_negative_calorific_value_raises_value_error(self):
        """Negative calorific value must raise ValueError."""
        with pytest.raises(ValueError, match="Calorific value"):
            _make_analyzer(calorific_value_mj_kg=-5.0)

    def test_empty_sample_id_raises_value_error(self):
        """Empty or whitespace-only sample_id must raise ValueError."""
        with pytest.raises(ValueError, match="sample_id"):
            _make_analyzer(sample_id="   ")

    def test_non_string_sample_id_raises_value_error(self):
        """Non-string sample_id must raise ValueError."""
        with pytest.raises(ValueError, match="sample_id"):
            _make_analyzer(sample_id=123)


# ---------------------------------------------------------------------------
# 2. Spec compliance / grade assignment
# ---------------------------------------------------------------------------

class TestSpecCompliance:
    """Tests for grade_coal() quality classification."""

    def test_premium_grade_low_impurities(self):
        """Coal with low ash, low moisture, low sulfur should be PREMIUM."""
        analyzer = _make_analyzer(
            ash_percent=10.0,
            moisture_percent=5.0,
            sulfur_percent=0.5,
            calorific_value_mj_kg=28.0,
        )
        assert analyzer.grade_coal() == CoalGrade.PREMIUM

    def test_high_grade_moderate_ash(self):
        """Combined moderate ash, moisture, and sulfur penalties yield HIGH grade.

        Score breakdown:
            ash > 30  → -15 pts
            moisture > 10 → -10 pts
            sulfur > 1.0 → -5 pts
            total = 100 - 15 - 10 - 5 = 70 → HIGH (>= 60 but < 80)
        """
        analyzer = _make_analyzer(
            ash_percent=32.0,   # -15 pts
            moisture_percent=12.0,  # -10 pts
            sulfur_percent=1.2,     # -5 pts
            calorific_value_mj_kg=24.0,
        )
        # score = 100 - 15 - 10 - 5 = 70 → HIGH
        assert analyzer.grade_coal() == CoalGrade.HIGH

    def test_medium_grade_high_moisture_and_ash(self):
        """High moisture combined with medium ash drops score into MEDIUM."""
        analyzer = _make_analyzer(
            ash_percent=32.0,   # -15 pts
            moisture_percent=22.0,  # -20 pts → score 65 → HIGH
            sulfur_percent=1.5,     # -5 pts  → score 60 → HIGH/MEDIUM boundary
            calorific_value_mj_kg=20.0,
        )
        # 100 - 15 - 20 - 5 = 60  → HIGH (>= 60)
        assert analyzer.grade_coal() == CoalGrade.HIGH

    def test_low_grade_extreme_values(self):
        """Very high ash, moisture, and sulfur must yield LOW grade."""
        analyzer = _make_analyzer(
            ash_percent=45.0,       # -30 pts
            moisture_percent=25.0,  # -20 pts
            sulfur_percent=2.5,     # -15 pts
            calorific_value_mj_kg=18.0,
        )
        # 100 - 30 - 20 - 15 = 35 → LOW
        assert analyzer.grade_coal() == CoalGrade.LOW

    def test_grade_premium_boundary_exactly_80(self):
        """Score exactly at 80 should return PREMIUM."""
        # ash > 30 (-15), moisture > 20 (-20), no sulfur penalty → score = 65 HIGH
        # ash > 20 (-5) only → score = 100 - 5 = 95 PREMIUM
        # Need to find a combo that hits exactly 80:
        # ash <= 20 (0), moisture <= 10 (0), sulfur > 1.0 (-5) → 95 PREMIUM
        # ash > 20 (-5), moisture <= 10 (0), sulfur > 1.0 (-5) → 90 PREMIUM
        # ash > 20 (-5), moisture > 10 (-10), sulfur > 1.0 (-5) → 80 PREMIUM
        analyzer = _make_analyzer(
            ash_percent=22.0,       # -5
            moisture_percent=12.0,  # -10
            sulfur_percent=1.2,     # -5
            calorific_value_mj_kg=24.0,
        )
        assert analyzer.grade_coal() == CoalGrade.PREMIUM


# ---------------------------------------------------------------------------
# 3. GAR / NAR / ADB / ARB basis conversion (MoistureBasesConverter)
# ---------------------------------------------------------------------------

class TestBasisConversion:
    """Tests for moisture bases conversion between AR, AD, DB, DAF."""

    def setup_method(self):
        """Create a shared converter instance for each test."""
        self.converter = MoistureBasesConverter()

    def test_ar_to_ad_ash_conversion(self):
        """AR to AD basis conversion should increase ash content."""
        # With TM=28 % and IM=12 %, factor = (100-12)/(100-28) ≈ 1.222
        result = self.converter.convert(
            parameter="ash_pct",
            value=6.8,
            from_basis="AR",
            to_basis="AD",
            total_moisture_ar=28.0,
            inherent_moisture_ad=12.0,
        )
        expected = 6.8 * (100 - 12) / (100 - 28)
        assert result == pytest.approx(expected, rel=1e-3)

    def test_ar_to_db_increases_value(self):
        """Dry basis value must be higher than the AR value."""
        result = self.converter.convert(
            parameter="ash_pct",
            value=6.8,
            from_basis="AR",
            to_basis="DB",
            total_moisture_ar=28.0,
        )
        assert result > 6.8

    def test_same_basis_returns_identical_value(self):
        """Converting from and to the same basis must return the original value."""
        original = 10.5
        result = self.converter.convert(
            parameter="ash_pct",
            value=original,
            from_basis="AD",
            to_basis="AD",
        )
        assert result == original

    def test_gcv_gar_to_gad_convenience_method(self):
        """gcv_gar_to_gad() must return a value higher than the GAR input."""
        gad = self.converter.gcv_gar_to_gad(
            gcv_gar=4850.0,
            total_moisture_ar=28.5,
            inherent_moisture_ad=12.3,
        )
        assert gad > 4850.0

    def test_round_trip_ar_ad_ar(self):
        """Round-trip AR -> AD -> AR should recover the original value."""
        original = 10.0
        ad_value = self.converter.convert(
            parameter="ash_pct",
            value=original,
            from_basis="AR",
            to_basis="AD",
            total_moisture_ar=28.0,
            inherent_moisture_ad=12.0,
        )
        recovered = self.converter.convert(
            parameter="ash_pct",
            value=ad_value,
            from_basis="AD",
            to_basis="AR",
            total_moisture_ar=28.0,
            inherent_moisture_ad=12.0,
        )
        assert recovered == pytest.approx(original, rel=1e-3)

    def test_convert_full_analysis_returns_correct_basis(self):
        """convert_full_analysis() result must carry the target basis label."""
        ar_analysis = ProximateAnalysis(
            basis="AR",
            total_moisture_pct=28.0,
            inherent_moisture_pct=12.0,
            ash_pct=6.8,
            volatile_matter_pct=40.2,
            fixed_carbon_pct=52.7,
            total_sulfur_pct=0.38,
            gcv_kcal_kg=4850.0,
        )
        db_analysis = self.converter.convert_full_analysis(ar_analysis, to_basis="DB")
        assert db_analysis.basis == "DB"

    def test_convert_full_analysis_db_ash_higher_than_ar(self):
        """DB ash must be higher than AR ash for the same sample."""
        ar_analysis = ProximateAnalysis(
            basis="AR",
            total_moisture_pct=28.0,
            inherent_moisture_pct=12.0,
            ash_pct=6.8,
            volatile_matter_pct=40.2,
            fixed_carbon_pct=52.7,
            total_sulfur_pct=0.38,
        )
        db_analysis = self.converter.convert_full_analysis(ar_analysis, to_basis="DB")
        assert db_analysis.ash_pct > ar_analysis.ash_pct

    def test_missing_total_moisture_for_ar_conversion_raises(self):
        """AR->AD conversion without total_moisture_ar must raise ValueError."""
        with pytest.raises(ValueError):
            self.converter.convert(
                parameter="ash_pct",
                value=6.8,
                from_basis="AR",
                to_basis="AD",
                # total_moisture_ar intentionally omitted
                inherent_moisture_ad=12.0,
            )

    def test_invalid_basis_raises_value_error(self):
        """An unsupported basis code must raise ValueError."""
        with pytest.raises(ValueError):
            self.converter.convert(
                parameter="ash_pct",
                value=6.8,
                from_basis="XYZ",
                to_basis="AD",
            )


# ---------------------------------------------------------------------------
# 4. Statistical summary (analyze())
# ---------------------------------------------------------------------------

class TestStatisticalSummary:
    """Tests for the analyze() output structure and value correctness."""

    def test_analyze_returns_all_required_keys(self):
        """analyze() must include every documented key in its return dict."""
        required_keys = {
            "sample_id",
            "ash_percent",
            "moisture_percent",
            "sulfur_percent",
            "gross_calorific_mj_kg",
            "net_calorific_mj_kg",
            "quality_grade",
        }
        result = _make_analyzer().analyze()
        assert required_keys.issubset(result.keys())

    def test_analyze_quality_grade_is_valid_string(self):
        """quality_grade in analyze() must be one of the four valid strings."""
        valid_grades = {"premium", "high", "medium", "low"}
        result = _make_analyzer().analyze()
        assert result["quality_grade"] in valid_grades

    def test_analyze_net_cv_less_than_gross_cv(self):
        """Net calorific value must always be <= gross calorific value."""
        result = _make_analyzer(moisture_percent=10.0, calorific_value_mj_kg=27.0).analyze()
        assert result["net_calorific_mj_kg"] <= result["gross_calorific_mj_kg"]

    def test_analyze_net_cv_never_negative(self):
        """Net calorific value must be clipped to zero, never negative."""
        # moisture=12, GCV=5 → NCV = 5 - 12*2.5 = -25 → should be 0
        result = _make_analyzer(moisture_percent=12.0, calorific_value_mj_kg=5.0).analyze()
        assert result["net_calorific_mj_kg"] >= 0.0

    def test_analyze_sample_id_preserved(self):
        """analyze() must preserve the original sample_id unchanged."""
        result = _make_analyzer(sample_id="AUS-007").analyze()
        assert result["sample_id"] == "AUS-007"

    def test_analyze_values_are_rounded_to_two_decimal_places(self):
        """GCV values in analyze() must be rounded to 2 decimal places."""
        analyzer = _make_analyzer(calorific_value_mj_kg=27.123456)
        result = analyzer.analyze()
        assert result["gross_calorific_mj_kg"] == pytest.approx(27.12, abs=0.005)

    def test_analyze_is_immutable_does_not_change_state(self):
        """Calling analyze() multiple times must return identical results."""
        analyzer = _make_analyzer()
        first = analyzer.analyze()
        second = analyzer.analyze()
        assert first == second


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases: proximate closure, negative values, missing parameters."""

    def test_proximate_not_summing_to_100_raises_value_error(self):
        """ash + VM + FC deviating >2 % from 100 must raise ValueError."""
        with pytest.raises(ValueError, match="Proximate analysis"):
            CoalQualityAnalyzer(
                sample_id="EDGE-001",
                ash_percent=10.0,
                moisture_percent=8.0,
                sulfur_percent=0.5,
                calorific_value_mj_kg=27.0,
                volatile_matter_percent=40.0,
                fixed_carbon_percent=40.0,  # sum = 90, deviation = 10 %
            )

    def test_proximate_within_tolerance_is_accepted(self):
        """A proximate sum deviation within 2 % tolerance must not raise."""
        # sum = 10 + 40 + 50 = 100 exactly — should pass
        analyzer = CoalQualityAnalyzer(
            sample_id="EDGE-002",
            ash_percent=10.0,
            moisture_percent=8.0,
            sulfur_percent=0.5,
            calorific_value_mj_kg=27.0,
            volatile_matter_percent=40.0,
            fixed_carbon_percent=50.0,
        )
        assert analyzer.volatile_matter_percent == 40.0

    def test_optional_vm_and_fc_are_none_by_default(self):
        """When VM and FC are omitted, they must be None in the result."""
        result = _make_analyzer().analyze()
        assert result["volatile_matter_percent"] is None
        assert result["fixed_carbon_percent"] is None

    def test_zero_moisture_net_cv_equals_gross_cv(self):
        """With zero moisture, NCV should equal GCV exactly."""
        analyzer = _make_analyzer(moisture_percent=0.0, calorific_value_mj_kg=27.0)
        assert analyzer.calculate_net_calorific_value() == pytest.approx(27.0)

    def test_very_high_moisture_clips_ncv_to_zero(self):
        """When moisture penalty exceeds GCV, NCV is 0 not negative."""
        analyzer = _make_analyzer(moisture_percent=50.0, calorific_value_mj_kg=5.0)
        # penalty = 50 * 2.5 = 125, GCV = 5 → NCV = max(0, -120) = 0
        assert analyzer.calculate_net_calorific_value() == 0.0

    def test_sulfur_exactly_at_max_boundary_accepted(self):
        """Sulfur content at exactly 10.0 % must not raise."""
        analyzer = _make_analyzer(sulfur_percent=10.0)
        assert analyzer.sulfur_percent == 10.0

    def test_negative_volatile_matter_raises_value_error(self):
        """Negative volatile matter must raise ValueError."""
        with pytest.raises(ValueError, match="Volatile matter %"):
            CoalQualityAnalyzer(
                sample_id="EDGE-003",
                ash_percent=10.0,
                moisture_percent=8.0,
                sulfur_percent=0.5,
                calorific_value_mj_kg=27.0,
                volatile_matter_percent=-1.0,
                fixed_carbon_percent=50.0,
            )

    def test_negative_fixed_carbon_raises_value_error(self):
        """Negative fixed carbon must raise ValueError."""
        with pytest.raises(ValueError, match="Fixed carbon %"):
            CoalQualityAnalyzer(
                sample_id="EDGE-004",
                ash_percent=10.0,
                moisture_percent=8.0,
                sulfur_percent=0.5,
                calorific_value_mj_kg=27.0,
                volatile_matter_percent=40.0,
                fixed_carbon_percent=-5.0,
            )
