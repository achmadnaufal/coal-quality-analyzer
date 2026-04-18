# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased] - 2026-04-19

### Added
- **Quality Deviation Report** (`src/quality_deviation_report.py`)
  - Frozen dataclasses: `QualitySample`, `ParameterSpec`, `ParameterDeviation`,
    `SampleReport`, `BatchStatistics`, `BatchReport`
  - `DeviationSeverity` enum: `within_spec` / `minor` / `major` / `critical`
  - `analyze_sample()` and `analyze_batch()` pure-function API returning new
    immutable reports (no input mutation)
  - Per-parameter severity classification scaled by a `minor_tolerance`
  - Batch aggregate statistics (mean, population stdev, min, max,
    out-of-spec count/ratio) and overall compliance ratio
  - `coefficient_of_variation()` helper for stability analysis
  - Fail-fast validation: invalid `basis`, negative numerics, out-of-plausible-
    range values, inverted spec bounds, and missing parameters raise
    `ValueError` with actionable messages
  - Zero external dependencies (standard library only)
  - 12 pytest cases in `tests/test_quality_deviation_report.py` covering
    happy-path, boundary severity bands, all validation branches, batch
    aggregation, empty-batch neutral element, and the CV helper
  - README section "New: Quality Deviation Report" with a runnable walkthrough
- Expanded `demo/sample_data.csv` to 20 rows with the canonical column set
  (`sample_id`, `sample_date`, `mine_block`, `seam`, `basis`,
  `calorific_value_kcal_kg`, `total_moisture_pct`, `inherent_moisture_pct`,
  `ash_pct`, `volatile_matter_pct`, `fixed_carbon_pct`, `total_sulphur_pct`,
  `hgi`, `size_category`) across `ar`/`ad`/`db`/`daf` bases

## [Unreleased] - 2026-04-18

### Added
- **Hardgrove Grindability Index (HGI) Analyzer** (`src/hardgrove_grindability_analyzer.py`)
  - `HGISample` frozen dataclass: HGI value, surface moisture %, ash %
  - `HGIAnalysis` frozen dataclass: corrected HGI, class, Bond W_i, mill kWh/t, capacity de-rate, warning
  - `GrindabilityClass` enum: very_hard, hard, medium, soft, very_soft (per ASTM D409 bands)
  - `correct_hgi_for_moisture()`: ISO 5074 Annex B moisture correction with clamping to a 1.0 floor
  - `classify_grindability()`: categorical band derived from corrected HGI
  - `bond_work_index()`: Bond W_i (kWh/short ton) from `W_i = 435 / HGI^1.25`
  - `mill_specific_energy()`: kWh/tonne mill consumption scaled from 12 kWh/t baseline at HGI 50
  - `capacity_derate_percent()`: throughput de-rate vs the 50-HGI reference
  - `analyze_sample()` / `analyze_batch()`: full pipeline, batch order preserved, empty input returns []
  - `meets_specification()`: buyer-window screening (default 45-65)
  - Validation: raises `ValueError` for non-positive HGI, negative moisture, ash > 100% or < 0; raises `TypeError` for wrong argument type; non-fatal warnings for out-of-typical-range inputs
  - Wired into `src/__init__.py` for top-level import
  - 35 pytest tests in `tests/test_hardgrove_grindability_analyzer.py` covering happy path, moisture correction (parametrized), classification boundaries, mill physics monotonicity, batch order, empty batch, division-by-zero guards, type validation, and buyer spec edges
  - README section "New: Hardgrove Grindability (HGI) Analyzer" with 3-step usage walkthrough

## [Unreleased] - 2026-04-17

### Added
- **SO2 Emission Estimator** (`src/sulfur_dioxide_emission_estimator.py`)
  - `CoalSample` frozen dataclass: sulfur %, GCV, plant efficiency, FGD efficiency, combustion retention
  - `EmissionResult` frozen dataclass: kg SO2/tonne, kg SO2/MWh (net and gross), raw emission factor, FGD reduction, warnings
  - `estimate_so2_emission()`: stoichiometric SO2 calculation with retention correction and FGD abatement
  - `estimate_batch()`: vectorized estimation over sequences of samples; returns empty list for empty input
  - `exceeds_threshold()`: boolean regulatory compliance check against a kg SO2/MWh limit
  - Input boundary validation with descriptive warnings for out-of-range sulfur, efficiency, and retention values
  - Raises `ValueError` for non-positive calorific value, `TypeError` for wrong argument type
  - 21 pytest tests in `tests/test_sulfur_dioxide_emission_estimator.py` covering happy path, zero sulfur, empty batch, FGD, out-of-range inputs, parametrized stoichiometry, and threshold checks
  - README section "New: SO2 Emission Estimator" with 4-step usage guide including batch CSV workflow

