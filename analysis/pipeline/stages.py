from __future__ import annotations

from typing import Any


PIPELINE_STAGE_DEFINITIONS = (
    ("extraction", "Extracción y normalización"),
    ("segmentation", "Segmentación y sincronización"),
    ("pose", "Análisis de pose"),
    ("audio", "Características acústicas"),
    ("movement", "Movimiento e interacción"),
    ("validation", "Validación de artefactos"),
    ("inference", "Inferencia"),
    ("demuca", "Proyección DEMUCA"),
    ("human_review", "Revisión profesional"),
)

VALID_STATUS_TRANSITIONS = {
    "queued": {"queued", "running", "blocked_review", "completed", "failed", "cancelled"},
    "running": {"running", "blocked_review", "completed", "failed", "cancelled"},
    "blocked_review": {"blocked_review", "completed", "failed", "cancelled"},
    "completed": {"completed"},
    "failed": {"failed"},
    "cancelled": {"cancelled"},
}


def initial_pipeline_stages() -> list[dict[str, Any]]:
    return [
        {
            "id": stage_id,
            "label": label,
            "status": "pending",
            "progress": 0,
            "message": None,
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "artifact_kinds": [],
        }
        for stage_id, label in PIPELINE_STAGE_DEFINITIONS
    ]


def normalize_pipeline_stages(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return initial_pipeline_stages()

    definitions = dict(PIPELINE_STAGE_DEFINITIONS)
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        stage_id = item.get("id") or item.get("key")
        if not isinstance(stage_id, str) or stage_id not in definitions:
            continue
        status = item.get("status", "pending")
        if status not in {"pending", "running", "completed", "skipped", "blocked", "failed"}:
            status = "pending"
        progress = item.get("progress", 0)
        try:
            progress = max(0, min(100, int(progress)))
        except (TypeError, ValueError):
            progress = 0
        artifacts = item.get("artifact_kinds", item.get("artifacts", []))
        if not isinstance(artifacts, list):
            artifacts = []
        normalized.append(
            {
                "id": stage_id,
                "label": item.get("label") or definitions[stage_id],
                "status": status,
                "progress": progress,
                "message": item.get("message"),
                "started_at": item.get("started_at"),
                "finished_at": item.get("finished_at"),
                "duration_ms": item.get("duration_ms"),
                "artifact_kinds": [str(value) for value in artifacts],
            }
        )

    by_id = {stage["id"]: stage for stage in normalized}
    return [by_id.get(stage_id, default) for stage_id, default in (
        (stage_id, item)
        for (stage_id, _), item in zip(PIPELINE_STAGE_DEFINITIONS, initial_pipeline_stages())
    )]


def result_semantic_status(result: Any) -> str:
    if not isinstance(result, dict):
        return "pending"
    status = result.get("semantic_status")
    if status in {"authorized_model", "provisional_evidence", "unavailable", "provisional", "draft"}:
        return status
    model_predictions = result.get("model_predictions")
    demuca = result.get("demuca")
    if (
        isinstance(model_predictions, dict)
        and model_predictions.get("status") == "unavailable"
    ):
        return "provisional_evidence"
    if isinstance(demuca, dict) and demuca.get("review_required") is True:
        return "provisional_evidence"
    return "completed" if result.get("status") == "completed" else "pending"
