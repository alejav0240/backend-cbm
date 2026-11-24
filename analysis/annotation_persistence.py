from __future__ import annotations

from typing import Any

from .annotation_models import AnnotationCase
from .models import ProcessingRun


def _prediction_windows(result: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("model_predictions", "prediction_review", "provisional_evidence"):
        payload = result.get(key)
        if isinstance(payload, dict) and isinstance(payload.get("windows"), list):
            return [item for item in payload["windows"] if isinstance(item, dict)]
    return []


def _positive_cases(
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    source = "model" if result.get("semantic_status") == "authorized_model" else "provisional"
    cases = []
    for window in _prediction_windows(result):
        predictions = window.get("predictions")
        if not isinstance(predictions, dict):
            continue
        try:
            start = float(window["start_seconds"])
            end = float(window["end_seconds"])
        except (KeyError, TypeError, ValueError):
            continue
        window_id = str(window.get("window_id") or "")
        if not window_id:
            continue
        for label, value in predictions.items():
            if isinstance(label, str) and bool(value):
                modality = label.split("__", 1)[0] if "__" in label else "multimodal"
                cases.append(
                    {
                        "window_id": window_id,
                        "label": label,
                        "start_seconds": start,
                        "end_seconds": end,
                        "modality": modality,
                        "actor_role": "unknown",
                        "source": source,
                        "proposal_json": window,
                    }
                )
    return cases


def persist_annotation_cases(run: ProcessingRun, result: dict[str, Any]) -> int:
    """Create review cases idempotently from positive temporal predictions."""
    if not result.get("review_required"):
        return 0

    return sum(
        AnnotationCase.objects.get_or_create(
            run=run,
            window_id=case["window_id"],
            label=case["label"],
            defaults={key: value for key, value in case.items() if key not in {"window_id", "label"}},
        )[1]
        for case in _positive_cases(result)
    )