## [0.7.0] - 2026-04-15
### Added
- Unit tests with pytest (`tests/test_analyzer.py`) covering parameter validation,
  spec compliance, basis conversion, statistical summary, and edge cases (8+ tests)
- Sample data for demo purposes (`demo/sample_data.csv`) — 20 rows of realistic
  Indonesian (Kalimantan, Sumatra) and Australian (Bowen Basin, Hunter Valley) coal
- Comprehensive docstrings across `quality_metrics.py` with Args, Returns, Raises,
  and Example sections
- Input validation and edge case handling in `CoalQualityAnalyzer`:
  - Proximate analysis closure check (ash + VM + FC must sum to 100 % ± 2 %)
  - Guard against negative volatile matter and fixed carbon inputs
  - NCV clipped to zero when moisture penalty exceeds GCV
- Improved README: Quick Start, Sample Data usage, Running Tests section

## [0.6.0] - 2026-04-14

### Added
- **ContractComplianceChecker** (`coal_quality/compliance_checker.py`)
  - `ContractSpec` dataclass: ash/sulfur/moisture/GHV specs + penalty schedule
  - `InspectionResult` dataclass: lot sample results across all quality parameters
  - `check_single_lot()`: PASS/FAIL per parameter vs contract spec
  - `check_multi_lot()`: aggregate compliance across lots
  - `calculate_penalties()`: out-of-spec penalty computation
  - `lot_risk_classification()`: LOW/MEDIUM/HIGH based on proximity to spec limits
  - `vendor_performance_summary()`: per-vendor compliance statistics
  - `acceptance_probability()`: logistic acceptance probability for new lots
- **Unit tests** — 25+ tests in `tests/test_compliance_checker.py`
- **Sample data** — `sample_data/contract_compliance_data.csv` (20 lots, 3 contracts)

### References
- ISO 23009-1 Coal Trade Specifications
- ASTM D3172 proximate analysis standards
- GCCSI Coal Trading Contract Standards (2022)

## [2.4.0] - 2026-04-03

### Added
- **AdvancedSponcomRiskClassifier** (`src/spontaneous_combustion_risk_advanced.py`) — Enhanced spontaneous combustion risk assessment with Crossing Point Temperature (CPT), R70 index, AS 4264.1 category classification, incubation period estimation, oxygen depletion modeling, and ranked mitigation actions. Covers lignite through anthracite across tropical ambient conditions.
- **Unit tests** — 30 tests in `tests/test_sponcom_risk_advanced.py`.

## [2.3.0] - 2026-04-02

### Added
- **WashabilityTrompAnalyzer** (`src/washability_tromp_analyzer.py`) — Float-sink washability analysis with Tromp partition curve Ep calculation organic efficiency and DMS cut-point optimisation
- **Unit tests** — new comprehensive test suite in `tests/test_washability_tromp_analyzer.py`
- **CHANGELOG** updated to v2.3.0

## [2.2.0] - 2026-03-31

### Added
- **Coal Blending Quality Predictor** (`src/coal_blending_quality_predictor.py`) — multi-component blend quality prediction with ASTM spec compliance
  - `CoalComponent` dataclass: proportion%, CV (MJ/kg GAR), ash, moisture, sulfur, VM, HGI, Na, Cl, cost
  - `BlendSpecification` dataclass: configurable CV/ash/moisture/sulfur/HGI/Na/Cl limits
  - `CoalBlendingQualityPredictor` class with mass-weighted linear mixing rules
  - Sengupta (2002) sqrt-weighted HGI blend correction (more accurate than linear averaging)
  - ASTM D388 rank classification from CV and volatile matter
  - Sodium (>0.3%) and chlorine (>100 ppm) caution flags for slagging/corrosion risk
  - `optimise_proportions()`: 2-component grid search for target CV with tolerance window
  - Violation messages per failed spec criterion with specific values
- **Unit tests** — 26 new tests in `tests/test_coal_blending_quality_predictor.py` (all passing)

### References
- ASTM D388 (2019) Standard Classification of Coals by Rank.
- Sengupta (2002) HGI of coal blends. Fuel 81:979-986.
- World Bank (2009) Coal Plant Performance — Quality Specifications.

## [2.1.0] - 2026-03-30

