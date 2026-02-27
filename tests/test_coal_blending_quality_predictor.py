"""Unit tests for coal_blending_quality_predictor module."""

import pytest
from src.coal_blending_quality_predictor import (
    BlendResult,
    BlendSpecification,
    CoalComponent,
    CoalBlendingQualityPredictor,
)


def _kaltim():
    return CoalComponent(
        "Kaltim-Prima", 60, cv_gar_mj_kg=26.5, ash_pct_ar=5.2,
        moisture_pct_ar=18.0, sulfur_pct_ar=0.45, volatile_matter_pct_adb=39.0, hgi=52,
        cost_usd_t=85.0
    )


def _adaro():
    return CoalComponent(
        "Adaro", 40, cv_gar_mj_kg=19.8, ash_pct_ar=3.8,
        moisture_pct_ar=28.0, sulfur_pct_ar=0.20, volatile_matter_pct_adb=40.0, hgi=58,
        cost_usd_t=55.0
    )


def _default_spec():
    return BlendSpecification("Standard", cv_gar_min_mj_kg=20.0, ash_max_pct_ar=12.0,
                               sulfur_max_pct_ar=0.8, moisture_max_pct_ar=30.0, hgi_min=45.0)


class TestCoalComponent:
    def test_valid(self):
        c = _kaltim()
        assert c.source_id == "Kaltim-Prima"

    def test_invalid_proportion(self):
        with pytest.raises(ValueError):
            CoalComponent("X", 110, 25.0, 5.0, 20.0, 0.5, 40.0, 50)

    def test_invalid_cv(self):
        with pytest.raises(ValueError):
            CoalComponent("X", 50, -1.0, 5.0, 20.0, 0.5, 40.0, 50)

    def test_invalid_sulfur(self):
        with pytest.raises(ValueError):
            CoalComponent("X", 50, 25.0, 5.0, 20.0, 15.0, 40.0, 50)

    def test_invalid_hgi_low(self):
        with pytest.raises(ValueError):
            CoalComponent("X", 50, 25.0, 5.0, 20.0, 0.5, 40.0, 10)

    def test_invalid_hgi_high(self):
        with pytest.raises(ValueError):
            CoalComponent("X", 50, 25.0, 5.0, 20.0, 0.5, 40.0, 130)


