"""
Unit tests for ExportComplianceChecker and CoalBatch.
"""

import pytest
from src.export_compliance import (
    ExportComplianceChecker,
    CoalBatch,
    MARKET_SPECS,
)


@pytest.fixture
def good_batch():
    """A coal batch that meets Japan standard specs."""
    return CoalBatch(
        batch_id="BATCH-GOOD-001",
        mine_code="KPC-EK",
        gcv_adb_kcal_kg=6300,
        total_moisture_pct=12.5,
        ash_adb_pct=11.0,
        total_sulfur_adb_pct=0.55,
        volatile_matter_adb_pct=37.0,
        tonnes=50000,
    )


@pytest.fixture
def bad_batch():
    """A coal batch that fails on multiple parameters."""
    return CoalBatch(
        batch_id="BATCH-FAIL-001",
        mine_code="MINE-B",
        gcv_adb_kcal_kg=5500,  # Below Japan min of 6000
        total_moisture_pct=20.0,  # Above Japan max of 18%
        ash_adb_pct=16.0,  # Above Japan max of 15%
        total_sulfur_adb_pct=0.90,  # Above Japan max of 0.80%
        volatile_matter_adb_pct=38.0,
    )


@pytest.fixture
def japan_checker():
    """ExportComplianceChecker for japan_standard market."""
    return ExportComplianceChecker("japan_standard")


class TestCoalBatch:

    def test_valid_batch(self, good_batch):
        """Test that a valid batch initializes correctly."""
        assert good_batch.batch_id == "BATCH-GOOD-001"
        assert good_batch.gcv_adb_kcal_kg == 6300

    def test_empty_batch_id_raises(self):
        """Test that empty batch_id raises ValueError."""
        with pytest.raises(ValueError, match="batch_id cannot be empty"):
            CoalBatch("", "MINE-A", 6000, 15, 12, 0.6, 35)

    def test_negative_gcv_raises(self):
        """Test that negative GCV raises ValueError."""
        with pytest.raises(ValueError, match="gcv_adb_kcal_kg must be positive"):
            CoalBatch("B1", "MINE-A", -100, 15, 12, 0.6, 35)

    def test_moisture_out_of_range_raises(self):
        """Test that moisture > 100% raises ValueError."""
        with pytest.raises(ValueError, match="total_moisture_pct must be 0-100"):
            CoalBatch("B1", "MINE-A", 6000, 105, 12, 0.6, 35)

    def test_sulfur_out_of_range_raises(self):
        """Test that sulfur > 10% raises ValueError."""
        with pytest.raises(ValueError, match="total_sulfur_adb_pct must be 0-10"):
            CoalBatch("B1", "MINE-A", 6000, 15, 12, 15.0, 35)


class TestExportComplianceChecker:

    def test_invalid_market_raises(self):
        """Test that unknown market raises ValueError."""
        with pytest.raises(ValueError, match="not recognized"):
            ExportComplianceChecker("uk_standard")

    def test_available_markets_returns_list(self):
        """Test that available_markets returns all market names."""
        markets = ExportComplianceChecker.available_markets()
        assert "japan_standard" in markets
        assert "china_standard" in markets
        assert "india_standard" in markets
        assert "indonesian_domestic" in markets

    def test_compliant_batch_passes(self, japan_checker, good_batch):
        """Test that a batch meeting all Japan specs is compliant."""
        result = japan_checker.check_batch(good_batch)
        assert result["is_compliant"] is True
        assert result["failed_count"] == 0

    def test_non_compliant_batch_fails(self, japan_checker, bad_batch):
        """Test that a failing batch reports non-compliance."""
        result = japan_checker.check_batch(bad_batch)
        assert result["is_compliant"] is False
        assert result["failed_count"] > 0

    def test_failed_parameters_identified(self, japan_checker, bad_batch):
        """Test that specific failing parameters are reported."""
        result = japan_checker.check_batch(bad_batch)
        failed = result["failed_parameters"]
        # GCV, moisture, ash, and sulfur should all fail
        assert "gcv_adb_kcal_kg" in failed
        assert "total_moisture_pct" in failed
        assert "ash_adb_pct" in failed
        assert "total_sulfur_adb_pct" in failed

    def test_china_more_lenient_than_japan(self, good_batch, bad_batch):
        """Test that a batch failing Japan standard may pass China standard."""
        # bad_batch has GCV 5500 which fails Japan (min 6000) but passes China (min 5000)
        china_checker = ExportComplianceChecker("china_standard")
        # GCV 5500 should pass China, but moisture/ash/sulfur might still fail
        result = china_checker.check_batch(bad_batch)
        # GCV should not be in failed for China
        assert "gcv_adb_kcal_kg" not in result["failed_parameters"]

    def test_check_batches_summary(self, japan_checker, good_batch, bad_batch):
        """Test fleet-level compliance summary."""
        summary = japan_checker.check_batches([good_batch, bad_batch])
        assert summary["total_batches"] == 2
        assert summary["compliant_batches"] == 1
        assert summary["non_compliant_batches"] == 1
        assert summary["compliance_rate_pct"] == 50.0

    def test_empty_batches_raises(self, japan_checker):
        """Test that empty batch list raises ValueError."""
        with pytest.raises(ValueError, match="batches list cannot be empty"):
            japan_checker.check_batches([])

    def test_parameter_result_structure(self, japan_checker, good_batch):
        """Test that parameter results contain required keys."""
        result = japan_checker.check_batch(good_batch)
        for param_result in result["parameter_results"]:
            assert "parameter" in param_result
            assert "passed" in param_result
            assert "value" in param_result
            assert "deviation" in param_result
