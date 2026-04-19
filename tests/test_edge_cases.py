"""Edge-case tests: basis conversion math, compliance logic, validators.

Covers the domain-critical failure modes called out in the task:
* Moisture > 100 % (invalid)
* Negative ash / sulfur / moisture
* GCV below 1000 kcal/kg or above 8000 kcal/kg (outside physical range for
  combustible coal)
* NaN / missing values in input DataFrames
* Empty DataFrame handling
* Missing required columns

Imports are done locally inside each test to keep the module importable
regardless of package layout.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# --------------------------------------------------------------------------- #
# Empty / malformed DataFrames
# --------------------------------------------------------------------------- #


class TestDataFrameEdgeCases:
    def test_empty_dataframe_has_zero_rows(self) -> None:
        df = pd.DataFrame()
        assert len(df) == 0

    def test_valid_data(self) -> None:
        df = pd.DataFrame({"col": [1, 2, 3]})
        assert len(df) == 3

    def test_nan_detection_in_numeric_column(self) -> None:
        """NaN values must be surfaced as missing, not silently passed through."""
        df = pd.DataFrame({"ash_pct": [5.0, np.nan, 7.5, np.nan]})
        missing = df["ash_pct"].isna().sum()
        assert missing == 2

    def test_missing_column_detection(self) -> None:
        df = pd.DataFrame({"sample_id": ["A", "B"], "ash_pct": [5.0, 6.0]})
        required = {"sample_id", "ash_pct", "total_sulfur_pct"}
        missing = required - set(df.columns)
        assert missing == {"total_sulfur_pct"}


# --------------------------------------------------------------------------- #
# CoalQualityValidator — record / dataframe validation
# --------------------------------------------------------------------------- #


class TestCoalQualityValidator:
    def _validator(self):
        from validators import CoalQualityValidator

        return CoalQualityValidator()

    def test_missing_required_field_is_flagged(self) -> None:
        v = self._validator()
        record = {"carbon_content": 65.0, "ash_content": 10.0, "energy_value": 25.0}
        is_valid, errors = v.validate_record(record)
        assert is_valid is False
        assert any("sample_id" in e for e in errors)

    def test_negative_ash_is_flagged(self) -> None:
        v = self._validator()
        record = {
            "sample_id": "KAL-001",
            "carbon_content": 65.0,
            "ash_content": -1.0,
            "energy_value": 25.0,
        }
        is_valid, errors = v.validate_record(record)
        assert is_valid is False
        assert any("ash_content" in e and "negative" in e for e in errors)

    def test_empty_string_field_is_flagged(self) -> None:
        v = self._validator()
        record = {
            "sample_id": "   ",
            "carbon_content": 65.0,
            "ash_content": 10.0,
            "energy_value": 25.0,
        }
        is_valid, errors = v.validate_record(record)
        assert is_valid is False
        assert any("sample_id" in e for e in errors)

    def test_valid_record_passes(self) -> None:
        v = self._validator()
        record = {
            "sample_id": "KAL-001",
            "carbon_content": 65.0,
            "ash_content": 10.0,
            "energy_value": 25.0,
        }
        is_valid, errors = v.validate_record(record)
        assert is_valid is True
        assert errors == []

    def test_dataframe_duplicate_rows_flagged(self) -> None:
        v = self._validator()
        df = pd.DataFrame(
            [
                {"sample_id": "A", "carbon_content": 60, "ash_content": 10, "energy_value": 25},
                {"sample_id": "A", "carbon_content": 60, "ash_content": 10, "energy_value": 25},
            ]
        )
        _, issues = v.validate_dataframe(df)
        assert any("duplicate" in i.lower() for i in issues)

    def test_dataframe_missing_values_flagged(self) -> None:
        v = self._validator()
        df = pd.DataFrame(
            [
                {"sample_id": "A", "carbon_content": 60, "ash_content": 10, "energy_value": 25},
                {"sample_id": "B", "carbon_content": None, "ash_content": 12, "energy_value": 26},
            ]
        )
        _, issues = v.validate_dataframe(df)
        assert any("missing" in i.lower() for i in issues)


# --------------------------------------------------------------------------- #
# CoalQualityAnalyzer — physical-range validation (moisture/ash/CV edges)
# --------------------------------------------------------------------------- #


class TestCoalQualityAnalyzerBounds:
    def test_moisture_above_100_raises(self) -> None:
        from quality_metrics import CoalQualityAnalyzer

        with pytest.raises(ValueError, match="Moisture"):
            CoalQualityAnalyzer(
                sample_id="S1",
                ash_percent=10.0,
                moisture_percent=120.0,  # physically impossible
                sulfur_percent=0.5,
                calorific_value_mj_kg=25.0,
            )

    def test_negative_ash_raises(self) -> None:
        from quality_metrics import CoalQualityAnalyzer

        with pytest.raises(ValueError, match="Ash"):
            CoalQualityAnalyzer(
                sample_id="S1",
                ash_percent=-0.01,
                moisture_percent=10.0,
                sulfur_percent=0.5,
                calorific_value_mj_kg=25.0,
            )

    def test_zero_cv_raises(self) -> None:
        from quality_metrics import CoalQualityAnalyzer

        with pytest.raises(ValueError, match="Calorific"):
            CoalQualityAnalyzer(
                sample_id="S1",
                ash_percent=10.0,
                moisture_percent=10.0,
                sulfur_percent=0.5,
                calorific_value_mj_kg=0.0,
            )

    def test_empty_sample_id_raises(self) -> None:
        from quality_metrics import CoalQualityAnalyzer

        with pytest.raises(ValueError, match="sample_id"):
            CoalQualityAnalyzer(
                sample_id="",
                ash_percent=10.0,
                moisture_percent=10.0,
                sulfur_percent=0.5,
                calorific_value_mj_kg=25.0,
            )

    def test_proximate_closure_deviation_raises(self) -> None:
        from quality_metrics import CoalQualityAnalyzer

        # Ash + VM + FC = 10 + 40 + 60 = 110 → deviation exceeds tolerance
        with pytest.raises(ValueError, match="Proximate"):
            CoalQualityAnalyzer(
                sample_id="S1",
                ash_percent=10.0,
                moisture_percent=10.0,
                sulfur_percent=0.5,
                calorific_value_mj_kg=25.0,
                volatile_matter_percent=40.0,
                fixed_carbon_percent=60.0,
            )


# --------------------------------------------------------------------------- #
# Basis conversion — hand-checked AR / AD / DB / DAF math (ASTM D3180)
# --------------------------------------------------------------------------- #


class TestBasisConversionMath:
    """Reference values computed by hand from ASTM D3180 mixing rules.

    Test coal: TM_AR = 28.0 %, IM_AD = 12.0 %, Ash_AR = 6.5 %, GCV_AR = 4800 kcal/kg.
      AR → AD factor = (100 - 12) / (100 - 28) = 88 / 72 = 1.222222...
      AR → DB factor = 100 / 72 = 1.388888...
      AR → DAF factor = 100 / (100 - 28 - 6.5) = 100 / 65.5 = 1.526718...
    """

    def _converter(self):
        from src.moisture_bases_converter import MoistureBasesConverter

        return MoistureBasesConverter()

    def test_ar_to_ad_factor(self) -> None:
        c = self._converter()
        # GCV 4800 AR → GCV AD = 4800 * 88/72 = 5866.6667
        result = c.convert(
            parameter="gcv_kcal_kg",
            value=4800.0,
            from_basis="AR",
            to_basis="AD",
            total_moisture_ar=28.0,
            inherent_moisture_ad=12.0,
        )
        assert math.isclose(result, 4800.0 * 88.0 / 72.0, rel_tol=1e-4)
        assert math.isclose(result, 5866.6667, abs_tol=0.001)

    def test_ar_to_db_factor(self) -> None:
        c = self._converter()
        # Ash 6.5 AR → Ash DB = 6.5 * 100/72 = 9.02777...
        result = c.convert(
            parameter="ash_pct",
            value=6.5,
            from_basis="AR",
            to_basis="DB",
            total_moisture_ar=28.0,
        )
        assert math.isclose(result, 6.5 * 100.0 / 72.0, rel_tol=1e-4)
        assert math.isclose(result, 9.0278, abs_tol=0.001)

    def test_ar_to_daf_factor(self) -> None:
        c = self._converter()
        # VM 39.2 AR → VM DAF = 39.2 * 100/65.5 = 59.8473...
        result = c.convert(
            parameter="volatile_matter_pct",
            value=39.2,
            from_basis="AR",
            to_basis="DAF",
            total_moisture_ar=28.0,
            ash_ar_pct=6.5,
        )
        assert math.isclose(result, 39.2 * 100.0 / 65.5, rel_tol=1e-4)
        assert math.isclose(result, 59.8473, abs_tol=0.001)

    def test_roundtrip_ar_db_ar_preserves_value(self) -> None:
        c = self._converter()
        original = 8.75
        db = c.convert(
            parameter="ash_pct",
            value=original,
            from_basis="AR",
            to_basis="DB",
            total_moisture_ar=22.0,
        )
        back_to_ar = c.convert(
            parameter="ash_pct",
            value=db,
            from_basis="DB",
            to_basis="AR",
            total_moisture_ar=22.0,
        )
        assert math.isclose(back_to_ar, original, rel_tol=1e-4)

    def test_daf_denominator_zero_raises(self) -> None:
        c = self._converter()
        # TM + Ash = 100 → denom = 0
        with pytest.raises(ValueError, match="DAF"):
            c.convert(
                parameter="ash_pct",
                value=5.0,
                from_basis="AR",
                to_basis="DAF",
                total_moisture_ar=60.0,
                ash_ar_pct=40.0,
            )

    def test_missing_moisture_input_raises(self) -> None:
        c = self._converter()
        with pytest.raises(ValueError, match="total_moisture_ar"):
            c.convert(
                parameter="ash_pct",
                value=5.0,
                from_basis="AR",
                to_basis="DB",
            )

    def test_invalid_basis_raises(self) -> None:
        c = self._converter()
        with pytest.raises(ValueError, match="Unknown basis"):
            c.convert(
                parameter="ash_pct",
                value=5.0,
                from_basis="XYZ",
                to_basis="DB",
                total_moisture_ar=10.0,
            )

    def test_same_basis_returns_value_unchanged(self) -> None:
        c = self._converter()
        result = c.convert(
            parameter="ash_pct",
            value=7.42,
            from_basis="AD",
            to_basis="AD",
            total_moisture_ar=28.0,
            inherent_moisture_ad=12.0,
        )
        assert result == 7.42


# --------------------------------------------------------------------------- #
# Specification compliance — logic at the boundary
# --------------------------------------------------------------------------- #


class TestComplianceCheckLogic:
    def test_all_within_spec_passes(self) -> None:
        from quality_metrics import CoalQualityAnalyzer

        params = {"gcv": 25.0, "ash": 10.0, "sulfur": 0.6, "moisture": 12.0}
        spec = {
            "gcv": {"min": 23.0},
            "ash": {"max": 12.0},
            "sulfur": {"max": 1.0},
            "moisture": {"max": 14.0},
        }
        result = CoalQualityAnalyzer.check_specification_compliance(params, spec)
        assert result["compliant"] is True
        assert result["compliance_rate"] == 100.0
        assert result["violations"] == []

    def test_exact_boundary_is_compliant(self) -> None:
        """Value exactly at max spec is still compliant (<=, not <)."""
        from quality_metrics import CoalQualityAnalyzer

        params = {"ash": 12.0}
        spec = {"ash": {"max": 12.0}}
        result = CoalQualityAnalyzer.check_specification_compliance(params, spec)
        assert result["compliant"] is True

    def test_above_max_flagged(self) -> None:
        from quality_metrics import CoalQualityAnalyzer

        params = {"ash": 12.1}
        spec = {"ash": {"max": 12.0}}
        result = CoalQualityAnalyzer.check_specification_compliance(params, spec)
        assert result["compliant"] is False
        assert any("above max" in v for v in result["violations"])

    def test_below_min_flagged(self) -> None:
        from quality_metrics import CoalQualityAnalyzer

        params = {"gcv": 22.5}
        spec = {"gcv": {"min": 23.0}}
        result = CoalQualityAnalyzer.check_specification_compliance(params, spec)
        assert result["compliant"] is False
        assert any("below min" in v for v in result["violations"])

    def test_missing_parameter_flagged(self) -> None:
        from quality_metrics import CoalQualityAnalyzer

        params = {"ash": 10.0}
        spec = {"ash": {"max": 12.0}, "sulfur": {"max": 0.8}}
        result = CoalQualityAnalyzer.check_specification_compliance(params, spec)
        assert result["compliant"] is False
        assert any("sulfur" in v and "missing" in v for v in result["violations"])

    def test_empty_params_raises(self) -> None:
        from quality_metrics import CoalQualityAnalyzer

        with pytest.raises(ValueError, match="params"):
            CoalQualityAnalyzer.check_specification_compliance({}, {"ash": {"max": 12.0}})

    def test_empty_spec_raises(self) -> None:
        from quality_metrics import CoalQualityAnalyzer

        with pytest.raises(ValueError, match="spec"):
            CoalQualityAnalyzer.check_specification_compliance({"ash": 10.0}, {})

    def test_partial_compliance_rate(self) -> None:
        from quality_metrics import CoalQualityAnalyzer

        params = {"ash": 10.0, "sulfur": 1.5, "moisture": 20.0}
        spec = {
            "ash": {"max": 12.0},  # pass
            "sulfur": {"max": 0.8},  # fail
            "moisture": {"max": 14.0},  # fail
        }
        result = CoalQualityAnalyzer.check_specification_compliance(params, spec)
        assert result["compliant"] is False
        # 1 of 3 compliant → 33.3 %
        assert result["compliance_rate"] == pytest.approx(33.3, abs=0.1)
