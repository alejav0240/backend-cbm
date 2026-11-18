import hmac
import json
import os

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import ProcessingArtifact, ProcessingRun


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

    run.status = status
    run.result_json = payload.get("result") or {}
    error = payload.get("error")
    if isinstance(error, dict):
        run.error_code = error.get("code")
        run.error_message = error.get("message")
    if isinstance(run.result_json, dict):
        run.source_sha256 = run.result_json.get("source_sha256", run.source_sha256)
    run.save()

    artifacts = run.result_json.get("artifacts", {}) if isinstance(run.result_json, dict) else {}
    if isinstance(artifacts, dict):
        for kind, uri in artifacts.items():
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
