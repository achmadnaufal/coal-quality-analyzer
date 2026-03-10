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
