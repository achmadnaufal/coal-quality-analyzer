"""Package: coal-quality-analyzer"""

from .hardgrove_grindability_analyzer import (
    GrindabilityClass,
    HGIAnalysis,
    HGISample,
    analyze_batch,
    analyze_sample,
    bond_work_index,
    capacity_derate_percent,
    classify_grindability,
    correct_hgi_for_moisture,
    meets_specification,
    mill_specific_energy,
)
from .blend_ratio_optimizer import (
    BlendResult,
    BlendTarget,
    CoalSource,
    optimize_binary_blend,
    optimize_blend,
)

__all__ = [
    "GrindabilityClass",
    "HGIAnalysis",
    "HGISample",
    "analyze_batch",
    "analyze_sample",
    "bond_work_index",
    "capacity_derate_percent",
    "classify_grindability",
    "correct_hgi_for_moisture",
    "meets_specification",
    "mill_specific_energy",
    "BlendResult",
    "BlendTarget",
    "CoalSource",
    "optimize_binary_blend",
    "optimize_blend",
]
