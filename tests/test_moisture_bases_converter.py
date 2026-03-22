"""
Unit tests for MoistureBasesConverter.
"""

import pytest
from src.moisture_bases_converter import MoistureBasesConverter, ProximateAnalysis


@pytest.fixture
def converter():
    return MoistureBasesConverter()


# Typical Kalimantan thermal coal reference values
TM_AR = 28.0    # Total moisture AR (%)
IM_AD = 12.0    # Inherent moisture AD (%)
ASH_AR = 6.5    # Ash AR (%)


class TestProximateAnalysisDataclass:
    def test_valid_basis_accepted(self):
        pa = ProximateAnalysis(basis="AR", ash_pct=6.5)
        assert pa.basis == "AR"

    def test_basis_case_insensitive(self):
        pa = ProximateAnalysis(basis="ad", ash_pct=8.0)
        assert pa.basis == "AD"

    def test_invalid_basis_raises(self):
        with pytest.raises(ValueError, match="Invalid basis"):
            ProximateAnalysis(basis="XX", ash_pct=5.0)


class TestConvert:
    def test_same_basis_returns_unchanged(self, converter):
        result = converter.convert("ash", 8.5, "AR", "AR")
        assert result == 8.5

    def test_ar_to_db_increases_value(self, converter):
        # Removing moisture increases relative concentration
        ash_db = converter.convert("ash", ASH_AR, "AR", "DB",
                                   total_moisture_ar=TM_AR)
        assert ash_db > ASH_AR

    def test_ar_to_ad_intermediate_value(self, converter):
        ash_ad = converter.convert("ash", ASH_AR, "AR", "AD",
                                   total_moisture_ar=TM_AR,
                                   inherent_moisture_ad=IM_AD)
        ash_db = converter.convert("ash", ASH_AR, "AR", "DB",
                                   total_moisture_ar=TM_AR)
        # AD value should be between AR and DB
        assert ASH_AR < ash_ad < ash_db

    def test_ar_to_db_to_ar_roundtrip(self, converter):
        ash_db = converter.convert("ash", ASH_AR, "AR", "DB",
                                   total_moisture_ar=TM_AR)
        ash_ar_back = converter.convert("ash", ash_db, "DB", "AR",
                                        total_moisture_ar=TM_AR)
        assert abs(ash_ar_back - ASH_AR) < 0.01

    def test_ar_to_ad_to_ar_roundtrip(self, converter):
        ash_ad = converter.convert("ash", ASH_AR, "AR", "AD",
                                   total_moisture_ar=TM_AR,
                                   inherent_moisture_ad=IM_AD)
        ash_ar_back = converter.convert("ash", ash_ad, "AD", "AR",
                                        total_moisture_ar=TM_AR,
                                        inherent_moisture_ad=IM_AD)
        assert abs(ash_ar_back - ASH_AR) < 0.01

    def test_ad_to_db(self, converter):
        ash_ad = 9.0
        ash_db = converter.convert("ash", ash_ad, "AD", "DB",
                                   inherent_moisture_ad=IM_AD)
        expected = ash_ad * 100.0 / (100 - IM_AD)
        assert abs(ash_db - expected) < 0.01

    def test_ar_to_daf(self, converter):
        # DAF value should be highest (moisture + ash removed)
        ash_daf = converter.convert("ash", ASH_AR, "AR", "DAF",
                                    total_moisture_ar=TM_AR,
                                    ash_ar_pct=ASH_AR)
        ash_db = converter.convert("ash", ASH_AR, "AR", "DB",
                                   total_moisture_ar=TM_AR)
        assert ash_daf > ash_db

    def test_unknown_basis_raises(self, converter):
        with pytest.raises(ValueError, match="Unknown basis"):
            converter.convert("ash", 8.0, "XX", "DB")

    def test_missing_moisture_for_ar_db_raises(self, converter):
        with pytest.raises(ValueError, match="total_moisture_ar"):
            converter.convert("ash", 8.0, "AR", "DB")


class TestGcvGarToGad:
    def test_gar_to_gad_gives_higher_value(self, converter):
        gcv_gar = 4800
        gcv_gad = converter.gcv_gar_to_gad(gcv_gar, TM_AR, IM_AD)
        assert gcv_gad > gcv_gar  # removing more moisture → higher GCV

    def test_reasonable_gcv_range(self, converter):
        # Indonesian coal: GAD typically 10-20% higher than GAR for high-moisture coal
        gcv_gar = 4800
        gcv_gad = converter.gcv_gar_to_gad(gcv_gar, TM_AR, IM_AD)
        assert 5000 < gcv_gad < 7000


class TestConvertFullAnalysis:
    @pytest.fixture
    def ar_analysis(self):
        return ProximateAnalysis(
            basis="AR",
            total_moisture_pct=28.0,
            inherent_moisture_pct=12.0,
            ash_pct=6.5,
            volatile_matter_pct=39.2,
            fixed_carbon_pct=24.3,
            total_sulfur_pct=0.38,
            gcv_kcal_kg=4800,
        )

    def test_returns_proximate_analysis(self, converter, ar_analysis):
        result = converter.convert_full_analysis(ar_analysis, "DB")
        assert isinstance(result, ProximateAnalysis)
        assert result.basis == "DB"

    def test_db_result_has_no_moisture_values(self, converter, ar_analysis):
        result = converter.convert_full_analysis(ar_analysis, "DB")
        assert result.total_moisture_pct is None
        assert result.inherent_moisture_pct is None

    def test_ar_result_preserves_total_moisture(self, converter, ar_analysis):
        result = converter.convert_full_analysis(ar_analysis, "AR")
        assert result.total_moisture_pct == 28.0

    def test_all_db_values_higher_than_ar(self, converter, ar_analysis):
        result = converter.convert_full_analysis(ar_analysis, "DB")
        assert result.ash_pct > ar_analysis.ash_pct
        assert result.volatile_matter_pct > ar_analysis.volatile_matter_pct
        assert result.gcv_kcal_kg > ar_analysis.gcv_kcal_kg


class TestBatchConvert:
    def test_batch_adds_converted_value(self, converter):
        rows = [
            {"value": 6.5, "total_moisture_ar": 28.0},
            {"value": 7.2, "total_moisture_ar": 25.0},
        ]
        result = converter.batch_convert(rows, "ash_pct", "AR", "DB")
        assert all("converted_value" in r for r in result)
        assert result[0]["converted_value"] > 6.5

    def test_missing_value_key_raises(self, converter):
        rows = [{"total_moisture_ar": 28.0}]
        with pytest.raises(ValueError, match="missing 'value'"):
            converter.batch_convert(rows, "ash", "AR", "DB")
