"""
Wash Plant Yield Calculator for Coal Processing Operations.

A coal wash plant (or preparation plant / coal prep plant) uses dense medium
separation (DMS), jigs, and spirals to separate coal from rock and ash-forming
minerals. The output is:

  - Clean coal (product): higher CV, lower ash, saleable product
  - Middlings: intermediate density material, sometimes re-processed
  - Discard (reject): waste rock/shale, sent to refuse dump

This module calculates mass balance, product yield, and quality upgrade across
wash plant circuits. Inputs are raw feed characteristics; outputs are predicted
product quality and yield at various specific gravities (SGs).

References:
    - Wills' Mineral Processing Technology (8th ed.)
    - ASTM D5142 / ISO 1171 (proximate analysis)
    - Tromp Curve methodology for dense medium separation efficiency

Author: github.com/achmadnaufal
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Default efficiency curves for separation types
# ---------------------------------------------------------------------------

# Probable Error (Ep) values by separator type — lower = sharper separation
SEPARATOR_EP: Dict[str, float] = {
    "dense_medium_cyclone": 0.020,   # DMC — very sharp
    "dense_medium_bath": 0.050,      # DM Bath — sharp
    "jig": 0.100,                    # Jig — moderate
    "spiral": 0.160,                 # Spiral — relatively imprecise
    "reflux_classifier": 0.080,      # RC — good for fine coal
}


@dataclass
class WashabilityFraction:
    """
    Represents a density fraction in a float-sink washability test.

    Attributes:
        sg_float: Float SG for this fraction (upper bound).
        mass_pct: Mass percentage of raw feed in this fraction.
        ash_pct: Ash content of this fraction (% air-dry basis).
        cv_mj_kg: Calorific value of this fraction (MJ/kg, GAR basis).
    """

    sg_float: float
    mass_pct: float
    ash_pct: float
    cv_mj_kg: float

    def __post_init__(self) -> None:
        if self.sg_float <= 1.0:
            raise ValueError("sg_float must be > 1.0 (cannot be lighter than water)")
        if not (0 <= self.mass_pct <= 100):
            raise ValueError("mass_pct must be between 0 and 100")
        if not (0 <= self.ash_pct <= 100):
            raise ValueError("ash_pct must be between 0 and 100")
        if self.cv_mj_kg < 0:
            raise ValueError("cv_mj_kg cannot be negative")


class WashPlantYieldCalculator:
    """
    Calculates wash plant product yield and quality from float-sink data.

    Uses the washability curve (float-sink analysis) to predict:
    - Yield % at any given separation SG
    - Clean coal ash and CV at any SG
    - Middlings and discard mass fractions
    - Tromp curve-based separation efficiency correction

    Attributes:
        feed_name (str): Name of the raw coal feed.
        feed_tph (float): Feed rate in tonnes per hour.
        fractions (list[WashabilityFraction]): Float-sink fractions.

    Example::

        calc = WashPlantYieldCalculator(feed_name="Pit-A ROM Coal", feed_tph=450.0)
        calc.add_fraction(WashabilityFraction(sg_float=1.30, mass_pct=12.5, ash_pct=4.2, cv_mj_kg=27.8))
        calc.add_fraction(WashabilityFraction(sg_float=1.40, mass_pct=28.0, ash_pct=6.1, cv_mj_kg=26.9))
        calc.add_fraction(WashabilityFraction(sg_float=1.50, mass_pct=18.5, ash_pct=9.8, cv_mj_kg=25.5))
        calc.add_fraction(WashabilityFraction(sg_float=1.70, mass_pct=10.0, ash_pct=18.5, cv_mj_kg=21.0))
        calc.add_fraction(WashabilityFraction(sg_float=2.00, mass_pct=31.0, ash_pct=68.0, cv_mj_kg=6.2))

        result = calc.calculate_yield(cut_sg=1.50, separator="dense_medium_cyclone")
        print(f"Yield: {result['yield_pct']:.1f}%, Clean ash: {result['product_ash_pct']:.1f}%")
    """

    def __init__(self, feed_name: str = "ROM Coal", feed_tph: float = 100.0) -> None:
        """
        Initialize the wash plant calculator.

        Args:
            feed_name: Descriptive name for the raw feed.
            feed_tph: Feed rate in tonnes per hour.

        Raises:
            ValueError: If feed_tph <= 0.
        """
        if feed_tph <= 0:
            raise ValueError("feed_tph must be positive.")
        self.feed_name = feed_name
        self.feed_tph = feed_tph
        self.fractions: List[WashabilityFraction] = []

    # ------------------------------------------------------------------
    # Data management
    # ------------------------------------------------------------------

    def add_fraction(self, fraction: WashabilityFraction) -> None:
        """
        Add a washability fraction to the dataset.

        Args:
            fraction: A :class:`WashabilityFraction` instance.

        Raises:
            ValueError: If a fraction with the same SG already exists.
        """
        if any(abs(f.sg_float - fraction.sg_float) < 0.001 for f in self.fractions):
            raise ValueError(f"Fraction at SG {fraction.sg_float} already exists.")
        self.fractions.append(fraction)
        # Keep sorted by SG
        self.fractions.sort(key=lambda f: f.sg_float)

    def load_fractions(self, fractions: List[WashabilityFraction]) -> None:
        """
        Load multiple fractions at once (replaces existing).

        Args:
            fractions: List of :class:`WashabilityFraction` instances.
        """
        self.fractions = sorted(fractions, key=lambda f: f.sg_float)

    def _validate_loaded(self) -> None:
        if not self.fractions:
            raise RuntimeError("No washability fractions loaded. Call add_fraction() first.")

    # ------------------------------------------------------------------
    # Tromp curve separation efficiency
    # ------------------------------------------------------------------

    def _tromp_partition_coefficient(
        self, sg: float, cut_sg: float, ep: float
    ) -> float:
        """
        Estimate partition coefficient using the Tromp curve (normal distribution).

        The partition coefficient is the probability that a particle of density ``sg``
        will report to the clean coal (float) product.

        Args:
            sg: Particle specific gravity.
            cut_sg: Separation SG (cut point).
            ep: Probable Error for separator type.

        Returns:
            Partition coefficient (0 = full reject, 1 = full product).
        """
        if ep <= 0:
            # Perfect separation
            return 1.0 if sg <= cut_sg else 0.0

        # Standard normal Z
        z = (sg - cut_sg) / (ep * math.sqrt(2))
        # erfc gives the probability particle reports to float product
        return 0.5 * math.erfc(z)

    # ------------------------------------------------------------------
    # Core calculations
    # ------------------------------------------------------------------

    def calculate_yield(
        self,
        cut_sg: float,
        separator: str = "dense_medium_cyclone",
        ep_override: Optional[float] = None,
    ) -> Dict:
        """
        Calculate clean coal yield and quality at a given separation SG.

        Uses Tromp curve efficiency to account for misplaced particles.

        Args:
            cut_sg: Target separation SG. Material floating below this SG → clean coal.
            separator: Separator type (key in :data:`SEPARATOR_EP`) or ``"ideal"``
                for perfect separation.
            ep_override: Override the default Ep value for the separator.

        Returns:
            dict with:

            - ``cut_sg`` – separation SG used
            - ``separator`` – separator type
            - ``ep`` – probable error applied
            - ``yield_pct`` – clean coal yield as % of feed mass
            - ``product_ash_pct`` – weighted-average ash of clean coal
            - ``product_cv_mj_kg`` – weighted-average CV of clean coal
            - ``discard_ash_pct`` – weighted-average ash of discard
            - ``clean_coal_tph`` – product tph at given feed rate
            - ``discard_tph`` – waste/discard tph

        Raises:
            RuntimeError: If no fractions are loaded.
            ValueError: If separator is unknown (and no ep_override provided).
        """
        self._validate_loaded()

        if separator == "ideal":
            ep = 0.0
        elif ep_override is not None:
            ep = ep_override
        elif separator in SEPARATOR_EP:
            ep = SEPARATOR_EP[separator]
        else:
            raise ValueError(
                f"Unknown separator '{separator}'. "
                f"Choose from: {list(SEPARATOR_EP)} or use ep_override."
            )

        product_mass = 0.0
        product_ash_mass = 0.0
        product_cv_weighted = 0.0
        discard_mass = 0.0
        discard_ash_mass = 0.0

        for frac in self.fractions:
            pc = self._tromp_partition_coefficient(frac.sg_float, cut_sg, ep)
            mass = frac.mass_pct  # in % of feed

            product_mass += mass * pc
            product_ash_mass += mass * pc * frac.ash_pct
            product_cv_weighted += mass * pc * frac.cv_mj_kg

            discard_mass += mass * (1 - pc)
            discard_ash_mass += mass * (1 - pc) * frac.ash_pct

        yield_pct = round(product_mass, 2)
        product_ash = round(product_ash_mass / product_mass, 2) if product_mass > 0 else 0.0
        product_cv = round(product_cv_weighted / product_mass, 2) if product_mass > 0 else 0.0
        discard_ash = round(discard_ash_mass / discard_mass, 2) if discard_mass > 0 else 0.0

        return {
            "cut_sg": cut_sg,
            "separator": separator,
            "ep": ep,
            "yield_pct": yield_pct,
            "discard_pct": round(100 - yield_pct, 2),
            "product_ash_pct": product_ash,
            "product_cv_mj_kg": product_cv,
            "discard_ash_pct": discard_ash,
            "clean_coal_tph": round(self.feed_tph * yield_pct / 100, 1),
            "discard_tph": round(self.feed_tph * (100 - yield_pct) / 100, 1),
        }

    def theoretical_yield_at_ash(self, target_ash_pct: float) -> Dict:
        """
        Find the theoretical maximum yield achievable at a target product ash.

        Iterates through SG cut points to find the highest yield that still
        meets the ash specification (ideal/perfect separation assumed).

        Args:
            target_ash_pct: Maximum allowable product ash content (%).

        Returns:
            dict with ``target_ash_pct``, ``best_sg``, ``max_yield_pct``,
            ``actual_ash_pct``, and ``product_cv_mj_kg``.

        Raises:
            RuntimeError: If no fractions are loaded.
        """
        self._validate_loaded()
        sg_candidates = [f.sg_float for f in self.fractions]
        best = {"max_yield_pct": 0.0, "best_sg": None, "actual_ash_pct": 0.0, "product_cv_mj_kg": 0.0}

        for sg in sg_candidates:
            result = self.calculate_yield(sg, separator="ideal")
            if result["product_ash_pct"] <= target_ash_pct and result["yield_pct"] > best["max_yield_pct"]:
                best["max_yield_pct"] = result["yield_pct"]
                best["best_sg"] = sg
                best["actual_ash_pct"] = result["product_ash_pct"]
                best["product_cv_mj_kg"] = result["product_cv_mj_kg"]

        return {
            "target_ash_pct": target_ash_pct,
            **best,
        }

    def yield_curve(
        self, separator: str = "dense_medium_cyclone"
    ) -> List[Dict]:
        """
        Generate a yield-ash curve across all fraction SG cut points.

        Args:
            separator: Separator type for efficiency correction.

        Returns:
            List of result dicts (one per SG cut point), sorted by SG.
        """
        self._validate_loaded()
        return [
            self.calculate_yield(f.sg_float, separator=separator)
            for f in self.fractions
        ]

    def feed_quality_summary(self) -> Dict:
        """
        Compute raw feed quality parameters from washability fractions.

        Returns:
            dict with weighted-average ash, CV, and total mass check.
        """
        self._validate_loaded()
        total_mass = sum(f.mass_pct for f in self.fractions)
        total_ash = sum(f.mass_pct * f.ash_pct for f in self.fractions)
        total_cv = sum(f.mass_pct * f.cv_mj_kg for f in self.fractions)

        return {
            "feed_name": self.feed_name,
            "feed_tph": self.feed_tph,
            "total_mass_pct": round(total_mass, 2),
            "feed_ash_pct": round(total_ash / total_mass, 2) if total_mass > 0 else 0.0,
            "feed_cv_mj_kg": round(total_cv / total_mass, 2) if total_mass > 0 else 0.0,
            "n_fractions": len(self.fractions),
        }

    def __len__(self) -> int:
        return len(self.fractions)

    def __repr__(self) -> str:
        return (
            f"WashPlantYieldCalculator(feed={self.feed_name!r}, "
            f"feed_tph={self.feed_tph}, fractions={len(self.fractions)})"
        )
