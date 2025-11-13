"""Tests for coal quality analysis."""
import pytest
from quality_metrics import CoalQualityAnalyzer


class TestQualityAnalysis:
    """Test coal quality methods."""
    
    def test_energy_content_calculation(self):
        """Test net calorific value calculation."""
        ncv = CoalQualityAnalyzer.calculate_energy_content(
            carbon_pct=75,
            hydrogen_pct=5,
            oxygen_pct=8,
            nitrogen_pct=1,
            sulfur_pct=0.8
        )
        assert ncv > 0
        assert ncv < 50  # Reasonable range
    
    def test_coal_grade_classification(self):
        """Test coal grade classification."""
        premium = CoalQualityAnalyzer.classify_coal_grade(10, 0.6)
        high = CoalQualityAnalyzer.classify_coal_grade(14, 1.0)
        standard = CoalQualityAnalyzer.classify_coal_grade(16, 1.4)
        low = CoalQualityAnalyzer.classify_coal_grade(22, 2.5)
        
        assert premium == "premium"
        assert high == "high_grade"
        assert standard == "standard"
        assert low == "low_grade"
    
    def test_quality_index(self):
        """Test quality index calculation."""
        index = CoalQualityAnalyzer.calculate_quality_index({
            'ash': 12,
            'sulfur': 0.8,
            'moisture': 10,
            'carbon': 75
        })
        assert 0 <= index <= 100
    
    def test_coal_blending(self):
        """Test coal blending calculation."""
        coal_a = {'ash': 10, 'sulfur': 0.5, 'carbon': 80}
        coal_b = {'ash': 15, 'sulfur': 1.0, 'carbon': 75}
        
        blended = CoalQualityAnalyzer.blend_coals(
            [coal_a, coal_b],
            [0.6, 0.4]
        )
        
        assert blended['ash'] == 12.0
        assert blended['carbon'] == 78.0
