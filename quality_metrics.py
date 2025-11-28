"""Coal quality analysis and metrics."""

from typing import Dict, List
import numpy as np


class CoalQualityAnalyzer:
    """Analyze coal quality parameters."""
    
    # Coal quality standards
    QUALITY_STANDARDS = {
        "ash": {"good": 12, "acceptable": 15, "poor": 20},
        "sulfur": {"good": 0.8, "acceptable": 1.2, "poor": 2.0},
        "moisture": {"good": 10, "acceptable": 15, "poor": 20},
        "carbon": {"good": 75, "acceptable": 70, "poor": 60},
    }
    
    @staticmethod
    def calculate_energy_content(
        carbon_pct: float,
        hydrogen_pct: float,
        oxygen_pct: float,
        nitrogen_pct: float,
        sulfur_pct: float
    ) -> float:
        """
        Calculate energy content (net calorific value) using Dulong formula.
        
        Args:
            carbon_pct: Carbon percentage by weight
            hydrogen_pct: Hydrogen percentage
            oxygen_pct: Oxygen percentage
            nitrogen_pct: Nitrogen percentage
            sulfur_pct: Sulfur percentage
            
        Returns:
            Net calorific value in MJ/kg
        """
        # Dulong formula: NCV = 337.9*C + 1418.9*(H - O/8) + 93.5*S
        # Values in percent, result in kcal/kg, convert to MJ/kg
        ncv_kcal = (337.9 * carbon_pct + 1418.9 * (hydrogen_pct - oxygen_pct/8) + 93.5 * sulfur_pct)
        ncv_mj = ncv_kcal * 0.00419  # Convert kcal/kg to MJ/kg
        
        return round(ncv_mj, 2)
    
    @staticmethod
    def classify_coal_grade(ash_content: float, sulfur_content: float) -> str:
        """
        Classify coal grade based on ash and sulfur content.
        
        Args:
            ash_content: Ash percentage
            sulfur_content: Sulfur percentage
            
        Returns:
            Coal grade classification
        """
        if ash_content <= 12 and sulfur_content <= 0.8:
            return "premium"
        elif ash_content <= 15 and sulfur_content <= 1.2:
            return "high_grade"
        elif ash_content <= 18 and sulfur_content <= 1.5:
            return "standard"
        else:
            return "low_grade"
    
    @staticmethod
    def calculate_quality_index(
        parameters: Dict[str, float]
    ) -> float:
        """
        Calculate overall coal quality index (0-100).
        
        Args:
            parameters: Dict with quality parameters (ash, sulfur, moisture, carbon)
            
        Returns:
            Quality index score
        """
        score = 100.0
        
        # Deduct points for poor parameters
        if parameters.get('ash', 0) > 15:
            score -= min((parameters['ash'] - 15) * 2, 30)
        if parameters.get('sulfur', 0) > 1.2:
            score -= min((parameters['sulfur'] - 1.2) * 10, 25)
        if parameters.get('moisture', 0) > 15:
            score -= min((parameters['moisture'] - 15) * 1.5, 20)
        if parameters.get('carbon', 0) < 70:
            score -= min((70 - parameters['carbon']) * 0.8, 25)
        
        return max(round(score, 1), 0)
    
    @staticmethod
    def blend_coals(
        coal_samples: List[Dict[str, float]],
        weights: List[float]
    ) -> Dict[str, float]:
        """
        Calculate blended coal quality from multiple samples.
        
        Args:
            coal_samples: List of dicts with quality parameters
            weights: Weight proportions for each sample
            
        Returns:
            Dictionary with blended parameters
        """
        if len(coal_samples) != len(weights):
            raise ValueError("Coal samples and weights must have same length")
        
        if abs(sum(weights) - 1.0) > 0.01:
            weights = [w / sum(weights) for w in weights]
        
        blended = {}
        parameters = set()
        
        for sample in coal_samples:
            parameters.update(sample.keys())
        
        for param in parameters:
            weighted_sum = sum(
                sample.get(param, 0) * weight
                for sample, weight in zip(coal_samples, weights)
            )
            blended[param] = round(weighted_sum, 2)
        
        return blended

    def classify_coal_grade(self, quality_params: dict) -> dict:
        """
        Classify coal grade based on quality parameters (GCV, ash, moisture, sulfur).
        
        Uses international coal classification standards (ISO 11760).
        
        Args:
            quality_params: Dict with calorific_value_mj_kg, ash_percent, 
                           moisture_percent, sulfur_percent
                           
        Returns:
            Dict with grade classification and suitability assessment
        """
        gcv = quality_params.get("calorific_value_mj_kg", 0)
        ash = quality_params.get("ash_percent", 0)
        moisture = quality_params.get("moisture_percent", 0)
        sulfur = quality_params.get("sulfur_percent", 0)
        
        # Grade classification based on GCV and ash content
        if gcv >= 26 and ash <= 5:
            grade = "Premium A"
            usage = "Power generation, premium coking"
        elif gcv >= 24 and ash <= 8:
            grade = "Grade A"
            usage = "Power generation, industrial use"
        elif gcv >= 22 and ash <= 12:
            grade = "Grade B"
            usage = "Industrial heating, cement"
        elif gcv >= 20 and ash <= 15:
            grade = "Grade C"
            usage = "Steel mills, basic heating"
        else:
            grade = "Sub-bituminous"
            usage = "Power generation (low efficiency)"
        
        # Quality score (0-100)
        gcv_score = min(100, (gcv / 27) * 100)  # Normalize to 27 MJ/kg max
        ash_score = max(0, 100 - (ash * 5))  # Each 1% ash = -5 points
        moisture_score = max(0, 100 - (moisture * 10))  # Each 1% moisture = -10 points
        sulfur_score = max(0, 100 - (sulfur * 20))  # Each 0.5% sulfur = -10 points
        
        quality_score = (gcv_score * 0.4 + ash_score * 0.3 + 
                        moisture_score * 0.2 + sulfur_score * 0.1)
        
        return {
            "coal_grade": grade,
            "primary_usage": usage,
            "quality_score": round(quality_score, 1),
            "calorific_value": gcv,
            "ash_content": ash,
            "moisture_content": moisture,
            "sulfur_content": sulfur,
            "suitable_for_power_gen": grade in ["Premium A", "Grade A", "Grade B"],
            "suitable_for_coking": grade in ["Premium A", "Grade A"],
        }
