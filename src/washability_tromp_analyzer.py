"""
Washability & Tromp Curve Analyzer
=====================================
Analyses coal float-sink washability data to optimise dense medium separation
(DMS) cut-point density for maximum yield at target product quality.
Implements:

  1. Float-sink washability table parsing and validation
  2. Tromp curve (partition curve) construction — probability of float
     reporting to clean coal vs. relative density (RD)
  3. Ep (Ecart Probable) calculation — measure of DMS efficiency
  4. Organic efficiency determination — actual vs theoretical yield
  5. Cut-point density optimisation for a target ash specification

References:
    - Napier-Munn et al. (1996). Mineral Comminution Circuits: Their
      Operation and Optimisation. JKMRC, Univ of Queensland.
    - Mikhail et al. (1991). Dense-medium cyclone simulations using
      Whiten partition model. Int. J. Miner. Process.
    - AS 4156.1 (1994). Coal Preparation — Float and Sink Testing.
    - ASTM D4371 (2015). Standard Guide for Coal Preparation Laboratory
      Float-Sink Analysis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FloatSinkFraction:
    """A single density fraction from float-sink test."""

    rd_lower: float          # Relative density lower bound (e.g. 1.30)
    rd_upper: float          # Relative density upper bound (e.g. 1.40); use float('inf') for sinks
    mass_pct: float          # Cumulative mass yield (% of feed)
    ash_pct: float           # Ash content of this fraction (%)
    gcv_adb_kcal_kg: Optional[float] = None  # Optional GCV of fraction

    def __post_init__(self) -> None:
        if self.rd_lower < 1.0:
            raise ValueError("rd_lower must be >= 1.0 (water density)")
        if self.mass_pct < 0 or self.mass_pct > 100:
            raise ValueError("mass_pct must be 0–100")
        if self.ash_pct < 0 or self.ash_pct > 80:
            raise ValueError("ash_pct must be 0–80%")

    @property
    def rd_midpoint(self) -> float:
        """Midpoint density of the fraction (uses lower+0.05 for sink)."""
        if math.isinf(self.rd_upper):
            return self.rd_lower + 0.05
        return (self.rd_lower + self.rd_upper) / 2


@dataclass
class TrompPoint:
    """A single point on the Tromp partition curve."""

    rd: float
    partition_number: float   # 0–100: % probability of reporting to float (clean) product


@dataclass
class WashabilityResult:
    """Full washability analysis output."""

    feed_ash_pct: float
    theoretical_yield_at_target_ash: Optional[float]   # % mass
    actual_yield_at_cut_density: Optional[float]        # % mass
    organic_efficiency_pct: Optional[float]              # actual/theoretical × 100
    optimal_cut_density: Optional[float]                 # RD for target ash
    ep_value: Optional[float]                            # Ecart Probable
    tromp_curve: List[TrompPoint]
    cumulative_float_table: List[Dict]                   # rich data table
    product_ash_at_cut: Optional[float]
    reject_ash_at_cut: Optional[float]
    recommendations: List[str]


# ---------------------------------------------------------------------------
# Core analyzer
# ---------------------------------------------------------------------------


class WashabilityTrompAnalyzer:
    """
    Analyses coal float-sink washability data and constructs Tromp curves
    for DMS process optimisation.

    Parameters
    ----------
    fractions : list of FloatSinkFraction
        Density fractions from float-sink analysis (ordered by RD).
    misplacement_factor : float, optional
        DMS misplacement factor — models imperfect partition (default 0.03).
        Higher values indicate more near-gravity material misplaced.

    Examples
    --------
    >>> from src.washability_tromp_analyzer import (
    ...     WashabilityTrompAnalyzer, FloatSinkFraction
    ... )
    >>> fractions = [
    ...     FloatSinkFraction(1.30, 1.35, 18.5, 3.2, 7200),
    ...     FloatSinkFraction(1.35, 1.40, 14.2, 6.1, 7050),
    ...     FloatSinkFraction(1.40, 1.50, 22.8, 12.5, 6800),
    ...     FloatSinkFraction(1.50, 1.60, 18.3, 22.0, 6200),
    ...     FloatSinkFraction(1.60, float('inf'), 26.2, 45.0, 5100),
    ... ]
    >>> analyzer = WashabilityTrompAnalyzer(fractions, target_ash_pct=10.0)
    >>> result = analyzer.analyse()
    >>> print(f"Theoretical yield @ 10% ash: {result.theoretical_yield_at_target_ash:.1f}%")
    """

    def __init__(
        self,
        fractions: List[FloatSinkFraction],
        target_ash_pct: float = 10.0,
        misplacement_factor: float = 0.03,
    ) -> None:
        if not fractions:
            raise ValueError("At least one fraction is required")
        if not (0 < target_ash_pct < 80):
            raise ValueError("target_ash_pct must be 0–80%")
        if not (0 <= misplacement_factor <= 0.5):
            raise ValueError("misplacement_factor must be 0–0.5")
        # Sort by lower RD
        self.fractions = sorted(fractions, key=lambda f: f.rd_lower)
        self.target_ash = target_ash_pct
        self.mpl = misplacement_factor

    # ------------------------------------------------------------------
    # Build cumulative float table
    # ------------------------------------------------------------------

    def _cumulative_table(self) -> List[Dict]:
        """
        Construct cumulative float table: cumulative mass yield, cumulative
        ash, and clean-coal incremental contribution.
        """
        cumulative_mass = 0.0
        cumulative_ash_mass = 0.0
        rows = []

        for frac in self.fractions:
            cumulative_mass += frac.mass_pct
            cumulative_ash_mass += frac.mass_pct * frac.ash_pct

            rows.append(
                {
                    "rd_lower": frac.rd_lower,
                    "rd_upper": frac.rd_upper,
                    "rd_mid": frac.rd_midpoint,
                    "incremental_mass_pct": round(frac.mass_pct, 3),
                    "incremental_ash_pct": round(frac.ash_pct, 3),
                    "cumulative_mass_pct": round(cumulative_mass, 3),
                    "cumulative_ash_pct": round(
                        cumulative_ash_mass / cumulative_mass if cumulative_mass > 0 else 0, 3
                    ),
                }
            )
        return rows

    @property
    def _total_mass(self) -> float:
        return sum(f.mass_pct for f in self.fractions)

    @property
    def _feed_ash(self) -> float:
        total_mass = self._total_mass
        return (
            sum(f.mass_pct * f.ash_pct for f in self.fractions) / total_mass
            if total_mass > 0
            else 0.0
        )

    # ------------------------------------------------------------------
    # Theoretical yield at target ash (interpolation)
    # ------------------------------------------------------------------

    def _theoretical_yield(self, table: List[Dict]) -> Optional[float]:
        """
        Find theoretical yield (% mass float) at which cumulative ash equals
        target_ash via linear interpolation of the washability curve.
        """
        for i in range(len(table) - 1):
            row_a, row_b = table[i], table[i + 1]
            ash_a, ash_b = row_a["cumulative_ash_pct"], row_b["cumulative_ash_pct"]
            if ash_a <= self.target_ash <= ash_b:
                if ash_b == ash_a:
                    return row_a["cumulative_mass_pct"]
                t = (self.target_ash - ash_a) / (ash_b - ash_a)
                return round(
                    row_a["cumulative_mass_pct"]
                    + t * (row_b["cumulative_mass_pct"] - row_a["cumulative_mass_pct"]),
                    2,
                )
        if table and table[-1]["cumulative_ash_pct"] <= self.target_ash:
            return round(table[-1]["cumulative_mass_pct"], 2)
        return None

    # ------------------------------------------------------------------
    # Optimal cut density (interpolation)
    # ------------------------------------------------------------------

    def _optimal_cut_density(self, table: List[Dict]) -> Optional[Tuple[float, float]]:
        """
        Returns (cut_density, product_ash, reject_ash) at theoretical yield.
        """
        theoretical_yield = self._theoretical_yield(table)
        if theoretical_yield is None:
            return None

        total_mass = self._total_mass
        # Walk cumulative mass to find the RD corresponding to theoretical yield
        for i, row in enumerate(table):
            if row["cumulative_mass_pct"] >= theoretical_yield:
                if i == 0:
                    return row["rd_lower"], row["cumulative_ash_pct"], self._feed_ash
                prev = table[i - 1]
                t = (
                    (theoretical_yield - prev["cumulative_mass_pct"])
                    / (row["cumulative_mass_pct"] - prev["cumulative_mass_pct"])
                )
                cut_rd = prev["rd_mid"] + t * (row["rd_mid"] - prev["rd_mid"])
                product_ash = prev["cumulative_ash_pct"] + t * (
                    row["cumulative_ash_pct"] - prev["cumulative_ash_pct"]
                )
                # Reject ash by mass balance
                float_mass = theoretical_yield / 100.0
                sink_mass = 1.0 - float_mass
                feed_ash = self._feed_ash
                if sink_mass > 0:
                    reject_ash = (feed_ash - float_mass * product_ash) / sink_mass
                else:
                    reject_ash = feed_ash
                return round(cut_rd, 3), round(product_ash, 3), round(reject_ash, 3)
        return None

    # ------------------------------------------------------------------
    # Tromp curve construction (Whiten model)
    # ------------------------------------------------------------------

    def _tromp_curve(self, cut_density: float) -> List[TrompPoint]:
        """
        Build Tromp partition curve using the Whiten/Lynch normalised model:
          P(x) = 1 / (1 + exp(α × (x - RD50)))
        where α is calibrated from misplacement_factor (Ep ≈ 0.675 / α).
        """
        if cut_density is None:
            return []

        # α from Ep: Ep ≈ misplacement_factor × cut_density; α = 0.675 / Ep
        ep_est = max(self.mpl * cut_density, 0.01)
        alpha = 0.675 / ep_est

        rds = [f.rd_midpoint for f in self.fractions]
        min_rd, max_rd = min(rds), max(rds)

        # Sample curve from min_rd − 0.2 to max_rd + 0.2
        points = []
        rd = min_rd - 0.2
        while rd <= max_rd + 0.2:
            p = 1.0 / (1.0 + math.exp(alpha * (rd - cut_density)))
            points.append(TrompPoint(rd=round(rd, 3), partition_number=round(p * 100, 2)))
            rd += 0.05

        return points

    # ------------------------------------------------------------------
    # Ep value
    # ------------------------------------------------------------------

    def _ep(self, tromp: List[TrompPoint]) -> Optional[float]:
        """
        Ecart Probable = (RD75 − RD25) / 2
        where RD25 and RD75 are densities at 25% and 75% partition.
        """
        if not tromp:
            return None
        rd25 = rd75 = None
        for pt in tromp:
            if rd25 is None and pt.partition_number <= 75:
                rd75 = pt.rd
            if rd25 is None and pt.partition_number <= 25:
                rd25 = pt.rd
                break
        # Scan properly
        rd25 = rd75 = None
        for i, pt in enumerate(tromp):
            if pt.partition_number <= 75 and rd75 is None:
                rd75 = pt.rd
            if pt.partition_number <= 25 and rd25 is None:
                rd25 = pt.rd
        if rd25 is not None and rd75 is not None:
            return round((rd25 - rd75) / 2, 4)
        return None

    # ------------------------------------------------------------------
    # Actual yield and organic efficiency
    # ------------------------------------------------------------------

    def _actual_yield(self, cut_density: float) -> float:
        """
        Estimate actual yield using Tromp partition: sum of fraction × partition.
        """
        ep_est = max(self.mpl * cut_density, 0.01)
        alpha = 0.675 / ep_est
        total_yield = 0.0
        total_mass = self._total_mass
        for frac in self.fractions:
            p = 1.0 / (1.0 + math.exp(alpha * (frac.rd_midpoint - cut_density)))
            total_yield += frac.mass_pct * p
        return round(total_yield / total_mass * 100, 2) if total_mass > 0 else 0.0

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _recommendations(
        self,
        ep: Optional[float],
        actual_yield: Optional[float],
        theoretical_yield: Optional[float],
        feed_ash: float,
    ) -> List[str]:
        recs = []
        if ep is not None:
            if ep < 0.02:
                recs.append(
                    f"Excellent DMS efficiency (Ep = {ep:.3f}). "
                    "Maintain current dense medium quality and cyclone pressure."
                )
            elif ep < 0.05:
                recs.append(
                    f"Good DMS efficiency (Ep = {ep:.3f}). "
                    "Minor medium contamination may be improving near-gravity separation."
                )
            else:
                recs.append(
                    f"High Ep ({ep:.3f}) indicates DMS inefficiency. "
                    "Check medium density stability, cyclone apex, and near-gravity material fraction."
                )

        if actual_yield is not None and theoretical_yield is not None:
            org_eff = actual_yield / theoretical_yield * 100 if theoretical_yield > 0 else 0
            if org_eff < 95:
                recs.append(
                    f"Organic efficiency {org_eff:.1f}% < 95%. "
                    "Investigate misplacement; consider medium viscosity adjustment."
                )
            else:
                recs.append(f"Organic efficiency {org_eff:.1f}% — acceptable plant performance.")

        if feed_ash > 30:
            recs.append(
                "High feed ash (>30%) — raw coal quality is marginal. "
                "Evaluate ROM blend optimisation to reduce feed variability."
            )
        return recs

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self) -> WashabilityResult:
        """
        Run the full washability and Tromp analysis.

        Returns
        -------
        WashabilityResult
            Comprehensive analysis including theoretical yield, Ep,
            Tromp curve, organic efficiency, and recommendations.
        """
        cum_table = self._cumulative_table()
        feed_ash = self._feed_ash
        theoretical_yield = self._theoretical_yield(cum_table)

        cut_result = self._optimal_cut_density(cum_table)
        if cut_result is not None:
            if len(cut_result) == 3:
                cut_density, product_ash, reject_ash = cut_result
            else:
                cut_density, product_ash, reject_ash = cut_result[0], None, None
        else:
            cut_density = product_ash = reject_ash = None

        tromp = self._tromp_curve(cut_density)
        ep = self._ep(tromp)
        actual_yield = self._actual_yield(cut_density) if cut_density else None
        organic_eff = (
            (actual_yield / theoretical_yield * 100)
            if (actual_yield and theoretical_yield)
            else None
        )

        recs = self._recommendations(ep, actual_yield, theoretical_yield, feed_ash)

        return WashabilityResult(
            feed_ash_pct=round(feed_ash, 3),
            theoretical_yield_at_target_ash=theoretical_yield,
            actual_yield_at_cut_density=actual_yield,
            organic_efficiency_pct=round(organic_eff, 2) if organic_eff is not None else None,
            optimal_cut_density=cut_density,
            ep_value=ep,
            tromp_curve=tromp,
            cumulative_float_table=cum_table,
            product_ash_at_cut=product_ash,
            reject_ash_at_cut=reject_ash,
            recommendations=recs,
        )
