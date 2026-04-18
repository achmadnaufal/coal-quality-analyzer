"""Quality Deviation Report module.

Compares a batch of coal quality samples against a target specification and
produces per-parameter deviation statistics, outlier flags, and an overall
quality stability summary suitable for mine-planning and shipment QC review.

Design notes:
- All dataclasses are frozen and methods never mutate inputs; every transform
  returns a new object (see ~/.claude/rules coding-style Immutability rule).
- Functions fail fast on invalid input (invalid basis, negative or out-of-range
  values, missing columns) and raise ``ValueError`` with an actionable message.
- No external dependencies beyond the Python standard library so the module is
  safe to import in minimal CI environments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import sqrt
from statistics import mean, pstdev
from typing import Iterable, Mapping, Sequence

VALID_BASES = ("ar", "ad", "db", "daf")

# Defensible upper bounds for validation. Values above these are almost
# certainly a unit mix-up or data-entry error and should fail loudly.
PARAMETER_RANGES: Mapping[str, tuple[float, float]] = {
    "calorific_value_kcal_kg": (1000.0, 9000.0),
    "total_moisture_pct": (0.0, 60.0),
    "inherent_moisture_pct": (0.0, 30.0),
    "ash_pct": (0.0, 50.0),
    "volatile_matter_pct": (0.0, 60.0),
    "fixed_carbon_pct": (0.0, 90.0),
    "total_sulphur_pct": (0.0, 10.0),
    "hgi": (20.0, 120.0),
}


class DeviationSeverity(str, Enum):
    """Categorical severity for a single-parameter deviation."""

    WITHIN = "within_spec"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


@dataclass(frozen=True)
class QualitySample:
    """A single coal quality observation.

    All percentage fields are ``float`` in percent (not fraction).
    ``basis`` must be one of ``VALID_BASES``.
    """

    sample_id: str
    basis: str
    calorific_value_kcal_kg: float
    total_moisture_pct: float
    ash_pct: float
    volatile_matter_pct: float
    fixed_carbon_pct: float
    total_sulphur_pct: float

    def __post_init__(self) -> None:
        if self.basis not in VALID_BASES:
            raise ValueError(
                f"invalid basis '{self.basis}'; expected one of {VALID_BASES}"
            )
        _validate_numeric("calorific_value_kcal_kg", self.calorific_value_kcal_kg)
        _validate_numeric("total_moisture_pct", self.total_moisture_pct)
        _validate_numeric("ash_pct", self.ash_pct)
        _validate_numeric("volatile_matter_pct", self.volatile_matter_pct)
        _validate_numeric("fixed_carbon_pct", self.fixed_carbon_pct)
        _validate_numeric("total_sulphur_pct", self.total_sulphur_pct)


@dataclass(frozen=True)
class ParameterSpec:
    """Target range for a single parameter.

    Either ``min_value`` or ``max_value`` may be ``None`` to express an
    open-ended band (for example, moisture has only a maximum limit and GCV
    has only a minimum limit in most buyer specs).
    """

    name: str
    min_value: float | None = None
    max_value: float | None = None
    # Tolerance (absolute, same unit as the parameter) below which a breach
    # is considered ``MINOR`` rather than ``MAJOR``.
    minor_tolerance: float = 0.0

    def __post_init__(self) -> None:
        if self.min_value is None and self.max_value is None:
            raise ValueError(
                f"spec '{self.name}' must define at least one of min_value/max_value"
            )
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValueError(
                f"spec '{self.name}': min_value {self.min_value} > max_value {self.max_value}"
            )
        if self.minor_tolerance < 0:
            raise ValueError(
                f"spec '{self.name}': minor_tolerance must be >= 0"
            )


@dataclass(frozen=True)
class ParameterDeviation:
    """Per-parameter deviation for a single sample."""

    parameter: str
    observed: float
    target_min: float | None
    target_max: float | None
    deviation: float  # signed absolute deviation from the nearest band edge
    severity: DeviationSeverity


@dataclass(frozen=True)
class SampleReport:
    """Deviation report for a single sample across all parameters."""

    sample_id: str
    basis: str
    deviations: tuple[ParameterDeviation, ...]
    worst_severity: DeviationSeverity

    @property
    def is_compliant(self) -> bool:
        """True when no parameter deviates beyond spec."""

        return self.worst_severity is DeviationSeverity.WITHIN


@dataclass(frozen=True)
class BatchStatistics:
    """Aggregate statistics for a single parameter across a batch."""

    parameter: str
    mean: float
    stdev: float
    minimum: float
    maximum: float
    out_of_spec_count: int
    sample_count: int

    @property
    def out_of_spec_ratio(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return self.out_of_spec_count / self.sample_count


@dataclass(frozen=True)
class BatchReport:
    """Report for a batch of samples."""

    sample_reports: tuple[SampleReport, ...]
    parameter_stats: tuple[BatchStatistics, ...]
    worst_severity: DeviationSeverity
    compliant_count: int = field(default=0)

    @property
    def total_samples(self) -> int:
        return len(self.sample_reports)

    @property
    def compliance_ratio(self) -> float:
        if self.total_samples == 0:
            return 0.0
        return self.compliant_count / self.total_samples


def _validate_numeric(name: str, value: float) -> None:
    """Reject negatives and out-of-plausible-range numerics."""

    if value is None:
        raise ValueError(f"parameter '{name}' is required")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"parameter '{name}' must be numeric") from exc
    if numeric < 0:
        raise ValueError(f"parameter '{name}' must be non-negative, got {numeric}")
    if name in PARAMETER_RANGES:
        lo, hi = PARAMETER_RANGES[name]
        if numeric < lo or numeric > hi:
            raise ValueError(
                f"parameter '{name}' value {numeric} outside plausible range [{lo}, {hi}]"
            )


def _classify_severity(deviation: float, minor_tolerance: float) -> DeviationSeverity:
    """Map a non-negative deviation into a severity band.

    Thresholds are multiplicative of ``minor_tolerance``:
    - <= tolerance: MINOR
    - <= 3x tolerance: MAJOR
    - > 3x tolerance: CRITICAL
    When ``minor_tolerance`` is 0 any breach is MAJOR unless it's also >50% of
    the observed value, in which case CRITICAL.
    """

    if deviation <= 0:
        return DeviationSeverity.WITHIN
    if minor_tolerance > 0:
        if deviation <= minor_tolerance:
            return DeviationSeverity.MINOR
        if deviation <= 3.0 * minor_tolerance:
            return DeviationSeverity.MAJOR
        return DeviationSeverity.CRITICAL
    return DeviationSeverity.MAJOR


def _deviation_for(value: float, spec: ParameterSpec) -> ParameterDeviation:
    """Compute signed distance from the closest spec-band edge."""

    breach = 0.0
    if spec.min_value is not None and value < spec.min_value:
        breach = spec.min_value - value
    elif spec.max_value is not None and value > spec.max_value:
        breach = value - spec.max_value
    severity = _classify_severity(breach, spec.minor_tolerance)
    return ParameterDeviation(
        parameter=spec.name,
        observed=value,
        target_min=spec.min_value,
        target_max=spec.max_value,
        deviation=breach,
        severity=severity,
    )


_SEVERITY_ORDER = {
    DeviationSeverity.WITHIN: 0,
    DeviationSeverity.MINOR: 1,
    DeviationSeverity.MAJOR: 2,
    DeviationSeverity.CRITICAL: 3,
}


def _worst(severities: Iterable[DeviationSeverity]) -> DeviationSeverity:
    worst = DeviationSeverity.WITHIN
    for sev in severities:
        if _SEVERITY_ORDER[sev] > _SEVERITY_ORDER[worst]:
            worst = sev
    return worst


def analyze_sample(
    sample: QualitySample, specs: Sequence[ParameterSpec]
) -> SampleReport:
    """Return a :class:`SampleReport` for a single sample against ``specs``.

    ``specs`` may cover a subset of parameters; missing specs are skipped.
    """

    if not specs:
        raise ValueError("at least one ParameterSpec is required")
    deviations: list[ParameterDeviation] = []
    for spec in specs:
        if not hasattr(sample, spec.name):
            raise ValueError(
                f"sample {sample.sample_id} missing required parameter '{spec.name}'"
            )
        deviations.append(_deviation_for(getattr(sample, spec.name), spec))
    worst = _worst(d.severity for d in deviations)
    return SampleReport(
        sample_id=sample.sample_id,
        basis=sample.basis,
        deviations=tuple(deviations),
        worst_severity=worst,
    )


def _parameter_stats(
    parameter: str,
    values: Sequence[float],
    out_of_spec: int,
) -> BatchStatistics:
    if not values:
        return BatchStatistics(
            parameter=parameter,
            mean=0.0,
            stdev=0.0,
            minimum=0.0,
            maximum=0.0,
            out_of_spec_count=0,
            sample_count=0,
        )
    return BatchStatistics(
        parameter=parameter,
        mean=mean(values),
        stdev=pstdev(values) if len(values) > 1 else 0.0,
        minimum=min(values),
        maximum=max(values),
        out_of_spec_count=out_of_spec,
        sample_count=len(values),
    )


def analyze_batch(
    samples: Sequence[QualitySample], specs: Sequence[ParameterSpec]
) -> BatchReport:
    """Return a :class:`BatchReport` summarising a collection of samples.

    Empty input returns a well-formed empty report rather than raising, so
    callers can treat it as a neutral element.
    """

    if samples and not specs:
        raise ValueError("at least one ParameterSpec is required")
    reports = tuple(analyze_sample(s, specs) for s in samples)
    compliant = sum(1 for r in reports if r.is_compliant)
    stats: list[BatchStatistics] = []
    for spec in specs:
        values = [float(getattr(s, spec.name)) for s in samples]
        out_of_spec = 0
        for report in reports:
            for dev in report.deviations:
                if dev.parameter == spec.name and dev.severity is not DeviationSeverity.WITHIN:
                    out_of_spec += 1
        stats.append(_parameter_stats(spec.name, values, out_of_spec))
    worst = _worst(r.worst_severity for r in reports)
    return BatchReport(
        sample_reports=reports,
        parameter_stats=tuple(stats),
        worst_severity=worst,
        compliant_count=compliant,
    )


def coefficient_of_variation(values: Sequence[float]) -> float:
    """Return the coefficient of variation (stdev/mean) or 0 for degenerate inputs."""

    if len(values) < 2:
        return 0.0
    mu = mean(values)
    if mu == 0:
        return 0.0
    variance = sum((v - mu) ** 2 for v in values) / len(values)
    return sqrt(variance) / abs(mu)
