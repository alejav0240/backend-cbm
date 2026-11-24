import hmac
import json
import os

from django.utils import timezone

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import ProcessingArtifact, ProcessingRun
from .pipeline.persistence import persist_demuca_evaluation
from .pipeline import normalize_pipeline_stages, result_semantic_status
from .pipeline import VALID_STATUS_TRANSITIONS
from .annotation_persistence import persist_annotation_cases


def _authorized(request):
    expected = getattr(settings, "ML_SERVICE_API_KEY", "") or os.getenv("ML_SERVICE_API_KEY", "")
    received = request.headers.get("X-ML-Service-Key", "")
    return bool(expected) and hmac.compare_digest(received, expected)


def _normalize_processing_error(error):
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    message = error.get("message")
    if (
        code == "ValueError"
        and isinstance(message, str)
        and "windows_missing_or_empty" in message
    ):
        return {
            "code": "insufficient_duration_for_window",
            "message": (
                "La sesión es demasiado corta para generar una ventana completa "
                "de análisis. Se requiere una duración mayor o igual a 5 segundos."
            ),
        }
    return error


def _update_run_status(run, status):
    run.status = status
    now = timezone.now()
    if status == ProcessingRun.Status.RUNNING and run.started_at is None:
        run.started_at = now
    if status in {
        ProcessingRun.Status.COMPLETED,
        ProcessingRun.Status.FAILED,
        ProcessingRun.Status.CANCELLED,
    }:
        run.finished_at = now


def _normalize_callback_result(payload):
    result = payload.get("result")
    result = result if isinstance(result, dict) else {}
    return {
        **result,
        "pipeline_stages": normalize_pipeline_stages(
            payload.get("pipeline_stages", result.get("pipeline_stages"))
        ),
        "semantic_status": payload.get("semantic_status")
        or result_semantic_status(result),
    }


def _persist_callback_artifacts(run, artifacts):
    if not isinstance(artifacts, dict):
        return
    for kind, artifact in artifacts.items():
        metadata = artifact if isinstance(artifact, dict) else {}
        uri = (
            metadata.get("uri") or metadata.get("path")
            if isinstance(artifact, dict)
            else artifact
        )
        if isinstance(uri, dict):
            uri = uri.get("uri") or uri.get("path")
        if not isinstance(uri, str) or not uri:
            continue
        ProcessingArtifact.objects.update_or_create(
            run=run,
            kind=kind,
            defaults={
                "uri": uri,
                "sha256": metadata.get("sha256") or "",
                "training_authorized": metadata.get("training_authorized") is True,
                "metadata_json": metadata,
            },
        )


def _parse_callback_payload(request):
    try:
        return json.loads(request.body.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, JsonResponse({"error": "invalid_json"}, status=400)


def _find_callback_run(payload):
    run_id = payload.get("run_id")
    if not isinstance(run_id, str):
        return None, JsonResponse({"error": "run_id_required"}, status=400)
    try:
        return ProcessingRun.objects.get(external_run_id=run_id), None
    except ProcessingRun.DoesNotExist:
        return None, JsonResponse({"error": "processing_run_not_found"}, status=404)


def _validate_callback_status(run, payload):
    status = payload.get("status")
    valid_statuses = {choice for choice, _ in ProcessingRun.Status.choices}
    if status not in valid_statuses:
        return None, JsonResponse({"error": "invalid_status"}, status=400)
    if status not in VALID_STATUS_TRANSITIONS.get(run.status, set()):
        return None, JsonResponse(
            {
                "error": "invalid_status_transition",
                "from": run.status,
                "to": status,
            },
            status=409,
        )
    return status, None


def _persist_completed_callback(run):
    evaluation = persist_demuca_evaluation(run)
    if evaluation:
        run.metadata_json = {
            **(run.metadata_json or {}),
            "demuca_evaluation_id": evaluation.pk,
            "demuca_persistence": "completed",
        }
        run.save(update_fields=["metadata_json", "updated_at"])
    persist_annotation_cases(run, run.result_json)


@csrf_exempt
@require_POST
def processing_callback(request):
    if not _authorized(request):
        return JsonResponse({"error": "service_not_authorized"}, status=401)

    payload, response = _parse_callback_payload(request)
    if response:
        return response
    run, response = _find_callback_run(payload)
    if response:
        return response
    status, response = _validate_callback_status(run, payload)
    if response:
        return response

    _update_run_status(run, status)
    run.result_json = _normalize_callback_result(payload)
    error = _normalize_processing_error(payload.get("error"))
    if isinstance(error, dict):
        run.error_code = error.get("code") or ""
        run.error_message = error.get("message") or ""
    if isinstance(run.result_json, dict):
        run.source_sha256 = run.result_json.get("source_sha256") or run.source_sha256
    run.save()

    if status == ProcessingRun.Status.COMPLETED:
        _persist_completed_callback(run)

    artifacts = run.result_json.get("artifacts") or run.result_json.get("derived_artifacts")
    _persist_callback_artifacts(run, artifacts)

    return JsonResponse({"ok": True, "run_id": run.external_run_id, "status": run.status})
