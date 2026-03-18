"""
Calorific value prediction and proximate analysis validation for coal.

Implements standard empirical formulae for gross calorific value (GCV) estimation
from proximate analysis (moisture, ash, volatile matter, fixed carbon) and
ultimate analysis (C, H, O, N, S). Used for:
  - Pre-shipment quality prediction when bomb calorimetry is unavailable
  - Cross-checking lab results against model predictions (outlier detection)
  - Coal ranking classification (ASTM D388 / ISO 11760)

References:
    - Dulong formula (1868) — C/H/O/S-based GCV estimation
    - Boie formula (1953) — improved ultimate analysis GCV
    - Majumdar et al. (1998) — proximate analysis regression for Indonesian coals
    - ASTM D388-19 — Standard Classification of Coals by Rank
    - ISO 11760:2018 — Classification of coals
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ASTM D388 coal rank thresholds based on Fixed Carbon (dry, mineral-matter-free)
# and GCV (moist, mineral-matter-free) — approximate boundaries
COAL_RANK_THRESHOLDS = {
    "Meta-anthracite":     {"fc_min": 98.0, "fc_max": 100.0, "gcv_min": 32_600},
    "Anthracite":          {"fc_min": 92.0, "fc_max": 98.0,  "gcv_min": 32_600},
    "Semi-anthracite":     {"fc_min": 86.0, "fc_max": 92.0,  "gcv_min": 32_600},
    "Low-volatile bituminous": {"fc_min": 78.0, "fc_max": 86.0, "gcv_min": 32_600},
    "Medium-volatile bituminous": {"fc_min": 69.0, "fc_max": 78.0, "gcv_min": 30_200},
    "High-volatile A bituminous": {"fc_min": 0.0,  "fc_max": 69.0, "gcv_min": 32_600},
    "High-volatile B bituminous": {"fc_min": 0.0,  "fc_max": 69.0, "gcv_min": 30_200},
    "High-volatile C bituminous": {"fc_min": 0.0,  "fc_max": 69.0, "gcv_min": 26_700},
    "Sub-bituminous A":    {"fc_min": 0.0,  "fc_max": 69.0, "gcv_min": 24_400},
    "Sub-bituminous B":    {"fc_min": 0.0,  "fc_max": 69.0, "gcv_min": 22_100},
    "Sub-bituminous C":    {"fc_min": 0.0,  "fc_max": 69.0, "gcv_min": 19_300},
    "Lignite A":           {"fc_min": 0.0,  "fc_max": 69.0, "gcv_min": 14_700},
    "Lignite B":           {"fc_min": 0.0,  "fc_max": 69.0, "gcv_min": 0},
}


@dataclass
class ProximateAnalysis:
    """
    Coal proximate analysis results (as-received basis unless stated).

    Attributes:
        moisture_pct (float): Total moisture content (%)
        ash_pct (float): Ash content (%)
        volatile_matter_pct (float): Volatile matter content (%)
        fixed_carbon_pct (float): Fixed carbon content (%).
            If 0.0, auto-calculated as 100 - moisture - ash - volatile_matter.
        sample_id (str): Sample identifier

    Note:
        Moisture + Ash + Volatile Matter + Fixed Carbon should sum to ~100%.
        Small deviations (<0.5%) are accepted due to lab rounding.

    Example:
        >>> prox = ProximateAnalysis(
        ...     moisture_pct=12.5, ash_pct=6.2, volatile_matter_pct=38.4,
        ...     fixed_carbon_pct=42.9, sample_id="IUP-2024-001"
        ... )
    """

    moisture_pct: float
    ash_pct: float
    volatile_matter_pct: float
    fixed_carbon_pct: float = 0.0
    sample_id: str = "UNKNOWN"

    def __post_init__(self):
        for attr, val in [
            ("moisture_pct", self.moisture_pct),
            ("ash_pct", self.ash_pct),
            ("volatile_matter_pct", self.volatile_matter_pct),
        ]:
            if not 0.0 <= val <= 100.0:
                raise ValueError(f"{attr} must be between 0 and 100, got {val}")

        if self.fixed_carbon_pct == 0.0:
            self.fixed_carbon_pct = max(
                0.0,
                100.0 - self.moisture_pct - self.ash_pct - self.volatile_matter_pct,
            )
        elif not 0.0 <= self.fixed_carbon_pct <= 100.0:
            raise ValueError(f"fixed_carbon_pct must be between 0 and 100")

        total = self.moisture_pct + self.ash_pct + self.volatile_matter_pct + self.fixed_carbon_pct
        if abs(total - 100.0) > 1.5:
            raise ValueError(
                f"Proximate analysis components sum to {total:.2f}% (expected ~100%). "
                f"Check input values for sample '{self.sample_id}'."
            )

    @property
    def dry_ash_free_volatile_matter(self) -> float:
        """Volatile matter on dry, ash-free (daf) basis."""
        daf_basis = 100.0 - self.moisture_pct - self.ash_pct
        if daf_basis <= 0:
            return 0.0
        return self.volatile_matter_pct / daf_basis * 100.0

    @property
    def dry_mineral_matter_free_fc(self) -> float:
        """
        Fixed carbon on dry, mineral-matter-free (dmmf) basis.

        Uses Parr formula: MM ≈ 1.08 × Ash + 0.55 × S (Sulphur approximated as 1%)
        """
        mineral_matter = 1.08 * self.ash_pct + 0.55 * 1.0  # approx 1% sulphur
        dmmf_basis = 100.0 - self.moisture_pct - mineral_matter
        if dmmf_basis <= 0:
            return 0.0
        fc_dry = self.fixed_carbon_pct / (1 - self.moisture_pct / 100.0)
        return fc_dry / dmmf_basis * (100.0 - mineral_matter)


@dataclass
class UltimateAnalysis:
    """
    Coal ultimate (elemental) analysis results (dry, ash-free basis unless noted).

    Attributes:
        carbon_pct (float): Carbon content (%)
        hydrogen_pct (float): Hydrogen content (%)
        oxygen_pct (float): Oxygen content (%)
        nitrogen_pct (float): Nitrogen content (%)
        sulphur_pct (float): Total sulphur content (%)
        sample_id (str): Sample identifier

    Example:
        >>> ult = UltimateAnalysis(
        ...     carbon_pct=67.2, hydrogen_pct=4.8, oxygen_pct=14.3,
        ...     nitrogen_pct=1.1, sulphur_pct=0.5, sample_id="IUP-2024-001"
        ... )
    """

    carbon_pct: float
    hydrogen_pct: float
    oxygen_pct: float
    nitrogen_pct: float
    sulphur_pct: float
    sample_id: str = "UNKNOWN"

    def __post_init__(self):
        for attr, val in [
            ("carbon_pct", self.carbon_pct),
            ("hydrogen_pct", self.hydrogen_pct),
            ("oxygen_pct", self.oxygen_pct),
            ("nitrogen_pct", self.nitrogen_pct),
            ("sulphur_pct", self.sulphur_pct),
        ]:
            if not 0.0 <= val <= 100.0:
                raise ValueError(f"{attr} must be between 0 and 100, got {val}")

        total = self.carbon_pct + self.hydrogen_pct + self.oxygen_pct + self.nitrogen_pct + self.sulphur_pct
        if total > 105.0:
            raise ValueError(
                f"Ultimate analysis sum {total:.1f}% exceeds 105% — check inputs for '{self.sample_id}'"
            )


class CalorificValuePredictor:
    """
    Predict gross calorific value (GCV) and classify coal rank from proximate
    and/or ultimate analysis data.

    Supports three prediction methods:
      1. Dulong formula — requires ultimate analysis (C, H, O, S)
      2. Boie formula — requires ultimate analysis (C, H, O, N, S)
      3. Majumdar regression — requires proximate analysis (M, A, VM, FC)

    Args:
        prefer_method (str): Default prediction method when multiple analyses
            are available. Options: 'dulong', 'boie', 'majumdar'. Default: 'boie'

    Example:
        >>> predictor = CalorificValuePredictor()
        >>> ult = UltimateAnalysis(67.2, 4.8, 14.3, 1.1, 0.5, "IUP-001")
        >>> gcv = predictor.predict_gcv_from_ultimate(ult)
        >>> print(f"Predicted GCV: {gcv:.0f} kcal/kg")
    """

    VALID_METHODS = {"dulong", "boie", "majumdar"}

    def __init__(self, prefer_method: str = "boie"):
        if prefer_method not in self.VALID_METHODS:
            raise ValueError(f"prefer_method must be one of {self.VALID_METHODS}")
        self.prefer_method = prefer_method

    def predict_gcv_from_ultimate(self, ult: UltimateAnalysis) -> float:
        """
        Predict GCV (kcal/kg) using the preferred ultimate analysis formula.

        Dulong formula:
            GCV = 8084 × C + 34462 × (H - O/8) + 2240 × S  [kcal/kg]

        Boie formula (more accurate):
            GCV = 8177 × C + 34963 × H - 3549 × O + 1504 × N + 10465 × S  [kcal/kg]

        (Proportions expressed as fractions 0.0–1.0 internally)

        Args:
            ult: UltimateAnalysis instance

        Returns:
            Predicted GCV in kcal/kg (as-received)

        Example:
            >>> ult = UltimateAnalysis(67.2, 4.8, 14.3, 1.1, 0.5)
            >>> gcv = predictor.predict_gcv_from_ultimate(ult)
        """
        c = ult.carbon_pct / 100.0
        h = ult.hydrogen_pct / 100.0
        o = ult.oxygen_pct / 100.0
        n = ult.nitrogen_pct / 100.0
        s = ult.sulphur_pct / 100.0

        if self.prefer_method == "dulong":
            return 8084 * c + 34462 * (h - o / 8.0) + 2240 * s

        # Boie (default)
        return 8177 * c + 34963 * h - 3549 * o + 1504 * n + 10465 * s

    def predict_gcv_from_proximate(self, prox: ProximateAnalysis) -> float:
        """
        Predict GCV (kcal/kg) from proximate analysis using Majumdar regression.

        Formula (Majumdar et al. 1998, calibrated for SE Asian coals):
            GCV = -197.26 × M + 52.71 × VM + 183.19 × FC - 74.61 × A + 4500

        Where M, VM, FC, A are percentages (as-received basis).

        Args:
            prox: ProximateAnalysis instance

        Returns:
            Predicted GCV in kcal/kg (as-received basis)

        Raises:
            ValueError: If predicted GCV is negative (invalid proximate composition)
        """
        gcv = (
            -197.26 * prox.moisture_pct
            + 52.71 * prox.volatile_matter_pct
            + 183.19 * prox.fixed_carbon_pct
            - 74.61 * prox.ash_pct
            + 4500
        )
        return max(0.0, gcv)

    def classify_coal_rank_astm(self, gcv_kcal_kg: float, fc_dmmf_pct: float) -> str:
        """
        Classify coal rank per ASTM D388 using GCV and fixed carbon (dmmf basis).

        High-rank coals (anthracite / semi-anthracite) are classified by FC alone.
        Lower-rank coals are classified primarily by GCV.

        Args:
            gcv_kcal_kg: Gross calorific value in kcal/kg (moist, mmf basis)
            fc_dmmf_pct: Fixed carbon on dry, mineral-matter-free basis (%)

        Returns:
            ASTM coal rank classification string

        Example:
            >>> rank = predictor.classify_coal_rank_astm(6200, 52.0)
            >>> print(rank)  # 'High-volatile A bituminous'
        """
        # High-rank classifications by FC
        if fc_dmmf_pct >= 98.0:
            return "Meta-anthracite"
        if fc_dmmf_pct >= 92.0:
            return "Anthracite"
        if fc_dmmf_pct >= 86.0:
            return "Semi-anthracite"
        if fc_dmmf_pct >= 78.0:
            return "Low-volatile bituminous"
        if fc_dmmf_pct >= 69.0:
            return "Medium-volatile bituminous"

        # Low-to-high volatile bituminous by GCV
        gcv_btu = gcv_kcal_kg * 1.8  # approximate conversion kcal/kg → BTU/lb
        if gcv_btu >= 14_000:
            return "High-volatile A bituminous"
        if gcv_btu >= 13_000:
            return "High-volatile B bituminous"
        if gcv_btu >= 11_500:
            return "High-volatile C bituminous"
        if gcv_btu >= 10_500:
            return "Sub-bituminous A"
        if gcv_btu >= 9_500:
            return "Sub-bituminous B"
        if gcv_btu >= 8_300:
            return "Sub-bituminous C"
        if gcv_btu >= 6_300:
            return "Lignite A"
        return "Lignite B"

    def validate_lab_result(
        self, reported_gcv: float, predicted_gcv: float, tolerance_pct: float = 5.0
    ) -> Dict:
        """
        Cross-check a lab-reported GCV against the model prediction.

        Flags potential outliers if the deviation exceeds the tolerance threshold.
        Used for quality control in sample handling and lab reporting.

        Args:
            reported_gcv: Lab-reported GCV in kcal/kg
            predicted_gcv: Model-predicted GCV in kcal/kg
            tolerance_pct: Acceptable deviation percentage (default ±5%)

        Returns:
            Dict with:
                - reported_gcv (float)
                - predicted_gcv (float)
                - deviation_pct (float): % difference from prediction
                - within_tolerance (bool): True if |deviation| <= tolerance_pct
                - flag (str): 'PASS', 'WARNING', or 'FAIL'
                - message (str): Human-readable explanation

        Raises:
            ValueError: If reported_gcv or predicted_gcv is negative

        Example:
            >>> result = predictor.validate_lab_result(6150, 6300, tolerance_pct=5.0)
            >>> print(result['flag'])  # 'PASS'
        """
        if reported_gcv < 0:
            raise ValueError("reported_gcv cannot be negative")
        if predicted_gcv <= 0:
            raise ValueError("predicted_gcv must be positive")

        deviation = (reported_gcv - predicted_gcv) / predicted_gcv * 100.0
        within = abs(deviation) <= tolerance_pct

        if within:
            flag = "PASS"
            message = f"Lab result within ±{tolerance_pct:.1f}% of model prediction"
        elif abs(deviation) <= tolerance_pct * 2:
            flag = "WARNING"
            message = (
                f"Lab result deviates {deviation:+.1f}% from prediction. "
                "Consider re-testing or checking sample preparation."
            )
        else:
            flag = "FAIL"
            message = (
                f"Lab result deviates {deviation:+.1f}% from prediction — "
                "significant outlier. Investigate sample contamination or calculation error."
            )

        return {
            "reported_gcv": reported_gcv,
            "predicted_gcv": round(predicted_gcv, 1),
            "deviation_pct": round(deviation, 2),
            "within_tolerance": within,
            "flag": flag,
            "message": message,
        }

    def batch_predict(
        self,
        samples: List[Tuple[str, Optional[ProximateAnalysis], Optional[UltimateAnalysis]]],
    ) -> List[Dict]:
        """
        Predict GCV and rank for a batch of coal samples.

        For each sample, uses ultimate analysis if available (Boie), otherwise
        falls back to proximate analysis (Majumdar).

        Args:
            samples: List of (sample_id, proximate, ultimate) tuples.
                Either proximate or ultimate may be None, but not both.

        Returns:
            List of dicts per sample:
                - sample_id (str)
                - predicted_gcv_kcal_kg (float)
                - method_used (str): 'boie', 'dulong', or 'majumdar'
                - coal_rank (str): ASTM classification
                - fc_dmmf_pct (float): Fixed carbon dmmf if proximate available

        Raises:
            ValueError: If both proximate and ultimate are None for a sample

        Example:
            >>> results = predictor.batch_predict([("S-001", prox1, None), ("S-002", None, ult2)])
        """
        results = []
        for sample_id, prox, ult in samples:
            if ult is None and prox is None:
                raise ValueError(f"Sample '{sample_id}': at least one analysis must be provided")

            if ult is not None:
                gcv = self.predict_gcv_from_ultimate(ult)
                method = self.prefer_method
                fc_dmmf = prox.dry_mineral_matter_free_fc if prox else 50.0
            else:
                gcv = self.predict_gcv_from_proximate(prox)
                method = "majumdar"
                fc_dmmf = prox.dry_mineral_matter_free_fc

            rank = self.classify_coal_rank_astm(gcv, fc_dmmf)
            results.append(
                {
                    "sample_id": sample_id,
                    "predicted_gcv_kcal_kg": round(gcv, 0),
                    "method_used": method,
                    "coal_rank": rank,
                    "fc_dmmf_pct": round(fc_dmmf, 2),
                }
            )
        return results
