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

    @staticmethod
    def calculate_export_premium(
        gcv_mj_kg: float,
        ash_pct: float,
        sulfur_pct: float,
        moisture_pct: float,
        benchmark_price_usd: float = 100.0,
        benchmark_gcv: float = 25.0,
    ) -> dict:
        """
        Calculate export price premium or discount vs benchmark specification.

        Uses a penalty/bonus system based on deviation from benchmark parameters.
        Commonly used for Indonesian HBA (Harga Batubara Acuan) adjustments.

        Args:
            gcv_mj_kg: Gross calorific value in MJ/kg (AR basis)
            ash_pct: Ash content percentage
            sulfur_pct: Total sulfur percentage
            moisture_pct: Total moisture percentage
            benchmark_price_usd: Reference coal price (USD/tonne), default 100
            benchmark_gcv: Reference GCV spec (MJ/kg), default 25.0 MJ/kg

        Returns:
            Dict with adjusted_price, premium_discount, quality_adjustments breakdown

        Raises:
            ValueError: If gcv_mj_kg <= 0 or benchmark_price_usd <= 0

        Example:
            >>> result = CoalQualityAnalyzer.calculate_export_premium(
            ...     gcv_mj_kg=24.5, ash_pct=9.2, sulfur_pct=0.7,
            ...     moisture_pct=11.5, benchmark_price_usd=90.0
            ... )
            >>> print(f"Adjusted price: ${result['adjusted_price']:.2f}/t")
        """
        if gcv_mj_kg <= 0:
            raise ValueError("gcv_mj_kg must be positive")
        if benchmark_price_usd <= 0:
            raise ValueError("benchmark_price_usd must be positive")
        if not (0 <= ash_pct <= 100):
            raise ValueError("ash_pct must be between 0 and 100")
        if not (0 <= sulfur_pct <= 10):
            raise ValueError("sulfur_pct must be between 0 and 10")

        adjustments = {}

        # GCV adjustment: proportional to calorific value ratio
        gcv_ratio = gcv_mj_kg / benchmark_gcv
        gcv_adj = benchmark_price_usd * (gcv_ratio - 1.0)
        adjustments["gcv_adjustment"] = round(gcv_adj, 2)

        # Ash penalty: -$0.40/tonne per 1% ash above 10%
        ash_penalty = max(0.0, (ash_pct - 10.0) * 0.40)
        adjustments["ash_penalty"] = round(-ash_penalty, 2)

        # Sulfur penalty: -$1.50/tonne per 0.1% sulfur above 0.8%
        sulfur_penalty = max(0.0, (sulfur_pct - 0.8) * 15.0)
        adjustments["sulfur_penalty"] = round(-sulfur_penalty, 2)

        # Moisture penalty: -$0.25/tonne per 1% moisture above 12%
        moisture_penalty = max(0.0, (moisture_pct - 12.0) * 0.25)
        adjustments["moisture_penalty"] = round(-moisture_penalty, 2)

        total_adj = gcv_adj - ash_penalty - sulfur_penalty - moisture_penalty
        adjusted_price = max(0.0, benchmark_price_usd + total_adj)

        return {
            "adjusted_price_usd_per_tonne": round(adjusted_price, 2),
            "benchmark_price_usd_per_tonne": benchmark_price_usd,
            "total_adjustment_usd": round(total_adj, 2),
            "premium_or_discount": "premium" if total_adj >= 0 else "discount",
            "quality_adjustments": adjustments,
            "calorific_ratio": round(gcv_ratio, 3),
        }

    @staticmethod
    def check_specification_compliance(
        params: dict,
        spec: dict,
    ) -> dict:
        """
        Check whether coal quality parameters meet a given specification.

        Args:
            params: Actual coal parameters dict (e.g. {'gcv': 24.0, 'ash': 11.0, ...})
            spec: Specification dict with 'min' and/or 'max' for each parameter

        Returns:
            Dict with overall compliance status and per-parameter results

        Raises:
            ValueError: If params or spec are empty

        Example:
            >>> params = {'gcv': 24.0, 'ash': 11.5, 'sulfur': 0.7, 'moisture': 12.0}
            >>> spec = {'gcv': {'min': 23.0}, 'ash': {'max': 12.0}, 'sulfur': {'max': 1.0}}
            >>> result = CoalQualityAnalyzer.check_specification_compliance(params, spec)
            >>> print(result['compliant'])  # True or False
        """
        if not params:
            raise ValueError("params dict cannot be empty")
        if not spec:
            raise ValueError("spec dict cannot be empty")

        results = {}
        all_compliant = True

        for param, limits in spec.items():
            if param not in params:
                results[param] = {"status": "missing", "value": None, "compliant": False}
                all_compliant = False
                continue

            value = params[param]
            min_val = limits.get("min")
            max_val = limits.get("max")

            compliant = True
            violations = []
            if min_val is not None and value < min_val:
                compliant = False
                violations.append(f"below min ({min_val})")
            if max_val is not None and value > max_val:
                compliant = False
                violations.append(f"above max ({max_val})")

            if not compliant:
                all_compliant = False

            results[param] = {
                "value": value,
                "compliant": compliant,
                "violations": violations,
                "min_spec": min_val,
                "max_spec": max_val,
            }

        return {
            "compliant": all_compliant,
            "compliance_rate": round(
                sum(1 for r in results.values() if r.get("compliant")) / len(results) * 100, 1
            ),
            "parameters": results,
        }
