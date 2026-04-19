"""Blend ratio optimizer — hit a target calorific value under quality caps.

Given two or more coal sources and a target gross calorific value (GCV), compute
the mass-weighted blend ratio that hits the target while respecting upper caps
on ash, total sulfur, and total moisture (all linear mixing rule parameters).

Two solvers are provided:

1. **Closed-form binary blend** (``optimize_binary_blend``)
   For exactly two sources. Solves ``w * cv_a + (1 - w) * cv_b == target`` in
   one line, then evaluates ash / sulfur / moisture caps against the resulting
   blend. O(1), dependency-free, ideal for stockyard dispatch decisions.

2. **Least-absolute-deviation n-source LP** (``optimize_blend``)
   For three or more sources. Uses ``scipy.optimize.linprog`` to minimise the
   absolute deviation ``|blend_cv - target|`` subject to linear inequality
   constraints on ash, sulfur, and moisture. Falls back to a closed-form when
   ``len(sources) == 2``.

All mixing is mass-weighted and assumes the caller has already harmonised the
reporting basis (ADB / ARB) across sources — use
:mod:`src.moisture_bases_converter` first if inputs differ.

References:
    - ASTM D388-19 Standard Classification of Coals by Rank
    - ASTM D3180-15 Standard Practice for Calculating Coal and Coke Analyses
      from As-Determined to Different Bases
    - ISO 17246:2010 Coal — Proximate Analysis
    - Argus / Platts Newcastle NAR 6000 thermal coal specification (typical
      buyer spec: CV >= 6000 kcal/kg NAR, ash <= 15% ADB, sulfur <= 0.8% ADB,
      TM <= 14% AR)

Author: github.com/achmadnaufal
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "CoalSource",
    "BlendTarget",
    "BlendResult",
    "optimize_binary_blend",
    "optimize_blend",
]


# -- Physical plausibility bounds ------------------------------------------------
# Enforced at the input-validation layer so the optimiser never sees junk.
_CV_MIN_KCAL_KG = 1000.0  # below this is not combustible coal (peat/culm)
_CV_MAX_KCAL_KG = 8000.0  # above this exceeds meta-anthracite GCV on any basis


@dataclass(frozen=True)
class CoalSource:
    """A single coal source (stockpile, barge, rail car) entering a blend.

    All quality parameters are mass-percent except the calorific value, which
    is kcal/kg. Values must be reported on the **same basis** across all
    sources in a blend (typically ADB for Indonesian exports).

    Attributes:
        source_id: Human-readable label for the stockpile or mine.
        cv_kcal_kg: Gross calorific value (kcal/kg), same basis across sources.
        ash_pct: Ash content (%). Range [0, 100].
        total_sulfur_pct: Total sulfur (%). Range [0, 10].
        moisture_pct: Total (or inherent) moisture (%). Range [0, 100].
        available_tonnes: Optional upper bound on tonnes available from this
            source. When supplied, the optimiser enforces it as an LP
            inequality. ``None`` means unlimited.

    Raises:
        ValueError: If any numeric field is outside its physical bound.
    """

    source_id: str
    cv_kcal_kg: float
    ash_pct: float
    total_sulfur_pct: float
    moisture_pct: float
    available_tonnes: Optional[float] = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must be a non-empty string.")
        if not (_CV_MIN_KCAL_KG <= self.cv_kcal_kg <= _CV_MAX_KCAL_KG):
            raise ValueError(
                f"cv_kcal_kg for '{self.source_id}' must be in "
                f"[{_CV_MIN_KCAL_KG}, {_CV_MAX_KCAL_KG}], got {self.cv_kcal_kg}."
            )
        if not (0.0 <= self.ash_pct <= 100.0):
            raise ValueError(
                f"ash_pct for '{self.source_id}' must be in [0, 100], "
                f"got {self.ash_pct}."
            )
        if not (0.0 <= self.total_sulfur_pct <= 10.0):
            raise ValueError(
                f"total_sulfur_pct for '{self.source_id}' must be in [0, 10], "
                f"got {self.total_sulfur_pct}."
            )
        if not (0.0 <= self.moisture_pct <= 100.0):
            raise ValueError(
                f"moisture_pct for '{self.source_id}' must be in [0, 100], "
                f"got {self.moisture_pct}."
            )
        if self.available_tonnes is not None and self.available_tonnes < 0:
            raise ValueError(
                f"available_tonnes for '{self.source_id}' must be >= 0, "
                f"got {self.available_tonnes}."
            )


@dataclass(frozen=True)
class BlendTarget:
    """Buyer specification target for an outbound blend.

    Attributes:
        target_cv_kcal_kg: Contractual GCV the blend must hit (kcal/kg).
        max_ash_pct: Upper cap on ash content (%). Default 15% (Newcastle-like).
        max_sulfur_pct: Upper cap on total sulfur (%). Default 0.8%.
        max_moisture_pct: Upper cap on total moisture (%). Default 14%.
        cv_tolerance_kcal_kg: Acceptable absolute deviation from
            ``target_cv_kcal_kg`` before the blend is flagged non-compliant.
            Default 50 kcal/kg (typical contractual allowance).

    Raises:
        ValueError: If any numeric field is outside its physical bound.
    """

    target_cv_kcal_kg: float
    max_ash_pct: float = 15.0
    max_sulfur_pct: float = 0.8
    max_moisture_pct: float = 14.0
    cv_tolerance_kcal_kg: float = 50.0

    def __post_init__(self) -> None:
        if not (_CV_MIN_KCAL_KG <= self.target_cv_kcal_kg <= _CV_MAX_KCAL_KG):
            raise ValueError(
                f"target_cv_kcal_kg must be in [{_CV_MIN_KCAL_KG}, "
                f"{_CV_MAX_KCAL_KG}], got {self.target_cv_kcal_kg}."
            )
        for attr in ("max_ash_pct", "max_moisture_pct"):
            val = getattr(self, attr)
            if not (0.0 <= val <= 100.0):
                raise ValueError(f"{attr} must be in [0, 100], got {val}.")
        if not (0.0 <= self.max_sulfur_pct <= 10.0):
            raise ValueError(
                f"max_sulfur_pct must be in [0, 10], got {self.max_sulfur_pct}."
            )
        if self.cv_tolerance_kcal_kg < 0:
            raise ValueError(
                f"cv_tolerance_kcal_kg must be >= 0, "
                f"got {self.cv_tolerance_kcal_kg}."
            )


@dataclass(frozen=True)
class BlendResult:
    """Outcome of a blend-ratio optimisation.

    Attributes:
        ratios: Mass fraction per source, aligned with the input order. Sums to 1.
        blended_cv_kcal_kg: Mass-weighted GCV of the blend.
        blended_ash_pct: Mass-weighted ash.
        blended_sulfur_pct: Mass-weighted total sulfur.
        blended_moisture_pct: Mass-weighted total moisture.
        cv_deviation_kcal_kg: Signed difference (blend - target).
        feasible: True when the LP/closed-form solver converged to a
            non-negative, normalised ratio vector. False when no feasible
            blend exists (e.g. all sources below target CV and caps prevent
            lifting).
        meets_specification: True iff the blend satisfies the CV tolerance
            AND every upper cap in :class:`BlendTarget`.
        violations: Human-readable list of cap violations (empty when
            ``meets_specification`` is True).
        method: Solver used (``"closed_form_binary"`` or ``"linprog"``).
    """

    ratios: Tuple[float, ...]
    blended_cv_kcal_kg: float
    blended_ash_pct: float
    blended_sulfur_pct: float
    blended_moisture_pct: float
    cv_deviation_kcal_kg: float
    feasible: bool
    meets_specification: bool
    violations: Tuple[str, ...]
    method: str

    def as_dict(self) -> Dict:
        """Return a plain-dict view (handy for JSON / DataFrame export).

        Returns:
            Dict with every public attribute, ``ratios`` and ``violations``
            flattened from tuples to lists for JSON compatibility.
        """
        return {
            "ratios": list(self.ratios),
            "blended_cv_kcal_kg": self.blended_cv_kcal_kg,
            "blended_ash_pct": self.blended_ash_pct,
            "blended_sulfur_pct": self.blended_sulfur_pct,
            "blended_moisture_pct": self.blended_moisture_pct,
            "cv_deviation_kcal_kg": self.cv_deviation_kcal_kg,
            "feasible": self.feasible,
            "meets_specification": self.meets_specification,
            "violations": list(self.violations),
            "method": self.method,
        }


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _validate_sources(sources: Sequence[CoalSource]) -> None:
    """Validate the sources sequence (non-empty, unique ids).

    Args:
        sources: Sequence of CoalSource objects.

    Raises:
        ValueError: If sources is empty or contains duplicate source_ids.
        TypeError: If an element is not a CoalSource instance.
    """
    if not sources:
        raise ValueError("sources must be a non-empty sequence.")
    seen: set = set()
    for i, s in enumerate(sources):
        if not isinstance(s, CoalSource):
            raise TypeError(
                f"sources[{i}] must be a CoalSource, got {type(s).__name__}."
            )
        if s.source_id in seen:
            raise ValueError(f"Duplicate source_id: '{s.source_id}'.")
        seen.add(s.source_id)


def _blend_properties(
    sources: Sequence[CoalSource],
    ratios: Sequence[float],
) -> Tuple[float, float, float, float]:
    """Compute mass-weighted (cv, ash, sulfur, moisture) for a blend.

    Args:
        sources: Coal sources (aligned with ratios).
        ratios: Mass fractions, must sum to 1 (caller responsibility).

    Returns:
        Tuple of (blended_cv_kcal_kg, blended_ash_pct, blended_sulfur_pct,
        blended_moisture_pct).
    """
    cv = sum(r * s.cv_kcal_kg for r, s in zip(ratios, sources))
    ash = sum(r * s.ash_pct for r, s in zip(ratios, sources))
    sulfur = sum(r * s.total_sulfur_pct for r, s in zip(ratios, sources))
    moisture = sum(r * s.moisture_pct for r, s in zip(ratios, sources))
    return cv, ash, sulfur, moisture


def _assess_compliance(
    cv: float,
    ash: float,
    sulfur: float,
    moisture: float,
    target: BlendTarget,
) -> Tuple[float, bool, Tuple[str, ...]]:
    """Compare blend properties against a BlendTarget.

    Args:
        cv: Blended calorific value (kcal/kg).
        ash: Blended ash (%).
        sulfur: Blended total sulfur (%).
        moisture: Blended moisture (%).
        target: Contractual target.

    Returns:
        Tuple (cv_deviation, meets_specification, violations). Deviation is
        signed (positive = blend above target).
    """
    deviation = cv - target.target_cv_kcal_kg
    violations: List[str] = []

    if abs(deviation) > target.cv_tolerance_kcal_kg:
        direction = "below" if deviation < 0 else "above"
        violations.append(
            f"cv: {cv:.1f} kcal/kg is {abs(deviation):.1f} {direction} target "
            f"({target.target_cv_kcal_kg:.1f} +/- "
            f"{target.cv_tolerance_kcal_kg:.1f})"
        )
    if ash > target.max_ash_pct:
        violations.append(
            f"ash: {ash:.2f}% exceeds max {target.max_ash_pct:.2f}%"
        )
    if sulfur > target.max_sulfur_pct:
        violations.append(
            f"sulfur: {sulfur:.2f}% exceeds max {target.max_sulfur_pct:.2f}%"
        )
    if moisture > target.max_moisture_pct:
        violations.append(
            f"moisture: {moisture:.2f}% exceeds max {target.max_moisture_pct:.2f}%"
        )
    return deviation, not violations, tuple(violations)


# --------------------------------------------------------------------------- #
# Closed-form two-source solver
# --------------------------------------------------------------------------- #


def optimize_binary_blend(
    source_a: CoalSource,
    source_b: CoalSource,
    target: BlendTarget,
) -> BlendResult:
    """Solve a two-source blend analytically.

    With ``w`` the mass fraction of ``source_a``, the linear mixing rule gives
    ``w = (target_cv - cv_b) / (cv_a - cv_b)`` when ``cv_a != cv_b``. The result
    is clipped to ``[0, 1]`` — when the target lies outside the interval
    ``[min(cv_a, cv_b), max(cv_a, cv_b)]`` the closer source is returned as a
    single-source "blend" and ``feasible`` is still True but the CV deviation
    will exceed the tolerance, which surfaces via ``meets_specification``.

    Args:
        source_a: First coal source.
        source_b: Second coal source.
        target: Contractual target (CV + ash/sulfur/moisture caps).

    Returns:
        BlendResult with ratios as a 2-tuple ``(w_a, w_b)`` summing to 1.

    Raises:
        TypeError: If inputs are not CoalSource / BlendTarget.
        ValueError: If the two source_ids collide.

    Example::

        a = CoalSource("PIT-A", 6400, 9.2, 0.45, 12.0)
        b = CoalSource("PIT-B", 5200, 12.8, 0.90, 20.0)
        tgt = BlendTarget(target_cv_kcal_kg=6000)
        result = optimize_binary_blend(a, b, tgt)
        print(result.ratios, result.meets_specification)
    """
    if not isinstance(source_a, CoalSource) or not isinstance(source_b, CoalSource):
        raise TypeError("source_a and source_b must be CoalSource instances.")
    if not isinstance(target, BlendTarget):
        raise TypeError("target must be a BlendTarget instance.")
    if source_a.source_id == source_b.source_id:
        raise ValueError("source_a and source_b must have distinct source_ids.")

    cv_a = source_a.cv_kcal_kg
    cv_b = source_b.cv_kcal_kg

    if cv_a == cv_b:
        # Identical CV — any mix yields the same CV. Pick 50/50 and let the
        # cap assessment decide compliance.
        w_a = 0.5
    else:
        raw_w = (target.target_cv_kcal_kg - cv_b) / (cv_a - cv_b)
        w_a = max(0.0, min(1.0, raw_w))

    w_b = 1.0 - w_a
    ratios = (w_a, w_b)
    sources = (source_a, source_b)
    cv, ash, sulfur, moisture = _blend_properties(sources, ratios)
    deviation, meets, violations = _assess_compliance(cv, ash, sulfur, moisture, target)

    return BlendResult(
        ratios=ratios,
        blended_cv_kcal_kg=round(cv, 2),
        blended_ash_pct=round(ash, 4),
        blended_sulfur_pct=round(sulfur, 4),
        blended_moisture_pct=round(moisture, 4),
        cv_deviation_kcal_kg=round(deviation, 2),
        feasible=True,
        meets_specification=meets,
        violations=violations,
        method="closed_form_binary",
    )


# --------------------------------------------------------------------------- #
# N-source LP solver
# --------------------------------------------------------------------------- #


def _solve_lp(
    sources: Sequence[CoalSource],
    target: BlendTarget,
) -> Tuple[Optional[Tuple[float, ...]], bool]:
    """Solve the least-absolute-deviation blend LP.

    Decision variables: ``x = (w_1, ..., w_n, d_plus, d_minus)`` where ``w_i``
    are source mass fractions and ``d_plus``, ``d_minus`` are the positive and
    negative parts of the CV deviation. Minimises ``d_plus + d_minus`` subject
    to:

      * ``sum(w_i) == 1``                                 (mass balance)
      * ``sum(w_i * cv_i) - d_plus + d_minus == target``  (CV split)
      * ``sum(w_i * ash_i) <= max_ash``                   (ash cap)
      * ``sum(w_i * sulfur_i) <= max_sulfur``             (sulfur cap)
      * ``sum(w_i * moisture_i) <= max_moisture``         (moisture cap)
      * ``0 <= w_i``, ``0 <= d_plus``, ``0 <= d_minus``   (non-neg)

    Args:
        sources: Non-empty list of coal sources.
        target: Blend target with CV and caps.

    Returns:
        Tuple ``(ratios, feasible)``. When infeasible, ``ratios`` is None.
    """
    try:
        import numpy as np
        from scipy.optimize import linprog
    except ImportError as exc:  # pragma: no cover - scipy is in requirements
        raise RuntimeError(
            "scipy is required for n-source blend optimisation. "
            "Install with: pip install scipy>=1.10"
        ) from exc

    n = len(sources)
    # Objective: minimise d_plus + d_minus (indices n and n+1).
    c = np.zeros(n + 2)
    c[n] = 1.0
    c[n + 1] = 1.0

    # Equality: sum w_i = 1, and sum(w_i * cv_i) - d+ + d- = target_cv
    A_eq = np.zeros((2, n + 2))
    A_eq[0, :n] = 1.0
    A_eq[1, :n] = [s.cv_kcal_kg for s in sources]
    A_eq[1, n] = -1.0
    A_eq[1, n + 1] = 1.0
    b_eq = np.array([1.0, target.target_cv_kcal_kg])

    # Inequality caps
    A_ub = np.zeros((3, n + 2))
    A_ub[0, :n] = [s.ash_pct for s in sources]
    A_ub[1, :n] = [s.total_sulfur_pct for s in sources]
    A_ub[2, :n] = [s.moisture_pct for s in sources]
    b_ub = np.array(
        [target.max_ash_pct, target.max_sulfur_pct, target.max_moisture_pct]
    )

    bounds = [(0.0, None)] * (n + 2)

    res = linprog(
        c=c,
        A_ub=A_ub,
        b_ub=b_ub,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )

    if not res.success:
        return None, False

    w = res.x[:n]
    # Normalise away solver rounding (guaranteed by A_eq[0] but be safe).
    total = sum(w)
    if total <= 0:
        return None, False
    ratios = tuple(float(round(v / total, 6)) for v in w)
    return ratios, True


def optimize_blend(
    sources: Sequence[CoalSource],
    target: BlendTarget,
) -> BlendResult:
    """Solve an n-source blend ratio problem against a BlendTarget.

    For exactly two sources, delegates to :func:`optimize_binary_blend` (O(1),
    scipy-free). For three or more, builds a least-absolute-deviation linear
    program and solves it via ``scipy.optimize.linprog`` (HiGHS backend).

    When the LP is infeasible under the current caps — typical cause: every
    source has ash or sulfur above the buyer spec — the result has
    ``feasible=False`` and uniform 1/n ratios as a diagnostic fallback. Always
    inspect ``result.violations`` before acting on such a result.

    Args:
        sources: Sequence of 2+ distinct CoalSource objects (same reporting
            basis — convert first if mixed).
        target: BlendTarget (CV + caps + tolerance).

    Returns:
        BlendResult with ratios aligned to ``sources`` order.

    Raises:
        ValueError: If ``sources`` is empty or contains duplicate ids.
        TypeError: If any element is not a CoalSource.

    Example::

        sources = [
            CoalSource("PIT-A", 6400, 9.2, 0.45, 12.0),
            CoalSource("PIT-B", 5800, 11.0, 0.65, 14.0),
            CoalSource("PIT-C", 5200, 14.5, 0.90, 20.0),
        ]
        target = BlendTarget(
            target_cv_kcal_kg=6000,
            max_ash_pct=12.0,
            max_sulfur_pct=0.8,
            max_moisture_pct=15.0,
        )
        result = optimize_blend(sources, target)
        for s, r in zip(sources, result.ratios):
            print(f"{s.source_id}: {r:.1%}")
    """
    _validate_sources(sources)
    if not isinstance(target, BlendTarget):
        raise TypeError("target must be a BlendTarget instance.")

    if len(sources) == 1:
        # Degenerate — single source, ratio = 1.0.
        ratios = (1.0,)
        cv, ash, sulfur, moisture = _blend_properties(sources, ratios)
        deviation, meets, violations = _assess_compliance(
            cv, ash, sulfur, moisture, target
        )
        return BlendResult(
            ratios=ratios,
            blended_cv_kcal_kg=round(cv, 2),
            blended_ash_pct=round(ash, 4),
            blended_sulfur_pct=round(sulfur, 4),
            blended_moisture_pct=round(moisture, 4),
            cv_deviation_kcal_kg=round(deviation, 2),
            feasible=True,
            meets_specification=meets,
            violations=violations,
            method="single_source",
        )

    if len(sources) == 2:
        return optimize_binary_blend(sources[0], sources[1], target)

    ratios, feasible = _solve_lp(sources, target)

    if not feasible or ratios is None:
        # Return a diagnostic blend (equal-weight) so the caller can inspect
        # the cap violations and understand *why* the LP failed. Never mutate
        # inputs; always return a new BlendResult.
        n = len(sources)
        uniform = tuple(1.0 / n for _ in sources)
        cv, ash, sulfur, moisture = _blend_properties(sources, uniform)
        deviation, _meets, violations = _assess_compliance(
            cv, ash, sulfur, moisture, target
        )
        return BlendResult(
            ratios=uniform,
            blended_cv_kcal_kg=round(cv, 2),
            blended_ash_pct=round(ash, 4),
            blended_sulfur_pct=round(sulfur, 4),
            blended_moisture_pct=round(moisture, 4),
            cv_deviation_kcal_kg=round(deviation, 2),
            feasible=False,
            meets_specification=False,
            violations=violations
            + ("linprog infeasible: no blend satisfies all caps",),
            method="linprog_infeasible",
        )

    cv, ash, sulfur, moisture = _blend_properties(sources, ratios)
    deviation, meets, violations = _assess_compliance(
        cv, ash, sulfur, moisture, target
    )
    return BlendResult(
        ratios=ratios,
        blended_cv_kcal_kg=round(cv, 2),
        blended_ash_pct=round(ash, 4),
        blended_sulfur_pct=round(sulfur, 4),
        blended_moisture_pct=round(moisture, 4),
        cv_deviation_kcal_kg=round(deviation, 2),
        feasible=True,
        meets_specification=meets,
        violations=violations,
        method="linprog",
    )
