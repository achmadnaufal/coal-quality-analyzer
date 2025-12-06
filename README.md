# Coal Quality Analyzer

Coal quality parameter analysis, blending simulation, and specification compliance for Indonesian thermal coal operations.

## Features
- Data ingestion from CSV/Excel input files
- Automated analysis and KPI calculation
- Summary statistics and trend reporting
- **Export price premium/discount calculation** vs HBA benchmark
- **Specification compliance checking** with per-parameter violation detail
- **Coal grade classification** using GCV, ash, moisture, and sulfur
- **Blending simulation** to meet buyer specifications
- Sample data generator for testing and development

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from src.main import CoalQualityAnalyzer

analyzer = CoalQualityAnalyzer()
df = analyzer.load_data("data/sample.csv")
result = analyzer.analyze(df)
print(result)
```

## Usage Examples

### Check Export Price vs HBA Benchmark

```python
from quality_metrics import CoalQualityAnalyzer

result = CoalQualityAnalyzer.calculate_export_premium(
    gcv_mj_kg=24.5,
    ash_pct=9.2,
    sulfur_pct=0.7,
    moisture_pct=11.5,
    benchmark_price_usd=90.0,
    benchmark_gcv=25.0,
)
print(f"Adjusted price: ${result['adjusted_price_usd_per_tonne']:.2f}/t")
print(f"Premium/Discount: {result['premium_or_discount']} (${result['total_adjustment_usd']:.2f})")
# Adjusted price: $87.40/t
# Premium/Discount: discount (-$2.60)
```

### Validate Against Buyer Specification

```python
params = {"gcv": 24.8, "ash": 11.5, "sulfur": 0.65, "moisture": 12.0}
spec   = {"gcv": {"min": 23.0}, "ash": {"max": 12.0}, "sulfur": {"max": 1.0}}

check = CoalQualityAnalyzer.check_specification_compliance(params, spec)
print(f"Compliant: {check['compliant']}")          # True
print(f"Compliance rate: {check['compliance_rate']}%")  # 100.0%
```

### Coal Grade Classification

```python
params = {
    "calorific_value_mj_kg": 25.2,
    "ash_percent": 9.0,
    "moisture_percent": 11.0,
    "sulfur_percent": 0.6,
}
grade = analyzer.classify_coal_grade(params)
print(grade["coal_grade"])        # Grade A
print(grade["quality_score"])     # 87.3
```

## Data Format

Expected CSV columns: `sample_id, pit, date, calorific_value, total_moisture, ash_pct, sulfur_pct, volatile_matter`

## Project Structure

```
coal-quality-analyzer/
├── src/
│   ├── main.py          # Core analysis logic
│   └── data_generator.py # Sample data generator
├── data/                # Data directory (gitignored for real data)
├── examples/            # Usage examples
├── requirements.txt
└── README.md
```

## License

MIT License — free to use, modify, and distribute.


## Usage Examples

Refer to the `tests/` directory for comprehensive example implementations.
