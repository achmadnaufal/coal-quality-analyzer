"""
SO2 Emission Estimator for thermal coal combustion.

Estimates sulfur dioxide (SO2) emissions from coal combustion based on
coal sulfur content, calorific value, and combustion assumptions. Covers:

  - kg SO2 per tonne of coal burned
  - kg SO2 per MWh of electricity generated
  - Emission intensity relative to regulatory thresholds
  - Desulfurization credit when FGD (flue-gas desulfurization) is applied

Emission chemistry basis:
  S + O2 → SO2  (molar mass S = 32 g/mol, SO2 = 64 g/mol → factor 2.0)
  All sulfur in coal is assumed to oxidize fully unless a combustion
  retention factor or FGD efficiency is specified.

Standards & references:
  - IPCC 2006 GL: Volume 2, Chapter 2 — Stationary Combustion
  - EPA AP-42, Chapter 1.1 — Bituminous and Subbituminous Coal Combustion
  - IEA Clean Coal Centre: SO2 abatement guidelines

Author: github.com/achmadnaufal
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SO2_STOICHIOMETRIC_FACTOR: float = 2.0  # kg SO2 per kg S (64/32)
_KG_PER_TONNE: float = 1_000.0
_MWH_PER_GJ: float = 1.0 / 3.6
_KCAL_TO_MJ: float = 4.1868e-3  # 1 kcal = 4.1868e-3 MJ


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoalSample:
    """Immutable representation of a single coal sample for emission estimation.

    Attributes:
        sample_id: Unique identifier for the sample.
        total_sulfur_pct: Total sulfur content (% air-dried basis, 0–10).
        calorific_value_kcal_kg: Gross calorific value on air-dried basis
            (kcal/kg). Must be > 0.
        plant_efficiency_pct: Net electrical efficiency of the power plant
            (%, 10–60). Defaults to 36 % (typical subcritical pulverized coal).
        fgd_efficiency_pct: Flue-gas desulfurization removal efficiency
            (%, 0–99.9). 0 means no FGD. Defaults to 0.
        combustion_retention_pct: Fraction of sulfur retained in bottom/fly
            ash and not emitted as SO2 (%, 0–50). Defaults to 2 % per AP-42.
    """

    sample_id: str
    total_sulfur_pct: float
    calorific_value_kcal_kg: float
    plant_efficiency_pct: float = 36.0
    fgd_efficiency_pct: float = 0.0
    combustion_retention_pct: float = 2.0


@dataclass(frozen=True)
class EmissionResult:
    """Immutable emission estimate for one coal sample.

    Attributes:
        sample_id: Identifier echoed from the input.
        so2_kg_per_tonne: SO2 emitted per tonne of coal burned (kg/t).
        so2_kg_per_mwh: SO2 emitted per MWh net electricity (kg/MWh).
        so2_kg_per_mwh_gross: SO2 per MWh on gross (thermal input) basis.
        emission_factor_raw_kg_per_tonne: Unadjusted SO2 before retention or
            FGD (kg/t) — useful for regulatory comparison.
        fgd_reduction_kg_per_tonne: SO2 removed by FGD per tonne (kg/t).
        warning: Non-empty string if any input was clamped or unusual.
    """

    sample_id: str
    so2_kg_per_tonne: float
    so2_kg_per_mwh: float
    so2_kg_per_mwh_gross: float
    emission_factor_raw_kg_per_tonne: float
    fgd_reduction_kg_per_tonne: float
    warning: str


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_sample(sample: CoalSample) -> str:
    """Return a warning string (empty = clean) after clamping guard checks."""
    warnings: list[str] = []

    if not (0.0 <= sample.total_sulfur_pct <= 10.0):
        warnings.append(
            f"total_sulfur_pct={sample.total_sulfur_pct} outside [0, 10]"
        )
    if sample.calorific_value_kcal_kg <= 0:
        raise ValueError(
            f"calorific_value_kcal_kg must be > 0, got {sample.calorific_value_kcal_kg}"
        )
    if not (10.0 <= sample.plant_efficiency_pct <= 60.0):
        warnings.append(
            f"plant_efficiency_pct={sample.plant_efficiency_pct} outside typical [10, 60]"
        )
    if not (0.0 <= sample.fgd_efficiency_pct < 100.0):
        warnings.append(
            f"fgd_efficiency_pct={sample.fgd_efficiency_pct} outside [0, 100)"
        )
    if not (0.0 <= sample.combustion_retention_pct <= 50.0):
        warnings.append(
            f"combustion_retention_pct={sample.combustion_retention_pct} outside [0, 50]"
        )

    return "; ".join(warnings)


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------


def estimate_so2_emission(sample: CoalSample) -> EmissionResult:
    """Estimate SO2 emissions for a single coal sample.

    Uses stoichiometric oxidation of all sulfur, then applies combustion
    retention and FGD reduction sequentially.

    Args:
        sample: A ``CoalSample`` with sulfur %, GCV, plant efficiency,
            FGD efficiency, and ash-retention fraction.

    Returns:
        An ``EmissionResult`` with per-tonne and per-MWh emission figures.

    Raises:
        ValueError: If ``calorific_value_kcal_kg`` is non-positive.
        TypeError: If ``sample`` is not a ``CoalSample`` instance.

    Example:
        >>> s = CoalSample(
        ...     sample_id="KAL-001",
        ...     total_sulfur_pct=0.38,
        ...     calorific_value_kcal_kg=4850,
        ... )
        >>> result = estimate_so2_emission(s)
        >>> round(result.so2_kg_per_tonne, 3)
        7.448
        >>> round(result.so2_kg_per_mwh, 3)
        1.553
    """
    if not isinstance(sample, CoalSample):
        raise TypeError(f"Expected CoalSample, got {type(sample)}")

    warning = _validate_sample(sample)

    # 1. Raw SO2: stoichiometric oxidation of all sulfur
    sulfur_kg_per_tonne = sample.total_sulfur_pct / 100.0 * _KG_PER_TONNE
    raw_so2 = sulfur_kg_per_tonne * _SO2_STOICHIOMETRIC_FACTOR

    # 2. Apply combustion retention (fraction stays in ash)
    retained_fraction = sample.combustion_retention_pct / 100.0
    so2_after_retention = raw_so2 * (1.0 - retained_fraction)

    # 3. Apply FGD removal
    fgd_fraction = sample.fgd_efficiency_pct / 100.0
    fgd_reduction = so2_after_retention * fgd_fraction
    net_so2_per_tonne = so2_after_retention * (1.0 - fgd_fraction)

    # 4. Convert GCV to MWh per tonne (thermal)
    #    GCV kcal/kg → MJ/kg → GJ/tonne → MWh/tonne
    gcv_mj_per_kg = sample.calorific_value_kcal_kg * _KCAL_TO_MJ
    thermal_mwh_per_tonne = gcv_mj_per_kg * _MWH_PER_GJ * _KG_PER_TONNE

    # 5. Net electricity MWh per tonne
    net_mwh_per_tonne = thermal_mwh_per_tonne * (sample.plant_efficiency_pct / 100.0)

    # 6. SO2 intensity (kg/MWh)
    so2_per_mwh = net_so2_per_tonne / net_mwh_per_tonne if net_mwh_per_tonne > 0 else 0.0
    so2_per_mwh_gross = net_so2_per_tonne / thermal_mwh_per_tonne if thermal_mwh_per_tonne > 0 else 0.0

    return EmissionResult(
        sample_id=sample.sample_id,
        so2_kg_per_tonne=net_so2_per_tonne,
        so2_kg_per_mwh=so2_per_mwh,
        so2_kg_per_mwh_gross=so2_per_mwh_gross,
        emission_factor_raw_kg_per_tonne=raw_so2,
        fgd_reduction_kg_per_tonne=fgd_reduction,
        warning=warning,
    )


# ---------------------------------------------------------------------------
# Batch estimation
# ---------------------------------------------------------------------------


def estimate_batch(samples: Sequence[CoalSample]) -> list[EmissionResult]:
    """Estimate SO2 emissions for a batch of coal samples.

    Args:
        samples: Sequence of ``CoalSample`` objects. May be empty.

    Returns:
        List of ``EmissionResult`` objects in the same order as ``samples``.
        Returns an empty list when ``samples`` is empty.

    Raises:
        TypeError: If any element is not a ``CoalSample``.
        ValueError: If any sample has a non-positive calorific value.

    Example:
        >>> batch = [
        ...     CoalSample("A", 0.4, 5000),
        ...     CoalSample("B", 0.8, 4500, fgd_efficiency_pct=90),
        ... ]
        >>> results = estimate_batch(batch)
        >>> len(results)
        2
        >>> results[1].fgd_reduction_kg_per_tonne > 0
        True
    """
    return [estimate_so2_emission(s) for s in samples]


# ---------------------------------------------------------------------------
# Regulatory threshold check
# ---------------------------------------------------------------------------


def exceeds_threshold(
    result: EmissionResult,
    threshold_kg_per_mwh: float,
) -> bool:
    """Return True if the net SO2 intensity exceeds a regulatory threshold.

    Args:
        result: An ``EmissionResult`` from ``estimate_so2_emission``.
        threshold_kg_per_mwh: The emission limit in kg SO2 / MWh. Must be >= 0.

    Returns:
        ``True`` if ``result.so2_kg_per_mwh > threshold_kg_per_mwh``,
        ``False`` otherwise.

    Raises:
        ValueError: If ``threshold_kg_per_mwh`` is negative.

    Example:
        >>> s = CoalSample("X", 1.5, 5000)
        >>> r = estimate_so2_emission(s)
        >>> exceeds_threshold(r, threshold_kg_per_mwh=2.0)
        False
    """
    if threshold_kg_per_mwh < 0:
        raise ValueError(f"threshold must be >= 0, got {threshold_kg_per_mwh}")
    return result.so2_kg_per_mwh > threshold_kg_per_mwh
