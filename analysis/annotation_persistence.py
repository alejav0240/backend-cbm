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


def _window_bounds(window: dict[str, Any]) -> tuple[float, float] | None:
    try:
        return float(window["start_seconds"]), float(window["end_seconds"])
    except (KeyError, TypeError, ValueError):
        return None


def _positive_predictions(window: dict[str, Any]) -> list[str]:
    predictions = window.get("predictions")
    if not isinstance(predictions, dict):
        return []
    return [
        label
        for label, value in predictions.items()
        if isinstance(label, str) and bool(value)
    ]


def _build_case(
    window: dict[str, Any],
    label: str,
    bounds: tuple[float, float],
    source: str,
) -> dict[str, Any]:
    modality = label.split("__", 1)[0] if "__" in label else "multimodal"
    return {
        "window_id": str(window["window_id"]),
        "label": label,
        "start_seconds": bounds[0],
        "end_seconds": bounds[1],
        "modality": modality,
        "actor_role": "unknown",
        "source": source,
        "proposal_json": window,
    }


def _positive_cases(result: dict[str, Any]) -> list[dict[str, Any]]:
    source = "model" if result.get("semantic_status") == "authorized_model" else "provisional"
    cases = []
    for window in _prediction_windows(result):
        window_id = str(window.get("window_id") or "")
        bounds = _window_bounds(window)
        if not window_id or bounds is None:
            continue
        cases.extend(
            _build_case(window, label, bounds, source)
            for label in _positive_predictions(window)
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
