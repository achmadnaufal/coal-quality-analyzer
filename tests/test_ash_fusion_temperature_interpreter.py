"""Unit tests for AshFusionTemperatureInterpreter."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ash_fusion_temperature_interpreter import (
    AshFusionTemperatureInterpreter,
    AshFusionTemperatures,
    AshComposition,
    AtmosphereType,
    SlaggingRisk,
    FoulingRisk,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_ash_comp(
    sio2=45.2, al2o3=22.1, fe2o3=12.5, cao=6.8, mgo=2.1,
    na2o=0.8, k2o=1.2, tio2=1.0, sulfur=0.6,
) -> AshComposition:
    return AshComposition(
        sio2=sio2, al2o3=al2o3, fe2o3=fe2o3, cao=cao,
        mgo=mgo, na2o=na2o, k2o=k2o, tio2=tio2,
        total_sulfur_pct=sulfur,
    )


def make_aft(
    sample_id="KTM_001",
    dt=1100, ht=1280, ft=1350,
    atmosphere=AtmosphereType.REDUCING,
    ash_comp=None,
) -> AshFusionTemperatures:
    return AshFusionTemperatures(
        sample_id=sample_id,
        coal_name="Test Coal",
        atmosphere=atmosphere,
        dt_c=dt,
        ht_c=ht,
        ft_c=ft,
        ash_composition=ash_comp,
    )


# ---------------------------------------------------------------------------
# AshComposition tests
# ---------------------------------------------------------------------------

class TestAshComposition:
    def test_base_acid_ratio(self):
        comp = make_ash_comp(fe2o3=10, cao=5, mgo=2, k2o=1, na2o=1, sio2=40, al2o3=20, tio2=1)
        # base = 19, acid = 61
        assert abs(comp.base_acid_ratio - 19/61) < 0.001

    def test_fouling_index(self):
        comp = make_ash_comp(na2o=2.0)
        fi = comp.fouling_index
        assert fi == pytest.approx(comp.base_acid_ratio * 2.0, abs=1e-9)

    def test_slagging_index_rs(self):
        comp = make_ash_comp(sulfur=1.0)
        assert abs(comp.slagging_index_rs - comp.base_acid_ratio) < 0.001

    def test_negative_oxide_raises(self):
        with pytest.raises(ValueError):
            make_ash_comp(sio2=-1)


# ---------------------------------------------------------------------------
# AshFusionTemperatures tests
# ---------------------------------------------------------------------------

class TestAshFusionTemperatures:
    def test_fusion_span(self):
        aft = make_aft(dt=1100, ft=1400)
        assert aft.fusion_span_c == 300

    def test_is_high_fusion_true(self):
        aft = make_aft(dt=1200, ht=1380, ft=1450)
        assert aft.is_high_fusion is True

    def test_is_high_fusion_false(self):
        aft = make_aft(dt=1000, ht=1150, ft=1250)
        assert aft.is_high_fusion is False

    def test_ft_below_ht_raises(self):
        with pytest.raises(ValueError):
            make_aft(dt=1000, ht=1300, ft=1200)

    def test_ht_below_dt_raises(self):
        with pytest.raises(ValueError):
            make_aft(dt=1300, ht=1100, ft=1400)

    def test_temperature_out_of_range_raises(self):
        with pytest.raises(ValueError):
            make_aft(dt=500, ht=600, ft=700)


# ---------------------------------------------------------------------------
# AshFusionTemperatureInterpreter tests
# ---------------------------------------------------------------------------

class TestInterpreter:
    def setup_method(self):
        self.interpreter = AshFusionTemperatureInterpreter()

    def test_interpret_without_ash_comp(self):
        aft = make_aft()
        result = self.interpreter.interpret(aft)
        assert result.slagging_risk is None
        assert result.fouling_risk is None

    def test_interpret_with_ash_comp(self):
        comp = make_ash_comp()
        aft = make_aft(ash_comp=comp)
        result = self.interpreter.interpret(aft)
        assert result.slagging_risk is not None
        assert result.fouling_risk is not None

    def test_high_fusion_no_slagging_warning(self):
        aft = make_aft(dt=1300, ht=1400, ft=1480)
        result = self.interpreter.interpret(aft)
        assert result.is_high_fusion is True

    def test_low_ft_recommendation_present(self):
        aft = make_aft(dt=900, ht=1100, ft=1200)
        result = self.interpreter.interpret(aft)
        assert any("Low FT" in r for r in result.furnace_recommendations)

    def test_slagging_classification_low(self):
        # Rs = B/A × S; low B/A → low Rs
        comp = make_ash_comp(fe2o3=3, cao=2, mgo=1, k2o=0.5, na2o=0.3, sio2=55, al2o3=30, tio2=1, sulfur=0.3)
        aft = make_aft(ash_comp=comp)
        result = self.interpreter.interpret(aft)
        assert result.slagging_risk == SlaggingRisk.LOW

    def test_batch_interpret(self):
        afts = [make_aft(f"S{i}", dt=1100, ht=1280, ft=1350+i*10) for i in range(3)]
        results = self.interpreter.batch_interpret(afts)
        assert len(results) == 3

    def test_batch_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            self.interpreter.batch_interpret([])

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            self.interpreter.interpret({"sample_id": "bad"})