class TestCoalBlendingQualityPredictor:
    def setup_method(self):
        self.pred = CoalBlendingQualityPredictor()

    def test_predict_basic(self):
        result = self.pred.predict([_kaltim(), _adaro()])
        assert isinstance(result, BlendResult)

    def test_proportion_sum_error(self):
        c1 = CoalComponent("A", 30, 25.0, 5.0, 20.0, 0.5, 40.0, 52)
        c2 = CoalComponent("B", 30, 20.0, 4.0, 25.0, 0.3, 39.0, 55)
        with pytest.raises(ValueError, match="100%"):
            self.pred.predict([c1, c2])

    def test_empty_components_raises(self):
        with pytest.raises(ValueError):
            self.pred.predict([])

    def test_blend_cv_is_weighted_mean(self):
        result = self.pred.predict([_kaltim(), _adaro()])
        expected = 26.5 * 0.6 + 19.8 * 0.4
        assert abs(result.blend_cv_gar_mj_kg - expected) < 0.05

    def test_blend_ash_is_weighted_mean(self):
        result = self.pred.predict([_kaltim(), _adaro()])
        expected = 5.2 * 0.6 + 3.8 * 0.4
        assert abs(result.blend_ash_pct_ar - expected) < 0.05

    def test_blend_moisture_is_weighted_mean(self):
        result = self.pred.predict([_kaltim(), _adaro()])
        expected = 18.0 * 0.6 + 28.0 * 0.4
        assert abs(result.blend_moisture_pct_ar - expected) < 0.05

    def test_blend_sulfur_is_weighted_mean(self):
        result = self.pred.predict([_kaltim(), _adaro()])
        expected = 0.45 * 0.6 + 0.20 * 0.4
        assert abs(result.blend_sulfur_pct_ar - expected) < 0.005

    def test_blend_hgi_sengupta_correction(self):
        result = self.pred.predict([_kaltim(), _adaro()])
        # Sengupta HGI blend should be between min and max component HGI
        assert 52 <= result.blend_hgi <= 58

    def test_blend_cost_computed(self):
        result = self.pred.predict([_kaltim(), _adaro()])
        expected = 85.0 * 0.6 + 55.0 * 0.4
        assert result.blend_cost_usd_t is not None
        assert abs(result.blend_cost_usd_t - expected) < 0.5

    def test_blend_cost_none_if_any_missing(self):
        k = _kaltim()
        a = _adaro()
        a.cost_usd_t = None
        result = self.pred.predict([k, a])
        assert result.blend_cost_usd_t is None

    def test_compliant_blend(self):
        # High CV, low ash blend should pass the spec
        spec = BlendSpecification("Strict", cv_gar_min_mj_kg=20.0, ash_max_pct_ar=10.0,
                                   sulfur_max_pct_ar=0.8, moisture_max_pct_ar=35.0)
        result = self.pred.predict([_kaltim(), _adaro()], spec)
        assert result.is_compliant
        assert len(result.violations) == 0

    def test_violation_low_cv(self):
        spec = BlendSpecification("High-CV spec", cv_gar_min_mj_kg=30.0)
        result = self.pred.predict([_kaltim(), _adaro()], spec)
        assert not result.is_compliant
        assert any("CV" in v for v in result.violations)

    def test_violation_high_ash(self):
        c1 = CoalComponent("HighAsh", 60, 22.0, 20.0, 15.0, 0.5, 38.0, 55)
        c2 = CoalComponent("MidAsh", 40, 20.0, 18.0, 12.0, 0.4, 37.0, 50)
        spec = BlendSpecification("LowAsh", ash_max_pct_ar=10.0)
        result = self.pred.predict([c1, c2], spec)
        assert not result.is_compliant
        assert any("Ash" in v for v in result.violations)

    def test_violation_high_sulfur(self):
        c1 = CoalComponent("HighS", 50, 24.0, 5.0, 15.0, 1.5, 38.0, 52)
        c2 = CoalComponent("LowS", 50, 22.0, 4.0, 18.0, 0.8, 36.0, 50)
        spec = BlendSpecification("LowSulfur", sulfur_max_pct_ar=0.8)
        result = self.pred.predict([c1, c2], spec)
        assert not result.is_compliant
        assert any("Sulfur" in v for v in result.violations)

    def test_astm_rank_bituminous(self):
        result = self.pred.predict([_kaltim(), _adaro()])
        assert "bituminous" in result.astm_rank.lower() or "subbituminous" in result.astm_rank.lower()

    def test_astm_rank_lignite_low_cv(self):
        c = CoalComponent("LigniteMine", 100, 12.0, 8.0, 40.0, 0.3, 50.0, 40)
        # HGI=40 is below valid range; use min valid
        c.hgi = 20
        result = self.pred.predict([c])
        assert result.astm_rank == "lignite"

    def test_three_component_blend(self):
        c1 = CoalComponent("A", 50, 26.5, 5.2, 18.0, 0.45, 39.0, 52)
        c2 = CoalComponent("B", 30, 22.0, 6.0, 22.0, 0.30, 40.0, 55)
        c3 = CoalComponent("C", 20, 18.5, 4.0, 30.0, 0.20, 41.0, 58)
        result = self.pred.predict([c1, c2, c3])
        assert isinstance(result, BlendResult)

    def test_sodium_caution(self):
        c1 = CoalComponent("HighNa", 60, 24.0, 5.0, 18.0, 0.4, 38.0, 52, sodium_pct_ar=0.5)
        c2 = CoalComponent("LowNa", 40, 22.0, 4.0, 20.0, 0.3, 37.0, 50, sodium_pct_ar=0.1)
        result = self.pred.predict([c1, c2])
        # Blend sodium = 0.34%, triggers caution (>0.3 threshold)
        assert any("odium" in c for c in result.cautions)

    def test_optimise_proportions_returns_results(self):
        comps = [_kaltim(), _adaro()]
        results = self.pred.optimise_proportions(comps, target_cv_gar=24.0, steps=10)
        # Should find at least one blend near 24 MJ/kg
        assert len(results) > 0
        for pct_a, pct_b, res in results:
            assert abs(res.blend_cv_gar_mj_kg - 24.0) <= 0.5

    def test_optimise_proportions_three_components_raises(self):
        c3 = CoalComponent("C", 30, 20.0, 4.0, 25.0, 0.3, 39.0, 55)
        with pytest.raises(ValueError, match="2 components"):
            self.pred.optimise_proportions([_kaltim(), _adaro(), c3], 24.0)
