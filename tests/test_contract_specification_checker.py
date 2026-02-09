"""Unit tests for contract_specification_checker module."""

import pytest
from src.contract_specification_checker import (
    CoalContractSpec,
    CoalContractType,
    ComplianceCheckResult,
    ContractSpecificationChecker,
    ShipmentAnalysis,
    SpecStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def checker():
    return ContractSpecificationChecker()


def _spec(**overrides) -> CoalContractSpec:
    defaults = dict(
        contract_id="PO-2026-001",
        contract_type=CoalContractType.THERMAL,
        gar_typical_kcal_kg=5500.0,
        gar_min_kcal_kg=5300.0,
        total_moisture_max_pct=28.0,
        ash_max_pct=12.0,
        total_sulphur_max_pct=0.8,
        hgi_min=45.0,
        price_adj_per_100kcal=0.12,
    )
    defaults.update(overrides)
    return CoalContractSpec(**defaults)


def _shipment(**overrides) -> ShipmentAnalysis:
    defaults = dict(
        shipment_id="SHIP-001",
        gar_kcal_kg=5520.0,
        total_moisture_pct=24.0,
        inherent_moisture_pct=12.0,
        ash_pct=10.5,
        volatile_matter_pct=38.0,
        total_sulphur_pct=0.55,
        hgi=52.0,
        tonnes=50_000.0,
    )
    defaults.update(overrides)
    return ShipmentAnalysis(**defaults)


# ---------------------------------------------------------------------------
# CoalContractSpec validation
# ---------------------------------------------------------------------------

class TestSpecValidation:
    def test_valid_spec_ok(self):
        s = _spec()
        assert s.contract_id == "PO-2026-001"

    def test_empty_contract_id_raises(self):
        with pytest.raises(ValueError, match="contract_id cannot be empty"):
            _spec(contract_id="  ")

    def test_zero_gar_typical_raises(self):
        with pytest.raises(ValueError, match="gar_typical_kcal_kg"):
            _spec(gar_typical_kcal_kg=0.0)

    def test_min_above_typical_raises(self):
        with pytest.raises(ValueError, match="gar_min_kcal_kg must be <= gar_typical"):
            _spec(gar_typical_kcal_kg=5000.0, gar_min_kcal_kg=5500.0)

    def test_negative_price_adj_raises(self):
        with pytest.raises(ValueError, match="price_adj_per_100kcal must be >= 0"):
            _spec(price_adj_per_100kcal=-1.0)


# ---------------------------------------------------------------------------
# ShipmentAnalysis validation
# ---------------------------------------------------------------------------

class TestShipmentValidation:
    def test_valid_shipment_ok(self):
        s = _shipment()
        assert s.shipment_id == "SHIP-001"

    def test_empty_shipment_id_raises(self):
        with pytest.raises(ValueError, match="shipment_id cannot be empty"):
            _shipment(shipment_id="")

    def test_moisture_out_of_range_raises(self):
        with pytest.raises(ValueError, match="total_moisture_pct must be between"):
            _shipment(total_moisture_pct=65.0)

    def test_zero_tonnes_raises(self):
        with pytest.raises(ValueError, match="tonnes must be > 0"):
            _shipment(tonnes=0.0)


# ---------------------------------------------------------------------------
# check() — accepted shipment
# ---------------------------------------------------------------------------

class TestCheckAccepted:
    def test_accepted_shipment_returns_accepted(self, checker):
        result = checker.check(_shipment(), _spec())
        assert result.overall_status == "ACCEPTED"

    def test_conformance_score_near_100_for_clean_shipment(self, checker):
        result = checker.check(_shipment(), _spec())
        assert result.conformance_score > 90.0

    def test_no_rejection_reasons_for_clean_shipment(self, checker):
        result = checker.check(_shipment(), _spec())
        assert len(result.rejection_reasons) == 0

    def test_returns_compliance_check_result(self, checker):
        result = checker.check(_shipment(), _spec())
        assert isinstance(result, ComplianceCheckResult)

    def test_shipment_id_preserved(self, checker):
        result = checker.check(_shipment(), _spec())
        assert result.shipment_id == "SHIP-001"

    def test_contract_id_preserved(self, checker):
        result = checker.check(_shipment(), _spec())
        assert result.contract_id == "PO-2026-001"


# ---------------------------------------------------------------------------
# check() — GARr below minimum → rejected
# ---------------------------------------------------------------------------

class TestCheckGarRejection:
    def test_gar_below_min_rejected(self, checker):
        ship = _shipment(gar_kcal_kg=5200.0)  # below 5300 min
        result = checker.check(ship, _spec())
        assert result.overall_status == "REJECTED"

    def test_gar_rejection_reason_present(self, checker):
        ship = _shipment(gar_kcal_kg=5200.0)
        result = checker.check(ship, _spec())
        assert any("GARr" in r or "gar" in r.lower() for r in result.rejection_reasons)

    def test_gar_within_spec(self, checker):
        ship = _shipment(gar_kcal_kg=5500.0)
        result = checker.check(ship, _spec())
        assert result.parameter_results["gar"] == SpecStatus.WITHIN_SPEC.value


# ---------------------------------------------------------------------------
# check() — price adjustment
# ---------------------------------------------------------------------------

class TestPriceAdjustment:
    def test_positive_price_adj_for_high_gar(self, checker):
        ship = _shipment(gar_kcal_kg=5800.0)  # 300 kcal above typical
        result = checker.check(ship, _spec())
        assert result.price_adjustment_usd_tonne > 0

    def test_negative_price_adj_for_low_gar(self, checker):
        ship = _shipment(gar_kcal_kg=5350.0)  # 150 kcal below typical
        result = checker.check(ship, _spec())
        assert result.price_adjustment_usd_tonne < 0

    def test_total_price_impact_calculated(self, checker):
        ship = _shipment(gar_kcal_kg=5800.0, tonnes=10_000.0)
        result = checker.check(ship, _spec())
        expected = result.price_adjustment_usd_tonne * 10_000.0
        assert abs(result.total_price_impact_usd - expected) < 1.0


# ---------------------------------------------------------------------------
# check() — parameter failures
# ---------------------------------------------------------------------------

class TestParameterFailures:
    def test_high_moisture_rejected(self, checker):
        ship = _shipment(total_moisture_pct=32.0)
        result = checker.check(ship, _spec())
        assert result.overall_status == "REJECTED"

    def test_high_sulphur_rejected(self, checker):
        ship = _shipment(total_sulphur_pct=1.2)
        result = checker.check(ship, _spec())
        assert result.overall_status == "REJECTED"

    def test_hgi_below_min_rejected(self, checker):
        ship = _shipment(hgi=38.0)
        result = checker.check(ship, _spec())
        assert result.overall_status == "REJECTED"

    def test_hgi_not_checked_if_spec_has_no_hgi_min(self, checker):
        spec = _spec(hgi_min=None)
        ship = _shipment(hgi=20.0)
        result = checker.check(ship, spec)
        assert "hgi" not in result.parameter_results

    def test_recommendations_generated_for_high_ash(self, checker):
        ship = _shipment(ash_pct=13.5)
        result = checker.check(ship, _spec())
        assert any("ash" in r.lower() for r in result.recommendations)

    def test_warnings_generated_near_gar_minimum(self, checker):
        ship = _shipment(gar_kcal_kg=5350.0)
        result = checker.check(ship, _spec())
        assert any("rejection minimum" in w or "100 kcal" in w for w in result.warnings)
