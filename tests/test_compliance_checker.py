"""Unit tests for coal_quality.compliance_checker."""

import math
from datetime import date

import pandas as pd
import pytest

from coal_quality.compliance_checker import (
    ComplianceChecker,
    ContractSpec,
    InspectionResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def spec_ctr001():
    return ContractSpec(
        contract_id="CTR-001",
        buyer_name="Power Plant A",
        coal_grade="GCV5800",
        ash_max_pct=14.0,
        sulfur_max_pct=0.70,
        moisture_max_pct=18.0,
        gcv_min_mjkg=23.0,
        price_usd_t=65.0,
        penalty_per_excess_unit=2.5,
        acceptance_tolerance_pct=5.0,
    )


@pytest.fixture
def spec_ctr002():
    return ContractSpec(
        contract_id="CTR-002",
        buyer_name="Power Plant B",
        coal_grade="GCV5500",
        ash_max_pct=16.0,
        sulfur_max_pct=0.80,
        moisture_max_pct=20.0,
        gcv_min_mjkg=21.0,
        price_usd_t=58.0,
        penalty_per_excess_unit=3.0,
        acceptance_tolerance_pct=10.0,
    )


@pytest.fixture
def lot_lot001(spec_ctr001):
    return InspectionResult(
        lot_id="LOT-2024-01",
        contract_id="CTR-001",
        sample_date="2026-01-15",
        ash_pct=13.0,
        sulfur_pct=0.60,
        moisture_pct=16.0,
        gcv_mjkg=24.0,
        size_fraction_pct=92,
        foreign_matter_pct=0.5,
    )


@pytest.fixture
def lot_fail_ash(spec_ctr001):
    return InspectionResult(
        lot_id="LOT-FAIL-ASH",
        contract_id="CTR-001",
        sample_date="2026-01-20",
        ash_pct=15.5,   # exceeds ash_max_pct=14.0
        sulfur_pct=0.60,
        moisture_pct=16.0,
        gcv_mjkg=24.0,
        size_fraction_pct=90,
        foreign_matter_pct=0.3,
    )


@pytest.fixture
def lot_fail_gcv(spec_ctr001):
    return InspectionResult(
        lot_id="LOT-FAIL-GCV",
        contract_id="CTR-001",
        sample_date="2026-01-21",
        ash_pct=13.0,
        sulfur_pct=0.60,
        moisture_pct=16.0,
        gcv_mjkg=22.0,   # below gcv_min_mjkg=23.0
        size_fraction_pct=88,
        foreign_matter_pct=0.4,
    )


@pytest.fixture
def lot_fail_multiple(spec_ctr001):
    return InspectionResult(
        lot_id="LOT-FAIL-MULTI",
        contract_id="CTR-001",
        sample_date="2026-01-22",
        ash_pct=15.5,   # FAIL
        sulfur_pct=0.80,  # FAIL (0.80 > 0.70)
        moisture_pct=16.0,
        gcv_mjkg=22.0,   # FAIL
        size_fraction_pct=87,
        foreign_matter_pct=0.6,
    )


@pytest.fixture
def checker():
    return ComplianceChecker()


# ---------------------------------------------------------------------------
# ContractSpec validation
# ---------------------------------------------------------------------------

class TestContractSpecValidation:
    def test_valid_spec_creation(self, spec_ctr001):
        assert spec_ctr001.contract_id == "CTR-001"
        assert spec_ctr001.buyer_name == "Power Plant A"
        assert spec_ctr001.ash_max_pct == 14.0
        assert spec_ctr001.penalty_per_excess_unit == 2.5

    def test_empty_contract_id_raises(self):
        with pytest.raises(ValueError, match="contract_id cannot be empty"):
            ContractSpec(
                contract_id="  ", buyer_name="Buyer", coal_grade="GCV5800",
                ash_max_pct=14.0, sulfur_max_pct=0.7, moisture_max_pct=18.0,
                gcv_min_mjkg=23.0, price_usd_t=65.0, penalty_per_excess_unit=2.5,
            )

    def test_negative_ash_limit_raises(self):
        with pytest.raises(ValueError, match="ash_max_pct must be positive"):
            ContractSpec(
                contract_id="CTR-X", buyer_name="Buyer", coal_grade="GCV5800",
                ash_max_pct=-1.0, sulfur_max_pct=0.7, moisture_max_pct=18.0,
                gcv_min_mjkg=23.0, price_usd_t=65.0, penalty_per_excess_unit=2.5,
            )

    def test_zero_gcv_raises(self):
        with pytest.raises(ValueError, match="gcv_min_mjkg must be positive"):
            ContractSpec(
                contract_id="CTR-X", buyer_name="Buyer", coal_grade="GCV5800",
                ash_max_pct=14.0, sulfur_max_pct=0.7, moisture_max_pct=18.0,
                gcv_min_mjkg=0.0, price_usd_t=65.0, penalty_per_excess_unit=2.5,
            )

    def test_tolerance_out_of_range_raises(self, spec_ctr001):
        with pytest.raises(ValueError, match="acceptance_tolerance_pct must be between"):
            ContractSpec(
                contract_id="CTR-X", buyer_name="Buyer", coal_grade="GCV5800",
                ash_max_pct=14.0, sulfur_max_pct=0.7, moisture_max_pct=18.0,
                gcv_min_mjkg=23.0, price_usd_t=65.0, penalty_per_excess_unit=2.5,
                acceptance_tolerance_pct=150.0,
            )


# ---------------------------------------------------------------------------
# InspectionResult validation
# ---------------------------------------------------------------------------

class TestInspectionResultValidation:
    def test_valid_inspection(self, lot_lot001):
        assert lot_lot001.lot_id == "LOT-2024-01"
        assert lot_lot001.ash_pct == 13.0
        assert lot_lot001.gcv_mjkg == 24.0

    def test_empty_lot_id_raises(self):
        with pytest.raises(ValueError, match="lot_id cannot be empty"):
            InspectionResult(
                lot_id="  ", contract_id="CTR-001", sample_date="2026-01-15",
                ash_pct=13.0, sulfur_pct=0.6, moisture_pct=16.0,
                gcv_mjkg=24.0, size_fraction_pct=92, foreign_matter_pct=0.5,
            )

    def test_ash_out_of_range_raises(self):
        with pytest.raises(ValueError, match="ash_pct must be between"):
            InspectionResult(
                lot_id="LOT-X", contract_id="CTR-001", sample_date="2026-01-15",
                ash_pct=55.0, sulfur_pct=0.6, moisture_pct=16.0,
                gcv_mjkg=24.0, size_fraction_pct=92, foreign_matter_pct=0.5,
            )

    def test_negative_gcv_raises(self):
        with pytest.raises(ValueError, match="gcv_mjkg must be positive"):
            InspectionResult(
                lot_id="LOT-X", contract_id="CTR-001", sample_date="2026-01-15",
                ash_pct=13.0, sulfur_pct=0.6, moisture_pct=16.0,
                gcv_mjkg=-5.0, size_fraction_pct=92, foreign_matter_pct=0.5,
            )

    def test_date_object_accepted(self):
        ins = InspectionResult(
            lot_id="LOT-X", contract_id="CTR-001", sample_date=date(2026, 3, 1),
            ash_pct=13.0, sulfur_pct=0.6, moisture_pct=16.0,
            gcv_mjkg=24.0, size_fraction_pct=92, foreign_matter_pct=0.5,
        )
        assert ins.sample_date == date(2026, 3, 1)


# ---------------------------------------------------------------------------
# check_single_lot
# ---------------------------------------------------------------------------

class TestCheckSingleLot:
    def test_all_pass_returns_pass(self, checker, lot_lot001, spec_ctr001):
        result = checker.check_single_lot(lot_lot001, spec_ctr001)
        assert result["overall_status"] == "PASS"
        assert all(v == "PASS" for v in result["parameter_results"].values())
        assert result["total_penalty"] == 0.0

    def test_ash_fail(self, checker, lot_fail_ash, spec_ctr001):
        result = checker.check_single_lot(lot_fail_ash, spec_ctr001)
        assert result["overall_status"] == "FAIL"
        assert result["parameter_results"]["ash"] == "FAIL"
        assert result["parameter_results"]["sulfur"] == "PASS"
        assert result["parameter_results"]["moisture"] == "PASS"
        assert result["parameter_results"]["gcv"] == "PASS"
        # ash excess = 15.5 - 14.0 = 1.5; penalty = 1.5 * 2.5 = 3.75
        assert result["total_penalty"] == 3.75

    def test_gcv_fail(self, checker, lot_fail_gcv, spec_ctr001):
        result = checker.check_single_lot(lot_fail_gcv, spec_ctr001)
        assert result["overall_status"] == "FAIL"
        assert result["parameter_results"]["gcv"] == "FAIL"
        # gcv shortfall = 23.0 - 22.0 = 1.0; penalty = 1.0 * 2.5 = 2.5
        assert result["total_penalty"] == 2.5

    def test_multiple_fail(self, checker, lot_fail_multiple, spec_ctr001):
        result = checker.check_single_lot(lot_fail_multiple, spec_ctr001)
        assert result["overall_status"] == "FAIL"
        # ash: 15.5 - 14.0 = 1.5 * 2.5 = 3.75
        # sulfur: 0.80 - 0.70 = 0.10 * 2.5 = 0.25
        # moisture: within spec = 0
        # gcv: 23.0 - 22.0 = 1.0 * 2.5 = 2.5
        expected = 3.75 + 0.25 + 2.5
        assert result["total_penalty"] == expected
        assert result["parameter_results"]["ash"] == "FAIL"
        assert result["parameter_results"]["sulfur"] == "FAIL"
        assert result["parameter_results"]["gcv"] == "FAIL"

    def test_ash_within_tolerance_is_pass(self, checker, spec_ctr001):
        # Ash at exactly limit — PASS (≤ limit)
        lot = InspectionResult(
            lot_id="LOT-BOUNDARY", contract_id="CTR-001", sample_date="2026-02-01",
            ash_pct=14.0, sulfur_pct=0.60, moisture_pct=16.0,
            gcv_mjkg=24.0, size_fraction_pct=92, foreign_matter_pct=0.5,
        )
        result = checker.check_single_lot(lot, spec_ctr001)
        assert result["parameter_results"]["ash"] == "PASS"

    def test_parameter_details_structure(self, checker, lot_fail_ash, spec_ctr001):
        result = checker.check_single_lot(lot_fail_ash, spec_ctr001)
        ash_detail = result["parameter_details"]["ash"]
        assert ash_detail["measured"] == 15.5
        assert ash_detail["limit"] == 14.0
        assert ash_detail["excess"] == 1.5
        assert ash_detail["status"] == "FAIL"


# ---------------------------------------------------------------------------
# check_multi_lot
# ---------------------------------------------------------------------------

class TestCheckMultiLot:
    def test_empty_list(self, checker, spec_ctr001):
        result = checker.check_multi_lot([], spec_ctr001)
        assert result["total_lots"] == 0
        assert result["pass_rate_pct"] == 0.0
        assert result["lot_results"] == []

    def test_all_pass(self, checker, spec_ctr001):
        lot1 = InspectionResult(
            lot_id="LOT-01", contract_id="CTR-001", sample_date="2026-01-01",
            ash_pct=13.0, sulfur_pct=0.60, moisture_pct=16.0,
            gcv_mjkg=24.0, size_fraction_pct=92, foreign_matter_pct=0.5,
        )
        lot2 = InspectionResult(
            lot_id="LOT-02", contract_id="CTR-001", sample_date="2026-01-02",
            ash_pct=12.5, sulfur_pct=0.55, moisture_pct=15.5,
            gcv_mjkg=24.5, size_fraction_pct=91, foreign_matter_pct=0.4,
        )
        result = checker.check_multi_lot([lot1, lot2], spec_ctr001)
        assert result["total_lots"] == 2
        assert result["passed_lots"] == 2
        assert result["failed_lots"] == 0
        assert result["pass_rate_pct"] == 100.0

    def test_all_fail(self, checker, lot_fail_ash, lot_fail_gcv, spec_ctr001):
        result = checker.check_multi_lot([lot_fail_ash, lot_fail_gcv], spec_ctr001)
        assert result["total_lots"] == 2
        assert result["passed_lots"] == 0
        assert result["failed_lots"] == 2
        assert result["pass_rate_pct"] == 0.0

    def test_mixed_results(self, checker, lot_lot001, lot_fail_ash, spec_ctr001):
        result = checker.check_multi_lot([lot_lot001, lot_fail_ash], spec_ctr001)
        assert result["total_lots"] == 2
        assert result["passed_lots"] == 1
        assert result["failed_lots"] == 1
        assert result["pass_rate_pct"] == 50.0

    def test_per_parameter_pass_rate(self, checker, lot_lot001, lot_fail_ash, spec_ctr001):
        result = checker.check_multi_lot([lot_lot001, lot_fail_ash], spec_ctr001)
        # ash: lot1 PASS, lot2 FAIL → 50%
        assert result["per_parameter_pass_rate"]["ash"] == 50.0
        # sulfur: both PASS → 100%
        assert result["per_parameter_pass_rate"]["sulfur"] == 100.0
        # moisture: both PASS → 100%
        assert result["per_parameter_pass_rate"]["moisture"] == 100.0
        # gcv: both PASS → 100%
        assert result["per_parameter_pass_rate"]["gcv"] == 100.0


# ---------------------------------------------------------------------------
# calculate_penalties
# ---------------------------------------------------------------------------

class TestCalculatePenalties:
    def test_no_penalties_when_all_pass(self, checker, lot_lot001, spec_ctr001):
        pens = checker.calculate_penalties(lot_lot001, spec_ctr001)
        assert all(v == 0.0 for k, v in pens.items() if k != "total_penalty")
        assert pens["total_penalty"] == 0.0

    def test_ash_penalty_only(self, checker, lot_fail_ash, spec_ctr001):
        pens = checker.calculate_penalties(lot_fail_ash, spec_ctr001)
        assert pens["ash"] == 3.75
        assert pens["sulfur"] == 0.0
        assert pens["moisture"] == 0.0
        assert pens["gcv"] == 0.0
        assert pens["total_penalty"] == 3.75

    def test_multiple_parameter_penalties(self, checker, lot_fail_multiple, spec_ctr001):
        pens = checker.calculate_penalties(lot_fail_multiple, spec_ctr001)
        # ash: 1.5 * 2.5 = 3.75
        # sulfur: 0.10 * 2.5 = 0.25
        # moisture: 0
        # gcv: 1.0 * 2.5 = 2.5
        assert pens["ash"] == 3.75
        assert pens["sulfur"] == 0.25
        assert pens["moisture"] == 0.0
        assert pens["gcv"] == 2.5
        assert pens["total_penalty"] == 6.5

    def test_total_penalty_is_sum(self, checker, lot_fail_multiple, spec_ctr001):
        pens = checker.calculate_penalties(lot_fail_multiple, spec_ctr001)
        individual_sum = (
            pens["ash"] + pens["sulfur"] + pens["moisture"] + pens["gcv"]
        )
        assert pens["total_penalty"] == individual_sum


# ---------------------------------------------------------------------------
# lot_risk_classification
# ---------------------------------------------------------------------------

class TestLotRiskClassification:
    def test_all_params_within_low_risk(self, checker, lot_lot001, spec_ctr001):
        risk = checker.lot_risk_classification(lot_lot001, spec_ctr001)
        assert risk["overall_risk"] == "LOW"
        assert all(v == "LOW" for v in risk["parameter_risks"].values())

    def test_ash_high_risk_when_at_90pct_of_limit(self, checker, spec_ctr001):
        # spec ash_max = 14.0; tolerance = 5% → acceptance band = 14.0*1.05 = 14.7
        # Use 14.64 to ensure prox = 0.914+ > 0.90 threshold (avoids float boundary)
        lot = InspectionResult(
            lot_id="LOT-RISK", contract_id="CTR-001", sample_date="2026-02-01",
            ash_pct=14.64, sulfur_pct=0.60, moisture_pct=16.0,
            gcv_mjkg=24.0, size_fraction_pct=92, foreign_matter_pct=0.5,
        )
        risk = checker.lot_risk_classification(lot, spec_ctr001)
        assert risk["parameter_risks"]["ash"] == "HIGH"

    def test_ash_high_risk_when_at_100pct_of_limit(self, checker, spec_ctr001):
        # ash at 14.7 (exactly at tolerance boundary) → 100% proximity → HIGH
        lot = InspectionResult(
            lot_id="LOT-RISK-2", contract_id="CTR-001", sample_date="2026-02-01",
            ash_pct=14.7, sulfur_pct=0.60, moisture_pct=16.0,
            gcv_mjkg=24.0, size_fraction_pct=92, foreign_matter_pct=0.5,
        )
        risk = checker.lot_risk_classification(lot, spec_ctr001)
        assert risk["parameter_risks"]["ash"] == "HIGH"

    def test_ash_medium_risk_at_50pct_proximity(self, checker, spec_ctr001):
        # ash at 14.36 → prox = 0.514 > 0.50 threshold → MEDIUM
        lot = InspectionResult(
            lot_id="LOT-RISK-3", contract_id="CTR-001", sample_date="2026-02-01",
            ash_pct=14.36, sulfur_pct=0.60, moisture_pct=16.0,
            gcv_mjkg=24.0, size_fraction_pct=92, foreign_matter_pct=0.5,
        )
        risk = checker.lot_risk_classification(lot, spec_ctr001)
        assert risk["parameter_risks"]["ash"] == "MEDIUM"

    def test_gcv_high_risk_when_below_floor(self, checker, spec_ctr001):
        # GCV shortfall with prox >= 0.90 → HIGH
        # gcv_min=23.0, tol=5% → acceptance band down to 20.35
        # Use gcv=21.0: shortfall=2.0, max_shortfall=2.65, prox=0.755 → MEDIUM
        # Use gcv=20.5: shortfall=2.5, prox=0.943 → HIGH
        lot = InspectionResult(
            lot_id="LOT-GCV-HIGH", contract_id="CTR-001", sample_date="2026-02-01",
            ash_pct=13.0, sulfur_pct=0.60, moisture_pct=16.0,
            gcv_mjkg=20.5, size_fraction_pct=88, foreign_matter_pct=0.4,
        )
        risk = checker.lot_risk_classification(lot, spec_ctr001)
        assert risk["overall_risk"] == "HIGH"
        assert risk["parameter_risks"]["gcv"] == "HIGH"

    def test_proximity_percentage_values(self, checker, lot_lot001, spec_ctr001):
        risk = checker.lot_risk_classification(lot_lot001, spec_ctr001)
        # lot values are well within spec → low proximity %
        for param, prox in risk["parameter_proximity_pct"].items():
            assert 0.0 <= prox <= 100.0


# ---------------------------------------------------------------------------
# acceptance_probability
# ---------------------------------------------------------------------------

class TestAcceptanceProbability:
    def test_all_pass_probability_one(self, checker, lot_lot001, spec_ctr001):
        prob = checker.acceptance_probability(lot_lot001, spec_ctr001)
        assert prob == 1.0

    def test_gcv_below_minimum_probability_zero(self, checker, spec_ctr001):
        # GCV below tolerance floor (below 20.0) → probability = 0
        lot = InspectionResult(
            lot_id="LOT-PROB-ZERO", contract_id="CTR-001", sample_date="2026-02-01",
            ash_pct=13.0, sulfur_pct=0.60, moisture_pct=16.0,
            gcv_mjkg=19.5, size_fraction_pct=88, foreign_matter_pct=0.4,
        )
        prob = checker.acceptance_probability(lot, spec_ctr001)
        assert prob == 0.0

    def test_probability_between_zero_and_one(self, checker, spec_ctr001):
        # Lot close to limits but within spec
        lot = InspectionResult(
            lot_id="LOT-PROW", contract_id="CTR-001", sample_date="2026-02-01",
            ash_pct=14.5, sulfur_pct=0.68, moisture_pct=17.5,
            gcv_mjkg=23.2, size_fraction_pct=92, foreign_matter_pct=0.5,
        )
        prob = checker.acceptance_probability(lot, spec_ctr001)
        assert 0.0 < prob < 1.0

    def test_invalid_slope_raises(self, checker, lot_lot001, spec_ctr001):
        with pytest.raises(ValueError, match="logistic_slope must be positive"):
            checker.acceptance_probability(lot_lot001, spec_ctr001, logistic_slope=-1.0)

    def test_probability_equals_one_for_perfect_lot(self, checker, spec_ctr001):
        lot = InspectionResult(
            lot_id="LOT-PERFECT", contract_id="CTR-001", sample_date="2026-02-01",
            ash_pct=10.0, sulfur_pct=0.40, moisture_pct=12.0,
            gcv_mjkg=26.0, size_fraction_pct=95, foreign_matter_pct=0.1,
        )
        prob = checker.acceptance_probability(lot, spec_ctr001)
        assert prob == 1.0


# ---------------------------------------------------------------------------
# vendor_performance_summary
# ---------------------------------------------------------------------------

class TestVendorPerformanceSummary:
    def test_empty_list(self, checker):
        df = checker.vendor_performance_summary([])
        assert df.empty

    def test_single_vendor_all_pass(self, checker, lot_lot001, spec_ctr001):
        lots = [(lot_lot001, spec_ctr001)]
        df = checker.vendor_performance_summary(lots)
        assert len(df) == 1
        row = df.iloc[0]
        assert row["vendor"] == "Power Plant A"
        assert row["total_lots"] == 1
        assert row["passed_lots"] == 1
        assert row["failed_lots"] == 0
        assert row["pass_rate_pct"] == 100.0
        assert row["avg_penalty_usd_t"] == 0.0

    def test_single_vendor_all_fail(self, checker, lot_fail_ash, lot_fail_multiple, spec_ctr001):
        lots = [
            (lot_fail_ash, spec_ctr001),
            (lot_fail_multiple, spec_ctr001),
        ]
        df = checker.vendor_performance_summary(lots)
        assert len(df) == 1
        row = df.iloc[0]
        assert row["total_lots"] == 2
        assert row["passed_lots"] == 0
        assert row["failed_lots"] == 2
        assert row["pass_rate_pct"] == 0.0
        assert row["avg_penalty_usd_t"] > 0.0

    def test_multiple_vendors(self, checker, lot_lot001, spec_ctr001, spec_ctr002):
        # lot_lot001 is for CTR-001 (Power Plant A); create a CTR-002 lot
        lot2 = InspectionResult(
            lot_id="LOT-02", contract_id="CTR-002", sample_date="2026-02-01",
            ash_pct=17.0, sulfur_pct=0.85, moisture_pct=21.0,
            gcv_mjkg=20.0, size_fraction_pct=88, foreign_matter_pct=0.8,
        )
        lots = [
            (lot_lot001, spec_ctr001),  # Power Plant A
            (lot2, spec_ctr002),         # Power Plant B
        ]
        df = checker.vendor_performance_summary(lots)
        assert len(df) == 2
        vendors = set(df["vendor"].values)
        assert "Power Plant A" in vendors
        assert "Power Plant B" in vendors

    def test_missing_vendor_param_columns(self, checker, lot_lot001, spec_ctr001):
        df = checker.vendor_performance_summary([(lot_lot001, spec_ctr001)])
        expected_cols = [
            "vendor", "total_lots", "passed_lots", "failed_lots",
            "pass_rate_pct", "avg_penalty_usd_t", "total_penalties_usd",
            "ash_fail_rate_pct", "sulfur_fail_rate_pct",
            "moisture_fail_rate_pct", "gcv_fail_rate_pct",
        ]
        assert all(col in df.columns for col in expected_cols)


# ---------------------------------------------------------------------------
# export_compliance_report
# ---------------------------------------------------------------------------

class TestExportComplianceReport:
    def test_empty_list(self, checker, spec_ctr001):
        df = checker.export_compliance_report([], {"CTR-001": spec_ctr001})
        assert df.empty

    def test_all_pass_report_columns(self, checker, lot_lot001, spec_ctr001):
        df = checker.export_compliance_report(
            [lot_lot001], {"CTR-001": spec_ctr001}
        )
        expected_cols = [
            "lot_id", "contract_id", "sample_date", "parameter",
            "measured_value", "limit_value", "excess_shortfall",
            "status", "penalty_usd_t", "risk_class",
        ]
        assert all(col in df.columns for col in expected_cols)

    def test_report_row_count(self, checker, lot_lot001, spec_ctr001):
        # 4 parameters per lot
        df = checker.export_compliance_report(
            [lot_lot001], {"CTR-001": spec_ctr001}
        )
        assert len(df) == 4  # ash, sulfur, moisture, gcv

    def test_multiple_lots_report(self, checker, lot_lot001, lot_fail_ash, spec_ctr001):
        df = checker.export_compliance_report(
            [lot_lot001, lot_fail_ash], {"CTR-001": spec_ctr001}
        )
        assert len(df) == 8  # 4 params x 2 lots

    def test_unknown_contract_skipped(self, checker, lot_lot001, spec_ctr001):
        df = checker.export_compliance_report(
            [lot_lot001], {"OTHER-CTR": spec_ctr001}  # wrong contract id
        )
        assert df.empty

    def test_fail_lot_penalty_nonzero(self, checker, lot_fail_ash, spec_ctr001):
        df = checker.export_compliance_report(
            [lot_fail_ash], {"CTR-001": spec_ctr001}
        )
        ash_row = df[df["parameter"] == "ash"]
        assert ash_row.iloc[0]["penalty_usd_t"] == 3.75
        assert ash_row.iloc[0]["status"] == "FAIL"

    def test_pass_lot_penalty_zero(self, checker, lot_lot001, spec_ctr001):
        df = checker.export_compliance_report(
            [lot_lot001], {"CTR-001": spec_ctr001}
        )
        ash_row = df[df["parameter"] == "ash"]
        assert ash_row.iloc[0]["penalty_usd_t"] == 0.0
        assert ash_row.iloc[0]["status"] == "PASS"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_missing_spec_parameter_keys_in_results(self, checker, lot_lot001, spec_ctr001):
        """All spec parameters should always be in parameter_results keys."""
        result = checker.check_single_lot(lot_lot001, spec_ctr001)
        assert set(result["parameter_results"].keys()) == {"ash", "sulfur", "moisture", "gcv"}

    def test_zero_penalty_per_excess_unit(self, checker, spec_ctr001):
        spec_zero_penalty = ContractSpec(
            contract_id="CTR-ZERO", buyer_name="Buyer", coal_grade="GCV5800",
            ash_max_pct=14.0, sulfur_max_pct=0.70, moisture_max_pct=18.0,
            gcv_min_mjkg=23.0, price_usd_t=65.0, penalty_per_excess_unit=0.0,
        )
        # Create lot directly to avoid fixture-scope issues
        lot_fail = InspectionResult(
            lot_id="LOT-FAIL-ASH", contract_id="CTR-001", sample_date="2026-01-20",
            ash_pct=15.5, sulfur_pct=0.60, moisture_pct=16.0,
            gcv_mjkg=24.0, size_fraction_pct=90, foreign_matter_pct=0.3,
        )
        result = checker.check_single_lot(lot_fail, spec_zero_penalty)
        assert result["total_penalty"] == 0.0
        assert result["overall_status"] == "FAIL"  # Still fails even with zero penalty

    def test_high_tolerance_spec(self, checker, spec_ctr002):
        # CTR-002 has 10% tolerance — use values well within the tolerance band
        # so all parameters clearly return LOW risk
        lot = InspectionResult(
            lot_id="LOT-TOL", contract_id="CTR-002", sample_date="2026-02-01",
            ash_pct=16.5, sulfur_pct=0.75, moisture_pct=19.5,
            gcv_mjkg=23.5, size_fraction_pct=92, foreign_matter_pct=0.5,
        )
        risk = checker.lot_risk_classification(lot, spec_ctr002)
        # All within spec, comfortably within tolerance → all LOW risk
        assert risk["overall_risk"] == "LOW"
