# Contributing to Coal Quality Analyzer

This project provides coal quality analysis tools for Indonesian thermal coal operations, including blending simulation, export pricing, and thermal risk modeling.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/<your-username>/coal-quality-analyzer.git`
3. Install dependencies: `pip install -r requirements.txt`
4. Create a feature branch: `git checkout -b feat/your-feature`

## Development Guidelines

- **Code style:** PEP 8. Type hints for public methods.
- **Tests:** New features require unit tests in `tests/`. Run `pytest tests/ -v`.
- **Domain accuracy:** Grade thresholds and price adjustments should reference published standards (HBA, ICI 4, ASTM). Cite in docstrings.
- **Real data:** Never commit real mine data. Use the `data_generator.py` for synthetic samples.

## Areas Where Help Is Needed

- 📐 GAR ↔ NAR conversion utilities
- 🌍 Additional export market specs (India CERC, China GB/T, Vietnam EVN)
- 📈 Platts / Argus index price feed integration
- 🔥 Enhanced Arrhenius model with humidity variables
- 📦 Streamlit app for interactive blending simulation

## Submitting a PR

1. Ensure all tests pass
2. Update `CHANGELOG.md`
3. Open a PR with clear description of changes

## Code of Conduct

Be professional. Domain accuracy matters — incorrect grade thresholds or price calculations can have real commercial consequences.
