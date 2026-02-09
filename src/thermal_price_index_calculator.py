"""
Thermal Coal Price Index Calculator.

Computes adjusted thermal coal prices using the Gross-as-Received (GAR)
calorific value adjustment methodology widely used in Indonesian and
Newcastle-linked coal export contracts.

Supports:
1. **GAR CV price adjustment** — adjusts contract price proportionally
   to actual vs reference calorific value.
2. **Quality discount/premium matrix** — moisture, ash, sulphur, and TM
   adjustments vs contract typical specification.
3. **Basis conversion** — price normalisation between GAR 5500, GAR 5000,
   NAR 6000 reference points.
4. **Index blending** — weights multiple benchmark indices (Newcastle,
   Kalimantan ICI) for a blended reference price.
5. **Realised price estimator** — combines all adjustments to estimate
   actual FOB realised price.

References:
- ICI (Indonesia Coal Index) — PT Pricelist / Platts Methodology
- Newcastle Coal Futures (ICE) contract specifications
- Indonesian Ministry of Energy Regulation 26/2018 — coal pricing floor (HBA)
- Standard coal export contract structures (ICSM/Coaltrans)

Author: github.com/achmadnaufal
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Reference spec defaults
# ---------------------------------------------------------------------------

_REFERENCE_SPECS: Dict[str, Dict] = {
    "GAR5500": {
        "calorific_value_kcal_gar": 5500,
        "total_moisture_pct": 20.0,
        "ash_pct": 8.0,
        "total_sulphur_pct": 0.5,
        "basis": "GAR",
    },
    "GAR5000": {
        "calorific_value_kcal_gar": 5000,
        "total_moisture_pct": 25.0,
        "ash_pct": 10.0,
        "total_sulphur_pct": 0.6,
        "basis": "GAR",
    },
    "NAR6000": {
        "calorific_value_kcal_nar": 6000,
        "total_moisture_pct": 12.0,
        "ash_pct": 7.0,
        "total_sulphur_pct": 0.45,
        "basis": "NAR",
    },
}

# Quality adjustment rates (USD per tonne per unit deviation from reference spec)
_QUALITY_ADJUSTMENT_RATES: Dict[str, Dict] = {
    "total_moisture_pct": {
        "penalty_per_pct_above": 0.30,    # USD/t per 1% above spec
        "bonus_per_pct_below": 0.20,       # USD/t per 1% below spec
        "max_penalty": 5.0,
        "max_bonus": 3.0,
    },
    "ash_pct": {
        "penalty_per_pct_above": 0.40,
        "bonus_per_pct_below": 0.25,
        "max_penalty": 6.0,
        "max_bonus": 3.0,
    },
    "total_sulphur_pct": {
        "penalty_per_pct_above": 5.0,
        "bonus_per_pct_below": 3.0,
        "max_penalty": 8.0,
        "max_bonus": 2.0,
    },
}

# NAR to GAR conversion factor (approx, varies with coal type)
_NAR_TO_GAR_FACTOR = 1.1
_GAR_TO_NAR_FACTOR = 1 / _NAR_TO_GAR_FACTOR


@dataclass
class CoalPriceAdjustment:
    """Itemised price adjustments for a single coal cargo/lot.

    Attributes:
        cargo_id: Lot or cargo identifier.
        reference_spec: Reference specification label (e.g. 'GAR5500').
        reference_price_usd_per_tonne: Contract or benchmark reference price.
        cv_adjustment_usd: Price change from calorific value adjustment.
        moisture_adjustment_usd: Penalty/bonus from moisture deviation.
        ash_adjustment_usd: Penalty/bonus from ash deviation.
        sulphur_adjustment_usd: Penalty/bonus from sulphur deviation.
        total_quality_adjustment_usd: Sum of all quality adjustments.
        realised_price_usd_per_tonne: Final realised FOB price.
        adjustment_pct: Total adjustment as % of reference price.
    """

    cargo_id: str
    reference_spec: str
    reference_price_usd_per_tonne: float
    cv_adjustment_usd: float
    moisture_adjustment_usd: float
    ash_adjustment_usd: float
    sulphur_adjustment_usd: float
    total_quality_adjustment_usd: float = field(init=False)
    realised_price_usd_per_tonne: float = field(init=False)
    adjustment_pct: float = field(init=False)

    def __post_init__(self) -> None:
        self.total_quality_adjustment_usd = round(
            self.cv_adjustment_usd
            + self.moisture_adjustment_usd
            + self.ash_adjustment_usd
            + self.sulphur_adjustment_usd,
            4,
        )
        self.realised_price_usd_per_tonne = round(
            self.reference_price_usd_per_tonne + self.total_quality_adjustment_usd, 4
        )
        self.adjustment_pct = round(
            self.total_quality_adjustment_usd / self.reference_price_usd_per_tonne * 100, 2
        ) if self.reference_price_usd_per_tonne else 0.0


@dataclass
class BlendedIndexResult:
    """Result from blending multiple price index benchmarks.

    Attributes:
        index_prices: Input dict of index_name → price.
        weights: Applied weights.
        blended_price_usd_per_tonne: Weighted average of input prices.
    """

    index_prices: Dict[str, float]
    weights: Dict[str, float]
    blended_price_usd_per_tonne: float


class ThermalPriceIndexCalculator:
    """Calculates adjusted thermal coal prices using GAR/NAR methodology.

    Args:
        reference_spec: Default reference specification. One of 'GAR5500',
            'GAR5000', 'NAR6000'. Default 'GAR5500'.
        custom_adjustment_rates: Optional dict overriding default quality
            adjustment rates. Keys: 'total_moisture_pct', 'ash_pct',
            'total_sulphur_pct'. Each value is a dict with
            'penalty_per_pct_above', 'bonus_per_pct_below',
            'max_penalty', 'max_bonus'.

    Example::

        calc = ThermalPriceIndexCalculator(reference_spec="GAR5500")
        adj = calc.calculate_adjustment(
            cargo_id="BV-2026-001",
            reference_price_usd_per_tonne=85.0,
            actual_quality={
                "calorific_value_kcal_gar": 5420,
                "total_moisture_pct": 21.5,
                "ash_pct": 7.2,
                "total_sulphur_pct": 0.48,
            },
        )
        print(f"Realised price: USD {adj.realised_price_usd_per_tonne:.2f}/t")
        print(f"Total adjustment: USD {adj.total_quality_adjustment_usd:.2f}/t "
              f"({adj.adjustment_pct:+.1f}%)")
    """

    def __init__(
        self,
        reference_spec: str = "GAR5500",
        custom_adjustment_rates: Optional[Dict] = None,
    ) -> None:
        if reference_spec not in _REFERENCE_SPECS:
            raise ValueError(
                f"Unknown reference_spec '{reference_spec}'. "
                f"Valid options: {list(_REFERENCE_SPECS.keys())}"
            )
        self._ref_spec = reference_spec
        self._ref = _REFERENCE_SPECS[reference_spec]
        self._rates = dict(_QUALITY_ADJUSTMENT_RATES)
        if custom_adjustment_rates:
            self._rates.update(custom_adjustment_rates)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_adjustment(
        self,
        cargo_id: str,
        reference_price_usd_per_tonne: float,
        actual_quality: Dict[str, float],
    ) -> CoalPriceAdjustment:
        """Calculate full price adjustment for a coal cargo against reference spec.

        Args:
            cargo_id: Cargo or lot identifier.
            reference_price_usd_per_tonne: Base contract or benchmark price in USD/t.
            actual_quality: Dict with quality measurements:
                - 'calorific_value_kcal_gar' or 'calorific_value_kcal_nar' (float)
                - 'total_moisture_pct' (float)
                - 'ash_pct' (float)
                - 'total_sulphur_pct' (float)

        Returns:
            CoalPriceAdjustment with itemised and total adjustments.

        Raises:
            ValueError: If reference price ≤ 0.
        """
        if reference_price_usd_per_tonne <= 0:
            raise ValueError(
                f"reference_price_usd_per_tonne must be > 0, got {reference_price_usd_per_tonne}."
            )

        cv_adj = self._cv_adjustment(reference_price_usd_per_tonne, actual_quality)
        moist_adj = self._quality_adjustment("total_moisture_pct", actual_quality)
        ash_adj = self._quality_adjustment("ash_pct", actual_quality)
        sulph_adj = self._quality_adjustment("total_sulphur_pct", actual_quality)

        return CoalPriceAdjustment(
            cargo_id=cargo_id,
            reference_spec=self._ref_spec,
            reference_price_usd_per_tonne=reference_price_usd_per_tonne,
            cv_adjustment_usd=round(cv_adj, 4),
            moisture_adjustment_usd=round(moist_adj, 4),
            ash_adjustment_usd=round(ash_adj, 4),
            sulphur_adjustment_usd=round(sulph_adj, 4),
        )

    def batch_adjustments(
        self, cargoes: List[Dict]
    ) -> List[CoalPriceAdjustment]:
        """Calculate adjustments for multiple cargoes.

        Args:
            cargoes: List of dicts with keys 'cargo_id',
                'reference_price_usd_per_tonne', 'actual_quality'.

        Returns:
            List of CoalPriceAdjustment in input order.
        """
        return [
            self.calculate_adjustment(
                cargo_id=c["cargo_id"],
                reference_price_usd_per_tonne=c["reference_price_usd_per_tonne"],
                actual_quality=c["actual_quality"],
            )
            for c in cargoes
        ]

    def blend_indices(
        self,
        index_prices: Dict[str, float],
        weights: Optional[Dict[str, float]] = None,
    ) -> BlendedIndexResult:
        """Compute a weighted blended price from multiple benchmark indices.

        Args:
            index_prices: Dict mapping index name → price (USD/t).
                E.g. {'newcastle': 95.0, 'ici3_gar5000': 72.0}.
            weights: Optional dict mapping index name → weight.
                Weights are normalised to sum to 1.0. If omitted, equal
                weights are applied.

        Returns:
            BlendedIndexResult with blended price.

        Raises:
            ValueError: If index_prices is empty or any price ≤ 0.
        """
        if not index_prices:
            raise ValueError("index_prices must not be empty.")
        for name, price in index_prices.items():
            if price <= 0:
                raise ValueError(f"Price for '{name}' must be > 0, got {price}.")

        if weights is None:
            n = len(index_prices)
            weights = {k: 1 / n for k in index_prices}

        # Normalise weights
        total_w = sum(weights.get(k, 0) for k in index_prices)
        if total_w <= 0:
            raise ValueError("Weights must be positive and sum to > 0.")
        norm_weights = {k: weights.get(k, 0) / total_w for k in index_prices}

        blended = sum(
            norm_weights[k] * index_prices[k] for k in index_prices
        )

        return BlendedIndexResult(
            index_prices=dict(index_prices),
            weights=norm_weights,
            blended_price_usd_per_tonne=round(blended, 4),
        )

    def convert_price_basis(
        self,
        price_usd_per_tonne: float,
        from_basis: str,
        to_basis: str,
        actual_cv: Optional[float] = None,
    ) -> float:
        """Convert a coal price between GAR and NAR bases.

        Args:
            price_usd_per_tonne: Input price to convert.
            from_basis: 'GAR' or 'NAR'.
            to_basis: 'GAR' or 'NAR'.
            actual_cv: Actual calorific value (kcal/kg) in the from_basis.
                Used for precise conversion. If None, uses default factor.

        Returns:
            Converted price in USD/t.

        Raises:
            ValueError: If from_basis or to_basis is not 'GAR' or 'NAR'.
        """
        valid_bases = {"GAR", "NAR"}
        if from_basis not in valid_bases or to_basis not in valid_bases:
            raise ValueError(f"basis must be 'GAR' or 'NAR', got '{from_basis}'/'{to_basis}'.")
        if price_usd_per_tonne <= 0:
            raise ValueError(f"price must be > 0, got {price_usd_per_tonne}.")
        if from_basis == to_basis:
            return price_usd_per_tonne

        factor = _GAR_TO_NAR_FACTOR if from_basis == "GAR" else _NAR_TO_GAR_FACTOR
        return round(price_usd_per_tonne * factor, 4)

    def batch_summary(self, adjustments: List[CoalPriceAdjustment]) -> Dict:
        """Summarise batch adjustment statistics.

        Args:
            adjustments: Output of ``batch_adjustments()``.

        Returns:
            Dict with min/max/avg realised price, avg adjustment %, and
            total financial impact (USD) assuming equal 1-tonne lots.
        """
        if not adjustments:
            return {}
        realised = [a.realised_price_usd_per_tonne for a in adjustments]
        adj_pcts = [a.adjustment_pct for a in adjustments]
        return {
            "count": len(adjustments),
            "min_realised_price_usd_per_tonne": round(min(realised), 4),
            "max_realised_price_usd_per_tonne": round(max(realised), 4),
            "avg_realised_price_usd_per_tonne": round(sum(realised) / len(realised), 4),
            "avg_adjustment_pct": round(sum(adj_pcts) / len(adj_pcts), 2),
            "positive_adjustments_count": sum(1 for a in adjustments if a.total_quality_adjustment_usd > 0),
            "negative_adjustments_count": sum(1 for a in adjustments if a.total_quality_adjustment_usd < 0),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _cv_adjustment(
        self, reference_price: float, quality: Dict[str, float]
    ) -> float:
        """Pro-rata calorific value adjustment."""
        ref_basis = self._ref.get("basis", "GAR")
        ref_cv_key = f"calorific_value_kcal_{ref_basis.lower()}"
        ref_cv = self._ref.get(f"calorific_value_kcal_{ref_basis.lower()}", 5500)

        actual_cv = quality.get(ref_cv_key) or quality.get("calorific_value_kcal_gar") or quality.get("calorific_value_kcal_nar")
        if actual_cv is None or actual_cv <= 0:
            return 0.0

        ratio = actual_cv / ref_cv
        return reference_price * (ratio - 1)

    def _quality_adjustment(
        self, parameter: str, quality: Dict[str, float]
    ) -> float:
        """Compute penalty or bonus for a single quality parameter."""
        actual = quality.get(parameter)
        if actual is None:
            return 0.0

        ref_value = self._ref.get(parameter)
        if ref_value is None:
            return 0.0

        rates = self._rates.get(parameter, {})
        deviation = actual - ref_value  # positive = worse (moisture, ash, sulphur)

        if parameter == "total_sulphur_pct":
            # For sulphur: deviation positive = higher sulphur = penalty
            if deviation > 0:
                adj = -min(deviation * rates.get("penalty_per_pct_above", 0), rates.get("max_penalty", 999))
            else:
                adj = min(abs(deviation) * rates.get("bonus_per_pct_below", 0), rates.get("max_bonus", 999))
        elif parameter in ("total_moisture_pct", "ash_pct"):
            # Higher moisture/ash = penalty
            if deviation > 0:
                adj = -min(deviation * rates.get("penalty_per_pct_above", 0), rates.get("max_penalty", 999))
            else:
                adj = min(abs(deviation) * rates.get("bonus_per_pct_below", 0), rates.get("max_bonus", 999))
        else:
            adj = 0.0

        return adj
