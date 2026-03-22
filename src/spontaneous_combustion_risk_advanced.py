"""
Spontaneous Combustion Risk Classifier (Advanced)
==================================================
Provides an enhanced spontaneous combustion risk assessment for coal stockpiles,
supplementing the existing `spontaneous_combustion_risk.py` module with:

 - Crossing point temperature (CPT) estimation from proximate analysis
 - R70 index (self-heating rate at 70°C relative to standard coal)
 - Sponcom category (AS 4264.1 / British Coal classification)
 - Oxygen depletion model for enclosed roadway/goaf assessment
 - Incubation period estimate (days to critical heating)

References:
 - Brooks & Glasser (1986) "A simplified model for the self-heating of coal"
 - Cliff et al. (1996) "Spontaneous Combustion in Open-Cut Mines" ACIRL
 - AS 4264.1-2012 Coal and coke — Sampling and testing
 - Mahidin et al. (2022) review of Indonesian coal sponcom indices
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class SponcomCategory(str, Enum):
    """Australian Coal Association classification."""
    CAT_I = "Category I — Low (>70°C CPT)"
    CAT_II = "Category II — Moderate (55–70°C CPT)"
    CAT_III = "Category III — High (40–55°C CPT)"
    CAT_IV = "Category IV — Very High (<40°C CPT)"


@dataclass
class CoalProximateData:
    """
    Proximate analysis and basic physical data for a coal sample.

    Parameters
    ----------
    sample_id : str
    moisture_pct : float  — total moisture (ar basis)
    volatile_matter_pct : float  — volatile matter (daf basis)
    ash_pct : float  — ash content (ar basis)
    fixed_carbon_pct : float  — fixed carbon (ar basis)
    sulfur_pct : float  — total sulfur (ar basis)
    rank : str  — "lignite", "subbituminous", "bituminous", "anthracite"
    ambient_temp_c : float  — site ambient temperature (°C)
    stockpile_height_m : float  — stockpile height (m); affects O₂ diffusion depth
    """
    sample_id: str
    moisture_pct: float
    volatile_matter_pct: float
    ash_pct: float
    fixed_carbon_pct: float
    sulfur_pct: float
    rank: str
    ambient_temp_c: float = 30.0
    stockpile_height_m: float = 8.0

    def __post_init__(self):
        if not 0 <= self.moisture_pct <= 60:
            raise ValueError("moisture_pct must be in [0, 60]")
        if not 0 <= self.volatile_matter_pct <= 80:
            raise ValueError("volatile_matter_pct must be in [0, 80]")
        if not 0 <= self.ash_pct <= 60:
            raise ValueError("ash_pct must be in [0, 60]")
        if not 0 <= self.fixed_carbon_pct <= 95:
            raise ValueError("fixed_carbon_pct must be in [0, 95]")
        if not 0 <= self.sulfur_pct <= 10:
            raise ValueError("sulfur_pct must be in [0, 10]")
        valid_ranks = {"lignite", "subbituminous", "bituminous", "anthracite"}
        if self.rank not in valid_ranks:
            raise ValueError(f"rank must be one of {valid_ranks}")
        if self.ambient_temp_c < -20 or self.ambient_temp_c > 55:
            raise ValueError("ambient_temp_c must be in [-20, 55]°C")
        if self.stockpile_height_m <= 0:
            raise ValueError("stockpile_height_m must be positive")


@dataclass
class SponcomRiskResult:
    """Output of spontaneous combustion risk assessment."""
    sample_id: str
    crossing_point_temp_c: float
    r70_index: float
    sponcom_category: SponcomCategory
    incubation_period_days: float
    o2_depletion_pct_per_day: float
    self_heating_rate_c_per_day: float
    risk_score: float        # composite 0–100
    critical_stockpile_age_days: float
    mitigation_actions: list


# ---------------------------------------------------------------------------
# Rank-based coefficients (from Cliff et al. 1996 and Mahidin et al. 2022)
# ---------------------------------------------------------------------------

_RANK_CPT_BASE: Dict[str, float] = {
    "lignite": 35.0,
    "subbituminous": 45.0,
    "bituminous": 65.0,
    "anthracite": 90.0,
}

# Volatile matter contribution to CPT (°C per % VM above 30%)
_VM_CPT_FACTOR = -0.6   # more VM → lower CPT (higher risk)
# Moisture correction: high moisture initially suppresses oxidation
_MOIST_CPT_FACTOR = 0.3  # °C per % moisture
# Sulfur correction: high sulfur promotes pyrite oxidation
_SULFUR_CPT_FACTOR = -2.5  # °C per % S above 0.5%

# R70 reference for standard bituminous at 50% VM (daf) — normalised to 1.0
_R70_VM_SLOPE = 0.03   # per % VM

# Oxygen depletion rate constants by rank (pct O₂/day)
_O2_DEPLETION_RATE: Dict[str, float] = {
    "lignite": 2.8,
    "subbituminous": 1.6,
    "bituminous": 0.8,
    "anthracite": 0.2,
}


class AdvancedSponcomRiskClassifier:
    """
    Advanced spontaneous combustion risk classifier.

    Examples
    --------
    >>> from coal_quality_analyzer.src.spontaneous_combustion_risk_advanced import (
    ...     AdvancedSponcomRiskClassifier, CoalProximateData
    ... )
    >>> sample = CoalProximateData(
    ...     sample_id="KTM-22A",
    ...     moisture_pct=35.0,
    ...     volatile_matter_pct=42.0,
    ...     ash_pct=8.0,
    ...     fixed_carbon_pct=15.0,
    ...     sulfur_pct=0.8,
    ...     rank="subbituminous",
    ...     ambient_temp_c=32.0,
    ...     stockpile_height_m=10.0,
    ... )
    >>> clf = AdvancedSponcomRiskClassifier()
    >>> result = clf.classify(sample)
    >>> 0 <= result.risk_score <= 100
    True
    """

    def crossing_point_temperature(self, coal: CoalProximateData) -> float:
        """
        Estimate Crossing Point Temperature (CPT) in °C.
        CPT is the temperature at which coal self-heating rate equals the
        heat loss rate. Lower CPT → higher sponcom risk.
        """
        base = _RANK_CPT_BASE[coal.rank]
        vm_correction = _VM_CPT_FACTOR * max(coal.volatile_matter_pct - 30.0, 0.0)
        moist_correction = _MOIST_CPT_FACTOR * coal.moisture_pct
        sulfur_excess = max(coal.sulfur_pct - 0.5, 0.0)
        sulfur_correction = _SULFUR_CPT_FACTOR * sulfur_excess
        cpt = base + vm_correction + moist_correction + sulfur_correction
        # Clamp to physically reasonable range
        return round(max(20.0, min(110.0, cpt)), 1)

    def r70_index(self, coal: CoalProximateData) -> float:
        """
        Compute R70 index — self-heating rate relative to a standard coal at 70°C.
        Higher R70 → greater sponcom tendency.
        Simplified from Brooks & Glasser (1986).
        """
        # Base: scaled by VM and rank factor
        base_r70 = _O2_DEPLETION_RATE[coal.rank] * 1.5
        vm_factor = 1.0 + _R70_VM_SLOPE * max(coal.volatile_matter_pct - 30.0, 0.0)
        moisture_suppression = 1.0 / (1.0 + 0.01 * coal.moisture_pct)
        temp_factor = math.exp(0.02 * (coal.ambient_temp_c - 25.0))
        r70 = base_r70 * vm_factor * moisture_suppression * temp_factor
        return round(max(0.1, r70), 3)

    def sponcom_category(self, cpt: float) -> SponcomCategory:
        """Map CPT to AS 4264.1 sponcom category."""
        if cpt > 70:
            return SponcomCategory.CAT_I
        elif cpt > 55:
            return SponcomCategory.CAT_II
        elif cpt > 40:
            return SponcomCategory.CAT_III
        else:
            return SponcomCategory.CAT_IV

    def incubation_period(self, coal: CoalProximateData, cpt: float) -> float:
        """
        Estimate incubation period (days) — time from stockpile formation to
        reaching critical heating temperature.
        Uses simplified thermal balance: incubation ∝ (CPT - ambient) / heating_rate.
        """
        heating_rate = self.self_heating_rate(coal)
        if heating_rate <= 0:
            return float("inf")
        delta_t = max(cpt - coal.ambient_temp_c, 1.0)
        return round(delta_t / heating_rate, 1)

    def self_heating_rate(self, coal: CoalProximateData) -> float:
        """
        Estimate self-heating rate (°C/day) at ambient temperature.
        Based on rank, VM, and stockpile height (taller → less aeration).
        """
        base = _O2_DEPLETION_RATE[coal.rank]
        vm_factor = 1.0 + 0.02 * max(coal.volatile_matter_pct - 30.0, 0.0)
        height_penalty = math.log1p(coal.stockpile_height_m) / math.log1p(5.0)
        temp_factor = math.exp(0.03 * (coal.ambient_temp_c - 25.0))
        rate = base * vm_factor * height_penalty * temp_factor
        return round(rate, 3)

    def o2_depletion_rate(self, coal: CoalProximateData) -> float:
        """
        O₂ depletion rate (%/day) inside enclosed void/stockpile interior.
        """
        base = _O2_DEPLETION_RATE[coal.rank]
        vm_factor = 1.0 + 0.015 * max(coal.volatile_matter_pct - 30.0, 0.0)
        return round(base * vm_factor, 3)

    def _composite_risk_score(
        self,
        cpt: float,
        r70: float,
        incubation: float,
    ) -> float:
        """
        Composite risk score 0–100.
        Low CPT, high R70, short incubation → high risk.
        """
        # Normalise CPT: lower CPT = higher risk
        cpt_score = max(0.0, 100 - cpt)  # CPT ≈ 40–90 → score 60–10

        # R70 normalised (assume typical range 0.1–10)
        r70_score = min(100.0, r70 * 10)

        # Incubation: shorter = riskier (assume 5–100 days range)
        if math.isinf(incubation):
            incubation_score = 0.0
        else:
            incubation_score = max(0.0, 100 - incubation)

        score = 0.45 * cpt_score + 0.35 * r70_score + 0.20 * incubation_score
        return round(min(100.0, max(0.0, score)), 1)

    def _mitigation_actions(
        self,
        category: SponcomCategory,
        coal: CoalProximateData,
    ) -> list:
        """Return ranked mitigation actions based on risk category."""
        actions = []
        if category in (SponcomCategory.CAT_III, SponcomCategory.CAT_IV):
            actions.append("Implement continuous temperature monitoring (thermocouple grid at 2m depth)")
            actions.append("Limit stockpile age to < 30 days; enforce FIFO rotation")
            actions.append("Apply inert coating (lime or sealing emulsion) to exposed surfaces")
            actions.append("Reduce stockpile height to ≤6 m to improve aeration")
        if category == SponcomCategory.CAT_IV:
            actions.append("CRITICAL: Establish fire watch; prepare water/CO₂ suppression equipment")
            actions.append("Consider immediate re-mining and re-blending to dilute high-risk material")
        if coal.sulfur_pct > 1.0:
            actions.append("High sulfur — monitor for pyrite oxidation; check for acid drainage")
        if coal.moisture_pct < 10:
            actions.append("Low moisture — increase surface wetting frequency (2×/day minimum)")
        if category == SponcomCategory.CAT_I:
            actions.append("Standard monitoring (weekly IR scan); no immediate intervention required")
        return actions

    def classify(self, coal: CoalProximateData) -> SponcomRiskResult:
        """
        Perform full spontaneous combustion risk assessment.

        Returns
        -------
        SponcomRiskResult
        """
        cpt = self.crossing_point_temperature(coal)
        r70 = self.r70_index(coal)
        category = self.sponcom_category(cpt)
        heating_rate = self.self_heating_rate(coal)
        incubation = self.incubation_period(coal, cpt)
        o2_rate = self.o2_depletion_rate(coal)
        risk_score = self._composite_risk_score(cpt, r70, incubation)

        # Critical stockpile age = incubation with 20% safety margin
        critical_age = incubation * 0.80 if not math.isinf(incubation) else 999.0

        mitigation = self._mitigation_actions(category, coal)

        return SponcomRiskResult(
            sample_id=coal.sample_id,
            crossing_point_temp_c=cpt,
            r70_index=r70,
            sponcom_category=category,
            incubation_period_days=incubation,
            o2_depletion_pct_per_day=o2_rate,
            self_heating_rate_c_per_day=heating_rate,
            risk_score=risk_score,
            critical_stockpile_age_days=round(critical_age, 1),
            mitigation_actions=mitigation,
        )
