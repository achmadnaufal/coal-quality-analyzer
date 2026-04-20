"""
Coal Rank Classifier per ASTM D388 — Standard Classification of Coals by Rank.

ASTM D388 is the definitive U.S. standard for assigning a coal specimen to one
of four classes and the sub-bituminous/bituminous/anthracite groups. Rank is a
measure of coal maturation (degree of coalification) and is the single best
predictor of combustion behaviour, coking ability, and long-term storage
stability. It is used for:

  - Contract classification (FOB price decks are rank-indexed)
  - Boiler design (PC, CFB, stoker — all tuned to a rank window)
  - Coke-making eligibility (only mid- to low-volatile bituminous coals)
  - Storage / self-heating risk triage (lower rank → higher Spon-Com risk)
  - Regulatory reporting (MSHA, IEA, UNFC resource codes)

Classification axes (ASTM D388-23):

  1. Higher-rank coals (Fixed Carbon >= 69 % dmmf, VM <= 31 % dmmf):
     classified by **Fixed Carbon on dry mineral-matter-free basis (dmmf)**.
       - meta-anthracite         FC >= 98
       - anthracite              92 <= FC < 98
       - semi-anthracite         86 <= FC < 92
       - low-volatile bituminous 78 <= FC < 86
       - medium-volatile bit.    69 <= FC < 78
  2. Lower-rank coals (FC < 69 % dmmf, VM > 31 % dmmf):
     classified by **Gross Calorific Value on moist mineral-matter-free
     basis (mmmf)** in Btu/lb, with agglomerating character tie-break at
     the bituminous / sub-bituminous boundary.
       - high-volatile A bit.    >= 14 000 Btu/lb         agglomerating
       - high-volatile B bit.    13 000 <= GCV < 14 000    agglomerating
       - high-volatile C bit.    11 500 <= GCV < 13 000    agglomerating
                                 or 10 500 <= GCV < 11 500 agglomerating
       - sub-bituminous A        10 500 <= GCV < 11 500    non-agglomerating
       - sub-bituminous B        9 500  <= GCV < 10 500
       - sub-bituminous C        8 300  <= GCV < 9 500
       - lignite A               6 300  <= GCV < 8 300
       - lignite B               GCV < 6 300

Mineral-matter corrections:

  - Parr formulas (ASTM D388 §X1):
        FC_dmmf = 100 * (FC - 0.15*S) / (100 - M - 1.08*A - 0.55*S)
        VM_dmmf = 100 - FC_dmmf
        GCV_mmmf = 100 * (GCV - 50*S) / (100 - 1.08*A - 0.55*S)
    where FC, VM, A (ash), S (sulfur) are %-weight on as-received (moist) basis
    and M is moisture %. GCV is in Btu/lb (or kcal/kg — the formula is unit-
    neutral for GCV; only the class thresholds are Btu/lb).

Unit conversions used:

  - 1 kcal/kg = 1.8 Btu/lb  (ASTM D5865 conversion)

References:
  - ASTM D388-23: Standard Classification of Coals by Rank
  - ASTM D3176: Standard Practice for Ultimate Analysis of Coal and Coke
  - Parr, S. W. (1928) "The Classification of Coal"
  - ISO 11760:2018: Classification of coals (cross-reference)

Author: github.com/achmadnaufal
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# kcal/kg → Btu/lb
_KCAL_PER_KG_TO_BTU_PER_LB: float = 1.8

# Parr mineral-matter correction coefficients (ASTM D388 §X1)
_PARR_ASH_COEFF: float = 1.08
_PARR_SULFUR_COEFF: float = 0.55
_PARR_GCV_SULFUR_BTU: float = 50.0   # Btu/lb per % S
_PARR_FC_SULFUR_COEFF: float = 0.15  # % S contribution to FC removal

# Fixed-carbon (dmmf) threshold separating higher- and lower-rank coals
_FC_DMMF_HIGHER_RANK_THRESHOLD: float = 69.0

# Agglomerating tie-break band for hvCb / sub-bituminous A (Btu/lb)
_AGGLOM_BAND_LOW: float = 10_500.0
_AGGLOM_BAND_HIGH: float = 11_500.0


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CoalClass(str, Enum):
    """Top-level ASTM D388 coal class."""

    ANTHRACITIC = "anthracitic"
    BITUMINOUS = "bituminous"
    SUB_BITUMINOUS = "sub_bituminous"
    LIGNITIC = "lignitic"


class CoalRank(str, Enum):
    """ASTM D388 rank (group) within a class."""

    META_ANTHRACITE = "meta_anthracite"
    ANTHRACITE = "anthracite"
    SEMI_ANTHRACITE = "semi_anthracite"
    LOW_VOLATILE_BITUMINOUS = "low_volatile_bituminous"
    MEDIUM_VOLATILE_BITUMINOUS = "medium_volatile_bituminous"
    HIGH_VOLATILE_A_BITUMINOUS = "high_volatile_a_bituminous"
    HIGH_VOLATILE_B_BITUMINOUS = "high_volatile_b_bituminous"
    HIGH_VOLATILE_C_BITUMINOUS = "high_volatile_c_bituminous"
    SUB_BITUMINOUS_A = "sub_bituminous_a"
    SUB_BITUMINOUS_B = "sub_bituminous_b"
    SUB_BITUMINOUS_C = "sub_bituminous_c"
    LIGNITE_A = "lignite_a"
    LIGNITE_B = "lignite_b"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProximateSample:
    """Immutable proximate analysis input on an as-received / moist basis.

    All percentages are % by mass on the as-received (moist) basis unless
    noted. `gcv` may be supplied in kcal/kg or Btu/lb (see `gcv_unit`).

    Attributes:
        sample_id: Unique identifier.
        moisture_pct: Total moisture, as-received (% mass, 0-60).
        ash_pct: Ash content, as-received (% mass, 0-50).
        volatile_matter_pct: Volatile matter, as-received (% mass, 0-60).
        fixed_carbon_pct: Fixed carbon, as-received (% mass, 0-90).
        sulfur_pct: Total sulfur, as-received (% mass, 0-10).
        gcv: Gross calorific value on as-received (moist) basis.
        gcv_unit: Unit for `gcv` — either "kcal_per_kg" or "btu_per_lb".
        agglomerating: True if the coal shows button-like agglomeration in
            the D720 free-swelling test; used as the hvCb/subA tie-breaker.
    """

    sample_id: str
    moisture_pct: float
    ash_pct: float
    volatile_matter_pct: float
    fixed_carbon_pct: float
    sulfur_pct: float
    gcv: float
    gcv_unit: str = "kcal_per_kg"
    agglomerating: bool = False


@dataclass(frozen=True)
class RankAnalysis:
    """Immutable ASTM D388 classification output for one sample.

    Attributes:
        sample_id: Echoed identifier.
        coal_class: Top-level class.
        coal_rank: Group (sub-class) within the class.
        fixed_carbon_dmmf_pct: Fixed carbon on dry mineral-matter-free basis.
        volatile_matter_dmmf_pct: Volatile matter on dmmf basis.
        gcv_mmmf_btu_per_lb: Gross calorific value on moist mmmf basis (Btu/lb).
        classification_axis: "fixed_carbon" or "calorific_value" — the axis
            that actually determined the rank.
        warning: Non-empty if inputs are unusual or the boundary is ambiguous.
    """

    sample_id: str
    coal_class: CoalClass
    coal_rank: CoalRank
    fixed_carbon_dmmf_pct: float
    volatile_matter_dmmf_pct: float
    gcv_mmmf_btu_per_lb: float
    classification_axis: str
    warning: str


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


_VALID_GCV_UNITS: frozenset[str] = frozenset({"kcal_per_kg", "btu_per_lb"})


def _validate_sample(sample: ProximateSample) -> str:
    """Validate a proximate sample; raise ValueError on hard errors.

    Returns a non-empty warning string if any value is outside the typical
    operational range but still physically plausible.
    """
    if not isinstance(sample, ProximateSample):
        raise TypeError(
            f"sample must be ProximateSample, got {type(sample).__name__}"
        )
    if sample.gcv_unit not in _VALID_GCV_UNITS:
        raise ValueError(
            f"gcv_unit must be one of {sorted(_VALID_GCV_UNITS)}, "
            f"got {sample.gcv_unit!r}"
        )
    for field_name, value in (
        ("moisture_pct", sample.moisture_pct),
        ("ash_pct", sample.ash_pct),
        ("volatile_matter_pct", sample.volatile_matter_pct),
        ("fixed_carbon_pct", sample.fixed_carbon_pct),
        ("sulfur_pct", sample.sulfur_pct),
    ):
        if value < 0:
            raise ValueError(f"{field_name} must be >= 0, got {value}")
        if value > 100:
            raise ValueError(f"{field_name} must be <= 100, got {value}")
    if sample.gcv <= 0:
        raise ValueError(f"gcv must be > 0, got {sample.gcv}")

    proximate_sum = (
        sample.moisture_pct
        + sample.ash_pct
        + sample.volatile_matter_pct
        + sample.fixed_carbon_pct
    )
    if not (97.0 <= proximate_sum <= 103.0):
        raise ValueError(
            "proximate closure failed: M + A + VM + FC = "
            f"{proximate_sum:.2f} (must be 100 ± 3)"
        )

    warnings: list[str] = []
    if sample.sulfur_pct > 5.0:
        warnings.append(f"sulfur_pct={sample.sulfur_pct} > 5 (very high S)")
    if sample.ash_pct > 40.0:
        warnings.append(f"ash_pct={sample.ash_pct} > 40 (atypical for rank test)")
    if sample.moisture_pct > 50.0:
        warnings.append(
            f"moisture_pct={sample.moisture_pct} > 50 (extreme; lignitic)"
        )
    return "; ".join(warnings)


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


def kcal_per_kg_to_btu_per_lb(kcal_per_kg: float) -> float:
    """Convert GCV from kcal/kg to Btu/lb (ASTM D5865)."""
    if kcal_per_kg <= 0:
        raise ValueError(f"kcal_per_kg must be > 0, got {kcal_per_kg}")
    return kcal_per_kg * _KCAL_PER_KG_TO_BTU_PER_LB


def gcv_in_btu_per_lb(gcv: float, unit: str) -> float:
    """Return the GCV value converted to Btu/lb, preserving sign semantics."""
    if unit == "btu_per_lb":
        return gcv
    if unit == "kcal_per_kg":
        return kcal_per_kg_to_btu_per_lb(gcv)
    raise ValueError(f"unit must be one of {sorted(_VALID_GCV_UNITS)}, got {unit!r}")


# ---------------------------------------------------------------------------
# Parr mineral-matter corrections
# ---------------------------------------------------------------------------


def parr_fixed_carbon_dmmf(
    fixed_carbon_pct: float,
    moisture_pct: float,
    ash_pct: float,
    sulfur_pct: float,
) -> float:
    """Compute Fixed Carbon on dry mineral-matter-free basis (Parr).

    FC_dmmf = 100 * (FC - 0.15*S) / (100 - M - 1.08*A - 0.55*S)

    Raises:
        ValueError: If the denominator collapses to <= 0 (impossible coal).
    """
    denom = (
        100.0
        - moisture_pct
        - _PARR_ASH_COEFF * ash_pct
        - _PARR_SULFUR_COEFF * sulfur_pct
    )
    if denom <= 0:
        raise ValueError(
            "Parr denominator <= 0; check moisture/ash/sulfur values "
            f"(got denom={denom:.3f})"
        )
    numerator = fixed_carbon_pct - _PARR_FC_SULFUR_COEFF * sulfur_pct
    return 100.0 * numerator / denom


def parr_gcv_mmmf_btu_per_lb(
    gcv_btu_per_lb: float,
    ash_pct: float,
    sulfur_pct: float,
) -> float:
    """Compute GCV on moist mineral-matter-free basis (Parr).

    GCV_mmmf = 100 * (GCV - 50*S) / (100 - 1.08*A - 0.55*S)

    `gcv_btu_per_lb` must already be on as-received (moist) basis in Btu/lb.
    """
    denom = 100.0 - _PARR_ASH_COEFF * ash_pct - _PARR_SULFUR_COEFF * sulfur_pct
    if denom <= 0:
        raise ValueError(
            "Parr GCV denominator <= 0; check ash/sulfur values "
            f"(got denom={denom:.3f})"
        )
    numerator = gcv_btu_per_lb - _PARR_GCV_SULFUR_BTU * sulfur_pct
    return 100.0 * numerator / denom


# ---------------------------------------------------------------------------
# Rank decision
# ---------------------------------------------------------------------------


def _classify_higher_rank(fc_dmmf: float) -> CoalRank:
    """Classify a higher-rank coal by Fixed Carbon (dmmf)."""
    if fc_dmmf >= 98.0:
        return CoalRank.META_ANTHRACITE
    if fc_dmmf >= 92.0:
        return CoalRank.ANTHRACITE
    if fc_dmmf >= 86.0:
        return CoalRank.SEMI_ANTHRACITE
    if fc_dmmf >= 78.0:
        return CoalRank.LOW_VOLATILE_BITUMINOUS
    return CoalRank.MEDIUM_VOLATILE_BITUMINOUS


def _classify_lower_rank(gcv_mmmf_btu: float, agglomerating: bool) -> CoalRank:
    """Classify a lower-rank coal by GCV (mmmf, Btu/lb) with agglomeration."""
    if gcv_mmmf_btu >= 14_000.0:
        return CoalRank.HIGH_VOLATILE_A_BITUMINOUS
    if gcv_mmmf_btu >= 13_000.0:
        return CoalRank.HIGH_VOLATILE_B_BITUMINOUS
    if gcv_mmmf_btu >= _AGGLOM_BAND_HIGH:
        # 11 500 – 13 000 : always hvCb (agglomerating by D388 design)
        return CoalRank.HIGH_VOLATILE_C_BITUMINOUS
    if gcv_mmmf_btu >= _AGGLOM_BAND_LOW:
        # 10 500 – 11 500 : hvCb if agglomerating, else sub-bituminous A
        return (
            CoalRank.HIGH_VOLATILE_C_BITUMINOUS
            if agglomerating
            else CoalRank.SUB_BITUMINOUS_A
        )
    if gcv_mmmf_btu >= 9_500.0:
        return CoalRank.SUB_BITUMINOUS_B
    if gcv_mmmf_btu >= 8_300.0:
        return CoalRank.SUB_BITUMINOUS_C
    if gcv_mmmf_btu >= 6_300.0:
        return CoalRank.LIGNITE_A
    return CoalRank.LIGNITE_B


_RANK_TO_CLASS: dict[CoalRank, CoalClass] = {
    CoalRank.META_ANTHRACITE: CoalClass.ANTHRACITIC,
    CoalRank.ANTHRACITE: CoalClass.ANTHRACITIC,
    CoalRank.SEMI_ANTHRACITE: CoalClass.ANTHRACITIC,
    CoalRank.LOW_VOLATILE_BITUMINOUS: CoalClass.BITUMINOUS,
    CoalRank.MEDIUM_VOLATILE_BITUMINOUS: CoalClass.BITUMINOUS,
    CoalRank.HIGH_VOLATILE_A_BITUMINOUS: CoalClass.BITUMINOUS,
    CoalRank.HIGH_VOLATILE_B_BITUMINOUS: CoalClass.BITUMINOUS,
    CoalRank.HIGH_VOLATILE_C_BITUMINOUS: CoalClass.BITUMINOUS,
    CoalRank.SUB_BITUMINOUS_A: CoalClass.SUB_BITUMINOUS,
    CoalRank.SUB_BITUMINOUS_B: CoalClass.SUB_BITUMINOUS,
    CoalRank.SUB_BITUMINOUS_C: CoalClass.SUB_BITUMINOUS,
    CoalRank.LIGNITE_A: CoalClass.LIGNITIC,
    CoalRank.LIGNITE_B: CoalClass.LIGNITIC,
}


def class_of(rank: CoalRank) -> CoalClass:
    """Return the ASTM D388 class of a given rank."""
    return _RANK_TO_CLASS[rank]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_sample(sample: ProximateSample) -> RankAnalysis:
    """Classify a single coal sample per ASTM D388.

    Steps:
      1. Validate inputs (raise on out-of-range, bad unit, closure failure).
      2. Convert GCV to Btu/lb if needed (ASTM D5865).
      3. Compute Parr dmmf fixed carbon and mmmf GCV.
      4. Branch on FC_dmmf >= 69 % → classify by fixed carbon; else by GCV.
      5. Map rank → class.

    Returns a new frozen ``RankAnalysis`` (no input mutation).

    Raises:
        TypeError: If ``sample`` is not a ``ProximateSample``.
        ValueError: On any validation failure.

    Example:
        >>> s = ProximateSample(
        ...     sample_id="LVB-01",
        ...     moisture_pct=2.0, ash_pct=7.0,
        ...     volatile_matter_pct=18.0, fixed_carbon_pct=73.0,
        ...     sulfur_pct=0.5, gcv=14_700.0, gcv_unit="btu_per_lb",
        ...     agglomerating=True,
        ... )
        >>> classify_sample(s).coal_rank.value
        'low_volatile_bituminous'
    """
    warning = _validate_sample(sample)

    gcv_btu = gcv_in_btu_per_lb(sample.gcv, sample.gcv_unit)

    fc_dmmf = parr_fixed_carbon_dmmf(
        sample.fixed_carbon_pct,
        sample.moisture_pct,
        sample.ash_pct,
        sample.sulfur_pct,
    )
    vm_dmmf = max(0.0, min(100.0, 100.0 - fc_dmmf))
    gcv_mmmf = parr_gcv_mmmf_btu_per_lb(
        gcv_btu, sample.ash_pct, sample.sulfur_pct
    )

    if fc_dmmf >= _FC_DMMF_HIGHER_RANK_THRESHOLD:
        rank = _classify_higher_rank(fc_dmmf)
        axis = "fixed_carbon"
    else:
        rank = _classify_lower_rank(gcv_mmmf, sample.agglomerating)
        axis = "calorific_value"

    return RankAnalysis(
        sample_id=sample.sample_id,
        coal_class=_RANK_TO_CLASS[rank],
        coal_rank=rank,
        fixed_carbon_dmmf_pct=fc_dmmf,
        volatile_matter_dmmf_pct=vm_dmmf,
        gcv_mmmf_btu_per_lb=gcv_mmmf,
        classification_axis=axis,
        warning=warning,
    )


def classify_batch(samples: Sequence[ProximateSample]) -> list[RankAnalysis]:
    """Classify a sequence of samples preserving input order.

    Empty input returns an empty list. Does not mutate inputs.
    """
    return [classify_sample(s) for s in samples]


def rank_rank_ordinal(rank: CoalRank) -> int:
    """Return an integer ordering of rank from lowest (0) to highest (12).

    Useful for sorting and trend analysis (lignite-B = 0,
    meta-anthracite = 12).
    """
    ordering = [
        CoalRank.LIGNITE_B,
        CoalRank.LIGNITE_A,
        CoalRank.SUB_BITUMINOUS_C,
        CoalRank.SUB_BITUMINOUS_B,
        CoalRank.SUB_BITUMINOUS_A,
        CoalRank.HIGH_VOLATILE_C_BITUMINOUS,
        CoalRank.HIGH_VOLATILE_B_BITUMINOUS,
        CoalRank.HIGH_VOLATILE_A_BITUMINOUS,
        CoalRank.MEDIUM_VOLATILE_BITUMINOUS,
        CoalRank.LOW_VOLATILE_BITUMINOUS,
        CoalRank.SEMI_ANTHRACITE,
        CoalRank.ANTHRACITE,
        CoalRank.META_ANTHRACITE,
    ]
    return ordering.index(rank)


def is_coking_candidate(analysis: RankAnalysis) -> bool:
    """Return True if the rank is typically eligible for metallurgical coke.

    Coking coals are conventionally MV-bit or LV-bit (ASTM D388 D720
    agglomeration required). Semi-anthracite and hv-bit are generally
    non-coking in isolation.
    """
    return analysis.coal_rank in (
        CoalRank.MEDIUM_VOLATILE_BITUMINOUS,
        CoalRank.LOW_VOLATILE_BITUMINOUS,
    )
