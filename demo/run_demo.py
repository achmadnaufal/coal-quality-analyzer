"""CLI demo: grade a coal sample, price it vs HBA, and check spec compliance.

Run from repo root:

    python3 demo/run_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quality_metrics import CoalQualityAnalyzer


def main() -> None:
    print("=" * 64)
    print("Coal Quality Analyzer — demo run")
    print("=" * 64)

    # 1) Sample-level analysis (instance API)
    sample = CoalQualityAnalyzer(
        sample_id="LOT-2026-04-19",
        ash_percent=11.2,
        moisture_percent=12.5,
        sulfur_percent=0.65,
        calorific_value_mj_kg=24.8,
    )
    a = sample.analyze()
    print("\n1) Sample analysis (LOT-2026-04-19):")
    for k, v in a.items():
        print(f"   {k:<24} {v}")

    # 2) Static grade classification (just ash + sulfur)
    print("\n2) Quick grade (static API): classify_coal_grade(ash, sulfur)")
    for ash, sulfur in [(10, 0.6), (14, 1.0), (16, 1.4), (22, 2.5)]:
        label = CoalQualityAnalyzer.classify_coal_grade(ash, sulfur)
        print(f"   ash={ash:>4.1f}% sulfur={sulfur:>4.2f}%  →  {label}")

    # 3) Export premium vs HBA $90/t benchmark
    print("\n3) Export premium vs HBA $90/t benchmark, 25.0 MJ/kg:")
    export = CoalQualityAnalyzer.calculate_export_premium(
        gcv_mj_kg=24.5,
        ash_pct=9.2,
        sulfur_pct=0.7,
        moisture_pct=11.5,
        benchmark_price_usd=90.0,
        benchmark_gcv=25.0,
    )
    print(f"   Adjusted price: ${export['adjusted_price_usd_per_tonne']:.2f}/t  ({export['premium_or_discount']})")
    print(f"   Total adj:      ${export['total_adjustment_usd']:.2f}/t   GCV ratio: {export['calorific_ratio']}")
    for k, v in export["quality_adjustments"].items():
        print(f"     {k:<18}  ${v:+.2f}/t")

    # 4) Specification compliance
    print("\n4) Buyer specification compliance:")
    params = {"gcv": 24.8, "ash": 11.5, "sulfur": 0.65, "moisture": 12.0}
    spec = {
        "gcv": {"min": 23.0},
        "ash": {"max": 12.0},
        "sulfur": {"max": 1.0},
        "moisture": {"max": 14.0},
    }
    chk = CoalQualityAnalyzer.check_specification_compliance(params, spec)
    print(f"   Compliant: {chk['compliant']}  |  Compliance rate: {chk['compliance_rate']}%")
    for param, detail in chk["parameters"].items():
        flag = "✓" if detail["compliant"] else "✗"
        print(f"     {flag} {param:<10} value={detail['value']:<6} min={detail['min_spec']} max={detail['max_spec']}")

    # 5) Blending two stocks
    print("\n5) Blending 60/40 — Source A (premium) + Source B (low-grade):")
    blend = CoalQualityAnalyzer.blend_coals(
        coal_samples=[
            {"gcv": 5800, "ash": 8.5, "sulfur": 0.5, "moisture": 10.0},
            {"gcv": 4200, "ash": 15.2, "sulfur": 1.1, "moisture": 18.0},
        ],
        weights=[0.60, 0.40],
    )
    for k in ("gcv", "ash", "sulfur", "moisture"):
        print(f"   {k:<10} {blend[k]}")

    print("\n" + "=" * 64)
    print("✅ Demo complete")
    print("=" * 64)


if __name__ == "__main__":
    main()