### Added
- **Stockpile Heat Balance Calculator** (`src/stockpile_heat_balance_calculator.py`) — daily thermal simulation of coal stockpile temperature for spontaneous combustion management
  - 4 coal ranks: lignite, subbituminous, bituminous, anthracite (Arrhenius Q0/Ea parameters from Carras & Young 1994 and Nugroho et al. 2000)
  - Forward Euler integration over configurable time step (0.1–24 hr)
  - Heat generation: Arrhenius oxidation with optional volatile-matter scaling
  - Heat loss: convective (wind-adjusted h), evaporative (latent heat 2.45 MJ/kg)
  - Risk flags per day: OK / WATCH (≥70°C) / WARNING (≥100°C) / CRITICAL (≥150°C)
  - `equilibrium_temperature_c()`: bisection solver for steady-state temperature
  - Cone-geometry surface area estimation from volume + height
  - `SimulationResult.summary()`: milestone days and peak temperature
- **Unit tests** — 31 new tests in `tests/test_stockpile_heat_balance_calculator.py`

### References
- Carras & Young (1994) Self-heating of coal and related materials. PECS 20(1):1–15.
- Nugroho et al. (2000) Thermal analysis of Indonesian and Australian coals. Fuel 79(14):1951–1961.

## [2.0.0] - 2026-03-30

### Added
- **ThermalPriceIndexCalculator** (`src/thermal_price_index_calculator.py`)
  - `ThermalPriceIndexCalculator` — computes adjusted thermal coal prices using GAR/NAR calorific value methodology for Indonesian and Newcastle-linked export contracts
  - `CoalPriceAdjustment` — itemised adjustment record: CV adjustment (pro-rata), moisture penalty/bonus, ash penalty/bonus, sulphur penalty/bonus, total adjustment, realised price, adjustment %
  - `BlendedIndexResult` — weighted blended benchmark price from multiple indices (Newcastle, ICI, etc.)
  - Three reference spec templates: GAR5500, GAR5000, NAR6000 with default penalty/bonus rate tables
  - `calculate_adjustment()` — single cargo price realisation
  - `batch_adjustments()` + `batch_summary()` — fleet/month cargo pricing
  - `blend_indices()` — weighted blend of multiple benchmark indices with normalised weights
  - `convert_price_basis()` — GAR ↔ NAR price basis conversion
- **Test Suite** (`tests/test_thermal_price_index_calculator.py`) — 40 unit tests covering all adjustment types, basis conversions, blending, edge cases, and batch operations

## [New] - 2026-03-28
### Added
- Edge case validators and handlers
- Comprehensive unit tests
- Realistic sample data (realistic_data.csv)
- Enhanced README with validation examples

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

## [2.0.0] - 2026-03-27

### Added
- **Spontaneous Combustion Risk Assessor** (`src/spontaneous_combustion_risk.py`) — Sponcom risk scoring for coal stockpile safety management
  - `CoalSample` dataclass: proximate analysis, sulfur, GCV, oxygen, inertinite, stockpile geometry, ambient conditions; auto-computed `fixed_carbon_daf_pct` and `estimated_oxygen_pct` (rank-based fallback)
  - Full input validation: 13 quality parameters with domain-appropriate ranges
  - `SpontaneousCombustionRiskAssessor` with configurable temperature monitoring frequency
  - `estimate_cpt()`: Crossing Point Temperature estimation from VM, oxygen, moisture, sulfur, inertinite (CPT range 100–250°C)
  - CPT susceptibility classes: very_high (<140°C), high (<155°C), moderate (<175°C), low (≥175°C)
  - 7-factor risk driver scoring: rank_reactivity, volatile_matter, oxygen_content, stockpile_geometry, ambient_temperature, age_in_stockpile, monitoring_gap
  - `_composite_risk_index()`: weighted risk score (0–100)
  - Risk classes: critical (≥75), high (≥55), moderate (≥35), low (<35)
  - `assess()`: full single-sample assessment with mitigation actions and safe stockpile life estimate
  - `batch_assess()`: multi-sample assessment sorted by risk descending
  - `high_risk_stockpiles()`: filter to critical/high risk only
  - `mine_risk_summary()`: aggregated per-mine statistics with has_critical_sample flag
  - Domain-appropriate mitigation: compaction, CO monitoring, FIFO dispatch, antioxidant coating, emergency response
- **Unit tests** — 34 new tests in `tests/test_spontaneous_combustion_risk.py` (all passing)

### References
- ADB (2012) Indonesian Coal Sector Guidelines: Spontaneous Combustion Management
- Cliff et al. (1998) Testing for self-heating susceptibility. CSIRO Coal reports
- SNI 13-6499-2000 Indonesian standard for coal storage and handling
