"""
spontaneous_combustion_risk.py — Spontaneous combustion risk assessment for coal stockpile management.

Spontaneous combustion (sponcom) is a major safety and quality hazard in coal operations.
Low-rank coals with high moisture, high volatile matter, and reactive macerals are most susceptible.
This module implements the CROSSING POINT TEMPERATURE (CPT) method and the Composite Risk Index
used by Indonesian coal operators, aligned with ADB Coal Safety Guidelines and SNI 13-6499.

Risk factors assessed:
  1. Coal rank and moisture (primary indicators)
  2. Reactive maceral content (inertinite vs vitrinite proportion)
  3. Oxidation susceptibility index (O/C ratio proxy)
  4. Stockpile geometry and ventilation factor
  5. Ambient temperature and rainfall context

References:
    - ADB (2012) Indonesian Coal Sector Guidelines: Spontaneous Combustion Management
    - Ejlali et al. (2009) Prediction of spontaneous combustion index. Int J Mining Sci Technol
    - Srirama et al. (2017) CPT method for sponcom susceptibility of Indian coals
    - SNI 13-6499-2000 Indonesian standard for coal storage and handling
    - Cliff et al. (1998) Testing for self-heating susceptibility. CSIRO Coal reports
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Risk classification thresholds (Composite Risk Index 0–100)
RISK_THRESHOLD_CRITICAL = 75
RISK_THRESHOLD_HIGH = 55
RISK_THRESHOLD_MODERATE = 35

# Crossing point temperature thresholds (°C) — higher = more susceptible
CPT_THRESHOLD_HIGH = 155.0   # Above this: high spontaneous combustion susceptibility
CPT_THRESHOLD_MODERATE = 175.0  # Above this: moderate (lower CPT = more reactive)
# Note: CPT is INVERSELY related to susceptibility — lower CPT = higher risk

# Volatile matter thresholds (%, daf)
VM_HIGH_RISK = 40.0  # VM% daf > 40% → elevated risk
VM_MODERATE_RISK = 30.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CoalSample:
    """Coal quality data for spontaneous combustion risk assessment.

    Attributes:
        sample_id: Unique sample identifier.
        mine_id: Mine or stockpile identifier.
        moisture_ad_pct: Air-dried moisture content (%).
        ash_ad_pct: Air-dried ash content (%).
        volatile_matter_daf_pct: Volatile matter on dry-ash-free basis (%).
        fixed_carbon_daf_pct: Fixed carbon on daf basis (%). Auto-computed if 0.
        sulfur_pct: Total sulfur content (%).
        gcv_gar_kcal_kg: Gross calorific value as-received (kcal/kg).
        oxygen_pct: Oxygen content (%, daf basis, optional — estimated if None).
        inertinite_pct: Inertinite maceral content (% volume, optional).
        stockpile_height_m: Stockpile height in metres (for geometry factor).
        ambient_temp_c: Ambient temperature at stockpile location (°C).
        days_in_stockpile: Number of days coal has been in the stockpile.

    Raises:
        ValueError: If quality parameters are outside plausible range.

    Example:
        >>> sample = CoalSample(
        ...     sample_id="KAL-01",
        ...     mine_id="MINE_A",
        ...     moisture_ad_pct=28.5,
        ...     ash_ad_pct=6.2,
        ...     volatile_matter_daf_pct=48.3,
        ...     fixed_carbon_daf_pct=51.7,
        ...     sulfur_pct=0.35,
        ...     gcv_gar_kcal_kg=4200,
        ... )
    """

    sample_id: str
    mine_id: str
    moisture_ad_pct: float
    ash_ad_pct: float
    volatile_matter_daf_pct: float
    fixed_carbon_daf_pct: float = 0.0
    sulfur_pct: float = 0.5
    gcv_gar_kcal_kg: float = 4500.0
    oxygen_pct: Optional[float] = None
    inertinite_pct: Optional[float] = None
    stockpile_height_m: float = 5.0
    ambient_temp_c: float = 32.0
    days_in_stockpile: int = 0

    def __post_init__(self) -> None:
        if not self.sample_id.strip():
            raise ValueError("sample_id must not be empty.")
        if not self.mine_id.strip():
            raise ValueError("mine_id must not be empty.")
        if not (0.0 <= self.moisture_ad_pct <= 70.0):
            raise ValueError(f"moisture_ad_pct {self.moisture_ad_pct} out of range [0, 70]%.")
        if not (0.0 <= self.ash_ad_pct <= 60.0):
            raise ValueError(f"ash_ad_pct {self.ash_ad_pct} out of range [0, 60]%.")
        if not (0.0 <= self.volatile_matter_daf_pct <= 100.0):
            raise ValueError("volatile_matter_daf_pct must be in [0, 100]%.")
        if not (0.0 <= self.sulfur_pct <= 10.0):
            raise ValueError("sulfur_pct must be in [0, 10]%.")
        if self.gcv_gar_kcal_kg < 0:
            raise ValueError("gcv_gar_kcal_kg must be non-negative.")
        if self.oxygen_pct is not None and not (0.0 <= self.oxygen_pct <= 50.0):
            raise ValueError("oxygen_pct must be in [0, 50]%.")
        if self.inertinite_pct is not None and not (0.0 <= self.inertinite_pct <= 100.0):
            raise ValueError("inertinite_pct must be in [0, 100]%.")
        if self.stockpile_height_m <= 0:
            raise ValueError("stockpile_height_m must be positive.")
        if not (0.0 <= self.ambient_temp_c <= 50.0):
            raise ValueError("ambient_temp_c must be in [0, 50]°C.")
        if self.days_in_stockpile < 0:
            raise ValueError("days_in_stockpile must be non-negative.")

        # Auto-compute FC daf if not provided
        if self.fixed_carbon_daf_pct == 0.0:
            self.fixed_carbon_daf_pct = max(0.0, 100.0 - self.volatile_matter_daf_pct)

    @property
    def estimated_oxygen_pct(self) -> float:
        """Estimate oxygen content (% daf) from coal rank proxy using GCV."""
        if self.oxygen_pct is not None:
            return self.oxygen_pct
        # Empirical approximation: lower rank (lower GCV) → higher oxygen
        # Fitted from Parr (1928) and proximate-ultimate correlations for SE Asian coals
        if self.gcv_gar_kcal_kg >= 6000:
            return 8.0   # bituminous
        elif self.gcv_gar_kcal_kg >= 5000:
            return 14.0  # sub-bituminous A
        elif self.gcv_gar_kcal_kg >= 4200:
            return 22.0  # sub-bituminous B
        elif self.gcv_gar_kcal_kg >= 3500:
            return 28.0  # sub-bituminous C
        else:
            return 38.0  # lignite


@dataclass
class SponcomRiskResult:
    """Spontaneous combustion risk assessment result.

    Attributes:
        sample_id: Sample identifier.
        mine_id: Mine identifier.
        crossing_point_temp_c: Estimated crossing point temperature (°C).
            Lower CPT = higher reactivity and risk.
        composite_risk_index: Overall risk score (0–100).
        risk_class: 'critical', 'high', 'moderate', or 'low'.
        susceptibility_class: CPT-based class: 'very_high', 'high', 'moderate', 'low'.
        risk_drivers: Dict of individual factor scores contributing to composite risk.
        mitigation_actions: List of recommended mitigation measures.
        stockpile_life_days: Estimated safe storage duration at current conditions.
    """

    sample_id: str
    mine_id: str
    crossing_point_temp_c: float
    composite_risk_index: float
    risk_class: str
    susceptibility_class: str
    risk_drivers: Dict[str, float]
    mitigation_actions: List[str]
    stockpile_life_days: int


# ---------------------------------------------------------------------------
# Core risk assessor
# ---------------------------------------------------------------------------


class SpontaneousCombustionRiskAssessor:
    """Assess spontaneous combustion susceptibility for coal stockpiles.

    Uses a composite risk scoring approach combining:
    - Coal rank proxy (moisture, VM, GCV)
    - Oxidation susceptibility (oxygen content, sulfur)
    - Stockpile geometry and ventilation
    - Time-in-stockpile accumulation factor
    - Ambient temperature enhancement

    Args:
        temperature_monitoring_frequency_hours: How often temperature is monitored
            in the stockpile (hours). Lower = better management = lower effective risk.
            Default 24 hours.

    Example:
        >>> assessor = SpontaneousCombustionRiskAssessor()
        >>> result = assessor.assess(sample)
        >>> result.risk_class
        'high'
    """

    def __init__(self, temperature_monitoring_frequency_hours: float = 24.0) -> None:
        if temperature_monitoring_frequency_hours <= 0:
            raise ValueError("temperature_monitoring_frequency_hours must be positive.")
        self._monitoring_freq = temperature_monitoring_frequency_hours

    def estimate_cpt(self, sample: CoalSample) -> float:
        """Estimate Crossing Point Temperature (CPT) in °C.

        CPT is empirically correlated to volatile matter content, moisture, and
        oxygen content. Lower CPT = higher reactivity = higher sponcom risk.

        The baseline formula is calibrated against CSIRO CPT test data for
        Indonesian sub-bituminous and lignite coals.

        Args:
            sample: CoalSample with proximate analysis data.

        Returns:
            Estimated CPT in °C (range approximately 120–220°C).
        """
        # Base CPT from VM: higher VM → lower CPT (more reactive)
        vm = sample.volatile_matter_daf_pct
        cpt_base = 220.0 - (vm * 1.5)  # 220°C at VM=0, 130°C at VM=60%

        # Oxygen adjustment: higher O2 → lower CPT (more reactive macerals)
        o2 = sample.estimated_oxygen_pct
        cpt_base -= o2 * 0.8

        # Moisture: high moisture slightly increases CPT (evaporative cooling)
        cpt_base += sample.moisture_ad_pct * 0.3

        # Sulfur: pyrite oxidation accelerates heating
        cpt_base -= sample.sulfur_pct * 2.0

        # Inertinite: higher inertinite = less reactive (increases CPT)
        if sample.inertinite_pct is not None:
            cpt_base += sample.inertinite_pct * 0.4

        return round(max(100.0, min(250.0, cpt_base)), 1)

    def _cpt_susceptibility_class(self, cpt: float) -> str:
        """Classify CPT-based susceptibility."""
        if cpt < 140:
            return "very_high"
        elif cpt < CPT_THRESHOLD_HIGH:  # 155
            return "high"
        elif cpt < CPT_THRESHOLD_MODERATE:  # 175
            return "moderate"
        else:
            return "low"

    def _compute_risk_drivers(self, sample: CoalSample, cpt: float) -> Dict[str, float]:
        """Compute individual risk driver scores (0–100 each)."""
        drivers: Dict[str, float] = {}

        # 1. Rank/reactivity score (from CPT) — lower CPT = higher score
        cpt_norm = max(0.0, (220.0 - cpt) / 120.0) * 100.0  # CPT range 100–220°C
        drivers["rank_reactivity"] = round(min(100.0, cpt_norm), 2)

        # 2. Volatile matter score
        vm_score = min(100.0, (sample.volatile_matter_daf_pct / VM_HIGH_RISK) * 100.0)
        drivers["volatile_matter"] = round(vm_score, 2)

        # 3. Oxygen content score
        o2 = sample.estimated_oxygen_pct
        o2_score = min(100.0, (o2 / 40.0) * 100.0)
        drivers["oxygen_content"] = round(o2_score, 2)

        # 4. Stockpile geometry score — taller piles = more heat accumulation
        height_score = min(100.0, (sample.stockpile_height_m / 15.0) * 100.0)
        drivers["stockpile_geometry"] = round(height_score, 2)

        # 5. Ambient temperature score — tropical = elevated baseline
        temp_score = min(100.0, ((sample.ambient_temp_c - 20.0) / 30.0) * 100.0)
        drivers["ambient_temperature"] = round(max(0.0, temp_score), 2)

        # 6. Age in stockpile — oxidation accumulates over time
        age_score = min(100.0, (sample.days_in_stockpile / 90.0) * 100.0)
        drivers["age_in_stockpile"] = round(age_score, 2)

        # 7. Monitoring frequency — more frequent monitoring reduces effective risk
        monitoring_reduction = min(0.5, (self._monitoring_freq - 4.0) / 44.0 * 0.5)
        drivers["monitoring_gap"] = round(monitoring_reduction * 100.0, 2)

        return drivers

    def _composite_risk_index(self, drivers: Dict[str, float]) -> float:
        """Compute weighted composite risk index (0–100)."""
        weights = {
            "rank_reactivity": 0.30,
            "volatile_matter": 0.20,
            "oxygen_content": 0.15,
            "stockpile_geometry": 0.10,
            "ambient_temperature": 0.10,
            "age_in_stockpile": 0.10,
            "monitoring_gap": 0.05,
        }
        total = sum(drivers.get(k, 0.0) * w for k, w in weights.items())
        return round(max(0.0, min(100.0, total)), 2)

    def _risk_class(self, index: float) -> str:
        """Classify composite risk index."""
        if index >= RISK_THRESHOLD_CRITICAL:
            return "critical"
        elif index >= RISK_THRESHOLD_HIGH:
            return "high"
        elif index >= RISK_THRESHOLD_MODERATE:
            return "moderate"
        return "low"

    def _safe_stockpile_life(self, sample: CoalSample, risk_index: float) -> int:
        """Estimate safe storage duration (days) before active intervention needed.

        Lower-rank, high-risk coals need to be processed or moved faster.
        """
        if risk_index >= RISK_THRESHOLD_CRITICAL:
            base_days = 14
        elif risk_index >= RISK_THRESHOLD_HIGH:
            base_days = 30
        elif risk_index >= RISK_THRESHOLD_MODERATE:
            base_days = 60
        else:
            base_days = 90

        # Ambient temperature modifier
        temp_factor = max(0.5, 1.0 - (sample.ambient_temp_c - 30.0) * 0.02)
        return max(7, int(base_days * temp_factor))

    def _generate_mitigations(
        self, sample: CoalSample, risk_class: str, cpt: float
    ) -> List[str]:
        """Generate mitigation recommendations based on risk profile."""
        actions = []

        if risk_class == "critical":
            actions.append(
                "IMMEDIATE ACTION: Deploy infrared/thermocouple temperature monitoring "
                "every 4 hours across the full stockpile footprint."
            )
            actions.append(
                "Segregate this coal to a ventilated pad; do not blend with oxidised material."
            )
            actions.append(
                "Activate Emergency Response Plan; notify Mine Safety Officer."
            )

        if risk_class in ("critical", "high"):
            actions.append(
                "Compact stockpile surface to reduce air infiltration (target density ≥ 1.2 t/m³)."
            )
            actions.append(
                "Schedule coal reclaim within 30 days; prioritise FIFO dispatch of oldest coal."
            )
            actions.append(
                "Install subsurface CO monitoring (early heating indicator before visible smoke)."
            )

        if sample.volatile_matter_daf_pct > VM_HIGH_RISK:
            actions.append(
                f"High VM ({sample.volatile_matter_daf_pct:.1f}% daf): limit stockpile height "
                f"to ≤ 6 m; consider covered storage or water misting to limit surface oxidation."
            )

        if sample.moisture_ad_pct < 10.0:
            actions.append(
                "Low moisture coal is prone to rapid oxidation — apply antioxidant coating "
                "(e.g., lime or proprietary oxidation inhibitor) to cut faces."
            )

        if sample.days_in_stockpile > 30:
            actions.append(
                f"Coal has been stockpiled for {sample.days_in_stockpile} days. "
                "Conduct full hot-spot survey with temperature probes before blending."
            )

        if cpt < 145.0:
            actions.append(
                f"Very low CPT ({cpt:.0f}°C): this coal is highly reactive — "
                "prioritise direct ship or blending with lower-VM coal to dilute reactivity."
            )

        if not actions:
            actions.append(
                "Maintain routine monitoring (daily surface temp survey). "
                "Ensure FIFO stockpile management and compact surface regularly."
            )

        return actions

    def assess(self, sample: CoalSample) -> SponcomRiskResult:
        """Run full spontaneous combustion risk assessment for a coal sample.

        Args:
            sample: CoalSample with proximate analysis and stockpile context.

        Returns:
            SponcomRiskResult with CPT, composite risk index, class, drivers,
            mitigations, and safe storage life estimate.

        Example:
            >>> result = assessor.assess(sample)
            >>> result.risk_class
            'high'
            >>> result.stockpile_life_days
            30
        """
        cpt = self.estimate_cpt(sample)
        susceptibility = self._cpt_susceptibility_class(cpt)
        drivers = self._compute_risk_drivers(sample, cpt)
        risk_index = self._composite_risk_index(drivers)
        risk_class = self._risk_class(risk_index)
        stockpile_life = self._safe_stockpile_life(sample, risk_index)
        mitigations = self._generate_mitigations(sample, risk_class, cpt)

        return SponcomRiskResult(
            sample_id=sample.sample_id,
            mine_id=sample.mine_id,
            crossing_point_temp_c=cpt,
            composite_risk_index=risk_index,
            risk_class=risk_class,
            susceptibility_class=susceptibility,
            risk_drivers=drivers,
            mitigation_actions=mitigations,
            stockpile_life_days=stockpile_life,
        )

    def batch_assess(self, samples: List[CoalSample]) -> List[SponcomRiskResult]:
        """Batch-assess multiple coal samples.

        Args:
            samples: List of CoalSample instances.

        Returns:
            List of SponcomRiskResult sorted by composite_risk_index descending.

        Raises:
            ValueError: If samples list is empty.
        """
        if not samples:
            raise ValueError("samples list must not be empty.")
        results = [self.assess(s) for s in samples]
        return sorted(results, key=lambda r: -r.composite_risk_index)

    def high_risk_stockpiles(
        self, results: List[SponcomRiskResult]
    ) -> List[SponcomRiskResult]:
        """Filter results to critical and high risk stockpiles only."""
        return [r for r in results if r.risk_class in ("critical", "high")]

    def mine_risk_summary(
        self, results: List[SponcomRiskResult]
    ) -> Dict[str, Dict]:
        """Aggregate risk summary per mine.

        Returns:
            Dict: {mine_id: {n_samples, risk_distribution, mean_cpt, mean_risk_index}}.
        """
        by_mine: Dict[str, List[SponcomRiskResult]] = {}
        for r in results:
            by_mine.setdefault(r.mine_id, []).append(r)

        summary = {}
        for mine_id, mine_results in by_mine.items():
            n = len(mine_results)
            risk_dist: Dict[str, int] = {}
            for r in mine_results:
                risk_dist[r.risk_class] = risk_dist.get(r.risk_class, 0) + 1
            mean_cpt = sum(r.crossing_point_temp_c for r in mine_results) / n
            mean_idx = sum(r.composite_risk_index for r in mine_results) / n
            summary[mine_id] = {
                "n_samples": n,
                "risk_distribution": risk_dist,
                "mean_cpt_c": round(mean_cpt, 1),
                "mean_composite_risk_index": round(mean_idx, 2),
                "has_critical_sample": any(r.risk_class == "critical" for r in mine_results),
            }
        return summary
