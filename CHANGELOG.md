# Changelog - Coal Quality Analyzer

## [1.5.0] - 2026-03-17

### Added
- **Export Compliance Checker** (`src/export_compliance.py`) — coal batch validation against market specs
  - `CoalBatch` dataclass: GCV, moisture, ash, sulfur, VM validation
  - `ExportComplianceChecker`: Japan, China, India, Indonesian domestic standards
  - Per-parameter pass/fail with deviation amounts
  - Fleet-level compliance summary for batch processing
  - Continuity check for proximate analysis sum
- **Unit tests** — 14 new tests in `tests/test_export_compliance.py`
- **Sample data** — `sample_data/export_batches.csv`: 9 batches across 4 markets

## [1.4.0] - 2026-03-15

### Added
- **Export Premium Calculator** — `calculate_export_premium()`: Adjusts coal price vs HBA benchmark based on GCV, ash, sulfur, and moisture deviations; returns premium/discount breakdown per parameter
- **Specification Compliance Checker** — `check_specification_compliance()`: Validates coal parameters against buyer/contract specs with per-parameter violation detail and overall compliance rate
- **Unit Tests** — 11 new tests in `tests/test_export_premium.py` covering premium/discount logic, edge cases, and validation errors
- **Sample Data** — Added `sample_data/export_specs.csv` with typical Indonesian export specifications

### Improved
- README: Added usage examples for export pricing and compliance checking
- Enhanced docstrings with `Raises` and `Example` sections throughout

## [1.3.0] - 2026-03-11

### Added
- **Coal Blending Optimization** — New `optimize_coal_blend()` method for:
  - Optimal coal source composition determination
  - Blended calorific value calculation
  - Multi-parameter constraint satisfaction (ash, sulfur limits)
  - Specification compliance checking
  - Cost-effective blend formulation
- **Coal Quality Sample Data** — Created `sample_data/coal_quality_samples.csv`:
  - 8 coal samples from Indonesian mines
  - Complete quality parameters (moisture, ash, volatile matter, calorific value)
  - Blend optimization reference data

## [1.2.0] - 2026-03-10

### Added

- **Quality Metrics Module**: New `quality_metrics.py` with CoalQualityAnalyzer
  - `calculate_energy_content()`: Net calorific value using Dulong formula
  - `classify_coal_grade()`: Premium/high/standard/low grade classification
  - `calculate_quality_index()`: Overall quality score (0-100)
  - `blend_coals()`: Blended coal analysis from multiple samples
- **Test Suite**: 4 comprehensive tests for quality analysis
- **Quality Standards**: Embedded quality benchmarks

## [1.1.0] - 2026-02-01

### Added

- Basic quality metrics
- Grade classification

## [1.0.0] - 2025-12-01

### Added

- Initial coal quality analyzer
