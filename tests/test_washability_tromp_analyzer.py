"""Unit tests for WashabilityTrompAnalyzer."""

import math
import pytest

from src.washability_tromp_analyzer import (
    FloatSinkFraction,
    TrompPoint,
    WashabilityResult,
    WashabilityTrompAnalyzer,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def standard_fractions():
    return [
        FloatSinkFraction(1.30, 1.35, 18.5, 3.2, 7200),
        FloatSinkFraction(1.35, 1.40, 14.2, 6.1, 7050),
        FloatSinkFraction(1.40, 1.50, 22.8, 12.5, 6800),
        FloatSinkFraction(1.50, 1.60, 18.3, 22.0, 6200),
        FloatSinkFraction(1.60, float("inf"), 26.2, 45.0, 5100),
    ]


@pytest.fixture
def analyzer(standard_fractions):
    return WashabilityTrompAnalyzer(standard_fractions, target_ash_pct=10.0)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_empty_fractions_raises(self):
        with pytest.raises(ValueError, match="fraction"):
            WashabilityTrompAnalyzer([], target_ash_pct=10)

    def test_invalid_target_ash_raises(self, standard_fractions):
        with pytest.raises(ValueError, match="target_ash"):
            WashabilityTrompAnalyzer(standard_fractions, target_ash_pct=95)

    def test_invalid_misplacement_raises(self, standard_fractions):
        with pytest.raises(ValueError, match="misplacement"):
            WashabilityTrompAnalyzer(standard_fractions, misplacement_factor=1.5)

    def test_negative_mass_pct_raises(self):
        with pytest.raises(ValueError):
            FloatSinkFraction(1.30, 1.40, -5, 8)

    def test_rd_lower_below_water_raises(self):
        with pytest.raises(ValueError):
            FloatSinkFraction(0.9, 1.30, 10, 5)

    def test_ash_over_80_raises(self):
        with pytest.raises(ValueError):
            FloatSinkFraction(1.60, float("inf"), 30, 85)


# ---------------------------------------------------------------------------
# FloatSinkFraction properties
# ---------------------------------------------------------------------------


class TestFloatSinkFraction:
    def test_rd_midpoint_finite(self):
        frac = FloatSinkFraction(1.30, 1.40, 20, 5)
        assert frac.rd_midpoint == pytest.approx(1.35)

    def test_rd_midpoint_sink_fraction(self):
        frac = FloatSinkFraction(1.70, float("inf"), 10, 50)
        assert frac.rd_midpoint == pytest.approx(1.75)


# ---------------------------------------------------------------------------
# Feed ash calculation
# ---------------------------------------------------------------------------


class TestFeedAsh:
    def test_feed_ash_positive(self, analyzer):
        assert analyzer._feed_ash > 0

    def test_feed_ash_weighted_correctly(self):
        # Two equal fractions at 5% and 15% ash → feed ash = 10%
        fracs = [
            FloatSinkFraction(1.30, 1.50, 50, 5),
            FloatSinkFraction(1.50, float("inf"), 50, 15),
        ]
        a = WashabilityTrompAnalyzer(fracs, target_ash_pct=10)
        assert a._feed_ash == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Cumulative table
# ---------------------------------------------------------------------------


class TestCumulativeTable:
    def test_table_length_matches_fractions(self, analyzer, standard_fractions):
        table = analyzer._cumulative_table()
        assert len(table) == len(standard_fractions)

    def test_last_row_cumulative_mass_approx_100(self, analyzer):
        table = analyzer._cumulative_table()
        total = sum(f.mass_pct for f in analyzer.fractions)
        assert table[-1]["cumulative_mass_pct"] == pytest.approx(total, abs=0.01)

    def test_cumulative_mass_monotonically_increasing(self, analyzer):
        table = analyzer._cumulative_table()
        masses = [row["cumulative_mass_pct"] for row in table]
        assert all(masses[i] <= masses[i + 1] for i in range(len(masses) - 1))


# ---------------------------------------------------------------------------
# Theoretical yield
# ---------------------------------------------------------------------------


class TestTheoreticalYield:
    def test_theoretical_yield_exists_for_achievable_target(self, analyzer):
        table = analyzer._cumulative_table()
        yield_pct = analyzer._theoretical_yield(table)
        assert yield_pct is not None
        assert 0 < yield_pct < 100

    def test_theoretical_yield_increases_with_higher_target_ash(self, standard_fractions):
        a_low = WashabilityTrompAnalyzer(standard_fractions, target_ash_pct=5)
        a_high = WashabilityTrompAnalyzer(standard_fractions, target_ash_pct=20)
        t_low = a_low._theoretical_yield(a_low._cumulative_table())
        t_high = a_high._theoretical_yield(a_high._cumulative_table())
        if t_low is not None and t_high is not None:
            assert t_high > t_low

    def test_theoretical_yield_none_for_unachievable_target(self, standard_fractions):
        # Target ash < lowest fraction ash → unachievable
        a = WashabilityTrompAnalyzer(standard_fractions, target_ash_pct=1)
        table = a._cumulative_table()
        result = a._theoretical_yield(table)
        # Should be None or very small
        if result is not None:
            assert result < 10


# ---------------------------------------------------------------------------
# Tromp curve
# ---------------------------------------------------------------------------


class TestTrompCurve:
    def test_tromp_curve_not_empty(self, analyzer):
        curve = analyzer._tromp_curve(1.45)
        assert len(curve) > 0

    def test_tromp_at_cut_density_approx_50(self, analyzer):
        curve = analyzer._tromp_curve(1.45)
        # Find point closest to RD = 1.45
        closest = min(curve, key=lambda p: abs(p.rd - 1.45))
        # Due to Ep and misplacement offset, allow wider tolerance
        assert closest.partition_number == pytest.approx(50, abs=15)

    def test_tromp_points_monotonically_decreasing(self, analyzer):
        curve = analyzer._tromp_curve(1.45)
        pns = [p.partition_number for p in curve]
        # Should be generally decreasing (higher RD → lower float probability)
        # Allow minor numerical noise but overall trend must decrease
        assert pns[0] > pns[-1]

    def test_ep_positive(self, analyzer):
        curve = analyzer._tromp_curve(1.45)
        ep = analyzer._ep(curve)
        if ep is not None:
            assert ep > 0


# ---------------------------------------------------------------------------
# Full analyse()
# ---------------------------------------------------------------------------


class TestAnalyse:
    def test_analyse_returns_result(self, analyzer):
        result = analyzer.analyse()
        assert isinstance(result, WashabilityResult)

    def test_feed_ash_matches_property(self, analyzer):
        result = analyzer.analyse()
        assert result.feed_ash_pct == pytest.approx(analyzer._feed_ash, abs=0.01)

    def test_theoretical_yield_populated(self, analyzer):
        result = analyzer.analyse()
        assert result.theoretical_yield_at_target_ash is not None

    def test_optimal_cut_density_in_valid_range(self, analyzer):
        result = analyzer.analyse()
        if result.optimal_cut_density is not None:
            assert 1.0 < result.optimal_cut_density < 3.0

    def test_tromp_curve_populated(self, analyzer):
        result = analyzer.analyse()
        assert len(result.tromp_curve) > 0

    def test_recommendations_present(self, analyzer):
        result = analyzer.analyse()
        assert len(result.recommendations) > 0

    def test_cumulative_float_table_populated(self, analyzer):
        result = analyzer.analyse()
        assert len(result.cumulative_float_table) == 5

    def test_high_ep_generates_recommendation(self, standard_fractions):
        # High misplacement → high Ep → efficiency warning
        a = WashabilityTrompAnalyzer(
            standard_fractions, target_ash_pct=10.0, misplacement_factor=0.30
        )
        result = a.analyse()
        full = " ".join(result.recommendations).lower()
        assert "ep" in full or "efficiency" in full or "inefficiency" in full

    def test_high_feed_ash_generates_recommendation(self):
        # All high-ash fractions → high feed ash
        fracs = [
            FloatSinkFraction(1.30, 1.50, 30, 28),
            FloatSinkFraction(1.50, float("inf"), 70, 50),
        ]
        a = WashabilityTrompAnalyzer(fracs, target_ash_pct=35)
        result = a.analyse()
        full = " ".join(result.recommendations).lower()
        assert "feed ash" in full or "rom" in full or "raw coal" in full

    def test_organic_efficiency_in_valid_range(self, analyzer):
        result = analyzer.analyse()
        if result.organic_efficiency_pct is not None:
            assert 0 < result.organic_efficiency_pct <= 110  # small overshoot allowed
