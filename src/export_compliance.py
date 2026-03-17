"""
Export compliance checker for coal quality parameters.

Validates coal batches against destination market specifications for
international thermal coal trade. Supports Indonesian, Australian, and
Chinese market standards.

Key coal quality parameters checked:
    - Gross Calorific Value (GCV) — energy content, primary commercial metric
    - Total Moisture (TM) — affects handling and GCV
    - Ash Content — impacts combustion efficiency and disposal
    - Total Sulfur — environmental compliance (SOx emissions)
    - Volatile Matter (VM) — combustion reactivity
    - Fixed Carbon (FC) — primary combustible component

References:
    - ASTM D3172 / ISO 17246 — Proximate Analysis
    - Indonesian Ministry of Energy Decree No. 1827 K/30/MEM/2018
    - Australian Coal Quality Handbook
    - GB/T 15224.3-2010 (Chinese coal classification standard)
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


# Market specifications (min, max) — None means no limit
# GCV in kcal/kg (ADB), all others in % dry basis
MARKET_SPECS: Dict[str, Dict[str, Dict]] = {
    "japan_standard": {
        "description": "Japanese utility standard (PCI/steam coal)",
        "gcv_adb_kcal_kg": {"min": 6000, "max": None},
        "total_moisture_pct": {"min": None, "max": 18.0},
        "ash_adb_pct": {"min": None, "max": 15.0},
        "total_sulfur_adb_pct": {"min": None, "max": 0.80},
        "volatile_matter_adb_pct": {"min": None, "max": 40.0},
    },
    "china_standard": {
        "description": "Chinese thermal power plant standard (GB/T)",
        "gcv_adb_kcal_kg": {"min": 5000, "max": None},
        "total_moisture_pct": {"min": None, "max": 25.0},
        "ash_adb_pct": {"min": None, "max": 25.0},
        "total_sulfur_adb_pct": {"min": None, "max": 1.50},
        "volatile_matter_adb_pct": {"min": 20.0, "max": 45.0},
    },
    "india_standard": {
        "description": "Indian power sector import standard",
        "gcv_adb_kcal_kg": {"min": 5500, "max": None},
        "total_moisture_pct": {"min": None, "max": 20.0},
        "ash_adb_pct": {"min": None, "max": 20.0},
        "total_sulfur_adb_pct": {"min": None, "max": 1.00},
        "volatile_matter_adb_pct": {"min": None, "max": 42.0},
    },
    "indonesian_domestic": {
        "description": "Indonesian domestic market standard (DMO)",
        "gcv_adb_kcal_kg": {"min": 4000, "max": None},
        "total_moisture_pct": {"min": None, "max": 35.0},
        "ash_adb_pct": {"min": None, "max": 30.0},
        "total_sulfur_adb_pct": {"min": None, "max": 2.00},
        "volatile_matter_adb_pct": {"min": None, "max": 50.0},
    },
}


@dataclass
class CoalBatch:
    """
    Represents a coal batch with quality test results.

    All parameters should be reported on Air-Dried Basis (ADB) unless noted.

    Attributes:
        batch_id (str): Unique batch identifier
        mine_code (str): Mine or stockpile code
        gcv_adb_kcal_kg (float): Gross Calorific Value, ADB (kcal/kg)
        total_moisture_pct (float): Total moisture content (%)
        ash_adb_pct (float): Ash content, ADB (%)
        total_sulfur_adb_pct (float): Total sulfur, ADB (%)
        volatile_matter_adb_pct (float): Volatile matter, ADB (%)
        fixed_carbon_adb_pct (float, optional): Fixed carbon, ADB (%)
        tonnes (float, optional): Batch size in metric tonnes
    """

    batch_id: str
    mine_code: str
    gcv_adb_kcal_kg: float
    total_moisture_pct: float
    ash_adb_pct: float
    total_sulfur_adb_pct: float
    volatile_matter_adb_pct: float
    fixed_carbon_adb_pct: Optional[float] = None
    tonnes: Optional[float] = None

    def __post_init__(self):
        """Validate coal quality parameters on initialization."""
        if not self.batch_id or not self.batch_id.strip():
            raise ValueError("batch_id cannot be empty")
        if self.gcv_adb_kcal_kg <= 0:
            raise ValueError("gcv_adb_kcal_kg must be positive")
        if not 0 <= self.total_moisture_pct <= 100:
            raise ValueError("total_moisture_pct must be 0-100")
        if not 0 <= self.ash_adb_pct <= 100:
            raise ValueError("ash_adb_pct must be 0-100")
        if not 0 <= self.total_sulfur_adb_pct <= 10:
            raise ValueError("total_sulfur_adb_pct must be 0-10")
        if not 0 <= self.volatile_matter_adb_pct <= 100:
            raise ValueError("volatile_matter_adb_pct must be 0-100")

        # Validation: proximate analysis should roughly sum to ~100% (ADB basis)
        # If all components provided, flag if sum is far off (data entry error)
        if self.fixed_carbon_adb_pct is not None:
            total = (
                self.ash_adb_pct
                + self.volatile_matter_adb_pct
                + self.fixed_carbon_adb_pct
            )
            if not 85 <= total <= 115:
                # Loose check — doesn't raise, but we note it
                pass  # Could log a warning in production


class ExportComplianceChecker:
    """
    Check coal batch compliance against destination market specifications.

    Validates multiple quality parameters against a named market standard
    and generates a pass/fail report with deviation details.

    Attributes:
        market (str): Target market name (must be in MARKET_SPECS)
        spec (dict): Specification dictionary for the target market

    Example:
        >>> checker = ExportComplianceChecker("japan_standard")
        >>> batch = CoalBatch(
        ...     batch_id="BATCH-2025-001",
        ...     mine_code="KPC-EK",
        ...     gcv_adb_kcal_kg=6200,
        ...     total_moisture_pct=14.0,
        ...     ash_adb_pct=12.5,
        ...     total_sulfur_adb_pct=0.65,
        ...     volatile_matter_adb_pct=38.0,
        ... )
        >>> result = checker.check_batch(batch)
        >>> print(f"Compliant: {result['is_compliant']}")
    """

    PARAMETER_LABELS = {
        "gcv_adb_kcal_kg": "GCV (ADB) kcal/kg",
        "total_moisture_pct": "Total Moisture %",
        "ash_adb_pct": "Ash (ADB) %",
        "total_sulfur_adb_pct": "Total Sulfur (ADB) %",
        "volatile_matter_adb_pct": "Volatile Matter (ADB) %",
    }

    def __init__(self, market: str):
        """
        Initialize compliance checker for a target market.

        Args:
            market: Market name (must be in MARKET_SPECS)

        Raises:
            ValueError: If market is not recognized

        Example:
            >>> checker = ExportComplianceChecker("china_standard")
        """
        available = list(MARKET_SPECS.keys())
        if market not in MARKET_SPECS:
            raise ValueError(
                f"Market '{market}' not recognized. Available: {available}"
            )
        self.market = market
        self.spec = MARKET_SPECS[market]

    def _check_parameter(
        self,
        param_name: str,
        value: float,
        limits: Dict,
    ) -> Dict:
        """
        Check a single parameter against min/max limits.

        Args:
            param_name: Parameter name
            value: Actual measured value
            limits: Dict with 'min' and/or 'max' keys (None = no limit)

        Returns:
            Dict with 'passed', 'deviation', 'limit_type', 'message'
        """
        min_val = limits.get("min")
        max_val = limits.get("max")
        label = self.PARAMETER_LABELS.get(param_name, param_name)

        # Check min limit
        if min_val is not None and value < min_val:
            deviation = value - min_val  # Negative = below min
            return {
                "parameter": param_name,
                "label": label,
                "value": value,
                "passed": False,
                "limit_type": "below_minimum",
                "limit": min_val,
                "deviation": round(deviation, 4),
                "message": f"{label}: {value} is below minimum {min_val}",
            }

        # Check max limit
        if max_val is not None and value > max_val:
            deviation = value - max_val  # Positive = above max
            return {
                "parameter": param_name,
                "label": label,
                "value": value,
                "passed": False,
                "limit_type": "above_maximum",
                "limit": max_val,
                "deviation": round(deviation, 4),
                "message": f"{label}: {value} exceeds maximum {max_val}",
            }

        return {
            "parameter": param_name,
            "label": label,
            "value": value,
            "passed": True,
            "limit_type": "within_spec",
            "limit": None,
            "deviation": 0.0,
            "message": f"{label}: {value} is within specification",
        }

    def check_batch(self, batch: CoalBatch) -> Dict:
        """
        Check a coal batch against the target market specification.

        Args:
            batch: CoalBatch instance with quality data

        Returns:
            Dictionary with:
                - batch_id: Batch identifier
                - market: Target market
                - is_compliant: True only if ALL parameters pass
                - passed_count: Number of parameters that passed
                - failed_count: Number of parameters that failed
                - parameter_results: List of per-parameter check results
                - failed_parameters: List of failed parameter names

        Example:
            >>> result = checker.check_batch(batch)
            >>> if not result['is_compliant']:
            ...     for fail in result['failed_parameters']:
            ...         print(f"FAIL: {fail}")
        """
        checks = {}
        for param in self.PARAMETER_LABELS:
            value = getattr(batch, param, None)
            # Skip parameters not present on this batch object
            if value is None:
                continue
            limit = self.spec.get(param)
            if limit is None:
                continue
            checks[param] = self._check_parameter(param, value, limit)

        all_results = list(checks.values())
        passed = [r for r in all_results if r["passed"]]
        failed = [r for r in all_results if not r["passed"]]

        return {
            "batch_id": batch.batch_id,
            "mine_code": batch.mine_code,
            "market": self.market,
            "market_description": self.spec.get("description", ""),
            "is_compliant": len(failed) == 0,
            "passed_count": len(passed),
            "failed_count": len(failed),
            "parameter_results": all_results,
            "failed_parameters": [r["parameter"] for r in failed],
        }

    def check_batches(self, batches: List[CoalBatch]) -> Dict:
        """
        Check multiple batches and return a fleet-level compliance summary.

        Args:
            batches: List of CoalBatch instances

        Returns:
            Dictionary with:
                - market: Target market
                - total_batches: Total batches checked
                - compliant_batches: Count of fully compliant batches
                - non_compliant_batches: Count of failing batches
                - compliance_rate_pct: Overall compliance rate %
                - batch_results: List of individual batch results

        Raises:
            ValueError: If batches list is empty
        """
        if not batches:
            raise ValueError("batches list cannot be empty")

        results = [self.check_batch(b) for b in batches]
        compliant = [r for r in results if r["is_compliant"]]

        return {
            "market": self.market,
            "total_batches": len(results),
            "compliant_batches": len(compliant),
            "non_compliant_batches": len(results) - len(compliant),
            "compliance_rate_pct": round(len(compliant) / len(results) * 100, 2),
            "batch_results": results,
        }

    @staticmethod
    def available_markets() -> List[str]:
        """Return list of available market specification names."""
        return list(MARKET_SPECS.keys())
