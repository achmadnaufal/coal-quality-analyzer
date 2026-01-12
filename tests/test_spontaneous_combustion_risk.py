"""Unit tests for src.spontaneous_combustion_risk.

Covers: CoalSample validation, computed properties, SpontaneousCombustionRiskAssessor
construction, CPT estimation, risk drivers, composite index, risk classification,
safe stockpile life, batch assessment, filtering, mine summary, and edge cases.
"""

import pytest
from src.spontaneous_combustion_risk import (
    CoalSample,
    SpontaneousCombustionRiskAssessor,
    SponcomRiskResult,
    RISK_THRESHOLD_CRITICAL,
    RISK_THRESHOLD_HIGH,
    RISK_THRESHOLD_MODERATE,
)


# ---------------------------------------------------------------------------
# CoalSample tests
# ---------------------------------------------------------------------------


def make_sample(
    sample_id="S1", mine_id="MINE_A",
    moisture=25.0, ash=8.0, vm_daf=45.0,
    sulfur=0.4, gcv=4000.0, **kwargs
):
    return CoalSample(
        sample_id=sample_id,
        mine_id=mine_id,
        moisture_ad_pct=moisture,
        ash_ad_pct=ash,
        volatile_matter_daf_pct=vm_daf,
        sulfur_pct=sulfur,
        gcv_gar_kcal_kg=gcv,
        **kwargs
    )


class TestCoalSample:
    def test_basic_creation(self):
        s = make_sample()
        assert s.sample_id == "S1"
        assert s.volatile_matter_daf_pct == 45.0

    def test_fc_auto_computed(self):
        s = make_sample(vm_daf=45.0)
        assert s.fixed_carbon_daf_pct == pytest.approx(55.0)

    def test_fc_explicit_not_overridden(self):
        s = CoalSample(
            "S1", "M1", 20, 8, volatile_matter_daf_pct=45.0,
            fixed_carbon_daf_pct=52.0,  # explicit value
            sulfur_pct=0.5, gcv_gar_kcal_kg=4500,
        )
        assert s.fixed_carbon_daf_pct == pytest.approx(52.0)

    def test_estimated_oxygen_high_rank(self):
        s = make_sample(gcv=6500.0)
        assert s.estimated_oxygen_pct == 8.0

    def test_estimated_oxygen_low_rank(self):
        s = make_sample(gcv=3000.0)
        assert s.estimated_oxygen_pct == 38.0

    def test_oxygen_explicit(self):
        s = CoalSample("S1", "M1", 20, 8, 45, sulfur_pct=0.5,
                        gcv_gar_kcal_kg=4500, oxygen_pct=25.0)
        assert s.estimated_oxygen_pct == 25.0

    def test_empty_sample_id_raises(self):
        with pytest.raises(ValueError, match="sample_id"):
            make_sample(sample_id="")

    def test_negative_moisture_raises(self):
        with pytest.raises(ValueError, match="moisture_ad_pct"):
            make_sample(moisture=-1.0)

    def test_moisture_too_high_raises(self):
        with pytest.raises(ValueError, match="moisture_ad_pct"):
            make_sample(moisture=75.0)

    def test_invalid_vm_raises(self):
        with pytest.raises(ValueError, match="volatile_matter_daf_pct"):
            make_sample(vm_daf=110.0)

    def test_invalid_sulfur_raises(self):
        with pytest.raises(ValueError, match="sulfur_pct"):
            make_sample(sulfur=15.0)

    def test_invalid_oxygen_raises(self):
        with pytest.raises(ValueError, match="oxygen_pct"):
            CoalSample("S", "M", 20, 8, 45, sulfur_pct=0.5, gcv_gar_kcal_kg=4500,
                        oxygen_pct=60.0)

    def test_negative_stockpile_height_raises(self):
        with pytest.raises(ValueError, match="stockpile_height_m"):
            make_sample(stockpile_height_m=0.0)

    def test_invalid_ambient_temp_raises(self):
        with pytest.raises(ValueError, match="ambient_temp_c"):
            make_sample(ambient_temp_c=60.0)


