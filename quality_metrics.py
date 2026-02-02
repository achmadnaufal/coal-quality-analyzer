"""Coal quality metrics and analysis module."""
from typing import Dict
from enum import Enum


class CoalGrade(Enum):
    """Coal quality grading."""
    PREMIUM = "premium"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CoalQualityAnalyzer:
    """Analyze coal quality metrics and calorific content."""
    
    def __init__(
        self,
        sample_id: str,
        ash_percent: float,
        moisture_percent: float,
        sulfur_percent: float,
        calorific_value_mj_kg: float,
    ):
        if not (0 <= ash_percent <= 100):
            raise ValueError("Ash % must be 0-100")
        if not (0 <= moisture_percent <= 100):
            raise ValueError("Moisture % must be 0-100")
        if not (0 <= sulfur_percent <= 10):
            raise ValueError("Sulfur % must be valid")
        if calorific_value_mj_kg <= 0:
            raise ValueError("Calorific value must be positive")
        
        self.sample_id = sample_id
        self.ash_percent = ash_percent
        self.moisture_percent = moisture_percent
        self.sulfur_percent = sulfur_percent
        self.calorific_value_mj_kg = calorific_value_mj_kg
    
    def calculate_net_calorific_value(self) -> float:
        """Calculate net calorific value accounting for moisture."""
        # Approximate: loss ~2.5 MJ/kg per 1% moisture
        moisture_loss = self.moisture_percent * 2.5
        return max(0, self.calorific_value_mj_kg - moisture_loss)
    
    def grade_coal(self) -> CoalGrade:
        """Grade coal based on quality metrics."""
        score = 100
        
        # Ash content scoring
        if self.ash_percent > 40:
            score -= 30
        elif self.ash_percent > 30:
            score -= 15
        elif self.ash_percent > 20:
            score -= 5
        
        # Moisture content scoring
        if self.moisture_percent > 20:
            score -= 20
        elif self.moisture_percent > 10:
            score -= 10
        
        # Sulfur content scoring
        if self.sulfur_percent > 2.0:
            score -= 15
        elif self.sulfur_percent > 1.0:
            score -= 5
        
        if score >= 80:
            return CoalGrade.PREMIUM
        elif score >= 60:
            return CoalGrade.HIGH
        elif score >= 40:
            return CoalGrade.MEDIUM
        else:
            return CoalGrade.LOW
    
    def analyze(self) -> Dict:
        """Generate comprehensive quality analysis."""
        return {
            "sample_id": self.sample_id,
            "ash_percent": self.ash_percent,
            "moisture_percent": self.moisture_percent,
            "sulfur_percent": self.sulfur_percent,
            "gross_calorific_mj_kg": round(self.calorific_value_mj_kg, 2),
            "net_calorific_mj_kg": round(self.calculate_net_calorific_value(), 2),
            "quality_grade": self.grade_coal().value,
        }
