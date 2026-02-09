"""
Coal contract specification compliance checker.

Validates a coal shipment's quality analysis against buyer contract
specifications, flags non-compliance, and computes rejection risk,
price adjustment penalties (gar-based bonus/deduction), and
the overall contract conformance score.

Covers both thermal coal (power generation) and coking/metallurgical coal
(steel-making) contract types, using typical Indonesian (ESDM/PTBA),
Australian (QCOAL, Whitehaven) and Japanese-spec contract structures.

References:
    - ASTM D388 (2019) Standard Classification of Coals by Rank
    - ISO 17246 (2010) Coal — Proximate Analysis
    - ISO 7936 (1992) Hard Coal — Washability Analysis
    - IEA (2022) Coal Market Report — quality specification trends
    - Directorate General of Minerals and Coal, Indonesia (2021) SNI quality standards
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class CoalContractType(Enum):
    """Broad coal contract classification."""
    THERMAL = "thermal"              # Electricity generation
    COKING = "coking"                # Metallurgical blast furnace coal
    PCI = "pci"                      # Pulverised Coal Injection (steel-making)
    SEMI_SOFT = "semi_soft"          # Semi-soft coking coal


class SpecStatus(Enum):
    """Individual parameter compliance status."""
    WITHIN_SPEC = "within_spec"
    MARGINAL = "marginal"            # Within rejection band but near limit
    PRICE_ADJUSTED = "price_adjusted"  # Out of typical but within penalty band
    REJECTED = "rejected"            # Exceeds rejection limit


@dataclass
class CoalContractSpec:
    """
    Buyer contract specification for coal quality parameters.

    All limits are on Air Dried Basis (ADB) unless noted.
    None means no contract limit for that parameter.

    Attributes:
        contract_id (str): Unique contract/purchase order identifier.
        contract_type (CoalContractType): Type of coal contract.
        gar_typical_kcal_kg (float): Typical gross-as-received calorific value (kcal/kg).
        gar_min_kcal_kg (float): Rejection minimum GARr calorific value.
        total_moisture_max_pct (float): Maximum total moisture on ARB (%).
        inherent_moisture_max_pct (Optional[float]): Max inherent moisture ADB (%).
        ash_max_pct (float): Maximum ash content ADB (%).
        ash_rejection_pct (Optional[float]): Rejection threshold (stricter than max).
        volatile_matter_min_pct (Optional[float]): Minimum VM ADB (%).
        volatile_matter_max_pct (Optional[float]): Maximum VM ADB (%).
        total_sulphur_max_pct (float): Maximum total sulphur ADB (%).
        hgi_min (Optional[float]): Minimum Hardgrove Grindability Index.
        csi_max (Optional[float]): Maximum Crucible Swelling Index (coking/PCI).
        price_adj_per_100kcal (float): Price adjustment per 100 kcal/kg deviation
            from typical (USD/tonne). 0 if no adjustment clause.

    Example:
        >>> spec = CoalContractSpec(
        ...     contract_id="PO-2026-089",
        ...     contract_type=CoalContractType.THERMAL,
        ...     gar_typical_kcal_kg=5500.0,
        ...     gar_min_kcal_kg=5300.0,
        ...     total_moisture_max_pct=28.0,
        ...     ash_max_pct=12.0,
        ...     total_sulphur_max_pct=0.8,
        ...     hgi_min=45.0,
        ...     price_adj_per_100kcal=0.12,
        ... )
    """

    contract_id: str
    contract_type: CoalContractType
    gar_typical_kcal_kg: float
    gar_min_kcal_kg: float
    total_moisture_max_pct: float
    ash_max_pct: float
    total_sulphur_max_pct: float
    inherent_moisture_max_pct: Optional[float] = None
    ash_rejection_pct: Optional[float] = None
    volatile_matter_min_pct: Optional[float] = None
    volatile_matter_max_pct: Optional[float] = None
    hgi_min: Optional[float] = None
    csi_max: Optional[float] = None
    price_adj_per_100kcal: float = 0.0

    def __post_init__(self) -> None:
        if not self.contract_id or not self.contract_id.strip():
            raise ValueError("contract_id cannot be empty.")
        if self.gar_typical_kcal_kg <= 0:
            raise ValueError("gar_typical_kcal_kg must be > 0.")
        if self.gar_min_kcal_kg <= 0:
            raise ValueError("gar_min_kcal_kg must be > 0.")
        if self.gar_min_kcal_kg > self.gar_typical_kcal_kg:
            raise ValueError("gar_min_kcal_kg must be <= gar_typical_kcal_kg.")
        if self.total_moisture_max_pct <= 0:
            raise ValueError("total_moisture_max_pct must be > 0.")
        if self.ash_max_pct <= 0:
            raise ValueError("ash_max_pct must be > 0.")
        if self.total_sulphur_max_pct <= 0:
            raise ValueError("total_sulphur_max_pct must be > 0.")
        if self.price_adj_per_100kcal < 0:
            raise ValueError("price_adj_per_100kcal must be >= 0.")


@dataclass
class ShipmentAnalysis:
    """
    Quality analysis results for a coal shipment (lot average certificate of analysis).

    Attributes:
        shipment_id (str): Shipment or vessel lot identifier.
        gar_kcal_kg (float): Measured GARr calorific value.
        total_moisture_pct (float): Measured total moisture ARB (%).
        inherent_moisture_pct (float): Measured inherent moisture ADB (%).
        ash_pct (float): Measured ash ADB (%).
        volatile_matter_pct (float): Measured volatile matter ADB (%).
        total_sulphur_pct (float): Measured total sulphur ADB (%).
        hgi (Optional[float]): Measured Hardgrove Grindability Index.
        csi (Optional[float]): Measured Crucible Swelling Index.
        tonnes (float): Shipment size in metric tonnes. Must be > 0.
    """

    shipment_id: str
    gar_kcal_kg: float
    total_moisture_pct: float
    inherent_moisture_pct: float
    ash_pct: float
    volatile_matter_pct: float
    total_sulphur_pct: float
    hgi: Optional[float] = None
    csi: Optional[float] = None
    tonnes: float = 1.0

    def __post_init__(self) -> None:
        if not self.shipment_id or not self.shipment_id.strip():
            raise ValueError("shipment_id cannot be empty.")
        if self.gar_kcal_kg <= 0:
            raise ValueError("gar_kcal_kg must be > 0.")
        if not (0.0 <= self.total_moisture_pct <= 60.0):
            raise ValueError("total_moisture_pct must be between 0 and 60.")
        if not (0.0 <= self.ash_pct <= 50.0):
            raise ValueError("ash_pct must be between 0 and 50.")
        if not (0.0 <= self.volatile_matter_pct <= 60.0):
            raise ValueError("volatile_matter_pct must be between 0 and 60.")
        if not (0.0 <= self.total_sulphur_pct <= 10.0):
            raise ValueError("total_sulphur_pct must be between 0 and 10.")
        if self.tonnes <= 0:
            raise ValueError("tonnes must be > 0.")


@dataclass
class ComplianceCheckResult:
    """Full compliance check output for one shipment vs one contract spec."""

    shipment_id: str
    contract_id: str
    overall_status: str             # ACCEPTED / CONDITIONALLY_ACCEPTED / REJECTED
    conformance_score: float        # 0–100
    parameter_results: Dict[str, str]   # param → SpecStatus.value
    price_adjustment_usd_tonne: float   # Negative = deduction, positive = bonus
    total_price_impact_usd: float
    non_conforming_parameters: List[str]
    rejection_reasons: List[str]
    recommendations: List[str]
    warnings: List[str] = field(default_factory=list)


class ContractSpecificationChecker:
    """
    Validate a coal shipment quality analysis against buyer contract specifications.

    Accepts shipments that are within all spec limits, applies conditional
    acceptance with price adjustment for CV deviations, and rejects shipments
    that exceed critical rejection limits.

    Example:
        >>> checker = ContractSpecificationChecker()
        >>> result = checker.check(shipment, spec)
        >>> print(f"Status: {result.overall_status} | Score: {result.conformance_score:.1f}")
    """

    def check(
        self, shipment: ShipmentAnalysis, spec: CoalContractSpec
    ) -> ComplianceCheckResult:
        """
        Check a shipment's quality analysis against the contract specification.

        Args:
            shipment: ShipmentAnalysis with laboratory results.
            spec: CoalContractSpec with buyer requirements.

        Returns:
            ComplianceCheckResult with acceptance decision and adjustments.
        """
        param_results: Dict[str, str] = {}
        non_conforming: List[str] = []
        rejection_reasons: List[str] = []
        penalty_per_tonne = 0.0

        # 1. GARr calorific value
        gar_status, gar_adj = self._check_gar(shipment, spec)
        param_results["gar"] = gar_status.value
        penalty_per_tonne += gar_adj
        if gar_status == SpecStatus.REJECTED:
            rejection_reasons.append(
                f"GARr {shipment.gar_kcal_kg:.0f} kcal/kg below rejection minimum "
                f"{spec.gar_min_kcal_kg:.0f} kcal/kg."
            )
            non_conforming.append("gar")
        elif gar_status in (SpecStatus.PRICE_ADJUSTED, SpecStatus.MARGINAL):
            non_conforming.append("gar")

        # 2. Total moisture
        tm_status = self._check_max("total_moisture", shipment.total_moisture_pct, spec.total_moisture_max_pct)
        param_results["total_moisture"] = tm_status.value
        if tm_status == SpecStatus.REJECTED:
            rejection_reasons.append(
                f"Total moisture {shipment.total_moisture_pct:.1f}% exceeds max {spec.total_moisture_max_pct:.1f}%."
            )
            non_conforming.append("total_moisture")

        # 3. Ash
        ash_rej = spec.ash_rejection_pct or spec.ash_max_pct * 1.05
        ash_status = self._check_ash(shipment.ash_pct, spec.ash_max_pct, ash_rej)
        param_results["ash"] = ash_status.value
        if ash_status == SpecStatus.REJECTED:
            rejection_reasons.append(
                f"Ash {shipment.ash_pct:.1f}% exceeds rejection limit {ash_rej:.1f}%."
            )
            non_conforming.append("ash")
        elif ash_status in (SpecStatus.PRICE_ADJUSTED, SpecStatus.MARGINAL):
            non_conforming.append("ash")

        # 4. Sulphur
        s_status = self._check_max("total_sulphur", shipment.total_sulphur_pct, spec.total_sulphur_max_pct)
        param_results["total_sulphur"] = s_status.value
        if s_status == SpecStatus.REJECTED:
            rejection_reasons.append(
                f"Total sulphur {shipment.total_sulphur_pct:.2f}% exceeds max {spec.total_sulphur_max_pct:.2f}%."
            )
            non_conforming.append("total_sulphur")

        # 5. Volatile matter (if specified)
        if spec.volatile_matter_min_pct is not None:
            vm_lo_ok = shipment.volatile_matter_pct >= spec.volatile_matter_min_pct
            param_results["volatile_matter_min"] = (
                SpecStatus.WITHIN_SPEC.value if vm_lo_ok else SpecStatus.REJECTED.value
            )
            if not vm_lo_ok:
                rejection_reasons.append(
                    f"Volatile matter {shipment.volatile_matter_pct:.1f}% below minimum "
                    f"{spec.volatile_matter_min_pct:.1f}%."
                )
                non_conforming.append("volatile_matter_min")

        if spec.volatile_matter_max_pct is not None:
            vm_hi_ok = shipment.volatile_matter_pct <= spec.volatile_matter_max_pct
            param_results["volatile_matter_max"] = (
                SpecStatus.WITHIN_SPEC.value if vm_hi_ok else SpecStatus.REJECTED.value
            )
            if not vm_hi_ok:
                rejection_reasons.append(
                    f"Volatile matter {shipment.volatile_matter_pct:.1f}% above maximum "
                    f"{spec.volatile_matter_max_pct:.1f}%."
                )
                non_conforming.append("volatile_matter_max")

        # 6. HGI (if specified)
        if spec.hgi_min is not None and shipment.hgi is not None:
            hgi_ok = shipment.hgi >= spec.hgi_min
            param_results["hgi"] = SpecStatus.WITHIN_SPEC.value if hgi_ok else SpecStatus.REJECTED.value
            if not hgi_ok:
                non_conforming.append("hgi")
                rejection_reasons.append(
                    f"HGI {shipment.hgi:.0f} below minimum {spec.hgi_min:.0f}."
                )

        # 7. CSI (if specified)
        if spec.csi_max is not None and shipment.csi is not None:
            csi_ok = shipment.csi <= spec.csi_max
            param_results["csi"] = SpecStatus.WITHIN_SPEC.value if csi_ok else SpecStatus.REJECTED.value
            if not csi_ok:
                non_conforming.append("csi")
                rejection_reasons.append(
                    f"CSI {shipment.csi:.1f} exceeds maximum {spec.csi_max:.1f}."
                )

        # Overall decision
        is_rejected = len(rejection_reasons) > 0
        overall = "REJECTED" if is_rejected else (
            "CONDITIONALLY_ACCEPTED" if non_conforming else "ACCEPTED"
        )
        conformance_score = self._conformance_score(param_results, non_conforming)
        total_impact = round(penalty_per_tonne * shipment.tonnes, 2)
        recommendations = self._recommendations(non_conforming, spec)
        warnings = self._warnings(shipment, spec)

        return ComplianceCheckResult(
            shipment_id=shipment.shipment_id,
            contract_id=spec.contract_id,
            overall_status=overall,
            conformance_score=round(conformance_score, 1),
            parameter_results=param_results,
            price_adjustment_usd_tonne=round(penalty_per_tonne, 4),
            total_price_impact_usd=total_impact,
            non_conforming_parameters=non_conforming,
            rejection_reasons=rejection_reasons,
            recommendations=recommendations,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_gar(
        shipment: ShipmentAnalysis, spec: CoalContractSpec
    ) -> Tuple[SpecStatus, float]:
        """Return (status, price_adjustment_usd_tonne)."""
        gar = shipment.gar_kcal_kg
        if gar < spec.gar_min_kcal_kg:
            return SpecStatus.REJECTED, 0.0
        deviation_100kcal = (gar - spec.gar_typical_kcal_kg) / 100.0
        adj = deviation_100kcal * spec.price_adj_per_100kcal
        if abs(deviation_100kcal) <= 1.0:
            return SpecStatus.WITHIN_SPEC, round(adj, 4)
        if abs(deviation_100kcal) <= 3.0:
            return SpecStatus.PRICE_ADJUSTED, round(adj, 4)
        return SpecStatus.MARGINAL, round(adj, 4)

    @staticmethod
    def _check_max(
        param: str, actual: float, limit: float
    ) -> SpecStatus:
        if actual <= limit * 0.95:
            return SpecStatus.WITHIN_SPEC
        if actual <= limit:
            return SpecStatus.MARGINAL
        return SpecStatus.REJECTED

    @staticmethod
    def _check_ash(actual: float, max_limit: float, rejection: float) -> SpecStatus:
        if actual > rejection:
            return SpecStatus.REJECTED
        if actual > max_limit:
            return SpecStatus.PRICE_ADJUSTED
        if actual > max_limit * 0.95:
            return SpecStatus.MARGINAL
        return SpecStatus.WITHIN_SPEC

    @staticmethod
    def _conformance_score(
        results: Dict[str, str], non_conforming: List[str]
    ) -> float:
        n = len(results)
        if n == 0:
            return 100.0
        passed = sum(1 for v in results.values() if v == SpecStatus.WITHIN_SPEC.value)
        return passed / n * 100.0

    @staticmethod
    def _recommendations(
        non_conforming: List[str], spec: CoalContractSpec
    ) -> List[str]:
        recs = []
        if "ash" in non_conforming:
            recs.append(
                "Review wash-plant density media settings to reduce product ash below spec."
            )
        if "total_sulphur" in non_conforming:
            recs.append(
                "Sulphur exceeds spec — audit overburden sources and blend "
                "high-sulphur seams with lower-sulphur material."
            )
        if "total_moisture" in non_conforming:
            recs.append(
                "Moisture above spec — extend stockpile drainage time before loading "
                "or consider thermal drying option."
            )
        if "gar" in non_conforming:
            recs.append(
                "GARr below typical — re-blend with higher-CV material before shipment "
                "or renegotiate price adjustment with buyer."
            )
        if "hgi" in non_conforming:
            recs.append(
                "HGI below spec — notify buyer's coal handling plant team; "
                "may require mill speed adjustment."
            )
        return recs

    @staticmethod
    def _warnings(
        shipment: ShipmentAnalysis, spec: CoalContractSpec
    ) -> List[str]:
        warnings = []
        gar_gap = shipment.gar_kcal_kg - spec.gar_min_kcal_kg
        if 0 < gar_gap < 100:
            warnings.append(
                f"GARr {shipment.gar_kcal_kg:.0f} kcal/kg is within 100 kcal/kg "
                "of the rejection minimum — monitor closely."
            )
        ash_margin = spec.ash_max_pct - shipment.ash_pct
        if 0 < ash_margin < 0.5:
            warnings.append(
                f"Ash at {shipment.ash_pct:.1f}% — only {ash_margin:.2f}% below max limit."
            )
        return warnings
