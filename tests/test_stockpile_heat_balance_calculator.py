"""
Unit tests for StockpileHeatBalanceCalculator.
"""

import pytest
from src.stockpile_heat_balance_calculator import (
    StockpileHeatBalanceCalculator,
    SimulationResult,
    DailyRecord,
    VALID_RANKS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def lignite_hot():
    return StockpileHeatBalanceCalculator(
        coal_rank="lignite",
        stockpile_volume_m3=3000.0,
        stockpile_height_m=6.0,
        initial_temperature_c=28.0,
        ambient_temperature_c=30.0,
        wind_speed_m_s=1.0,
        moisture_content_pct=15.0,
    )


@pytest.fixture
def bituminous_windy():
    return StockpileHeatBalanceCalculator(
        coal_rank="bituminous",
        stockpile_volume_m3=8000.0,
        stockpile_height_m=10.0,
        initial_temperature_c=25.0,
        ambient_temperature_c=22.0,
        wind_speed_m_s=8.0,
        moisture_content_pct=10.0,
    )


@pytest.fixture
def small_subbituminous():
    return StockpileHeatBalanceCalculator(
        coal_rank="subbituminous",
        stockpile_volume_m3=500.0,
        stockpile_height_m=4.0,
        initial_temperature_c=25.0,
        volatile_matter_pct=38.0,
    )


# ---------------------------------------------------------------------------
# Instantiation & validation
# ---------------------------------------------------------------------------

class TestInstantiation:
    def test_valid_creation(self, lignite_hot):
        assert lignite_hot.coal_rank == "lignite"

    def test_all_ranks_valid(self):
        for rank in VALID_RANKS:
            c = StockpileHeatBalanceCalculator(rank, 1000.0, 5.0)
            assert c.coal_rank == rank

    def test_invalid_rank_raises(self):
        with pytest.raises(ValueError, match="coal_rank"):
            StockpileHeatBalanceCalculator("peat", 1000.0, 5.0)

    def test_zero_volume_raises(self):
        with pytest.raises(ValueError, match="stockpile_volume"):
            StockpileHeatBalanceCalculator("bituminous", 0.0, 5.0)

    def test_negative_height_raises(self):
        with pytest.raises(ValueError, match="stockpile_height"):
            StockpileHeatBalanceCalculator("bituminous", 1000.0, -1.0)

    def test_extreme_initial_temp_raises(self):
        with pytest.raises(ValueError, match="initial_temperature"):
            StockpileHeatBalanceCalculator("bituminous", 1000.0, 5.0, initial_temperature_c=80.0)

    def test_extreme_wind_raises(self):
        with pytest.raises(ValueError, match="wind_speed"):
            StockpileHeatBalanceCalculator("bituminous", 1000.0, 5.0, wind_speed_m_s=50.0)

    def test_extreme_moisture_raises(self):
        with pytest.raises(ValueError, match="moisture"):
            StockpileHeatBalanceCalculator("bituminous", 1000.0, 5.0, moisture_content_pct=80.0)

    def test_invalid_vm_raises(self):
        with pytest.raises(ValueError, match="volatile_matter"):
            StockpileHeatBalanceCalculator("bituminous", 1000.0, 5.0, volatile_matter_pct=110.0)


# ---------------------------------------------------------------------------
# Simulation structure
# ---------------------------------------------------------------------------

class TestSimulate:
    def test_returns_simulation_result(self, lignite_hot):
        result = lignite_hot.simulate(days=10)
        assert isinstance(result, SimulationResult)

    def test_daily_records_length(self, lignite_hot):
        result = lignite_hot.simulate(days=15)
        assert len(result.daily_records) == 15

    def test_records_are_daily_record_type(self, lignite_hot):
        result = lignite_hot.simulate(days=5)
        assert all(isinstance(r, DailyRecord) for r in result.daily_records)

    def test_day_sequence(self, lignite_hot):
        result = lignite_hot.simulate(days=7)
        days = [r.day for r in result.daily_records]
        assert days == list(range(1, 8))

    def test_zero_days_raises(self, lignite_hot):
        with pytest.raises(ValueError):
            lignite_hot.simulate(days=0)

    def test_over_365_days_raises(self, lignite_hot):
        with pytest.raises(ValueError):
            lignite_hot.simulate(days=400)

    def test_invalid_time_step_raises(self, lignite_hot):
        with pytest.raises(ValueError):
            lignite_hot.simulate(days=10, time_step_hours=0.0)

    def test_peak_temperature_ge_initial(self, lignite_hot):
        result = lignite_hot.simulate(days=30)
        assert result.peak_temperature_c >= lignite_hot.initial_temperature_c

    def test_summary_keys(self, lignite_hot):
        result = lignite_hot.simulate(days=10)
        s = result.summary()
        for k in ("coal_rank", "peak_temperature_c", "critical_day", "days_simulated"):
            assert k in s

    def test_net_heat_is_gen_minus_loss(self, lignite_hot):
        result = lignite_hot.simulate(days=5)
        for r in result.daily_records:
            expected = r.heat_generation_w - r.heat_loss_w
            assert abs(r.net_heat_w - expected) < 0.1

    def test_cumulative_rise_consistent(self, lignite_hot):
        result = lignite_hot.simulate(days=10)
        for r in result.daily_records:
            expected = r.temperature_c - lignite_hot.initial_temperature_c
            assert abs(r.cumulative_temp_rise_c - expected) < 0.01


# ---------------------------------------------------------------------------
# Risk flags
# ---------------------------------------------------------------------------

class TestRiskFlags:
    def test_initial_ok_flag(self, bituminous_windy):
        result = bituminous_windy.simulate(days=1)
        assert result.daily_records[0].risk_flag == "OK"

    def test_risk_flags_valid_values(self, lignite_hot):
        result = lignite_hot.simulate(days=20)
        valid_flags = {"OK", "WATCH", "WARNING", "CRITICAL"}
        for r in result.daily_records:
            assert r.risk_flag in valid_flags

    def test_flag_matches_temperature(self, lignite_hot):
        result = lignite_hot.simulate(days=60)
        for r in result.daily_records:
            if r.temperature_c >= 150:
                assert r.risk_flag == "CRITICAL"
            elif r.temperature_c >= 100:
                assert r.risk_flag == "WARNING"
            elif r.temperature_c >= 70:
                assert r.risk_flag == "WATCH"
            else:
                assert r.risk_flag == "OK"


# ---------------------------------------------------------------------------
# Coal rank effects
# ---------------------------------------------------------------------------

class TestCoalRankEffects:
    def test_lignite_warms_faster_than_anthracite(self):
        c_lig = StockpileHeatBalanceCalculator("lignite", 3000.0, 6.0, initial_temperature_c=25.0, wind_speed_m_s=0.5, moisture_content_pct=5.0)
        c_ant = StockpileHeatBalanceCalculator("anthracite", 3000.0, 6.0, initial_temperature_c=25.0, wind_speed_m_s=0.5, moisture_content_pct=5.0)
        r_lig = c_lig.simulate(days=30)
        r_ant = c_ant.simulate(days=30)
        assert r_lig.peak_temperature_c > r_ant.peak_temperature_c

    def test_subbituminous_warms_faster_than_bituminous(self):
        kwargs = dict(stockpile_volume_m3=2000.0, stockpile_height_m=5.0, wind_speed_m_s=0.5, moisture_content_pct=5.0)
        c_sub = StockpileHeatBalanceCalculator("subbituminous", **kwargs)
        c_bit = StockpileHeatBalanceCalculator("bituminous", **kwargs)
        r_sub = c_sub.simulate(days=30)
        r_bit = c_bit.simulate(days=30)
        assert r_sub.peak_temperature_c >= r_bit.peak_temperature_c


# ---------------------------------------------------------------------------
# Wind and moisture effects
# ---------------------------------------------------------------------------

class TestEnvironmentalEffects:
    def test_higher_wind_cools_more(self):
        c_low_wind = StockpileHeatBalanceCalculator("lignite", 2000.0, 5.0, wind_speed_m_s=0.5)
        c_high_wind = StockpileHeatBalanceCalculator("lignite", 2000.0, 5.0, wind_speed_m_s=10.0)
        r_low = c_low_wind.simulate(days=30)
        r_high = c_high_wind.simulate(days=30)
        assert r_high.peak_temperature_c < r_low.peak_temperature_c

    def test_higher_moisture_cools_more(self):
        c_dry = StockpileHeatBalanceCalculator("subbituminous", 2000.0, 5.0, moisture_content_pct=2.0)
        c_wet = StockpileHeatBalanceCalculator("subbituminous", 2000.0, 5.0, moisture_content_pct=25.0)
        r_dry = c_dry.simulate(days=30)
        r_wet = c_wet.simulate(days=30)
        assert r_wet.peak_temperature_c < r_dry.peak_temperature_c


# ---------------------------------------------------------------------------
# equilibrium_temperature_c
# ---------------------------------------------------------------------------

class TestEquilibriumTemperature:
    def test_returns_float(self, bituminous_windy):
        eq = bituminous_windy.equilibrium_temperature_c()
        assert isinstance(eq, float)

    def test_equilibrium_above_ambient(self, bituminous_windy):
        eq = bituminous_windy.equilibrium_temperature_c()
        assert eq >= bituminous_windy.ambient_temperature_c

    def test_high_wind_lowers_equilibrium(self):
        """More wind → more convective cooling → lower equilibrium temperature."""
        c_calm = StockpileHeatBalanceCalculator("subbituminous", 2000.0, 5.0, wind_speed_m_s=0.5, moisture_content_pct=2.0)
        c_windy = StockpileHeatBalanceCalculator("subbituminous", 2000.0, 5.0, wind_speed_m_s=15.0, moisture_content_pct=2.0)
        eq_calm = c_calm.equilibrium_temperature_c()
        eq_windy = c_windy.equilibrium_temperature_c()
        assert eq_calm >= eq_windy


# ---------------------------------------------------------------------------
# Volatile matter scaling
# ---------------------------------------------------------------------------

class TestVolatileMatter:
    def test_high_vm_heats_faster(self):
        c_high = StockpileHeatBalanceCalculator("subbituminous", 1000.0, 4.0, volatile_matter_pct=45.0, wind_speed_m_s=0.5)
        c_low = StockpileHeatBalanceCalculator("subbituminous", 1000.0, 4.0, volatile_matter_pct=20.0, wind_speed_m_s=0.5)
        r_high = c_high.simulate(days=20)
        r_low = c_low.simulate(days=20)
        assert r_high.peak_temperature_c >= r_low.peak_temperature_c
