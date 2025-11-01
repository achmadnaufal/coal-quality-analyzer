# Coal Quality Analyzer

Coal quality parameter analysis, blending simulation, and specification compliance

## Features
- Data ingestion from CSV/Excel input files
- Automated analysis and KPI calculation
- Summary statistics and trend reporting
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
