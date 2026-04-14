"""Coal quality metrics and analysis module.

Provides grade classification, net calorific value estimation, and
comprehensive quality analysis for thermal coal samples. Supports
typical Indonesian and Australian coal quality ranges.

References:
    - ISO 1928:2009 Solid mineral fuels — Determination of gross calorific value
    - ASTM D388 Standard Classification of Coals by Rank
    - Indonesian Ministry of Energy Regulation No. 23/2018 (HBA benchmark)
"""
from typing import Dict
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