# ---------------------------------------------------------------------------
# SpontaneousCombustionRiskAssessor construction
# ---------------------------------------------------------------------------


class TestAssessorInit:
    def test_default_creation(self):
        a = SpontaneousCombustionRiskAssessor()
        assert a._monitoring_freq == 24.0

    def test_custom_monitoring(self):
        a = SpontaneousCombustionRiskAssessor(temperature_monitoring_frequency_hours=8.0)
        assert a._monitoring_freq == 8.0

    def test_zero_monitoring_raises(self):
        with pytest.raises(ValueError, match="temperature_monitoring"):
            SpontaneousCombustionRiskAssessor(temperature_monitoring_frequency_hours=0.0)


# ---------------------------------------------------------------------------
# CPT estimation tests
# ---------------------------------------------------------------------------


class TestCPTEstimation:
    def test_cpt_in_valid_range(self):
        assessor = SpontaneousCombustionRiskAssessor()
        sample = make_sample(vm_daf=45.0, moisture=25.0)
        cpt = assessor.estimate_cpt(sample)
        assert 100.0 <= cpt <= 250.0

    def test_higher_vm_gives_lower_cpt(self):
        assessor = SpontaneousCombustionRiskAssessor()
        s_low = make_sample(vm_daf=20.0)
        s_high = make_sample(vm_daf=55.0)
        cpt_low = assessor.estimate_cpt(s_low)
        cpt_high = assessor.estimate_cpt(s_high)
        assert cpt_high < cpt_low  # higher VM → lower CPT → more reactive

    def test_higher_sulfur_lowers_cpt(self):
        assessor = SpontaneousCombustionRiskAssessor()
        s_low_s = make_sample(vm_daf=40.0, sulfur=0.2)
        s_high_s = make_sample(vm_daf=40.0, sulfur=3.0)
        assert assessor.estimate_cpt(s_high_s) < assessor.estimate_cpt(s_low_s)

    def test_inertinite_increases_cpt(self):
        assessor = SpontaneousCombustionRiskAssessor()
        s_no_inert = make_sample(vm_daf=40.0)
        s_high_inert = CoalSample("S", "M", 20, 8, 40, sulfur_pct=0.4,
                                   gcv_gar_kcal_kg=4500, inertinite_pct=80.0)
        assert assessor.estimate_cpt(s_high_inert) > assessor.estimate_cpt(s_no_inert)


# ---------------------------------------------------------------------------
# Full assessment tests
# ---------------------------------------------------------------------------


@pytest.fixture
def assessor():
    return SpontaneousCombustionRiskAssessor()


