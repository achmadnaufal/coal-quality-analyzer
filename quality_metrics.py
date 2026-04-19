"""Coal quality metrics and analysis module.

Provides grade classification, net calorific value estimation, and
comprehensive quality analysis for thermal coal samples. Supports
typical Indonesian and Australian coal quality ranges.

References:
    - ISO 1928:2009 Solid mineral fuels — Determination of gross calorific value
    - ASTM D388 Standard Classification of Coals by Rank
    - Indonesian Ministry of Energy Regulation No. 23/2018 (HBA benchmark)
"""
from typing import Dict, List
from enum import Enum


# Proximate analysis closure tolerance — sum of ash + VM + FC (moisture-free)
# must be within this window of 100 % before an alert is raised.
_PROXIMATE_SUM_TOLERANCE_PCT = 2.0

# Maximum physically plausible sulfur content (%)
_SULFUR_MAX_PCT = 10.0

# Moisture penalty factor used in net calorific value approximation (MJ/kg per % moisture)
_MOISTURE_NCV_PENALTY_MJ = 2.5


class CoalGrade(Enum):
    """Coal quality grading tiers based on composite quality score.

    Scores are computed from ash, moisture, and sulfur content against
    typical export thermal coal benchmarks.

    Values:
        PREMIUM: Quality score >= 80
        HIGH:    Quality score >= 60
        MEDIUM:  Quality score >= 40
        LOW:     Quality score < 40
    """

    PREMIUM = "premium"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CoalQualityAnalyzer:
    """Analyze coal quality metrics and calorific content.

    Validates input parameters at construction time, then exposes methods
    for net calorific value estimation, grade classification, and
    comprehensive quality reporting.

    Args:
        sample_id: Unique identifier for the coal sample (e.g. "KAL-001").
        ash_percent: Ash content on the analysis basis (%). Range [0, 100].
        moisture_percent: Total or inherent moisture content (%). Range [0, 100].
        sulfur_percent: Total sulfur content (%). Range [0, 10].
        calorific_value_mj_kg: Gross calorific value on the analysis basis (MJ/kg).
            Must be positive (> 0).
        volatile_matter_percent: Volatile matter content (%). Optional. Range [0, 100].
        fixed_carbon_percent: Fixed carbon content (%). Optional. Range [0, 100].

    Raises:
        ValueError: If any parameter is outside its valid range or if the
            proximate analysis components do not sum to approximately 100 %.

    Example::

        analyzer = CoalQualityAnalyzer(
            sample_id="KAL-001",
            ash_percent=6.8,
            moisture_percent=12.3,
            sulfur_percent=0.38,
            calorific_value_mj_kg=20.3,
            volatile_matter_percent=40.2,
            fixed_carbon_percent=52.7,
        )
        result = analyzer.analyze()
        print(result["quality_grade"])  # "premium"
    """

    def __init__(
        self,
        sample_id: str,
        ash_percent: float,
        moisture_percent: float,
        sulfur_percent: float,
        calorific_value_mj_kg: float,
        volatile_matter_percent: float = None,
        fixed_carbon_percent: float = None,
    ):
        """Initialise and validate a coal sample for analysis.

        Performs range checks on every supplied parameter and, when both
        volatile_matter_percent and fixed_carbon_percent are provided,
        verifies that their sum with ash_percent is within
        _PROXIMATE_SUM_TOLERANCE_PCT of 100 %.

        Args:
            sample_id: Unique sample label.
            ash_percent: Ash content (%).
            moisture_percent: Moisture content (%).
            sulfur_percent: Total sulfur (%).
            calorific_value_mj_kg: Gross calorific value (MJ/kg).
            volatile_matter_percent: Volatile matter (%). Optional.
            fixed_carbon_percent: Fixed carbon (%). Optional.

        Raises:
            ValueError: On any out-of-range or logically inconsistent value.
        """
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError("sample_id must be a non-empty string.")
        if not (0 <= ash_percent <= 100):
            raise ValueError(f"Ash % must be between 0 and 100, got {ash_percent}.")
        if not (0 <= moisture_percent <= 100):
            raise ValueError(f"Moisture % must be between 0 and 100, got {moisture_percent}.")
        if not (0 <= sulfur_percent <= _SULFUR_MAX_PCT):
            raise ValueError(
                f"Sulfur % must be between 0 and {_SULFUR_MAX_PCT}, got {sulfur_percent}."
            )
        if calorific_value_mj_kg <= 0:
            raise ValueError(
                f"Calorific value must be positive, got {calorific_value_mj_kg}."
            )
        if volatile_matter_percent is not None and not (0 <= volatile_matter_percent <= 100):
            raise ValueError(
                f"Volatile matter % must be between 0 and 100, got {volatile_matter_percent}."
            )
        if fixed_carbon_percent is not None and not (0 <= fixed_carbon_percent <= 100):
            raise ValueError(
                f"Fixed carbon % must be between 0 and 100, got {fixed_carbon_percent}."
            )

        # Validate proximate closure when all three components are available
        if volatile_matter_percent is not None and fixed_carbon_percent is not None:
            proximate_sum = ash_percent + volatile_matter_percent + fixed_carbon_percent
            deviation = abs(proximate_sum - 100.0)
            if deviation > _PROXIMATE_SUM_TOLERANCE_PCT:
                raise ValueError(
                    f"Proximate analysis components (ash + VM + FC) sum to "
                    f"{proximate_sum:.2f} % — deviates from 100 % by "
                    f"{deviation:.2f} %, which exceeds the allowed tolerance of "
                    f"{_PROXIMATE_SUM_TOLERANCE_PCT} %."
                )

        self.sample_id = sample_id
        self.ash_percent = ash_percent
        self.moisture_percent = moisture_percent
        self.sulfur_percent = sulfur_percent
        self.calorific_value_mj_kg = calorific_value_mj_kg
        self.volatile_matter_percent = volatile_matter_percent
        self.fixed_carbon_percent = fixed_carbon_percent

    def calculate_net_calorific_value(self) -> float:
        """Calculate net calorific value (NCV) accounting for moisture content.

        Uses a simplified moisture penalty of
        ``_MOISTURE_NCV_PENALTY_MJ`` MJ/kg per percent moisture. The result
        is clipped to zero so it is never negative.

        Returns:
            Estimated net calorific value (MJ/kg). Always >= 0.

        Example::

            analyzer = CoalQualityAnalyzer("S1", 10.0, 10.0, 0.5, 27.0)
            ncv = analyzer.calculate_net_calorific_value()
            # 27.0 - 10 * 2.5 = 2.0
        """
        moisture_loss = self.moisture_percent * _MOISTURE_NCV_PENALTY_MJ
        return max(0.0, self.calorific_value_mj_kg - moisture_loss)

    def grade_coal(self) -> CoalGrade:
        """Classify the coal sample into a quality grade tier.

        Deducts points from an initial score of 100 based on ash, moisture,
        and sulfur content relative to typical export benchmark thresholds.

        Score bands:
            - >= 80 → PREMIUM
            - >= 60 → HIGH
            - >= 40 → MEDIUM
            - <  40 → LOW

        Returns:
            CoalGrade enum member corresponding to the computed score.

        Example::

            analyzer = CoalQualityAnalyzer("S1", 10.0, 5.0, 0.5, 28.0)
            assert analyzer.grade_coal() == CoalGrade.PREMIUM
        """
        score = 100

        # Ash content deductions
        if self.ash_percent > 40:
            score -= 30
        elif self.ash_percent > 30:
            score -= 15
        elif self.ash_percent > 20:
            score -= 5

        # Moisture content deductions
        if self.moisture_percent > 20:
            score -= 20
        elif self.moisture_percent > 10:
            score -= 10

        # Sulfur content deductions
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
        """Generate a comprehensive quality analysis report.

        Combines all quality parameters, the computed net calorific value,
        and the quality grade into a single immutable result dictionary.
        The original object state is never modified.

        Returns:
            Dict with keys:
                - sample_id (str)
                - ash_percent (float)
                - moisture_percent (float)
                - sulfur_percent (float)
                - volatile_matter_percent (float | None)
                - fixed_carbon_percent (float | None)
                - gross_calorific_mj_kg (float): rounded to 2 dp
                - net_calorific_mj_kg (float): rounded to 2 dp
                - quality_grade (str): one of "premium", "high", "medium", "low"

        Example::

            result = analyzer.analyze()
            print(result["quality_grade"])   # e.g. "premium"
            print(result["net_calorific_mj_kg"])
        """
        return {
            "sample_id": self.sample_id,
            "ash_percent": self.ash_percent,
            "moisture_percent": self.moisture_percent,
            "sulfur_percent": self.sulfur_percent,
            "volatile_matter_percent": self.volatile_matter_percent,
            "fixed_carbon_percent": self.fixed_carbon_percent,
            "gross_calorific_mj_kg": round(self.calorific_value_mj_kg, 2),
            "net_calorific_mj_kg": round(self.calculate_net_calorific_value(), 2),
            "quality_grade": self.grade_coal().value,
        }

    # ------------------------------------------------------------------
    # Static API — stateless utilities for batch / cross-sample work.
    # Mirrors the patterns used in batch CSV pipelines (see demo/run_demo.py).
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_energy_content(
        carbon_pct: float,
        hydrogen_pct: float,
        oxygen_pct: float,
        nitrogen_pct: float,
        sulfur_pct: float,
    ) -> float:
        """Net calorific value via the SI-form Dulong formula (MJ/kg).

        GCV = 0.3383*C + 1.443*(H - O/8) + 0.0942*S, where C/H/O/S are
        mass percent (Speight, Handbook of Coal Analysis).
        """
        ncv_mj = (
            0.3383 * carbon_pct
            + 1.443 * (hydrogen_pct - oxygen_pct / 8)
            + 0.0942 * sulfur_pct
        )
        return round(ncv_mj, 2)

    @staticmethod
    def classify_coal_grade(ash_content: float, sulfur_content: float) -> str:
        """Classify coal grade from ash + sulfur (returns a string label)."""
        if ash_content <= 12 and sulfur_content <= 0.8:
            return "premium"
        if ash_content <= 15 and sulfur_content <= 1.2:
            return "high_grade"
        if ash_content <= 18 and sulfur_content <= 1.5:
            return "standard"
        return "low_grade"

    @staticmethod
    def calculate_quality_index(parameters: Dict[str, float]) -> float:
        """Overall 0-100 quality index from a parameters dict (ash/sulfur/moisture/carbon)."""
        score = 100.0
        if parameters.get("ash", 0) > 15:
            score -= min((parameters["ash"] - 15) * 2, 30)
        if parameters.get("sulfur", 0) > 1.2:
            score -= min((parameters["sulfur"] - 1.2) * 10, 25)
        if parameters.get("moisture", 0) > 15:
            score -= min((parameters["moisture"] - 15) * 1.5, 20)
        if parameters.get("carbon", 0) < 70:
            score -= min((70 - parameters["carbon"]) * 0.8, 25)
        return max(round(score, 1), 0)

    @staticmethod
    def blend_coals(
        coal_samples: List[Dict[str, float]],
        weights: List[float],
    ) -> Dict[str, float]:
        """Weighted-average blend of multiple coal samples (raises if lengths mismatch)."""
        if len(coal_samples) != len(weights):
            raise ValueError("Coal samples and weights must have same length")
        if abs(sum(weights) - 1.0) > 0.01:
            weights = [w / sum(weights) for w in weights]

        params: set = set()
        for sample in coal_samples:
            params.update(sample.keys())

        blended: Dict[str, float] = {}
        for param in params:
            weighted_sum = sum(
                sample.get(param, 0) * weight
                for sample, weight in zip(coal_samples, weights)
            )
            blended[param] = round(weighted_sum, 2)
        return blended

    @staticmethod
    def calculate_export_premium(
        gcv_mj_kg: float,
        ash_pct: float,
        sulfur_pct: float,
        moisture_pct: float,
        benchmark_price_usd: float = 100.0,
        benchmark_gcv: float = 25.0,
    ) -> Dict:
        """Export price premium/discount vs an HBA-style benchmark."""
        if gcv_mj_kg <= 0:
            raise ValueError("gcv_mj_kg must be positive")
        if benchmark_price_usd <= 0:
            raise ValueError("benchmark_price_usd must be positive")
        if not (0 <= ash_pct <= 100):
            raise ValueError("ash_pct must be between 0 and 100")
        if not (0 <= sulfur_pct <= 10):
            raise ValueError("sulfur_pct must be between 0 and 10")

        gcv_ratio = gcv_mj_kg / benchmark_gcv
        gcv_adj = benchmark_price_usd * (gcv_ratio - 1.0)
        ash_penalty = max(0.0, (ash_pct - 10.0) * 0.40)
        sulfur_penalty = max(0.0, (sulfur_pct - 0.8) * 15.0)
        moisture_penalty = max(0.0, (moisture_pct - 12.0) * 0.25)
        total_adj = gcv_adj - ash_penalty - sulfur_penalty - moisture_penalty
        adjusted_price = max(0.0, benchmark_price_usd + total_adj)

        return {
            "adjusted_price_usd_per_tonne": round(adjusted_price, 2),
            "benchmark_price_usd_per_tonne": benchmark_price_usd,
            "total_adjustment_usd": round(total_adj, 2),
            "premium_or_discount": "premium" if total_adj >= 0 else "discount",
            "quality_adjustments": {
                "gcv_adjustment": round(gcv_adj, 2),
                "ash_penalty": round(-ash_penalty, 2),
                "sulfur_penalty": round(-sulfur_penalty, 2),
                "moisture_penalty": round(-moisture_penalty, 2),
            },
            "calorific_ratio": round(gcv_ratio, 3),
        }

    @staticmethod
    def check_specification_compliance(params: Dict, spec: Dict) -> Dict:
        """Per-parameter min/max compliance check for a single coal sample."""
        if not params:
            raise ValueError("params dict cannot be empty")
        if not spec:
            raise ValueError("spec dict cannot be empty")

        results: Dict[str, Dict] = {}
        all_compliant = True
        violations: List[str] = []

        for param, limits in spec.items():
            if param not in params:
                results[param] = {"status": "missing", "value": None, "compliant": False}
                violations.append(f"{param}: missing")
                all_compliant = False
                continue

            value = params[param]
            min_val = limits.get("min")
            max_val = limits.get("max")
            compliant = True
            param_violations: List[str] = []
            if min_val is not None and value < min_val:
                compliant = False
                param_violations.append(f"below min ({min_val})")
            if max_val is not None and value > max_val:
                compliant = False
                param_violations.append(f"above max ({max_val})")
            if not compliant:
                all_compliant = False
                violations.append(f"{param}: {', '.join(param_violations)}")

            results[param] = {
                "value": value,
                "compliant": compliant,
                "violations": param_violations,
                "min_spec": min_val,
                "max_spec": max_val,
            }

        return {
            "compliant": all_compliant,
            "compliance_rate": round(
                sum(1 for r in results.values() if r.get("compliant"))
                / len(results)
                * 100,
                1,
            ),
            "violations": violations,
            "parameters": results,
        }
