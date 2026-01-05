"""
Ash Fusion Temperature (AFT) Interpreter for coal quality analysis.

Ash fusion temperatures characterise the behaviour of coal ash when heated
in a reducing or oxidising atmosphere. Critical for:
  - Furnace/boiler design: selecting operating temperature below Fluid Temperature
  - Slagging risk assessment: predicting ash deposits on furnace walls
  - Fouling index: stickiness in convection sections
  - Gasifier temperature targeting: ensuring ash remains fluid for slag tap

AFT measurement standard:
  - ISO 540:2008 — Hard coal and coke: Determination of fusibility of ash
  - ASTM D1857/D1857M — Standard Test Method for Fusibility of Coal and Coke Ash

Four temperature stages (both reducing and oxidising atmosphere):
  1. Deformation Temperature (DT / IDT): First rounding of corners
  2. Sphere Temperature (ST): Ash fused into sphere, H ≈ W
  3. Hemisphere Temperature (HT / HIT): H = W/2, hemisphere shape
  4. Flow Temperature (FT / FLT): Ash spread to height ≤ 1/6 of original

Slagging index calculation:
  - Base/Acid Ratio (B/A): (Fe2O3 + CaO + MgO + K2O + Na2O) / (SiO2 + Al2O3 + TiO2)
  - Silica Ratio (SR): SiO2 / (SiO2 + Fe2O3 + CaO + MgO)
  - Slagging Potential Index (Rs) = B/A × S (sulfur)

Author: github.com/achmadnaufal
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class AtmosphereType(str, Enum):
    """Furnace atmosphere for AFT measurement."""
    REDUCING = "reducing"      # H2 + CO (typical for AFT standard test)
    OXIDISING = "oxidising"    # Air/O2


class SlaggingRisk(str, Enum):
    """Slagging risk classification for boiler furnace design."""
    LOW = "low"           # Rs < 0.6
    MEDIUM = "medium"     # 0.6 ≤ Rs < 2.0
    HIGH = "high"         # 2.0 ≤ Rs < 2.6
    SEVERE = "severe"     # Rs ≥ 2.6


class FoulingRisk(str, Enum):
    """Fouling risk for convection section (superheater/reheater)."""
    LOW = "low"           # Fouling index < 0.2
    MEDIUM = "medium"     # 0.2 ≤ FI < 1.0
    HIGH = "high"         # 1.0 ≤ FI < 40.0
    SEVERE = "severe"     # FI ≥ 40.0


# Slagging risk thresholds (Rs = B/A × S)
SLAGGING_RS_THRESHOLDS: Dict[SlaggingRisk, Tuple[float, float]] = {
    SlaggingRisk.LOW: (0.0, 0.6),
    SlaggingRisk.MEDIUM: (0.6, 2.0),
    SlaggingRisk.HIGH: (2.0, 2.6),
    SlaggingRisk.SEVERE: (2.6, float("inf")),
}

# Fouling index thresholds
FOULING_INDEX_THRESHOLDS: Dict[FoulingRisk, Tuple[float, float]] = {
    FoulingRisk.LOW: (0.0, 0.2),
    FoulingRisk.MEDIUM: (0.2, 1.0),
    FoulingRisk.HIGH: (1.0, 40.0),
    FoulingRisk.SEVERE: (40.0, float("inf")),
}

# Operating margin below Flow Temperature for slag-tab furnace
SLAG_TAP_SAFETY_MARGIN_C: int = 50


@dataclass
class AshComposition:
    """Coal ash major oxide composition (% by mass, sum ≈ 100%).

    All values in weight percent of the total ash.

    Attributes:
        sio2: Silicon dioxide (%).
        al2o3: Aluminium oxide (%).
        fe2o3: Iron oxide (%).
        cao: Calcium oxide (%).
        mgo: Magnesium oxide (%).
        na2o: Sodium oxide (%).
        k2o: Potassium oxide (%).
        tio2: Titanium oxide (%).
        so3: Sulfur trioxide (%).
        p2o5: Phosphorus pentoxide (%).
        total_sulfur_pct: Total sulfur in coal (%, DAF basis) — used for Rs calculation.
    """

    sio2: float
    al2o3: float
    fe2o3: float
    cao: float
    mgo: float
    na2o: float
    k2o: float
    tio2: float = 0.0
    so3: float = 0.0
    p2o5: float = 0.0
    total_sulfur_pct: float = 0.5   # coal total sulfur for slagging index

    def __post_init__(self) -> None:
        for attr in ("sio2", "al2o3", "fe2o3", "cao", "mgo", "na2o", "k2o"):
            val = getattr(self, attr)
            if val < 0:
                raise ValueError(f"{attr} cannot be negative; got {val}")

    @property
    def base_oxides_pct(self) -> float:
        """Sum of basic oxides: Fe2O3 + CaO + MgO + K2O + Na2O."""
        return self.fe2o3 + self.cao + self.mgo + self.k2o + self.na2o

    @property
    def acid_oxides_pct(self) -> float:
        """Sum of acidic oxides: SiO2 + Al2O3 + TiO2."""
        return self.sio2 + self.al2o3 + self.tio2

    @property
    def base_acid_ratio(self) -> float:
        """Base/Acid ratio (B/A). High B/A → more fusible, higher slagging risk."""
        if self.acid_oxides_pct == 0:
            return 0.0
        return self.base_oxides_pct / self.acid_oxides_pct

    @property
    def silica_ratio(self) -> float:
        """Silica Ratio (SR). High SR → lower slagging tendency."""
        denom = self.sio2 + self.fe2o3 + self.cao + self.mgo
        if denom == 0:
            return 0.0
        return (self.sio2 / denom) * 100

    @property
    def slagging_index_rs(self) -> float:
        """Slagging Potential Index (Rs) = B/A × S (total sulfur)."""
        return self.base_acid_ratio * self.total_sulfur_pct

    @property
    def fouling_index(self) -> float:
        """Fouling Index (FI) = B/A × Na2O content."""
        return self.base_acid_ratio * self.na2o


@dataclass
class AshFusionTemperatures:
    """Measured ash fusion temperatures for a coal sample.

    Attributes:
        sample_id: Unique sample identifier.
        coal_name: Coal source/origin name.
        atmosphere: Measurement atmosphere (reducing/oxidising).
        dt_c: Deformation Temperature (°C).
        st_c: Sphere Temperature (°C). Optional.
        ht_c: Hemisphere Temperature (°C).
        ft_c: Flow Temperature (°C).
        ash_composition: Optional major oxide composition for slagging indices.
    """

    sample_id: str
    coal_name: str
    atmosphere: AtmosphereType
    dt_c: float
    ht_c: float
    ft_c: float
    st_c: Optional[float] = None
    ash_composition: Optional[AshComposition] = None

    def __post_init__(self) -> None:
        for label, val in [("DT", self.dt_c), ("HT", self.ht_c), ("FT", self.ft_c)]:
            if val < 700 or val > 1700:
                raise ValueError(f"{label} of {val}°C is outside plausible range 700–1700°C")
        if self.ft_c < self.ht_c:
            raise ValueError(f"FT ({self.ft_c}°C) must be ≥ HT ({self.ht_c}°C)")
        if self.ht_c < self.dt_c:
            raise ValueError(f"HT ({self.ht_c}°C) must be ≥ DT ({self.dt_c}°C)")

    @property
    def fusion_span_c(self) -> float:
        """Temperature span from DT to FT — narrow span = rapid fusion onset."""
        return self.ft_c - self.dt_c

    @property
    def is_high_fusion(self) -> bool:
        """True if FT ≥ 1400°C — low slagging tendency for typical PC boilers."""
        return self.ft_c >= 1400

    @property
    def safe_operating_temp_for_slag_tap_c(self) -> float:
        """Recommended max furnace exit temperature for slag-tap operation (°C)."""
        return self.ft_c + SLAG_TAP_SAFETY_MARGIN_C


@dataclass
class AFTInterpretationResult:
    """Full AFT interpretation and slagging/fouling risk assessment.

    Attributes:
        sample_id: Reference sample.
        coal_name: Coal name.
        atmosphere: AFT atmosphere.
        dt_c: Deformation temperature (°C).
        ht_c: Hemisphere temperature (°C).
        ft_c: Flow temperature (°C).
        fusion_span_c: DT–FT span.
        is_high_fusion: Whether coal qualifies as high fusion.
        slagging_risk: Slagging risk tier (None if no ash composition provided).
        fouling_risk: Fouling risk tier (None if no ash composition provided).
        slagging_index_rs: Rs index (None if no ash composition).
        fouling_index: FI index (None if no ash composition).
        base_acid_ratio: B/A ratio (None if no ash composition).
        furnace_recommendations: List of operational recommendations.
    """

    sample_id: str
    coal_name: str
    atmosphere: AtmosphereType
    dt_c: float
    ht_c: float
    ft_c: float
    fusion_span_c: float
    is_high_fusion: bool
    slagging_risk: Optional[SlaggingRisk]
    fouling_risk: Optional[FoulingRisk]
    slagging_index_rs: Optional[float]
    fouling_index: Optional[float]
    base_acid_ratio: Optional[float]
    furnace_recommendations: List[str]


class AshFusionTemperatureInterpreter:
    """Interprets AFT measurements and computes slagging/fouling risk indices.

    Uses ISO 540 / ASTM D1857 measurement stages and applies industry
    slagging/fouling risk assessment frameworks for pulverised coal boilers.

    Example:
        >>> interpreter = AshFusionTemperatureInterpreter()
        >>> ash = AshComposition(
        ...     sio2=45.2, al2o3=22.1, fe2o3=12.5, cao=6.8, mgo=2.1,
        ...     na2o=0.8, k2o=1.2, tio2=1.0, total_sulfur_pct=0.6,
        ... )
        >>> aft = AshFusionTemperatures(
        ...     sample_id="KTM_Q1_2026",
        ...     coal_name="Kaltim Prima",
        ...     atmosphere=AtmosphereType.REDUCING,
        ...     dt_c=1100, ht_c=1280, ft_c=1350,
        ...     ash_composition=ash,
        ... )
        >>> result = interpreter.interpret(aft)
        >>> print(result.slagging_risk)
    """

    def interpret(self, aft: AshFusionTemperatures) -> AFTInterpretationResult:
        """Interpret AFT data and compute risk indices.

        Args:
            aft: AshFusionTemperatures measurement data.

        Returns:
            AFTInterpretationResult with full risk assessment.
        """
        if not isinstance(aft, AshFusionTemperatures):
            raise TypeError("aft must be an AshFusionTemperatures instance")

        slagging_risk = None
        fouling_risk = None
        rs = None
        fi = None
        ba = None

        if aft.ash_composition is not None:
            comp = aft.ash_composition
            rs = round(comp.slagging_index_rs, 3)
            fi = round(comp.fouling_index, 3)
            ba = round(comp.base_acid_ratio, 3)
            slagging_risk = self._classify_slagging(rs)
            fouling_risk = self._classify_fouling(fi)

        recommendations = self._generate_recommendations(aft, slagging_risk, fouling_risk)

        return AFTInterpretationResult(
            sample_id=aft.sample_id,
            coal_name=aft.coal_name,
            atmosphere=aft.atmosphere,
            dt_c=aft.dt_c,
            ht_c=aft.ht_c,
            ft_c=aft.ft_c,
            fusion_span_c=aft.fusion_span_c,
            is_high_fusion=aft.is_high_fusion,
            slagging_risk=slagging_risk,
            fouling_risk=fouling_risk,
            slagging_index_rs=rs,
            fouling_index=fi,
            base_acid_ratio=ba,
            furnace_recommendations=recommendations,
        )

    def batch_interpret(self, aft_list: List[AshFusionTemperatures]) -> List[AFTInterpretationResult]:
        """Interpret a list of AFT measurements.

        Args:
            aft_list: List of AshFusionTemperatures.

        Returns:
            List of AFTInterpretationResult.

        Raises:
            ValueError: If aft_list is empty.
        """
        if not aft_list:
            raise ValueError("aft_list cannot be empty")
        return [self.interpret(a) for a in aft_list]

    @staticmethod
    def _classify_slagging(rs: float) -> SlaggingRisk:
        for risk, (lo, hi) in SLAGGING_RS_THRESHOLDS.items():
            if lo <= rs < hi:
                return risk
        return SlaggingRisk.SEVERE

    @staticmethod
    def _classify_fouling(fi: float) -> FoulingRisk:
        for risk, (lo, hi) in FOULING_INDEX_THRESHOLDS.items():
            if lo <= fi < hi:
                return risk
        return FoulingRisk.SEVERE

    @staticmethod
    def _generate_recommendations(
        aft: AshFusionTemperatures,
        slagging: Optional[SlaggingRisk],
        fouling: Optional[FoulingRisk],
    ) -> List[str]:
        recs: List[str] = []
        if aft.ft_c < 1250:
            recs.append(
                f"Low FT ({aft.ft_c:.0f}°C): not suitable for dry-bottom pulverised coal boilers. "
                "Recommend slag-tap (wet-bottom) furnace or blend with high-fusion coal."
            )
        if aft.fusion_span_c < 100:
            recs.append(
                f"Narrow fusion span ({aft.fusion_span_c:.0f}°C): rapid ash phase transition. "
                "Increase furnace temperature monitoring frequency."
            )
        if slagging in (SlaggingRisk.HIGH, SlaggingRisk.SEVERE):
            recs.append(
                f"High slagging risk (Rs={aft.ash_composition.slagging_index_rs:.2f}): "
                "increase furnace wall blower frequency; reduce excess air to control flame shape."
            )
        if fouling in (FoulingRisk.HIGH, FoulingRisk.SEVERE):
            recs.append(
                f"High fouling risk (FI={aft.ash_composition.fouling_index:.2f}): "
                "Na2O={aft.ash_composition.na2o:.1f}% — risk of sticky deposits on superheater tubes. "
                "Increase soot-blower frequency in convection section."
            )
        if aft.is_high_fusion:
            recs.append(
                f"High fusion temperature (FT {aft.ft_c:.0f}°C): suitable for high-load PC boilers. "
                "Low slagging tendency; standard operating protocol applies."
            )
        if not recs:
            recs.append("AFT properties within normal operating range. No corrective action required.")
        return recs
