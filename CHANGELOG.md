# Changelog - Coal Quality Analyzer

## [1.9.0] - 2026-03-26

### Added
- **AshFusionTemperatureInterpreter** (`src/ash_fusion_temperature_interpreter.py`) — ISO 540/ASTM D1857 AFT risk analysis
  - AshComposition dataclass with major oxide inputs (SiO2, Al2O3, Fe2O3, CaO, MgO, Na2O, K2O, TiO2)
  - Computed indices: Base/Acid Ratio (B/A), Silica Ratio (SR), Slagging Index Rs (B/A × S), Fouling Index (B/A × Na2O)
  - Slagging risk classification: LOW / MEDIUM / HIGH / SEVERE vs Rs thresholds
  - Fouling risk classification: LOW / MEDIUM / HIGH / SEVERE vs FI thresholds
  - AshFusionTemperatures dataclass: DT, ST, HT, FT with temperature-stage validation
  - Fusion span and high-fusion flag (FT ≥ 1400°C) for boiler compatibility
  - Operational furnace recommendations: slag-tap suitability, rapid fusion warning, soot-blower guidance
  - `batch_interpret()` for multi-sample lab report processing
- Unit tests: 14 new tests in `tests/test_ash_fusion_temperature_interpreter.py`

## [1.8.0] - 2026-03-23

### Added
- `src/wash_plant_yield_calculator.py` — Wash plant mass balance and yield prediction
  - `WashabilityFraction` dataclass with float-sink density, mass, ash, and CV
  - `WashPlantYieldCalculator` with Tromp curve separation efficiency model
  - `calculate_yield()` — clean coal yield, ash, and CV at any SG cut point
  - `theoretical_yield_at_ash()` — maximum yield at a given product ash specification
  - `yield_curve()` — full yield-ash curve across all density fractions
  - `feed_quality_summary()` — weighted-average raw feed quality
  - Separator types: DMC, DM Bath, Jig, Spiral, Reflux Classifier
- `data/sample_washability_data.csv` — float-sink data for 2 Kalimantan/Sumatra samples
- 27 unit tests in `tests/test_wash_plant_yield.py`

### References
- Wills' Mineral Processing Technology (8th ed.)
- Tromp Curve methodology for dense medium separation

## [1.7.0] - 2026-03-22

### Added
- **Moisture Bases Converter** (`src/moisture_bases_converter.py`) — ISO 17246 / ASTM D3180 coal quality basis conversion
  - Converts proximate analysis parameters across four bases: AR (As-Received), AD (Air-Dried), DB (Dry Basis), DAF (Dry-Ash-Free)
  - Full bidirectional support: all 12 pairwise basis conversions (AR↔AD, AR↔DB, AR↔DAF, AD↔DB, AD↔DAF, DB↔DAF)
  - `convert()` — single-parameter conversion with required moisture/ash input validation
  - `gcv_gar_to_gad()` — convenience wrapper for ISO 1928 GCV GAR→GAD conversion (used in Indonesian export contracts)
  - `convert_full_analysis()` — converts an entire ProximateAnalysis dataclass to a target basis in one call
  - `batch_convert()` — applies conversion across a list of row-dicts (pipeline-friendly for tabular data)
  - `ProximateAnalysis` dataclass with basis validation and auto-uppercase normalization
  - All inputs validated: basis codes, moisture range [0–100], non-negative moisture requirement
- **Unit tests** — 22 new tests in `tests/test_moisture_bases_converter.py` covering roundtrips, edge cases, and error handling

### References
- ISO 17246:2010 Coal — Proximate Analysis
- ASTM D3180 Standard Practice for Calculating Coal and Coke Analyses
- ISO 1928:2009 Solid mineral fuels — Determination of gross calorific value

## [1.6.0] - 2026-03-18

### Added
- **Calorific Value Predictor** (`src/calorific_value_predictor.py`) — empirical GCV prediction and coal rank classification
  - `ProximateAnalysis` and `UltimateAnalysis` dataclasses with full input validation and auto-calculated fields (FC, daf VM, dmmf FC)
  - Three GCV prediction formulae: Dulong (ultimate), Boie (ultimate, default), Majumdar regression (proximate — calibrated for SE Asian coals)
  - ASTM D388 coal rank classification (Meta-anthracite through Lignite B) from GCV and dmmf fixed carbon
  - `validate_lab_result()`: cross-checks reported GCV against prediction with PASS/WARNING/FAIL flags (configurable tolerance)
  - `batch_predict()`: multi-sample processing with automatic method selection (ultimate > proximate fallback)
- **Sample data** — `sample_data/proximate_ultimate_analysis.csv` with 10 Indonesian coal samples (Kalimantan, South Sumatra, Papua)
- **Unit tests** — 30 tests in `tests/test_calorific_value_predictor.py` covering all formulae, rank classification, validation flags, and edge cases

### References
- Dulong (1868), Boie (1953) calorific value formulae
- Majumdar et al. (1998) SE Asian coal regression
- ASTM D388-19 coal rank classification

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
