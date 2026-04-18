"""Pytest suite for src.quality_deviation_report.

Covers happy-path, boundary, edge-case, and input-validation behaviour.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.quality_deviation_report import (  # noqa: E402
    BatchReport,
    DeviationSeverity,
    ParameterSpec,
    QualitySample,
    analyze_batch,
    analyze_sample,
    coefficient_of_variation,
)


def _sample(**overrides) -> QualitySample:
    defaults = dict(
        sample_id="S-1",
        basis="ar",
        calorific_value_kcal_kg=5200.0,
        total_moisture_pct=25.0,
        ash_pct=6.0,
        volatile_matter_pct=40.0,
        fixed_carbon_pct=29.0,
        total_sulphur_pct=0.5,
    )
    defaults.update(overrides)
    return QualitySample(**defaults)


def _buyer_specs() -> list[ParameterSpec]:
    return [
        ParameterSpec("calorific_value_kcal_kg", min_value=5000.0, minor_tolerance=100.0),
        ParameterSpec("total_moisture_pct", max_value=30.0, minor_tolerance=1.0),
        ParameterSpec("ash_pct", max_value=10.0, minor_tolerance=0.5),
        ParameterSpec("total_sulphur_pct", max_value=0.8, minor_tolerance=0.1),
    ]


def test_compliant_sample_reports_within_spec() -> None:
    report = analyze_sample(_sample(), _buyer_specs())
    assert report.is_compliant
    assert report.worst_severity is DeviationSeverity.WITHIN
    assert len(report.deviations) == 4
    assert all(d.deviation == 0.0 for d in report.deviations)


def test_minor_breach_classified_as_minor() -> None:
    # Moisture 30.5 is 0.5 above 30 (spec max), within 1.0 tolerance -> MINOR
    report = analyze_sample(_sample(total_moisture_pct=30.5), _buyer_specs())
    moisture = next(d for d in report.deviations if d.parameter == "total_moisture_pct")
    assert moisture.severity is DeviationSeverity.MINOR
    assert moisture.deviation == pytest.approx(0.5)
    assert report.worst_severity is DeviationSeverity.MINOR


def test_critical_breach_classified_as_critical() -> None:
    # Ash 15 vs max 10 with tolerance 0.5 -> deviation 5.0 > 3 * 0.5 -> CRITICAL
    report = analyze_sample(_sample(ash_pct=15.0), _buyer_specs())
    ash = next(d for d in report.deviations if d.parameter == "ash_pct")
    assert ash.severity is DeviationSeverity.CRITICAL
    assert not report.is_compliant


def test_invalid_basis_rejected() -> None:
    with pytest.raises(ValueError, match="invalid basis"):
        _sample(basis="xx")


def test_negative_value_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        _sample(ash_pct=-1.0)


def test_out_of_plausible_range_rejected() -> None:
    with pytest.raises(ValueError, match="outside plausible range"):
        _sample(calorific_value_kcal_kg=50.0)


def test_spec_requires_min_or_max() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ParameterSpec("ash_pct")


def test_spec_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="min_value .* > max_value"):
        ParameterSpec("ash_pct", min_value=10.0, max_value=5.0)


def test_analyze_batch_aggregates_stats() -> None:
    samples = [
        _sample(sample_id="A", ash_pct=6.0),
        _sample(sample_id="B", ash_pct=7.0),
        _sample(sample_id="C", ash_pct=12.0),  # out of spec (max 10)
    ]
    report: BatchReport = analyze_batch(samples, _buyer_specs())
    assert report.total_samples == 3
    assert report.compliant_count == 2
    assert report.compliance_ratio == pytest.approx(2 / 3)
    ash_stats = next(s for s in report.parameter_stats if s.parameter == "ash_pct")
    assert ash_stats.out_of_spec_count == 1
    assert ash_stats.maximum == 12.0
    assert ash_stats.minimum == 6.0


def test_analyze_batch_empty_is_neutral() -> None:
    report = analyze_batch([], _buyer_specs())
    assert report.total_samples == 0
    assert report.compliance_ratio == 0.0
    assert report.worst_severity is DeviationSeverity.WITHIN


def test_missing_parameter_raises_clear_error() -> None:
    bad_spec = [ParameterSpec("nonexistent_field", max_value=1.0)]
    with pytest.raises(ValueError, match="missing required parameter"):
        analyze_sample(_sample(), bad_spec)


def test_coefficient_of_variation_handles_degenerate() -> None:
    assert coefficient_of_variation([]) == 0.0
    assert coefficient_of_variation([5.0]) == 0.0
    assert coefficient_of_variation([0.0, 0.0, 0.0]) == 0.0
    cv = coefficient_of_variation([4800.0, 5000.0, 5200.0])
    assert cv > 0.0
    assert cv < 0.1  # ~3% cv expected
