"""Pipeline lifecycle stages and persistence adapters for ML processing runs."""

from .stages import (
    VALID_STATUS_TRANSITIONS,
    initial_pipeline_stages,
    normalize_pipeline_stages,
    result_semantic_status,
)

__all__ = [
    "VALID_STATUS_TRANSITIONS",
    "initial_pipeline_stages",
    "normalize_pipeline_stages",
    "result_semantic_status",
]
