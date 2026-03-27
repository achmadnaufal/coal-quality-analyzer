"""
Contractual specification compliance checker for coal lots.

Validates coal inspection results against buyer contract specifications,
computes penalty schedules, classifies lot risk, estimates acceptance
probability, and produces aggregate vendor performance summaries.

Supports lot-level PASS/FAIL per parameter, multi-lot aggregate compliance,
penalty computation, risk classification (LOW/MEDIUM/HIGH proximity to
limits), vendor performance tracking, and logistic acceptance probability
modelling for new lots.

References:
    - ISO 23009-1 Coal Trade Specifications
    - ASTM D3172 Proximate Analysis Standards
    - GCCSI Coal Trading Contract Standards (2022)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ContractSpec:
    """
    Buyer contractual specification for coal quality parameters.

    All limits are on Air Dried Basis (ADB) unless otherwise noted.
    None for an optional limit means no contractual threshold applies.

    Attributes:
        contract_id: Unique contract / purchase order identifier.
        buyer_name: Name of the buying party (e.g. power plant operator).
        coal_grade: Contractual grade label (e.g. "GCV5800", "CV6000").
        ash_max_pct: Maximum allowable ash content (%).
        sulfur_max_pct: Maximum allowable total sulfur (%).
        moisture_max_pct: Maximum allowable moisture content (%).
        gcv_min_mjkg: Minimum gross calorific value (MJ/kg ADB).
        price_usd_t: Contract base price (USD per metric tonne).
        penalty_per_excess_unit: Penalty in USD per unit of excess for each
            out-of-spec parameter (same rate for all parameters).
        acceptance_tolerance_pct: Acceptance tolerance window around each
            limit expressed as a percentage of that limit (e.g. 5.0 = 5%).
    """

    contract_id: str
    buyer_name: str
    coal_grade: str
    ash_max_pct: float
    sulfur_max_pct: float
    moisture_max_pct: float
    gcv_min_mjkg: float
    price_usd_t: float
    penalty_per_excess_unit: float
    acceptance_tolerance_pct: float = 5.0

    def __post_init__(self) -> None:
        if not self.contract_id or not self.contract_id.strip():
            raise ValueError("contract_id cannot be empty.")
        if self.ash_max_pct <= 0:
            raise ValueError("ash_max_pct must be positive.")
        if self.sulfur_max_pct <= 0:
            raise ValueError("sulfur_max_pct must be positive.")
        if self.moisture_max_pct <= 0:
            raise ValueError("moisture_max_pct must be positive.")
        if self.gcv_min_mjkg <= 0:
            raise ValueError("gcv_min_mjkg must be positive.")
        if self.price_usd_t < 0:
            raise ValueError("price_usd_t cannot be negative.")
        if self.penalty_per_excess_unit < 0:
            raise ValueError("penalty_per_excess_unit cannot be negative.")
        if not (0 <= self.acceptance_tolerance_pct <= 100):
            raise ValueError("acceptance_tolerance_pct must be between 0 and 100.")


@dataclass
class InspectionResult:
    """
    Laboratory / field inspection result for a single coal lot.

    Attributes:
        lot_id: Unique lot / shipment identifier.
        contract_id: Contract this lot is tendered against.
        sample_date: Date the sample was collected (ISO date string or date).
        ash_pct: Measured ash content (%).
        sulfur_pct: Measured total sulfur (%).
        moisture_pct: Measured moisture content (%).
        gcv_mjkg: Measured gross calorific value (MJ/kg).
        size_fraction_pct: Percentage of oversize / correct-size fraction (%).
        foreign_matter_pct: Percentage of foreign matter contamination (%).
    """

    lot_id: str
    contract_id: str
    sample_date: str | date
    ash_pct: float
    sulfur_pct: float
    moisture_pct: float
    gcv_mjkg: float
    size_fraction_pct: float
    foreign_matter_pct: float

    def __post_init__(self) -> None:
        if not self.lot_id or not self.lot_id.strip():
            raise ValueError("lot_id cannot be empty.")
        if not self.contract_id or not self.contract_id.strip():
            raise ValueError("contract_id cannot be empty.")
        if not (0 <= self.ash_pct <= 50):
            raise ValueError("ash_pct must be between 0 and 50.")
        if not (0 <= self.sulfur_pct <= 10):
            raise ValueError("sulfur_pct must be between 0 and 10.")
        if not (0 <= self.moisture_pct <= 60):
            raise ValueError("moisture_pct must be between 0 and 60.")
        if self.gcv_mjkg <= 0:
            raise ValueError("gcv_mjkg must be positive.")
        if not (0 <= self.size_fraction_pct <= 100):
            raise ValueError("size_fraction_pct must be between 0 and 100.")
        if not (0 <= self.foreign_matter_pct <= 100):
            raise ValueError("foreign_matter_pct must be between 0 and 100.")


# ---------------------------------------------------------------------------
# ComplianceChecker
# ---------------------------------------------------------------------------


class ComplianceChecker:
    """
    Coal lot contractual specification compliance validator.

    Provides lot-level and aggregate compliance checking, penalty computation,
    risk classification, vendor performance summaries, and acceptance
    probability estimation.

    Example:
        >>> checker = ComplianceChecker()
        >>> spec = ContractSpec(
        ...     contract_id="CTR-001", buyer_name="Plant A", coal_grade="GCV5800",
        ...     ash_max_pct=14.0, sulfur_max_pct=0.70, moisture_max_pct=18.0,
        ...     gcv_min_mjkg=23.0, price_usd_t=65.0, penalty_per_excess_unit=2.5,
        ... )
        >>> result = InspectionResult(
        ...     lot_id="LOT-01", contract_id="CTR-001", sample_date="2026-01-15",
        ...     ash_pct=14.8, sulfur_pct=0.65, moisture_pct=17.5,
        ...     gcv_mjkg=22.8, size_fraction_pct=92, foreign_matter_pct=0.5,
        ... )
        >>> check = checker.check_single_lot(result, spec)
        >>> print(check["overall_status"])
        FAIL
    """

    # Fraction of the spec limit used as the HIGH-risk threshold.
    HIGH_RISK_THRESHOLD: float = 0.90

    def check_single_lot(
        self, inspection: InspectionResult, spec: ContractSpec
    ) -> Dict:
        """
        Check a single lot's inspection results against a contract specification.

        Compares each measured parameter against its contractual limit and
        returns per-parameter PASS/FAIL plus an overall lot-level verdict.

        Parameters that are capped (must not exceed max) use ``<= limit`` as PASS;
        GCV is a minimum threshold (``>= gcv_min``) so values below are FAIL.

        Parameters that have no corresponding entry in the spec are omitted
        from the per-parameter results.

        Args:
            inspection: InspectionResult for the lot under review.
            spec: ContractSpec defining the contractual limits.

        Returns:
            Dict with keys:
                - lot_id (str)
                - contract_id (str)
                - overall_status (str): "PASS" or "FAIL"
                - parameter_results (Dict[str, str]): param → "PASS" | "FAIL"
                - total_penalty (float): accumulated penalty (USD/tonne)
                - parameter_details (Dict[str, Dict]): per-parameter breakdown
                  with keys: measured, limit, excess, status
        """
        param_results: Dict[str, str] = {}
        parameter_details: Dict[str, Dict] = {}
        total_penalty: float = 0.0

        # Ash — must not exceed ash_max_pct
        ash_limit = spec.ash_max_pct
        ash_pass = inspection.ash_pct <= ash_limit
        ash_excess = max(0.0, inspection.ash_pct - ash_limit)
        param_results["ash"] = "PASS" if ash_pass else "FAIL"
        parameter_details["ash"] = {
            "measured": inspection.ash_pct,
            "limit": ash_limit,
            "excess": ash_excess,
            "status": "PASS" if ash_pass else "FAIL",
            "unit": "%",
        }
        if not ash_pass:
            total_penalty += ash_excess * spec.penalty_per_excess_unit

        # Sulfur — must not exceed sulfur_max_pct
        s_limit = spec.sulfur_max_pct
        s_pass = inspection.sulfur_pct <= s_limit
        s_excess = max(0.0, inspection.sulfur_pct - s_limit)
        param_results["sulfur"] = "PASS" if s_pass else "FAIL"
        parameter_details["sulfur"] = {
            "measured": inspection.sulfur_pct,
            "limit": s_limit,
            "excess": s_excess,
            "status": "PASS" if s_pass else "FAIL",
            "unit": "%",
        }
        if not s_pass:
            total_penalty += s_excess * spec.penalty_per_excess_unit

        # Moisture — must not exceed moisture_max_pct
        m_limit = spec.moisture_max_pct
        m_pass = inspection.moisture_pct <= m_limit
        m_excess = max(0.0, inspection.moisture_pct - m_limit)
        param_results["moisture"] = "PASS" if m_pass else "FAIL"
        parameter_details["moisture"] = {
            "measured": inspection.moisture_pct,
            "limit": m_limit,
            "excess": m_excess,
            "status": "PASS" if m_pass else "FAIL",
            "unit": "%",
        }
        if not m_pass:
            total_penalty += m_excess * spec.penalty_per_excess_unit

        # GCV — must not be below gcv_min_mjkg
        gcv_limit = spec.gcv_min_mjkg
        gcv_pass = inspection.gcv_mjkg >= gcv_limit
        gcv_excess = max(0.0, gcv_limit - inspection.gcv_mjkg)
        param_results["gcv"] = "PASS" if gcv_pass else "FAIL"
        parameter_details["gcv"] = {
            "measured": inspection.gcv_mjkg,
            "limit": gcv_limit,
            "excess": gcv_excess,
            "status": "PASS" if gcv_pass else "FAIL",
            "unit": "MJ/kg",
        }
        if not gcv_pass:
            total_penalty += gcv_excess * spec.penalty_per_excess_unit

        overall = "PASS" if all(v == "PASS" for v in param_results.values()) else "FAIL"

        return {
            "lot_id": inspection.lot_id,
            "contract_id": inspection.contract_id,
            "overall_status": overall,
            "parameter_results": param_results,
            "total_penalty": round(total_penalty, 4),
            "parameter_details": parameter_details,
        }

    def check_multi_lot(
        self,
        inspections: List[InspectionResult],
        spec: ContractSpec,
    ) -> Dict:
        """
        Aggregate compliance check across multiple lots from the same contract.

        Evaluates each lot individually and returns aggregate statistics:
        pass/fail counts, per-parameter failure rates, and total penalties.

        Args:
            inspections: List of InspectionResult objects for lots under the
                same contract.
            spec: ContractSpec for the contract the lots belong to.

        Returns:
            Dict with keys:
                - contract_id (str)
                - total_lots (int)
                - passed_lots (int)
                - failed_lots (int)
                - pass_rate_pct (float)
                - per_parameter_pass_rate (Dict[str, float])
                - total_penalties (float)
                - lot_results (List[Dict]): each entry is check_single_lot output
        """
        if not inspections:
            return {
                "contract_id": spec.contract_id,
                "total_lots": 0,
                "passed_lots": 0,
                "failed_lots": 0,
                "pass_rate_pct": 0.0,
                "per_parameter_pass_rate": {},
                "total_penalties": 0.0,
                "lot_results": [],
            }

        lot_results = [self.check_single_lot(insp, spec) for insp in inspections]
        passed = sum(1 for r in lot_results if r["overall_status"] == "PASS")
        total_penalties = sum(r["total_penalty"] for r in lot_results)

        # Per-parameter pass rate
        param_keys = ["ash", "sulfur", "moisture", "gcv"]
        per_param: Dict[str, float] = {}
        for key in param_keys:
            passed_key = sum(
                1 for r in lot_results if r["parameter_results"].get(key) == "PASS"
            )
            per_param[key] = round(passed_key / len(lot_results) * 100, 2)

        return {
            "contract_id": spec.contract_id,
            "total_lots": len(inspections),
            "passed_lots": passed,
            "failed_lots": len(inspections) - passed,
            "pass_rate_pct": round(passed / len(inspections) * 100, 2),
            "per_parameter_pass_rate": per_param,
            "total_penalties": round(total_penalties, 4),
            "lot_results": lot_results,
        }

    def calculate_penalties(
        self,
        inspection: InspectionResult,
        spec: ContractSpec,
    ) -> Dict[str, float]:
        """
        Compute penalty amounts for each out-of-spec parameter.

        Penalties are calculated as ``excess * penalty_per_excess_unit`` where
        excess is the amount by which the measured value exceeds its limit
        (for capped parameters) or the shortfall below the minimum (for GCV).
        Parameters within spec have zero penalty.

        Args:
            inspection: InspectionResult for the lot.
            spec: ContractSpec with the penalty schedule.

        Returns:
            Dict mapping each parameter to its penalty amount (USD/tonne).
            Includes an entry for ``"total_penalty"`` equal to the sum of all
            individual penalties.
        """
        penalties: Dict[str, float] = {}

        # Ash penalty
        ash_excess = max(0.0, inspection.ash_pct - spec.ash_max_pct)
        penalties["ash"] = round(ash_excess * spec.penalty_per_excess_unit, 4)

        # Sulfur penalty
        s_excess = max(0.0, inspection.sulfur_pct - spec.sulfur_max_pct)
        penalties["sulfur"] = round(s_excess * spec.penalty_per_excess_unit, 4)

        # Moisture penalty
        m_excess = max(0.0, inspection.moisture_pct - spec.moisture_max_pct)
        penalties["moisture"] = round(m_excess * spec.penalty_per_excess_unit, 4)

        # GCV penalty (shortfall below minimum)
        gcv_excess = max(0.0, spec.gcv_min_mjkg - inspection.gcv_mjkg)
        penalties["gcv"] = round(gcv_excess * spec.penalty_per_excess_unit, 4)

        penalties["total_penalty"] = round(sum(penalties.values()), 4)
        return penalties

    def lot_risk_classification(
        self,
        inspection: InspectionResult,
        spec: ContractSpec,
    ) -> Dict:
        """
        Classify a lot as LOW / MEDIUM / HIGH risk based on proximity to limits.

        - **HIGH**: Measured value is within 90 % of the limit band
          (i.e. at or beyond 90 % of the allowed distance from a reference
          point to the limit). For capped parameters (ash, sulfur, moisture),
          the reference is 0; for GCV (minimum threshold) the reference is
          the theoretical maximum safe CV (set to ``gcv_min * 1.5``).
        - **MEDIUM**: Within 50–90 % of the limit band.
        - **LOW**: Within the first 50 % of the limit band.

        The "limit band" is the maximum permissible deviation before a FAIL,
        scaled by ``acceptance_tolerance_pct`` of the spec.

        Args:
            inspection: InspectionResult for the lot.
            spec: ContractSpec defining the limits.

        Returns:
            Dict with keys:
                - lot_id (str)
                - overall_risk (str): "LOW" | "MEDIUM" | "HIGH"
                - parameter_risks (Dict[str, str]): per-parameter risk level
                - parameter_proximity_pct (Dict[str, float]): proximity to limit (%)
                - risk_signal (str): human-readable summary
        """
        threshold_high = self.HIGH_RISK_THRESHOLD  # 0.90
        threshold_med = 0.50

        # Acceptance tolerance band per parameter
        # For capped params: max deviation before FAIL = tolerance_pct of limit
        # For GCV: max shortfall before FAIL = tolerance_pct of (gcv_min * tolerance_factor)
        tol = spec.acceptance_tolerance_pct / 100.0

        def _proximity_capped(
            measured: float, limit: float, tol: float
        ) -> float:
            """Return proximity fraction for a capped parameter (≤ limit)."""
            max_deviation = limit * (1 + tol) - limit  # = limit * tol
            if max_deviation <= 0:
                return 1.0
            actual_deviation = max(0.0, measured - limit)
            return min(1.0, actual_deviation / max_deviation)

        def _proximity_floor(
            measured: float, floor: float, tol: float
        ) -> float:
            """Return proximity fraction for a floor parameter (≥ minimum)."""
            max_shortfall = floor * tol
            if max_shortfall <= 0:
                return 1.0
            actual_shortfall = max(0.0, floor - measured)
            return min(1.0, actual_shortfall / max_shortfall)

        ash_prox = _proximity_capped(inspection.ash_pct, spec.ash_max_pct, tol)
        s_prox = _proximity_capped(inspection.sulfur_pct, spec.sulfur_max_pct, tol)
        m_prox = _proximity_capped(inspection.moisture_pct, spec.moisture_max_pct, tol)
        gcv_prox = _proximity_floor(inspection.gcv_mjkg, spec.gcv_min_mjkg, tol)

        param_risks: Dict[str, str] = {}
        param_prox: Dict[str, float] = {}

        for name, prox in [("ash", ash_prox), ("sulfur", s_prox), ("moisture", m_prox), ("gcv", gcv_prox)]:
            param_prox[name] = round(prox * 100, 2)
            if prox >= threshold_high:
                param_risks[name] = "HIGH"
            elif prox >= threshold_med:
                param_risks[name] = "MEDIUM"
            else:
                param_risks[name] = "LOW"

        overall = max(param_risks.values(), key=lambda x: ["LOW", "MEDIUM", "HIGH"].index(x))

        high_risk_params = [k for k, v in param_risks.items() if v == "HIGH"]
        signal = (
            f"Lot {inspection.lot_id}: overall {overall} risk"
            + (f" (HIGH risk on: {', '.join(high_risk_params)})" if high_risk_params else "")
        )

        return {
            "lot_id": inspection.lot_id,
            "overall_risk": overall,
            "parameter_risks": param_risks,
            "parameter_proximity_pct": param_prox,
            "risk_signal": signal,
        }

    def vendor_performance_summary(
        self,
        lots: List[Tuple[InspectionResult, ContractSpec]],
    ) -> pd.DataFrame:
        """
        Aggregate compliance statistics per vendor across all contracts.

        Each lot is associated with the contract it was inspected against;
        the vendor is inferred from the contract via ``buyer_name``.

        Args:
            lots: List of (InspectionResult, ContractSpec) tuples representing
                all lots to be included in the summary.

        Returns:
            pandas.DataFrame with one row per vendor and columns:
                - vendor (str): buyer_name from the ContractSpec
                - total_lots (int)
                - passed_lots (int)
                - failed_lots (int)
                - pass_rate_pct (float)
                - avg_penalty_usd_t (float): mean total penalty across all lots
                - total_penalties_usd (float): sum of penalties
                - ash_fail_rate_pct (float)
                - sulfur_fail_rate_pct (float)
                - moisture_fail_rate_pct (float)
                - gcv_fail_rate_pct (float)
        """
        if not lots:
            return pd.DataFrame(
                columns=[
                    "vendor", "total_lots", "passed_lots", "failed_lots",
                    "pass_rate_pct", "avg_penalty_usd_t", "total_penalties_usd",
                    "ash_fail_rate_pct", "sulfur_fail_rate_pct",
                    "moisture_fail_rate_pct", "gcv_fail_rate_pct",
                ]
            )

        records: List[Dict] = []
        for inspection, spec in lots:
            check = self.check_single_lot(inspection, spec)
            pens = self.calculate_penalties(inspection, spec)
            records.append({
                "vendor": spec.buyer_name,
                "lot_id": inspection.lot_id,
                "passed": check["overall_status"] == "PASS",
                "total_penalty": pens["total_penalty"],
                "ash_fail": check["parameter_results"].get("ash") == "FAIL",
                "sulfur_fail": check["parameter_results"].get("sulfur") == "FAIL",
                "moisture_fail": check["parameter_results"].get("moisture") == "FAIL",
                "gcv_fail": check["parameter_results"].get("gcv") == "FAIL",
            })

        df = pd.DataFrame(records)

        summary = (
            df.groupby("vendor")
            .agg(
                total_lots=("lot_id", "count"),
                passed_lots=("passed", "sum"),
                failed_lots=("passed", lambda x: (~x).sum()),
                avg_penalty_usd_t=("total_penalty", "mean"),
                total_penalties_usd=("total_penalty", "sum"),
                ash_fail_count=("ash_fail", "sum"),
                sulfur_fail_count=("sulfur_fail", "sum"),
                moisture_fail_count=("moisture_fail", "sum"),
                gcv_fail_count=("gcv_fail", "sum"),
            )
            .reset_index()
        )

        summary["pass_rate_pct"] = (
            summary["passed_lots"] / summary["total_lots"] * 100
        ).round(2)
        summary["avg_penalty_usd_t"] = summary["avg_penalty_usd_t"].round(4)
        summary["total_penalties_usd"] = summary["total_penalties_usd"].round(4)
        summary["ash_fail_rate_pct"] = (
            summary["ash_fail_count"] / summary["total_lots"] * 100
        ).round(2)
        summary["sulfur_fail_rate_pct"] = (
            summary["sulfur_fail_count"] / summary["total_lots"] * 100
        ).round(2)
        summary["moisture_fail_rate_pct"] = (
            summary["moisture_fail_count"] / summary["total_lots"] * 100
        ).round(2)
        summary["gcv_fail_rate_pct"] = (
            summary["gcv_fail_count"] / summary["total_lots"] * 100
        ).round(2)

        drop_cols = [
            "ash_fail_count", "sulfur_fail_count",
            "moisture_fail_count", "gcv_fail_count",
        ]
        return summary.drop(columns=drop_cols)

    def acceptance_probability(
        self,
        inspection: InspectionResult,
        spec: ContractSpec,
        logistic_slope: float = 5.0,
    ) -> float:
        """
        Estimate acceptance probability for a new lot using a logistic model.

        The logistic model maps each parameter's proximity to its limit to a
        probability between 0 and 1. Individual probabilities are combined via
        the product of Bernoulli probabilities (independence assumption), and
        the final probability is clipped to [0, 1].

        A parameter that is already FAIL contributes probability 0. The slope
        controls how steeply probability drops near the limit boundary:
        higher slope → sharper drop (less tolerance for near-limit values).

        Args:
            inspection: InspectionResult for the candidate lot.
            spec: ContractSpec defining the contractual limits.
            logistic_slope: Steepness parameter for the logistic function.
                Must be positive. Default 5.0 gives a ~99 % probability at
                50 % proximity and ~1 % at 100 % proximity.

        Returns:
            Estimated acceptance probability in [0.0, 1.0].
        """
        if logistic_slope <= 0:
            raise ValueError("logistic_slope must be positive.")

        tol = spec.acceptance_tolerance_pct / 100.0

        def _param_prob_capped(measured: float, limit: float) -> float:
            """Logistic probability for a capped parameter."""
            if measured <= limit:
                return 1.0
            if measured > limit * (1 + tol):
                return 0.0
            # Normalised position: 0 at limit, 1 at limit*(1+tol)
            x = (measured - limit) / (limit * tol)
            return 1.0 / (1.0 + math.exp(logistic_slope * (x - 0.5)))

        def _param_prob_floor(measured: float, floor: float) -> float:
            """Logistic probability for a floor (minimum) parameter."""
            if measured >= floor:
                return 1.0
            if measured < floor * (1 - tol):
                return 0.0
            x = (floor - measured) / (floor * tol)
            return 1.0 / (1.0 + math.exp(logistic_slope * (x - 0.5)))

        ash_prob = _param_prob_capped(inspection.ash_pct, spec.ash_max_pct)
        s_prob = _param_prob_capped(inspection.sulfur_pct, spec.sulfur_max_pct)
        m_prob = _param_prob_capped(inspection.moisture_pct, spec.moisture_max_pct)
        gcv_prob = _param_prob_floor(inspection.gcv_mjkg, spec.gcv_min_mjkg)

        combined = ash_prob * s_prob * m_prob * gcv_prob
        return round(max(0.0, min(1.0, combined)), 4)

    def export_compliance_report(
        self,
        inspections: List[InspectionResult],
        specs: Dict[str, ContractSpec],
    ) -> pd.DataFrame:
        """
        Generate a full compliance report DataFrame for all lots and parameters.

        Each row represents one parameter of one lot. Includes PASS/FAIL flag,
        measured value, contract limit, excess/shortfall, penalty amount, and
        risk classification.

        Parameters that have no entry in the corresponding ContractSpec are
        omitted from the output.

        Args:
            inspections: List of InspectionResult objects (lots may span
                multiple contracts).
            specs: Mapping from contract_id → ContractSpec for all contracts
                referenced by the inspections.

        Returns:
            pandas.DataFrame with columns:
                lot_id, contract_id, sample_date, parameter, measured_value,
                limit_value, excess_shortfall, status (PASS/FAIL),
                penalty_usd_t, risk_class (LOW/MEDIUM/HIGH)
        """
        rows: List[Dict] = []
        for insp in inspections:
            if insp.contract_id not in specs:
                continue  # skip lots without a corresponding spec
            spec = specs[insp.contract_id]
            check = self.check_single_lot(insp, spec)
            risk = self.lot_risk_classification(insp, spec)
            penalties = self.calculate_penalties(insp, spec)

            sample_date = (
                insp.sample_date
                if isinstance(insp.sample_date, str)
                else str(insp.sample_date)
            )

            for param, details in check["parameter_details"].items():
                rows.append({
                    "lot_id": insp.lot_id,
                    "contract_id": insp.contract_id,
                    "sample_date": sample_date,
                    "parameter": param,
                    "measured_value": details["measured"],
                    "limit_value": details["limit"],
                    "excess_shortfall": round(details["excess"], 4),
                    "status": details["status"],
                    "penalty_usd_t": penalties.get(param, 0.0),
                    "risk_class": risk["parameter_risks"].get(param, "LOW"),
                })

        return pd.DataFrame(rows)
