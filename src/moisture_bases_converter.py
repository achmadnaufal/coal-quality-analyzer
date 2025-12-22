"""
Coal Quality Moisture Bases Converter.

Converts proximate analysis parameters between the four standard coal
reporting bases:
  - AR  (As-Received):    includes total moisture, reflects actual delivered state
  - AD  (Air-Dried):      equilibrated at lab conditions (~60% RH, 25°C)
  - DB  (Dry Basis):      moisture-free (hypothetical; used for ash, sulfur)
  - DAF (Dry-Ash-Free):   moisture and ash free (used for VM, FC, organic content)

Accurate basis conversion is critical for:
- Comparing quality from different sampling campaigns
- Calculating calorific value in different contract bases (ARB vs GAD)
- Ensuring ISO 17246 / ASTM D3180 compliance for export certificates

Methodology references:
- ISO 17246:2010 Coal — Proximate Analysis
- ASTM D3180 Standard Practice for Calculating Coal and Coke Analyses
- ISO 1928:2009 Solid mineral fuels — Determination of gross calorific value
- AS 4264.1 Coal and coke — Sampling

Author: github.com/achmadnaufal
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProximateAnalysis:
    """Full proximate analysis on a single reporting basis.

    Attributes:
        basis: Reporting basis code: 'AR', 'AD', 'DB', or 'DAF'.
        total_moisture_pct: Total moisture (% mass). Relevant only for AR.
        inherent_moisture_pct: Inherent (equilibrium) moisture (%). Relevant for AD.
        ash_pct: Ash content (%).
        volatile_matter_pct: Volatile matter (%).
        fixed_carbon_pct: Fixed carbon (%). Calculated as 100 - IM - ash - VM.
        total_sulfur_pct: Total sulfur (%).
        gcv_kcal_kg: Gross calorific value (kcal/kg). Optional.
    """

    basis: str
    total_moisture_pct: Optional[float] = None
    inherent_moisture_pct: Optional[float] = None
    ash_pct: Optional[float] = None
    volatile_matter_pct: Optional[float] = None
    fixed_carbon_pct: Optional[float] = None
    total_sulfur_pct: Optional[float] = None
    gcv_kcal_kg: Optional[float] = None

    def __post_init__(self) -> None:
        valid_bases = {"AR", "AD", "DB", "DAF"}
        if self.basis.upper() not in valid_bases:
            raise ValueError(
                f"Invalid basis '{self.basis}'. Expected one of: {valid_bases}"
            )
        self.basis = self.basis.upper()


_VALID_BASES = {"AR", "AD", "DB", "DAF"}


class MoistureBasesConverter:
    """Converts coal proximate analysis parameters between ISO/ASTM reporting bases.

    Supports four standard bases:
    - **AR** (As-Received): Includes all surface + inherent moisture.
    - **AD** (Air-Dried): Lab-equilibrated at ~60% RH / 25°C.
    - **DB** (Dry Basis): Theoretically moisture-free.
    - **DAF** (Dry-Ash-Free): Moisture- and ash-free, organic fraction only.

    The conversion factors are derived from the moisture content differentials
    between bases:

    .. code-block::

        Factor AR→AD = (100 - IM_AD) / (100 - TM_AR)
        Factor AR→DB = (100 - 0)     / (100 - TM_AR)   # i.e. 100 / (100-TM)
        Factor AR→DAF = 100 / (100 - TM_AR - Ash_AR)
        Factor AD→DB = 100 / (100 - IM_AD)

    Args:
        None

    Example::

        converter = MoistureBasesConverter()

        # Convert AR analysis to AD, DB, DAF
        result = converter.convert(
            parameter="ash_pct",
            value=8.5,
            from_basis="AR",
            to_basis="DB",
            total_moisture_ar=28.0,
            inherent_moisture_ad=12.0,
        )
        print(f"Ash (DB): {result:.2f}%")

        # Convert full proximate analysis
        ar_analysis = ProximateAnalysis(
            basis="AR",
            total_moisture_pct=28.0,
            inherent_moisture_pct=12.0,
            ash_pct=6.5,
            volatile_matter_pct=39.2,
            fixed_carbon_pct=24.3,
            total_sulfur_pct=0.38,
            gcv_kcal_kg=4800,
        )
        ad_analysis = converter.convert_full_analysis(ar_analysis, to_basis="AD")
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(
        self,
        parameter: str,
        value: float,
        from_basis: str,
        to_basis: str,
        total_moisture_ar: Optional[float] = None,
        inherent_moisture_ad: Optional[float] = None,
        ash_ar_pct: Optional[float] = None,
    ) -> float:
        """Convert a single quality parameter between two reporting bases.

        Args:
            parameter: Name of the parameter being converted (for error messages;
                does not affect calculation). E.g. 'ash_pct', 'volatile_matter_pct'.
            value: Value of the parameter on the source basis.
            from_basis: Source reporting basis ('AR', 'AD', 'DB', 'DAF').
            to_basis: Target reporting basis ('AR', 'AD', 'DB', 'DAF').
            total_moisture_ar: Total moisture on AR basis (%). Required for
                conversions involving AR.
            inherent_moisture_ad: Inherent moisture on AD basis (%). Required
                for conversions involving AD or DB.
            ash_ar_pct: Ash content on AR basis (%). Required for DAF conversions.

        Returns:
            Converted parameter value on the target basis.

        Raises:
            ValueError: If an unsupported basis pair is specified or if required
                moisture/ash inputs are missing.

        Example::

            converter = MoistureBasesConverter()
            ash_db = converter.convert(
                parameter="ash_pct",
                value=6.5,
                from_basis="AR",
                to_basis="DB",
                total_moisture_ar=28.0,
            )
        """
        from_upper = from_basis.upper()
        to_upper = to_basis.upper()

        self._validate_basis(from_upper)
        self._validate_basis(to_upper)

        if from_upper == to_upper:
            return value

        factor = self._conversion_factor(
            from_basis=from_upper,
            to_basis=to_upper,
            total_moisture_ar=total_moisture_ar,
            inherent_moisture_ad=inherent_moisture_ad,
            ash_ar_pct=ash_ar_pct,
        )

        return round(value * factor, 4)

    def convert_full_analysis(
        self,
        analysis: ProximateAnalysis,
        to_basis: str,
    ) -> ProximateAnalysis:
        """Convert a complete proximate analysis to a target basis.

        Moisture values are handled separately: total_moisture only applies on AR;
        inherent_moisture only on AD. GCV is converted if provided.

        Args:
            analysis: ProximateAnalysis object on the source basis.
            to_basis: Target basis code: 'AR', 'AD', 'DB', or 'DAF'.

        Returns:
            New ProximateAnalysis on the target basis. Moisture attributes not
            relevant for the target basis will be None.

        Raises:
            ValueError: If required moisture inputs are missing in the source
                analysis, or if the basis conversion is not supported.

        Example::

            ar = ProximateAnalysis(
                basis="AR",
                total_moisture_pct=28.0,
                inherent_moisture_pct=12.0,
                ash_pct=6.5,
                volatile_matter_pct=39.2,
                fixed_carbon_pct=24.3,
                total_sulfur_pct=0.38,
                gcv_kcal_kg=4800,
            )
            db = converter.convert_full_analysis(ar, "DB")
        """
        from_upper = analysis.basis.upper()
        to_upper = to_basis.upper()

        # Extract moisture values from analysis for the conversion factor
        tm_ar = analysis.total_moisture_pct
        im_ad = analysis.inherent_moisture_pct
        ash_ar = analysis.ash_pct if from_upper == "AR" else None

        def conv(val: Optional[float]) -> Optional[float]:
            if val is None:
                return None
            return self.convert(
                parameter="generic",
                value=val,
                from_basis=from_upper,
                to_basis=to_upper,
                total_moisture_ar=tm_ar,
                inherent_moisture_ad=im_ad,
                ash_ar_pct=ash_ar,
            )

        # Determine moisture fields for target basis
        result_tm = tm_ar if to_upper == "AR" else None
        result_im = im_ad if to_upper == "AD" else None

        result_ash = conv(analysis.ash_pct)
        result_vm = conv(analysis.volatile_matter_pct)
        result_fc = conv(analysis.fixed_carbon_pct)
        result_s = conv(analysis.total_sulfur_pct)
        result_gcv = conv(analysis.gcv_kcal_kg)

        return ProximateAnalysis(
            basis=to_upper,
            total_moisture_pct=result_tm,
            inherent_moisture_pct=result_im,
            ash_pct=result_ash,
            volatile_matter_pct=result_vm,
            fixed_carbon_pct=result_fc,
            total_sulfur_pct=result_s,
            gcv_kcal_kg=result_gcv,
        )

    def gcv_gar_to_gad(
        self,
        gcv_gar: float,
        total_moisture_ar: float,
        inherent_moisture_ad: float,
    ) -> float:
        """Convert Gross Calorific Value from AR (GAR) to Air-Dried (GAD) basis.

        Convenience wrapper aligned with ISO 1928 terminology used in
        Indonesian coal export contracts.

        Args:
            gcv_gar: Gross Calorific Value on As-Received basis (kcal/kg).
            total_moisture_ar: Total moisture on AR basis (%).
            inherent_moisture_ad: Inherent moisture on AD basis (%).

        Returns:
            GCV on Air-Dried (GAD) basis (kcal/kg).
        """
        return self.convert(
            parameter="gcv_kcal_kg",
            value=gcv_gar,
            from_basis="AR",
            to_basis="AD",
            total_moisture_ar=total_moisture_ar,
            inherent_moisture_ad=inherent_moisture_ad,
        )

    def batch_convert(
        self,
        rows: List[Dict],
        parameter: str,
        from_basis: str,
        to_basis: str,
    ) -> List[Dict]:
        """Convert a parameter across multiple rows (e.g., a DataFrame-like list).

        Each row dict must include ``value``, ``total_moisture_ar`` (if needed),
        ``inherent_moisture_ad`` (if needed), and optionally ``ash_ar_pct``.

        Args:
            rows: List of dicts with conversion inputs.
            parameter: Parameter name (for error labelling).
            from_basis: Source basis.
            to_basis: Target basis.

        Returns:
            Same list of dicts, each with an added key ``converted_value``.
        """
        result = []
        for i, row in enumerate(rows):
            val = row.get("value")
            if val is None:
                raise ValueError(f"Row {i} missing 'value' key.")
            converted = self.convert(
                parameter=parameter,
                value=val,
                from_basis=from_basis,
                to_basis=to_basis,
                total_moisture_ar=row.get("total_moisture_ar"),
                inherent_moisture_ad=row.get("inherent_moisture_ad"),
                ash_ar_pct=row.get("ash_ar_pct"),
            )
            result.append({**row, "converted_value": converted})
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_basis(basis: str) -> None:
        if basis not in _VALID_BASES:
            raise ValueError(
                f"Unknown basis '{basis}'. Expected one of: {_VALID_BASES}"
            )

    @staticmethod
    def _require(value: Optional[float], name: str) -> float:
        if value is None:
            raise ValueError(
                f"'{name}' is required for this basis conversion but was not provided."
            )
        if not (0.0 <= value <= 100.0):
            raise ValueError(f"'{name}' must be in [0, 100], got {value}.")
        return value

    def _conversion_factor(
        self,
        from_basis: str,
        to_basis: str,
        total_moisture_ar: Optional[float],
        inherent_moisture_ad: Optional[float],
        ash_ar_pct: Optional[float],
    ) -> float:
        """Return the multiplicative conversion factor for the basis pair."""

        # Build a conversion via intermediate DB representation
        # All factors expressed relative to the "dry basis denominator" concept.

        pair = (from_basis, to_basis)

        if pair == ("AR", "AD"):
            tm = self._require(total_moisture_ar, "total_moisture_ar")
            im = self._require(inherent_moisture_ad, "inherent_moisture_ad")
            return (100 - im) / (100 - tm)

        if pair == ("AR", "DB"):
            tm = self._require(total_moisture_ar, "total_moisture_ar")
            return 100.0 / (100 - tm)

        if pair == ("AR", "DAF"):
            tm = self._require(total_moisture_ar, "total_moisture_ar")
            ash = self._require(ash_ar_pct, "ash_ar_pct")
            denom = 100 - tm - ash
            if denom <= 0:
                raise ValueError(
                    "Sum of total_moisture_ar and ash_ar_pct must be < 100 for DAF conversion."
                )
            return 100.0 / denom

        if pair == ("AD", "AR"):
            tm = self._require(total_moisture_ar, "total_moisture_ar")
            im = self._require(inherent_moisture_ad, "inherent_moisture_ad")
            return (100 - tm) / (100 - im)

        if pair == ("AD", "DB"):
            im = self._require(inherent_moisture_ad, "inherent_moisture_ad")
            return 100.0 / (100 - im)

        if pair == ("AD", "DAF"):
            im = self._require(inherent_moisture_ad, "inherent_moisture_ad")
            # Need ash on AD basis — compute from AR if available
            # If ash_ar_pct provided, convert first to AD
            # Otherwise, expect caller to pass ash correctly
            if ash_ar_pct is not None and total_moisture_ar is not None:
                ar_to_ad = (100 - im) / (100 - total_moisture_ar)
                ash_ad = ash_ar_pct * ar_to_ad
            else:
                raise ValueError(
                    "AD→DAF conversion requires either (total_moisture_ar + ash_ar_pct) "
                    "to derive ash_ad. Provide these or pass ash_ar_pct as ash on AD basis."
                )
            denom = 100 - im - ash_ad
            if denom <= 0:
                raise ValueError("IM + Ash_AD sum must be < 100 for DAF conversion.")
            return 100.0 / denom

        if pair == ("DB", "AR"):
            tm = self._require(total_moisture_ar, "total_moisture_ar")
            return (100 - tm) / 100.0

        if pair == ("DB", "AD"):
            im = self._require(inherent_moisture_ad, "inherent_moisture_ad")
            return (100 - im) / 100.0

        if pair == ("DB", "DAF"):
            ash = self._require(ash_ar_pct, "ash_ar_pct")  # treat as ash_db
            denom = 100 - ash
            if denom <= 0:
                raise ValueError("Ash on DB basis must be < 100 for DAF conversion.")
            return 100.0 / denom

        if pair == ("DAF", "AR"):
            tm = self._require(total_moisture_ar, "total_moisture_ar")
            ash = self._require(ash_ar_pct, "ash_ar_pct")
            return (100 - tm - ash) / 100.0

        if pair == ("DAF", "AD"):
            im = self._require(inherent_moisture_ad, "inherent_moisture_ad")
            if ash_ar_pct is not None and total_moisture_ar is not None:
                ar_to_ad = (100 - im) / (100 - total_moisture_ar)
                ash_ad = ash_ar_pct * ar_to_ad
            else:
                raise ValueError(
                    "DAF→AD conversion requires total_moisture_ar + ash_ar_pct."
                )
            return (100 - im - ash_ad) / 100.0

        if pair == ("DAF", "DB"):
            ash = self._require(ash_ar_pct, "ash_ar_pct")  # treat as ash_db
            return (100 - ash) / 100.0

        raise ValueError(
            f"Unsupported basis conversion: {from_basis} → {to_basis}. "
            f"Supported bases: {_VALID_BASES}"
        )
