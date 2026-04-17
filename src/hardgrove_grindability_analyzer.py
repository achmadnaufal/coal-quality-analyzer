"""
Hardgrove Grindability Index (HGI) Analyzer for coal mill performance.

The Hardgrove Grindability Index is a relative measure of how easily coal can
be pulverised in a power-plant mill. Higher HGI = softer coal = easier
grinding = lower mill power per tonne. Critical for:

  - Pulveriser sizing and capacity de-rating studies
  - Specific mill power consumption (kWh/t) estimates
  - Off-design coal acceptance: blended fuels with HGI shifts
  - Bond Work Index cross-checks (Bond W_i ≈ 435 / HGI^1.25 for coal)
  - Buyer specification screening (typical bituminous spec: HGI 45-60)

Method references:
  - ASTM D409 / D409M: Standard Test Method for Grindability of Coal by the
    Hardgrove-Machine Method
  - ISO 5074:2015 — Hard coal — Determination of Hardgrove grindability index
  - Bond, F. C. (1961) "Crushing and Grinding Calculations"
  - Power Engineering, mill capacity de-rate curves (1990)

HGI temperature/moisture sensitivity: HGI is measured on air-dried coal
ground at 60% RH. Field HGI varies with surface moisture; this module
provides a moisture correction following ISO 5074 Annex B.

Author: github.com/achmadnaufal
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Bond Work Index empirical conversion: W_i (kWh/short ton) = 435 / HGI^1.25
_BOND_WI_COEFFICIENT: float = 435.0
_BOND_WI_EXPONENT: float = 1.25

# Reference mill specific energy (kWh per tonne) at HGI = 50 baseline
_REFERENCE_MILL_KWH_PER_T_AT_HGI_50: float = 12.0

# Reference moisture for HGI lab measurement (air-dried, % surface moisture)
_REFERENCE_MOISTURE_PCT: float = 1.0


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class GrindabilityClass(str, Enum):
    """Categorical grindability class derived from HGI value."""

    VERY_HARD = "very_hard"        # HGI < 40 — anthracite-like, mill de-rate
    HARD = "hard"                  # 40 <= HGI < 50
    MEDIUM = "medium"              # 50 <= HGI < 70
    SOFT = "soft"                  # 70 <= HGI < 90
    VERY_SOFT = "very_soft"        # HGI >= 90 — lignite-like, fines risk


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HGISample:
    """Immutable HGI input record for a single coal sample.

    Attributes:
        sample_id: Unique identifier for the sample.
        hgi: Measured Hardgrove Grindability Index (typical range 30-110).
        surface_moisture_pct: Surface moisture at point of measurement
            (% mass, 0-30). Used for ISO 5074 Annex B correction.
        ash_pct: Ash content on air-dried basis (%, 0-50). Optional, used
            for buyer spec screening.
    """

    sample_id: str
    hgi: float
    surface_moisture_pct: float = _REFERENCE_MOISTURE_PCT
    ash_pct: float = 0.0


@dataclass(frozen=True)
class HGIAnalysis:
    """Immutable HGI analysis result for one coal sample.

    Attributes:
        sample_id: Identifier echoed from the input.
        hgi_corrected: HGI corrected to reference moisture (1%).
        grindability_class: Categorical band per ASTM D409 convention.
        bond_work_index_kwh_per_short_ton: Estimated Bond W_i in kWh/short ton.
        mill_specific_energy_kwh_per_t: Estimated mill power consumption
            (kWh per metric tonne) at the corrected HGI.
        capacity_derate_pct: Mill capacity de-rate vs HGI = 50 baseline (%).
            Positive = capacity loss, negative = capacity gain.
        warning: Non-empty if any input was flagged as unusual.
    """

    sample_id: str
    hgi_corrected: float
    grindability_class: GrindabilityClass
    bond_work_index_kwh_per_short_ton: float
    mill_specific_energy_kwh_per_t: float
    capacity_derate_pct: float
    warning: str


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_sample(sample: HGISample) -> str:
    """Validate the sample and return a non-empty warning if anything looks off.

    Raises:
        ValueError: If HGI is non-positive, surface moisture is negative,
            or ash content is negative.
    """
    if sample.hgi <= 0:
        raise ValueError(
            f"hgi must be > 0 (typical 30-110), got {sample.hgi}"
        )
    if sample.surface_moisture_pct < 0:
        raise ValueError(
            f"surface_moisture_pct must be >= 0, got {sample.surface_moisture_pct}"
        )
    if sample.ash_pct < 0:
        raise ValueError(
            f"ash_pct must be >= 0, got {sample.ash_pct}"
        )
    if sample.ash_pct > 100:
        raise ValueError(
            f"ash_pct must be <= 100, got {sample.ash_pct}"
        )

    warnings: list[str] = []
    if not (30.0 <= sample.hgi <= 110.0):
        warnings.append(f"hgi={sample.hgi} outside typical range [30, 110]")
    if sample.surface_moisture_pct > 30.0:
        warnings.append(
            f"surface_moisture_pct={sample.surface_moisture_pct} > 30 (very wet)"
        )
    if sample.ash_pct > 50.0:
        warnings.append(f"ash_pct={sample.ash_pct} > 50 (atypical for power coal)")

    return "; ".join(warnings)


# ---------------------------------------------------------------------------
# Core calculations
# ---------------------------------------------------------------------------


def correct_hgi_for_moisture(hgi: float, surface_moisture_pct: float) -> float:
    """Correct an as-measured HGI to the reference moisture (1 %).

    Per ISO 5074 Annex B, surface moisture above ~1 % softens the coal
    and inflates the apparent HGI. The empirical correction is
    approximately:

        HGI_corrected = HGI - 1.3 * (M - 1)

    where M is the surface moisture percentage. The correction is clamped
    to a minimum of 1.0 to avoid non-physical values.

    Args:
        hgi: Measured HGI on the as-tested coal.
        surface_moisture_pct: Surface moisture at the time of measurement (%).

    Returns:
        Moisture-corrected HGI (float, never less than 1.0).

    Raises:
        ValueError: If HGI is non-positive or moisture is negative.

    Example:
        >>> round(correct_hgi_for_moisture(55.0, 5.0), 2)
        49.8
    """
    if hgi <= 0:
        raise ValueError(f"hgi must be > 0, got {hgi}")
    if surface_moisture_pct < 0:
        raise ValueError(
            f"surface_moisture_pct must be >= 0, got {surface_moisture_pct}"
        )
    correction = 1.3 * (surface_moisture_pct - _REFERENCE_MOISTURE_PCT)
    corrected = hgi - correction
    return max(corrected, 1.0)


def classify_grindability(hgi: float) -> GrindabilityClass:
    """Map a corrected HGI value to a categorical grindability class.

    Args:
        hgi: Corrected HGI value.

    Returns:
        A ``GrindabilityClass`` enum member.

    Raises:
        ValueError: If HGI is non-positive.

    Example:
        >>> classify_grindability(55).value
        'medium'
    """
    if hgi <= 0:
        raise ValueError(f"hgi must be > 0, got {hgi}")
    if hgi < 40:
        return GrindabilityClass.VERY_HARD
    if hgi < 50:
        return GrindabilityClass.HARD
    if hgi < 70:
        return GrindabilityClass.MEDIUM
    if hgi < 90:
        return GrindabilityClass.SOFT
    return GrindabilityClass.VERY_SOFT


def bond_work_index(hgi: float) -> float:
    """Estimate the Bond Work Index (kWh/short ton) from HGI.

    Uses the Bond (1961) empirical relation:

        W_i = 435 / HGI^1.25

    Args:
        hgi: Corrected HGI value.

    Returns:
        Bond Work Index in kWh per short ton.

    Raises:
        ValueError: If HGI is non-positive.

    Example:
        >>> round(bond_work_index(50), 3)
        3.276
    """
    if hgi <= 0:
        raise ValueError(f"hgi must be > 0, got {hgi}")
    return _BOND_WI_COEFFICIENT / (hgi ** _BOND_WI_EXPONENT)


def mill_specific_energy(hgi: float) -> float:
    """Estimate mill-specific energy (kWh/tonne) at a given HGI.

    Scaled inversely from a 12 kWh/t baseline at HGI = 50:

        E = 12 * (50 / HGI)^1.25

    Args:
        hgi: Corrected HGI value.

    Returns:
        Specific energy in kWh per metric tonne of coal milled.

    Raises:
        ValueError: If HGI is non-positive.

    Example:
        >>> round(mill_specific_energy(50), 2)
        12.0
        >>> round(mill_specific_energy(40), 2) > 12
        True
    """
    if hgi <= 0:
        raise ValueError(f"hgi must be > 0, got {hgi}")
    return _REFERENCE_MILL_KWH_PER_T_AT_HGI_50 * ((50.0 / hgi) ** _BOND_WI_EXPONENT)


def capacity_derate_percent(hgi: float) -> float:
    """Calculate mill capacity de-rate vs the HGI = 50 baseline.

    A negative value means capacity gain (softer coal, more throughput);
    a positive value means capacity loss (harder coal).

    Args:
        hgi: Corrected HGI value.

    Returns:
        De-rate percentage relative to the 50-HGI baseline.

    Raises:
        ValueError: If HGI is non-positive.

    Example:
        >>> round(capacity_derate_percent(50), 2)
        0.0
        >>> capacity_derate_percent(40) > 0
        True
    """
    baseline = mill_specific_energy(50.0)
    actual = mill_specific_energy(hgi)
    return (actual - baseline) / baseline * 100.0


# ---------------------------------------------------------------------------
# High-level analysis
# ---------------------------------------------------------------------------


def analyze_sample(sample: HGISample) -> HGIAnalysis:
    """Run the full HGI analysis pipeline for a single sample.

    Applies moisture correction, then computes grindability class,
    Bond Work Index, mill-specific energy, and capacity de-rate.

    Args:
        sample: An ``HGISample`` instance.

    Returns:
        An immutable ``HGIAnalysis`` containing all derived metrics.

    Raises:
        TypeError: If ``sample`` is not an ``HGISample``.
        ValueError: If any input field is out of allowed bounds.

    Example:
        >>> s = HGISample(sample_id="KAL-001", hgi=52.0, surface_moisture_pct=3.0)
        >>> result = analyze_sample(s)
        >>> result.grindability_class.value
        'medium'
        >>> result.mill_specific_energy_kwh_per_t > 0
        True
    """
    if not isinstance(sample, HGISample):
        raise TypeError(f"Expected HGISample, got {type(sample)}")

    warning = _validate_sample(sample)
    corrected = correct_hgi_for_moisture(sample.hgi, sample.surface_moisture_pct)

    return HGIAnalysis(
        sample_id=sample.sample_id,
        hgi_corrected=corrected,
        grindability_class=classify_grindability(corrected),
        bond_work_index_kwh_per_short_ton=bond_work_index(corrected),
        mill_specific_energy_kwh_per_t=mill_specific_energy(corrected),
        capacity_derate_pct=capacity_derate_percent(corrected),
        warning=warning,
    )


def analyze_batch(samples: Sequence[HGISample]) -> list[HGIAnalysis]:
    """Run ``analyze_sample`` over a sequence of samples.

    Args:
        samples: Sequence of ``HGISample`` records. May be empty.

    Returns:
        List of ``HGIAnalysis`` results in the same order as input.

    Raises:
        TypeError: If any element is not an ``HGISample``.
        ValueError: If any sample fails validation.

    Example:
        >>> batch = [HGISample("A", 55), HGISample("B", 45)]
        >>> analyses = analyze_batch(batch)
        >>> len(analyses)
        2
    """
    return [analyze_sample(s) for s in samples]


# ---------------------------------------------------------------------------
# Buyer spec screening
# ---------------------------------------------------------------------------


def meets_specification(
    analysis: HGIAnalysis,
    min_hgi: float = 45.0,
    max_hgi: float = 65.0,
) -> bool:
    """Check whether an analysis meets a buyer's HGI specification window.

    Many thermal coal buyers require HGI in [45, 65] for compatibility with
    standard pulverisers (avoids both excessive mill wear and over-fines).

    Args:
        analysis: An ``HGIAnalysis`` from ``analyze_sample``.
        min_hgi: Lower bound of the acceptable HGI window. Default 45.
        max_hgi: Upper bound of the acceptable HGI window. Default 65.

    Returns:
        ``True`` if ``min_hgi <= corrected HGI <= max_hgi``, else ``False``.

    Raises:
        ValueError: If ``min_hgi`` >= ``max_hgi`` or either bound is
            non-positive.

    Example:
        >>> s = HGISample("X", 55)
        >>> a = analyze_sample(s)
        >>> meets_specification(a)
        True
    """
    if min_hgi <= 0 or max_hgi <= 0:
        raise ValueError("HGI bounds must be positive")
    if min_hgi >= max_hgi:
        raise ValueError(
            f"min_hgi ({min_hgi}) must be < max_hgi ({max_hgi})"
        )
    return min_hgi <= analysis.hgi_corrected <= max_hgi