class TestAssess:
    def test_returns_sponcom_result(self, assessor):
        s = make_sample()
        result = assessor.assess(s)
        assert isinstance(result, SponcomRiskResult)

    def test_result_has_all_fields(self, assessor):
        s = make_sample()
        result = assessor.assess(s)
        assert result.sample_id == "S1"
        assert isinstance(result.composite_risk_index, float)
        assert result.risk_class in ("critical", "high", "moderate", "low")
        assert result.susceptibility_class in ("very_high", "high", "moderate", "low")
        assert len(result.mitigation_actions) > 0
        assert result.stockpile_life_days > 0

    def test_low_rank_high_vm_is_high_risk(self, assessor):
        # Low-rank, high VM, high O2, lots of time in stockpile
        s = make_sample(
            vm_daf=55.0, moisture=30.0, gcv=3500.0, sulfur=0.8,
            days_in_stockpile=60, stockpile_height_m=10.0
        )
        result = assessor.assess(s)
        assert result.risk_class in ("critical", "high")

    def test_high_rank_low_vm_is_lower_risk(self, assessor):
        # High-rank bituminous coal
        s = CoalSample(
            "ANTH", "MINE_ANTH", moisture_ad_pct=5.0, ash_ad_pct=8.0,
            volatile_matter_daf_pct=15.0, sulfur_pct=0.2,
            gcv_gar_kcal_kg=7000.0, days_in_stockpile=5
        )
        result = assessor.assess(s)
        assert result.risk_class in ("low", "moderate")

    def test_stockpile_life_shorter_for_higher_risk(self, assessor):
        low_risk = CoalSample(
            "L", "M", 5.0, 8.0, 15.0, sulfur_pct=0.2, gcv_gar_kcal_kg=7000.0
        )
        high_risk = make_sample(vm_daf=55.0, moisture=28.0, gcv=3500.0, days_in_stockpile=50)
        r_low = assessor.assess(low_risk)
        r_high = assessor.assess(high_risk)
        assert r_high.stockpile_life_days <= r_low.stockpile_life_days

    def test_risk_drivers_have_expected_keys(self, assessor):
        s = make_sample()
        result = assessor.assess(s)
        expected_keys = {
            "rank_reactivity", "volatile_matter", "oxygen_content",
            "stockpile_geometry", "ambient_temperature", "age_in_stockpile",
            "monitoring_gap"
        }
        assert set(result.risk_drivers.keys()) == expected_keys

    def test_composite_risk_in_range(self, assessor):
        s = make_sample()
        result = assessor.assess(s)
        assert 0.0 <= result.composite_risk_index <= 100.0


# ---------------------------------------------------------------------------
# Batch assessment tests
# ---------------------------------------------------------------------------


class TestBatchAssess:
    def test_batch_returns_all(self, assessor):
        samples = [make_sample(f"S{i}", "MINE_A", vm_daf=30 + i * 5) for i in range(5)]
        results = assessor.batch_assess(samples)
        assert len(results) == 5

    def test_batch_sorted_by_risk_desc(self, assessor):
        samples = [make_sample(f"S{i}", "MINE_A", vm_daf=20 + i * 10) for i in range(4)]
        results = assessor.batch_assess(samples)
        indices = [r.composite_risk_index for r in results]
        assert all(indices[i] >= indices[i + 1] for i in range(len(indices) - 1))

    def test_empty_batch_raises(self, assessor):
        with pytest.raises(ValueError, match="empty"):
            assessor.batch_assess([])


# ---------------------------------------------------------------------------
# Mine risk summary tests
# ---------------------------------------------------------------------------


class TestMineRiskSummary:
    def test_summary_structure(self, assessor):
        samples = [
            make_sample("S1", "MINE_A", vm_daf=50.0),
            make_sample("S2", "MINE_A", vm_daf=35.0),
            make_sample("S3", "MINE_B", vm_daf=20.0),
        ]
        results = assessor.batch_assess(samples)
        summary = assessor.mine_risk_summary(results)
        assert "MINE_A" in summary
        assert "MINE_B" in summary
        assert summary["MINE_A"]["n_samples"] == 2
        assert summary["MINE_B"]["n_samples"] == 1

    def test_has_critical_flag(self, assessor):
        samples = [
            make_sample("S1", "MINE_X", vm_daf=60.0, moisture=28.0, gcv=3200.0,
                        days_in_stockpile=80, stockpile_height_m=12.0),
        ]
        results = assessor.batch_assess(samples)
        summary = assessor.mine_risk_summary(results)
        # Should have a boolean flag
        assert isinstance(summary["MINE_X"]["has_critical_sample"], bool)


# ---------------------------------------------------------------------------
# High risk filter
# ---------------------------------------------------------------------------


class TestHighRiskFilter:
    def test_filters_correctly(self, assessor):
        samples = [make_sample(f"S{i}", "MINE_A", vm_daf=20 + i * 10) for i in range(5)]
        results = assessor.batch_assess(samples)
        high = assessor.high_risk_stockpiles(results)
        for r in high:
            assert r.risk_class in ("critical", "high")
