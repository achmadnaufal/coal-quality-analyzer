"""Coal blending quality predictor using linear mixing rules and ASTM constraints.

Predicts blended coal quality parameters (CV, ash, moisture, sulfur, VM) from
constituent coal properties using mass-weighted linear mixing, then validates
the blend against ASTM/ISO power station and coking coal specifications.

References:
    ASTM D388 (2019) Standard Classification of Coals by Rank.
    ISO 17246 (2010) Coal — Proximate analysis.
    Elliot (1981) Chemistry of Coal Utilization (Supplementary Vol. 2). Wiley.
    World Bank (2009) Coal Plant Performance — Quality Specifications for Power Generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


class CoalRank(str):
    """ASTM D388 coal rank classification."""
    ANTHRACITE = "anthracite"
    BITUMINOUS_HIGH = "bituminous_high_volatile"
    BITUMINOUS_MED = "bituminous_med_volatile"
    BITUMINOUS_LOW = "bituminous_low_volatile"
    SUBBITUMINOUS = "subbituminous"
    LIGNITE = "lignite"


@dataclass
class CoalComponent:
    """Single coal source component in a blend.

    Args:
        source_id: Unique identifier for this coal source (mine/stockpile).
        proportion_pct: Weight percentage in blend (0–100); proportions must sum to 100.
        cv_gar_mj_kg: Gross calorific value, as-received (MJ/kg).
        ash_pct_ar: Ash content, as-received (%).
        moisture_pct_ar: Total moisture, as-received (%).
        sulfur_pct_ar: Total sulfur, as-received (%).
        volatile_matter_pct_adb: Volatile matter, air-dried basis (%).
        hgi: Hardgrove Grindability Index (20–120).
        sodium_pct_ar: Sodium (as Na2O) in ash, as-received (%). Optional.
        chlorine_ppm: Chlorine content (ppm air-dried). Optional.
        cost_usd_t: Cost per tonne USD (for blend cost optimisation). Optional.
    """
    source_id: str
    proportion_pct: float
    cv_gar_mj_kg: float
    ash_pct_ar: float
    moisture_pct_ar: float
    sulfur_pct_ar: float
    volatile_matter_pct_adb: float
    hgi: float
    sodium_pct_ar: float = 0.0
    chlorine_ppm: float = 0.0
    cost_usd_t: Optional[float] = None

    def __post_init__(self) -> None:
        if not 0 <= self.proportion_pct <= 100:
            raise ValueError(f"proportion_pct must be 0–100, got {self.proportion_pct}")
        if self.cv_gar_mj_kg <= 0:
            raise ValueError("cv_gar_mj_kg must be positive")
        if not 0 <= self.ash_pct_ar <= 100:
            raise ValueError("ash_pct_ar must be 0–100")
        if not 0 <= self.moisture_pct_ar <= 100:
            raise ValueError("moisture_pct_ar must be 0–100")
        if not 0 <= self.sulfur_pct_ar <= 10:
            raise ValueError("sulfur_pct_ar must be 0–10")
        if not 20 <= self.hgi <= 120:
            raise ValueError("hgi must be 20–120 (ASTM D409 range)")


@dataclass
class BlendSpecification:
    """Quality specification constraints for the blended coal product.

    All bounds are inclusive (value must be within [min, max]).
    None means unconstrained.
    """
    name: str = "Power Station Thermal Coal"
    cv_gar_min_mj_kg: Optional[float] = 18.0
    cv_gar_max_mj_kg: Optional[float] = None
    ash_max_pct_ar: Optional[float] = 15.0
    moisture_max_pct_ar: Optional[float] = 35.0
    sulfur_max_pct_ar: Optional[float] = 1.0
    volatile_matter_min_pct: Optional[float] = None
    volatile_matter_max_pct: Optional[float] = None
    hgi_min: Optional[float] = 45.0
    hgi_max: Optional[float] = None
    sodium_max_pct_ar: Optional[float] = 0.5
    chlorine_max_ppm: Optional[float] = 200.0


@dataclass
class BlendResult:
    """Predicted quality of a blended coal and specification compliance."""
    blend_cv_gar_mj_kg: float
    blend_ash_pct_ar: float
    blend_moisture_pct_ar: float
    blend_sulfur_pct_ar: float
    blend_volatile_matter_pct_adb: float
    blend_hgi: float
    blend_sodium_pct_ar: float
    blend_chlorine_ppm: float
    blend_cost_usd_t: Optional[float]
    spec_compliance: Dict[str, bool]
    is_compliant: bool
    violations: List[str]
    cautions: List[str]
    astm_rank: str


class CoalBlendingQualityPredictor:
    """Predict blended coal quality and check specification compliance.

    Uses mass-weighted linear mixing rules (valid for ash, moisture, sulfur,
    calorific value on as-received basis). HGI uses a non-linear empirical
    correction after Sengupta (2002).

    Example::

        predictor = CoalBlendingQualityPredictor()
        components = [
            CoalComponent("Kaltim-Prima", 60, cv_gar_mj_kg=26.5, ash_pct_ar=5.2,
                          moisture_pct_ar=18.0, sulfur_pct_ar=0.45, volatile_matter_pct_adb=39.0, hgi=52),
            CoalComponent("Adaro", 40, cv_gar_mj_kg=19.8, ash_pct_ar=3.8,
                          moisture_pct_ar=28.0, sulfur_pct_ar=0.20, volatile_matter_pct_adb=40.0, hgi=58),
        ]
        spec = BlendSpecification("India PLI Import Spec", cv_gar_min_mj_kg=23.0, ash_max_pct_ar=14.0)
        result = predictor.predict(components, spec)
        print(f"Blend CV: {result.blend_cv_gar_mj_kg:.1f} MJ/kg, Compliant: {result.is_compliant}")
    """

    def _validate_proportions(self, components: List[CoalComponent]) -> None:
        if not components:
            raise ValueError("At least one coal component required")
        total = sum(c.proportion_pct for c in components)
        if abs(total - 100.0) > 0.5:
            raise ValueError(
                f"Component proportions sum to {total:.1f}%, must be 100% (±0.5%)"
            )

    def _weighted_mean(self, components: List[CoalComponent], attr: str) -> float:
        total = sum(c.proportion_pct for c in components)
        return sum(getattr(c, attr) * c.proportion_pct / total for c in components)

    def _blend_hgi(self, components: List[CoalComponent]) -> float:
        """Blend HGI using ASTM empirical formula (Sengupta correction).

        Simple mass-weighted HGI overestimates grindability for high-HGI blends.
        Using sqrt-weighted blend after Sengupta (2002) Fuel 81:979-986.
        """
        total = sum(c.proportion_pct for c in components)
        # Blend as square-root weighted mean, then re-square
        sqrt_weighted = sum(
            (c.hgi ** 0.5) * c.proportion_pct / total for c in components
        )
        return round(sqrt_weighted ** 2, 1)

    def _classify_rank(self, cv_gar: float, volatile_matter: float) -> str:
        """Simple ASTM D388 rank classification from CV and VM."""
        if cv_gar >= 35.0 and volatile_matter < 8:
            return CoalRank.ANTHRACITE
        elif cv_gar >= 28.0 and volatile_matter < 22:
            return CoalRank.BITUMINOUS_LOW
        elif cv_gar >= 26.0 and volatile_matter < 31:
            return CoalRank.BITUMINOUS_MED
        elif cv_gar >= 22.0:
            return CoalRank.BITUMINOUS_HIGH
        elif cv_gar >= 15.0:
            return CoalRank.SUBBITUMINOUS
        else:
            return CoalRank.LIGNITE

    def _check_spec(
        self, result: "BlendResult", spec: BlendSpecification
    ) -> Tuple[Dict[str, bool], bool, List[str], List[str]]:
        compliance = {}
        violations = []
        cautions = []

        checks = [
            ("cv_gar_min", spec.cv_gar_min_mj_kg, result.blend_cv_gar_mj_kg, ">=",
             f"CV {result.blend_cv_gar_mj_kg:.1f} MJ/kg below minimum {spec.cv_gar_min_mj_kg}"),
            ("cv_gar_max", spec.cv_gar_max_mj_kg, result.blend_cv_gar_mj_kg, "<=",
             f"CV {result.blend_cv_gar_mj_kg:.1f} MJ/kg above maximum {spec.cv_gar_max_mj_kg}"),
            ("ash_max", spec.ash_max_pct_ar, result.blend_ash_pct_ar, "<=",
             f"Ash {result.blend_ash_pct_ar:.1f}% exceeds limit {spec.ash_max_pct_ar}%"),
            ("moisture_max", spec.moisture_max_pct_ar, result.blend_moisture_pct_ar, "<=",
             f"Moisture {result.blend_moisture_pct_ar:.1f}% exceeds limit {spec.moisture_max_pct_ar}%"),
            ("sulfur_max", spec.sulfur_max_pct_ar, result.blend_sulfur_pct_ar, "<=",
             f"Sulfur {result.blend_sulfur_pct_ar:.2f}% exceeds limit {spec.sulfur_max_pct_ar}%"),
            ("hgi_min", spec.hgi_min, result.blend_hgi, ">=",
             f"HGI {result.blend_hgi:.0f} below minimum {spec.hgi_min}"),
            ("hgi_max", spec.hgi_max, result.blend_hgi, "<=",
             f"HGI {result.blend_hgi:.0f} above maximum {spec.hgi_max}"),
            ("sodium_max", spec.sodium_max_pct_ar, result.blend_sodium_pct_ar, "<=",
             f"Sodium {result.blend_sodium_pct_ar:.2f}% exceeds limit {spec.sodium_max_pct_ar}% (slagging risk)"),
            ("chlorine_max", spec.chlorine_max_ppm, result.blend_chlorine_ppm, "<=",
             f"Chlorine {result.blend_chlorine_ppm:.0f} ppm exceeds limit {spec.chlorine_max_ppm} ppm (corrosion risk)"),
        ]

        for key, limit, value, op, msg in checks:
            if limit is None:
                compliance[key] = True
                continue
            passed = (value >= limit) if op == ">=" else (value <= limit)
            compliance[key] = passed
            if not passed:
                violations.append(msg)

        # Cautions (not hard limits but worth flagging)
        if result.blend_sodium_pct_ar > 0.3:
            cautions.append(
                f"Sodium {result.blend_sodium_pct_ar:.2f}% is elevated — assess slagging/fouling index"
            )
        if result.blend_chlorine_ppm > 100:
            cautions.append(
                f"Chlorine {result.blend_chlorine_ppm:.0f} ppm — verify superheater tube corrosion tolerance"
            )
        vm_range_warning = (
            spec.volatile_matter_min_pct and result.blend_volatile_matter_pct_adb < spec.volatile_matter_min_pct
        )
        if vm_range_warning:
            violations.append(
                f"VM {result.blend_volatile_matter_pct_adb:.1f}% below minimum {spec.volatile_matter_min_pct}%"
            )
            compliance["vm_min"] = False
        elif spec.volatile_matter_max_pct and result.blend_volatile_matter_pct_adb > spec.volatile_matter_max_pct:
            violations.append(
                f"VM {result.blend_volatile_matter_pct_adb:.1f}% above maximum {spec.volatile_matter_max_pct}%"
            )
            compliance["vm_max"] = False

        return compliance, len(violations) == 0, violations, cautions

    def predict(
        self, components: List[CoalComponent], spec: Optional[BlendSpecification] = None
    ) -> BlendResult:
        """Predict blended coal quality and check specification compliance.

        Args:
            components: List of CoalComponent with proportions summing to 100%.
            spec: Optional specification for compliance checking.

        Returns:
            BlendResult with predicted quality and compliance status.
        """
        self._validate_proportions(components)
        if spec is None:
            spec = BlendSpecification()

        cv = round(self._weighted_mean(components, "cv_gar_mj_kg"), 2)
        ash = round(self._weighted_mean(components, "ash_pct_ar"), 2)
        moisture = round(self._weighted_mean(components, "moisture_pct_ar"), 2)
        sulfur = round(self._weighted_mean(components, "sulfur_pct_ar"), 3)
        vm = round(self._weighted_mean(components, "volatile_matter_pct_adb"), 2)
        sodium = round(self._weighted_mean(components, "sodium_pct_ar"), 3)
        chlorine = round(self._weighted_mean(components, "chlorine_ppm"), 1)
        hgi = self._blend_hgi(components)

        # Blend cost (only if all components have cost)
        costs = [c.cost_usd_t for c in components]
        blend_cost: Optional[float] = None
        if all(c is not None for c in costs):
            total = sum(c.proportion_pct for c in components)
            blend_cost = round(
                sum(c.cost_usd_t * c.proportion_pct / total for c in components), 2  # type: ignore
            )

        rank = self._classify_rank(cv, vm)

        result = BlendResult(
            blend_cv_gar_mj_kg=cv,
            blend_ash_pct_ar=ash,
            blend_moisture_pct_ar=moisture,
            blend_sulfur_pct_ar=sulfur,
            blend_volatile_matter_pct_adb=vm,
            blend_hgi=hgi,
            blend_sodium_pct_ar=sodium,
            blend_chlorine_ppm=chlorine,
            blend_cost_usd_t=blend_cost,
            spec_compliance={},
            is_compliant=False,
            violations=[],
            cautions=[],
            astm_rank=rank,
        )

        compliance, is_ok, violations, cautions = self._check_spec(result, spec)
        result.spec_compliance = compliance
        result.is_compliant = is_ok
        result.violations = violations
        result.cautions = cautions
        return result

    def optimise_proportions(
        self,
        components: List[CoalComponent],
        target_cv_gar: float,
        tolerance_mj_kg: float = 0.5,
        steps: int = 5,
    ) -> List[Tuple[float, float, BlendResult]]:
        """Grid search over two-component proportions to find blends hitting target CV.

        Only works for exactly two components. Returns list of (prop_A, prop_B, result)
        tuples sorted by |blend_CV - target_CV|.

        Args:
            components: Exactly 2 CoalComponent instances (proportions ignored for search).
            target_cv_gar: Desired blend CV (MJ/kg, GAR).
            tolerance_mj_kg: Accept blends within ± tolerance of target.
            steps: Number of proportion steps from 0–100% for component A.

        Returns:
            Filtered list of (prop_A, prop_B, BlendResult) within tolerance, sorted by closeness.
        """
        if len(components) != 2:
            raise ValueError("optimise_proportions requires exactly 2 components")

        results = []
        step_size = 100.0 / steps
        for i in range(steps + 1):
            pct_a = round(i * step_size, 1)
            pct_b = round(100.0 - pct_a, 1)
            if pct_a <= 0 or pct_b <= 0:
                continue
            trial = [
                CoalComponent(
                    source_id=components[0].source_id,
                    proportion_pct=pct_a,
                    cv_gar_mj_kg=components[0].cv_gar_mj_kg,
                    ash_pct_ar=components[0].ash_pct_ar,
                    moisture_pct_ar=components[0].moisture_pct_ar,
                    sulfur_pct_ar=components[0].sulfur_pct_ar,
                    volatile_matter_pct_adb=components[0].volatile_matter_pct_adb,
                    hgi=components[0].hgi,
                    cost_usd_t=components[0].cost_usd_t,
                ),
                CoalComponent(
                    source_id=components[1].source_id,
                    proportion_pct=pct_b,
                    cv_gar_mj_kg=components[1].cv_gar_mj_kg,
                    ash_pct_ar=components[1].ash_pct_ar,
                    moisture_pct_ar=components[1].moisture_pct_ar,
                    sulfur_pct_ar=components[1].sulfur_pct_ar,
                    volatile_matter_pct_adb=components[1].volatile_matter_pct_adb,
                    hgi=components[1].hgi,
                    cost_usd_t=components[1].cost_usd_t,
                ),
            ]
            res = self.predict(trial)
            if abs(res.blend_cv_gar_mj_kg - target_cv_gar) <= tolerance_mj_kg:
                results.append((pct_a, pct_b, res))

        results.sort(key=lambda x: abs(x[2].blend_cv_gar_mj_kg - target_cv_gar))
        return results
