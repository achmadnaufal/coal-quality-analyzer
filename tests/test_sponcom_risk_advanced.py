"""Tests for AdvancedSponcomRiskClassifier."""
import math
import pytest
from src.spontaneous_combustion_risk_advanced import (
    AdvancedSponcomRiskClassifier,
    CoalProximateData,
    SponcomCategory,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def subbit_sample():
    return CoalProximateData(
        sample_id="KTM-22A",
        moisture_pct=35.0,
        volatile_matter_pct=42.0,
        ash_pct=8.0,
        fixed_carbon_pct=15.0,
        sulfur_pct=0.8,
        rank="subbituminous",
        ambient_temp_c=32.0,
        stockpile_height_m=10.0,
    )


@pytest.fixture
def anthracite_sample():
    return CoalProximateData(
        sample_id="ANT-01",
        moisture_pct=2.0,
        volatile_matter_pct=8.0,
        ash_pct=10.0,
        fixed_carbon_pct=80.0,
        sulfur_pct=0.3,
        rank="anthracite",
        ambient_temp_c=25.0,
        stockpile_height_m=5.0,
    )


@pytest.fixture
def lignite_sample():
    return CoalProximateData(
        sample_id="LIG-01",
        moisture_pct=40.0,
        volatile_matter_pct=45.0,
        ash_pct=5.0,
        fixed_carbon_pct=10.0,
        sulfur_pct=1.5,
        rank="lignite",
        ambient_temp_c=35.0,
        stockpile_height_m=12.0,
    )


@pytest.fixture
def clf():
    return AdvancedSponcomRiskClassifier()


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestCoalProximateDataValidation:
    def test_invalid_moisture_raises(self):
        with pytest.raises(ValueError, match="moisture_pct"):
            CoalProximateData("X", 70, 30, 10, 60, 0.5, "bituminous")

    def test_invalid_rank_raises(self):
        with pytest.raises(ValueError, match="rank"):
            CoalProximateData("X", 20, 30, 10, 40, 0.5, "peat")

    def test_invalid_ambient_temp_raises(self):
        with pytest.raises(ValueError, match="ambient_temp_c"):
            CoalProximateData("X", 20, 30, 10, 40, 0.5, "bituminous", ambient_temp_c=70)

    def test_zero_stockpile_height_raises(self):
        with pytest.raises(ValueError, match="stockpile_height_m"):
            CoalProximateData("X", 20, 30, 10, 40, 0.5, "bituminous", stockpile_height_m=0)


# ---------------------------------------------------------------------------
# CPT tests
# ---------------------------------------------------------------------------

class TestCrossingPointTemperature:
    def test_anthracite_higher_cpt_than_lignite(self, clf, anthracite_sample, lignite_sample):
        cpt_ant = clf.crossing_point_temperature(anthracite_sample)
        cpt_lig = clf.crossing_point_temperature(lignite_sample)
        assert cpt_ant > cpt_lig

    def test_cpt_in_realistic_range(self, clf, subbit_sample):
        cpt = clf.crossing_point_temperature(subbit_sample)
        assert 20.0 <= cpt <= 110.0

    def test_high_sulfur_lowers_cpt(self, clf):
        base = CoalProximateData("A", 20, 35, 10, 35, 0.5, "bituminous")
        high_s = CoalProximateData("B", 20, 35, 10, 35, 3.0, "bituminous")
        assert clf.crossing_point_temperature(high_s) < clf.crossing_point_temperature(base)

    def test_high_moisture_raises_cpt(self, clf):
        dry = CoalProximateData("A", 5, 35, 10, 50, 0.5, "bituminous")
        wet = CoalProximateData("B", 40, 35, 10, 15, 0.5, "bituminous")
        assert clf.crossing_point_temperature(wet) > clf.crossing_point_temperature(dry)


# ---------------------------------------------------------------------------
# R70 tests
# ---------------------------------------------------------------------------

class TestR70Index:
    def test_r70_positive(self, clf, subbit_sample):
        assert clf.r70_index(subbit_sample) > 0

    def test_lignite_higher_r70_than_anthracite(self, clf, lignite_sample, anthracite_sample):
        assert clf.r70_index(lignite_sample) > clf.r70_index(anthracite_sample)

    def test_higher_ambient_temp_raises_r70(self, clf):
        cold = CoalProximateData("A", 20, 35, 10, 35, 0.5, "bituminous", ambient_temp_c=15)
        hot = CoalProximateData("B", 20, 35, 10, 35, 0.5, "bituminous", ambient_temp_c=40)
        assert clf.r70_index(hot) > clf.r70_index(cold)


# ---------------------------------------------------------------------------
# Category tests
# ---------------------------------------------------------------------------

class TestSponcomCategory:
    def test_cpt_above_70_is_cat_I(self, clf):
        assert clf.sponcom_category(75.0) == SponcomCategory.CAT_I

    def test_cpt_60_is_cat_II(self, clf):
        assert clf.sponcom_category(60.0) == SponcomCategory.CAT_II

    def test_cpt_50_is_cat_III(self, clf):
        assert clf.sponcom_category(50.0) == SponcomCategory.CAT_III

    def test_cpt_35_is_cat_IV(self, clf):
        assert clf.sponcom_category(35.0) == SponcomCategory.CAT_IV


# ---------------------------------------------------------------------------
# Full classification tests
# ---------------------------------------------------------------------------

class TestClassify:
    def test_returns_result(self, clf, subbit_sample):
        r = clf.classify(subbit_sample)
        assert r.sample_id == "KTM-22A"

    def test_risk_score_in_range(self, clf, subbit_sample):
        r = clf.classify(subbit_sample)
        assert 0 <= r.risk_score <= 100

    def test_anthracite_lower_risk_than_lignite(self, clf, anthracite_sample, lignite_sample):
        r_ant = clf.classify(anthracite_sample)
        r_lig = clf.classify(lignite_sample)
        assert r_ant.risk_score < r_lig.risk_score

    def test_mitigation_not_empty(self, clf, subbit_sample):
        r = clf.classify(subbit_sample)
        assert len(r.mitigation_actions) > 0

    def test_cat_iv_has_critical_action(self, clf):
        high_risk = CoalProximateData(
            "HR", 5, 60, 5, 30, 2.0, "lignite", ambient_temp_c=40, stockpile_height_m=15
        )
        r = clf.classify(high_risk)
        assert any("CRITICAL" in a for a in r.mitigation_actions)

    def test_incubation_period_positive(self, clf, subbit_sample):
        r = clf.classify(subbit_sample)
        assert r.incubation_period_days > 0

    def test_critical_age_leq_incubation(self, clf, subbit_sample):
        r = clf.classify(subbit_sample)
        if not math.isinf(r.incubation_period_days):
            assert r.critical_stockpile_age_days <= r.incubation_period_days

    def test_high_sulfur_triggers_acid_note(self, clf):
        high_s = CoalProximateData(
            "HS", 20, 35, 10, 35, 2.5, "bituminous", ambient_temp_c=30
        )
        r = clf.classify(high_s)
        assert any("sulfur" in a.lower() for a in r.mitigation_actions)
