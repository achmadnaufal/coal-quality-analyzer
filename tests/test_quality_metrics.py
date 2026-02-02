"""Tests for coal quality metrics."""
import pytest
from quality_metrics import CoalQualityAnalyzer, CoalGrade


class TestCoalQualityAnalyzer:
    """Test coal quality analysis."""
    
    def test_initialization_valid(self):
        """Test valid initialization."""
        analyzer = CoalQualityAnalyzer(
            sample_id="COAL-001",
            ash_percent=15.0,
            moisture_percent=8.0,
            sulfur_percent=0.8,
            calorific_value_mj_kg=27.0,
        )
        assert analyzer.sample_id == "COAL-001"
    
    def test_invalid_ash_percent(self):
        """Test invalid ash percent."""
        with pytest.raises(ValueError):
            CoalQualityAnalyzer(
                sample_id="COAL",
                ash_percent=150.0,
                moisture_percent=8.0,
                sulfur_percent=0.8,
                calorific_value_mj_kg=27.0,
            )
    
    def test_net_calorific_value(self):
        """Test net calorific value calculation."""
        analyzer = CoalQualityAnalyzer(
            sample_id="COAL-002",
            ash_percent=20.0,
            moisture_percent=10.0,
            sulfur_percent=0.8,
            calorific_value_mj_kg=27.0,
        )
        net_cv = analyzer.calculate_net_calorific_value()
        # 27 - (10 * 2.5) = 2
        assert net_cv == pytest.approx(2.0, 0.1)
    
    def test_grade_premium(self):
        """Test premium grade coal."""
        analyzer = CoalQualityAnalyzer(
            sample_id="COAL-003",
            ash_percent=10.0,
            moisture_percent=5.0,
            sulfur_percent=0.5,
            calorific_value_mj_kg=28.0,
        )
        grade = analyzer.grade_coal()
        assert grade == CoalGrade.PREMIUM
    
    def test_grade_low(self):
        """Test low grade coal."""
        analyzer = CoalQualityAnalyzer(
            sample_id="COAL-004",
            ash_percent=45.0,
            moisture_percent=25.0,
            sulfur_percent=2.5,
            calorific_value_mj_kg=20.0,
        )
        grade = analyzer.grade_coal()
        assert grade == CoalGrade.LOW
    
    def test_analysis_output(self):
        """Test analysis output structure."""
        analyzer = CoalQualityAnalyzer(
            sample_id="COAL-005",
            ash_percent=18.0,
            moisture_percent=9.0,
            sulfur_percent=0.9,
            calorific_value_mj_kg=26.5,
        )
        result = analyzer.analyze()
        assert "quality_grade" in result
        assert "net_calorific_mj_kg" in result
        assert result["quality_grade"] in ["premium", "high", "medium", "low"]
