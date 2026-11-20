import hmac
import json
import os

from django.utils import timezone

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import ProcessingArtifact, ProcessingRun
from .demuca_persistence import persist_demuca_evaluation
from .pipeline import normalize_pipeline_stages, result_semantic_status
from .pipeline import VALID_STATUS_TRANSITIONS
from .annotation_persistence import persist_annotation_cases


def _authorized(request):
    expected = getattr(settings, "ML_SERVICE_API_KEY", "") or os.getenv("ML_SERVICE_API_KEY", "")
    received = request.headers.get("X-ML-Service-Key", "")
    return bool(expected) and hmac.compare_digest(received, expected)


@csrf_exempt
@require_POST
def processing_callback(request):
    if not _authorized(request):
        return JsonResponse({"error": "service_not_authorized"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "invalid_json"}, status=400)

    run_id = payload.get("run_id")
    if not isinstance(run_id, str):
        return JsonResponse({"error": "run_id_required"}, status=400)

    try:
        run = ProcessingRun.objects.get(external_run_id=run_id)
    except ProcessingRun.DoesNotExist:
        return JsonResponse({"error": "processing_run_not_found"}, status=404)

    status = payload.get("status")
    valid_statuses = {choice for choice, _ in ProcessingRun.Status.choices}
    if status not in valid_statuses:
        return JsonResponse({"error": "invalid_status"}, status=400)
    if status not in VALID_STATUS_TRANSITIONS.get(run.status, set()):
        return JsonResponse(
            {
                "error": "invalid_status_transition",
                "from": run.status,
                "to": status,
            },
            status=409,
        )

    run.status = status
    now = timezone.now()
    if status == ProcessingRun.Status.RUNNING and run.started_at is None:
        run.started_at = now
    if status in {ProcessingRun.Status.COMPLETED, ProcessingRun.Status.FAILED, ProcessingRun.Status.CANCELLED}:
        run.finished_at = now
    run.result_json = payload.get("result") or {}
    if not isinstance(run.result_json, dict):
        run.result_json = {}
    run.result_json = {
        **run.result_json,
        "pipeline_stages": normalize_pipeline_stages(
            payload.get("pipeline_stages", run.result_json.get("pipeline_stages"))
        ),
        "semantic_status": payload.get("semantic_status")
        or result_semantic_status(run.result_json),
    }
    error = payload.get("error")
    if isinstance(error, dict):
        run.error_code = error.get("code")
        run.error_message = error.get("message")
    if isinstance(run.result_json, dict):
        run.source_sha256 = run.result_json.get("source_sha256", run.source_sha256)
    run.save()

    if status == ProcessingRun.Status.COMPLETED:
        evaluation = persist_demuca_evaluation(run)
        if evaluation:
            run.metadata_json = {
                **(run.metadata_json or {}),
                "demuca_evaluation_id": evaluation.pk,
                "demuca_persistence": "completed",
            }
            run.save(update_fields=["metadata_json", "updated_at"])
        persist_annotation_cases(run, run.result_json)

    artifacts = {}
    if isinstance(run.result_json, dict):
        artifacts = run.result_json.get("artifacts") or run.result_json.get("derived_artifacts") or {}
    if isinstance(artifacts, dict):
        for kind, uri in artifacts.items():
            if isinstance(uri, dict):
                uri = uri.get("uri") or uri.get("path")
            if not isinstance(uri, str) or not uri:
                continue
            ProcessingArtifact.objects.update_or_create(
                run=run,
                kind=kind,
                defaults={
                    "uri": uri,
                    "training_authorized": False,
                },
            )

    return JsonResponse({"ok": True, "run_id": run.external_run_id, "status": run.status})
