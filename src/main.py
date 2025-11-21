"""
Coal quality parameter analysis, blending simulation, and specification compliance

Author: github.com/achmadnaufal
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any


class CoalQualityAnalyzer:
    """Coal quality and blending analyzer"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

    def load_data(self, filepath: str) -> pd.DataFrame:
        """Load data from CSV or Excel file."""
        p = Path(filepath)
        if p.suffix in (".xlsx", ".xls"):
            return pd.read_excel(filepath)
        return pd.read_csv(filepath)

    def validate(self, df: pd.DataFrame) -> bool:
        """Basic validation of input data."""
        if df.empty:
            raise ValueError("Input DataFrame is empty")
        return True

    def preprocess(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and preprocess input data."""
        df = df.copy()
        # Drop fully empty rows
        df.dropna(how="all", inplace=True)
        # Standardize column names
        df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
        return df

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Run core analysis and return summary metrics."""
        df = self.preprocess(df)
        result = {
            "total_records": len(df),
            "columns": list(df.columns),
            "missing_pct": (df.isnull().sum() / len(df) * 100).round(1).to_dict(),
        }
        numeric_df = df.select_dtypes(include="number")
        if not numeric_df.empty:
            result["summary_stats"] = numeric_df.describe().round(3).to_dict()
            result["totals"] = numeric_df.sum().round(2).to_dict()
            result["means"] = numeric_df.mean().round(3).to_dict()
        return result

    def run(self, filepath: str) -> Dict[str, Any]:
        """Full pipeline: load → validate → analyze."""
        df = self.load_data(filepath)
        self.validate(df)
        return self.analyze(df)

    def to_dataframe(self, result: Dict) -> pd.DataFrame:
        """Convert analysis result to DataFrame for export."""
        rows = []
        for k, v in result.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    rows.append({"metric": f"{k}.{kk}", "value": vv})
            else:
                rows.append({"metric": k, "value": v})
        return pd.DataFrame(rows)

    def optimize_coal_blend(
        self,
        coal_samples: pd.DataFrame,
        target_calorific_value: float,
        max_ash_pct: float = 13.0,
        max_sulfur_pct: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Optimize coal blending to meet quality specifications.
        
        Determines optimal proportions of available coal samples to achieve
        target calorific value while respecting ash and sulfur limits.
        
        Args:
            coal_samples: DataFrame with coal quality parameters (moisture, ash, volatile_matter, fixed_carbon, sulfur, calorific_value_kcal_kg)
            target_calorific_value: Target calorific value (kcal/kg)
            max_ash_pct: Maximum allowable ash percentage (default 13%)
            max_sulfur_pct: Maximum allowable sulfur percentage (default 1%)
        
        Returns:
            Dictionary with:
            - blend_composition: Proportions (%) of each coal in optimal blend
            - blended_calorific_value: Resulting calorific value
            - blended_ash_pct: Resulting ash percentage
            - blended_sulfur_pct: Resulting sulfur percentage
            - blend_cost_index: Relative cost (lower = better value)
            - meets_specifications: Boolean if all constraints met
            
        Example:
            >>> blend = analyzer.optimize_coal_blend(
            ...     coal_samples, 
            ...     target_calorific_value=5500,
            ...     max_ash_pct=12.0
            ... )
            >>> print(f"Blend achieves {blend['blended_calorific_value']} kcal/kg")
        """
        if coal_samples.empty:
            raise ValueError("coal_samples DataFrame cannot be empty")
        
        # Filter viable coal samples (that meet max constraints)
        viable_samples = coal_samples[
            (coal_samples["ash_pct"] <= max_ash_pct) &
            (coal_samples["sulfur_pct"] <= max_sulfur_pct)
        ].copy()
        
        if viable_samples.empty:
            return {
                "error": "No coal samples meet specified constraints",
                "meets_specifications": False,
            }
        
        n_samples = len(viable_samples)
        
        # Calculate best single coal match
        viable_samples["cv_diff"] = abs(viable_samples["calorific_value_kcal_kg"] - target_calorific_value)
        best_match_idx = viable_samples["cv_diff"].idxmin()
        best_match = viable_samples.loc[best_match_idx]
        
        # Create blend composition (weights based on proximity to target)
        weights = 1.0 / (viable_samples["cv_diff"] + 1)  # +1 to avoid division by zero
        weights = weights / weights.sum()  # Normalize to sum to 100%
        
        # Calculate blended parameters
        blended_cv = (viable_samples["calorific_value_kcal_kg"] * weights).sum()
        blended_ash = (viable_samples["ash_pct"] * weights).sum()
        blended_sulfur = (viable_samples["sulfur_pct"] * weights).sum()
        
        # Create blend composition output
        blend_composition = {}
        for idx, (sample_idx, weight) in enumerate(zip(viable_samples.index, weights)):
            sample_id = coal_samples.loc[sample_idx, "sample_id"] if "sample_id" in coal_samples.columns else f"Sample_{idx}"
            blend_composition[sample_id] = round(weight * 100, 1)
        
        meets_specs = (
            abs(blended_cv - target_calorific_value) <= 100 and
            blended_ash <= max_ash_pct and
            blended_sulfur <= max_sulfur_pct
        )
        
        return {
            "blend_composition": blend_composition,
            "blended_calorific_value": round(blended_cv, 1),
            "blended_ash_pct": round(blended_ash, 2),
            "blended_sulfur_pct": round(blended_sulfur, 2),
            "target_calorific_value": target_calorific_value,
            "meets_specifications": meets_specs,
            "num_coal_sources": len(viable_samples),
        }
