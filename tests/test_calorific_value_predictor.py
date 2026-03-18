"""
Unit tests for the calorific value predictor and coal rank classifier.
"""

import pytest
from src.calorific_value_predictor import (
    ProximateAnalysis,
    UltimateAnalysis,
    CalorificValuePredictor,
)


# ---------------------------------------------------------------------------
# ProximateAnalysis tests
# ---------------------------------------------------------------------------


class TestProximateAnalysis:
    def test_valid_creation_auto_fc(self):
        prox = ProximateAnalysis(12.5, 6.2, 38.4, sample_id="S-001")
        assert prox.fixed_carbon_pct == pytest.approx(42.9, abs=0.1)

    def test_valid_creation_explicit_fc(self):
        prox = ProximateAnalysis(12.5, 6.2, 38.4, 42.9, "S-001")
        assert prox.fixed_carbon_pct == pytest.approx(42.9)

    def test_sum_not_100_raises(self):
        with pytest.raises(ValueError, match="sum to"):
            ProximateAnalysis(12.5, 6.2, 38.4, 10.0)  # total ~67.1%

    def test_moisture_above_100_raises(self):
        with pytest.raises(ValueError, match="moisture_pct"):
            ProximateAnalysis(110.0, 6.2, 38.4)

    def test_daf_volatile_matter(self):
        prox = ProximateAnalysis(10.0, 5.0, 40.0, 45.0)
        # daf basis = 100 - 10 - 5 = 85; VM_daf = 40/85*100 ≈ 47.06
        assert prox.dry_ash_free_volatile_matter == pytest.approx(40.0 / 85.0 * 100, rel=1e-3)

    def test_fc_dmmf(self):
        prox = ProximateAnalysis(10.0, 5.0, 40.0, 45.0)
        assert prox.dry_mineral_matter_free_fc > 0

    def test_negative_moisture_raises(self):
        with pytest.raises(ValueError, match="moisture_pct"):
            ProximateAnalysis(-5.0, 6.2, 38.4)


# ---------------------------------------------------------------------------
# UltimateAnalysis tests
# ---------------------------------------------------------------------------


class TestUltimateAnalysis:
    def test_valid_creation(self):
        ult = UltimateAnalysis(67.2, 4.8, 14.3, 1.1, 0.5, "S-001")
        assert ult.carbon_pct == 67.2

    def test_sum_too_high_raises(self):
        with pytest.raises(ValueError, match="exceeds 105%"):
            UltimateAnalysis(70.0, 10.0, 20.0, 8.0, 5.0)  # sum = 113%

    def test_negative_carbon_raises(self):
        with pytest.raises(ValueError, match="carbon_pct"):
            UltimateAnalysis(-10.0, 4.8, 14.3, 1.1, 0.5)

    def test_sulphur_above_100_raises(self):
        with pytest.raises(ValueError, match="sulphur_pct"):
            UltimateAnalysis(67.0, 4.8, 14.3, 1.1, 150.0)


# ---------------------------------------------------------------------------
# CalorificValuePredictor tests
# ---------------------------------------------------------------------------


@pytest.fixture
def predictor():
    return CalorificValuePredictor(prefer_method="boie")


@pytest.fixture
def ult():
    return UltimateAnalysis(67.2, 4.8, 14.3, 1.1, 0.5, "S-001")


@pytest.fixture
def prox():
    return ProximateAnalysis(12.5, 6.2, 38.4, 42.9, "S-001")


class TestCalorificValuePredictor:
    def test_invalid_method_raises(self):
        with pytest.raises(ValueError, match="prefer_method must be one of"):
            CalorificValuePredictor(prefer_method="invalid")

    def test_boie_gcv_positive(self, predictor, ult):
        gcv = predictor.predict_gcv_from_ultimate(ult)
        assert gcv > 0

    def test_boie_gcv_reasonable_range(self, predictor, ult):
        gcv = predictor.predict_gcv_from_ultimate(ult)
        # Indonesian sub-bituminous to bituminous: 4000-8000 kcal/kg
        assert 4000 <= gcv <= 9000

    def test_dulong_gcv_positive(self, ult):
        predictor = CalorificValuePredictor(prefer_method="dulong")
        gcv = predictor.predict_gcv_from_ultimate(ult)
        assert gcv > 0

    def test_majumdar_gcv_positive(self, predictor, prox):
        gcv = predictor.predict_gcv_from_proximate(prox)
        assert gcv > 0

    def test_majumdar_gcv_floor_at_zero(self, predictor):
        # Extreme high-moisture, high-ash coal
        prox = ProximateAnalysis(60.0, 30.0, 5.0, 5.0)
        gcv = predictor.predict_gcv_from_proximate(prox)
        assert gcv >= 0.0

    def test_higher_carbon_means_higher_gcv(self, predictor):
        ult_low = UltimateAnalysis(50.0, 4.0, 15.0, 1.0, 0.5)
        ult_high = UltimateAnalysis(75.0, 4.0, 5.0, 1.0, 0.5)
        assert predictor.predict_gcv_from_ultimate(ult_high) > predictor.predict_gcv_from_ultimate(ult_low)

    def test_coal_rank_anthracite(self, predictor):
        rank = predictor.classify_coal_rank_astm(8500, 95.0)
        assert rank == "Anthracite"

    def test_coal_rank_lignite(self, predictor):
        rank = predictor.classify_coal_rank_astm(2500, 30.0)
        assert rank == "Lignite B"

    def test_coal_rank_subbituminous(self, predictor):
        rank = predictor.classify_coal_rank_astm(5200, 45.0)
        assert "Sub-bituminous" in rank or "bituminous" in rank

    def test_validate_lab_pass(self, predictor):
        result = predictor.validate_lab_result(6200, 6300, tolerance_pct=5.0)
        assert result["flag"] == "PASS"
        assert result["within_tolerance"] is True

    def test_validate_lab_fail(self, predictor):
        result = predictor.validate_lab_result(5000, 6300, tolerance_pct=5.0)
        assert result["flag"] == "FAIL"
        assert result["within_tolerance"] is False

    def test_validate_lab_warning(self, predictor):
        result = predictor.validate_lab_result(6000, 6300, tolerance_pct=3.0)
        assert result["flag"] in ("WARNING", "FAIL")

    def test_validate_lab_negative_reported_raises(self, predictor):
        with pytest.raises(ValueError, match="reported_gcv cannot be negative"):
            predictor.validate_lab_result(-100, 6300)

    def test_validate_lab_zero_predicted_raises(self, predictor):
        with pytest.raises(ValueError, match="predicted_gcv must be positive"):
            predictor.validate_lab_result(6200, 0.0)

    def test_batch_predict_returns_all(self, predictor, prox, ult):
        results = predictor.batch_predict([
            ("S-001", prox, None),
            ("S-002", None, ult),
        ])
        assert len(results) == 2

    def test_batch_predict_keys(self, predictor, prox):
        results = predictor.batch_predict([("S-001", prox, None)])
        expected = {"sample_id", "predicted_gcv_kcal_kg", "method_used", "coal_rank", "fc_dmmf_pct"}
        assert expected.issubset(results[0].keys())

    def test_batch_predict_no_analysis_raises(self, predictor):
        with pytest.raises(ValueError, match="at least one analysis"):
            predictor.batch_predict([("S-bad", None, None)])

    def test_batch_predict_rank_is_string(self, predictor, prox):
        results = predictor.batch_predict([("S-001", prox, None)])
        assert isinstance(results[0]["coal_rank"], str)
        assert len(results[0]["coal_rank"]) > 0
