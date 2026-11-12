"""HTTP adapter for the multimodal pipeline module."""

from __future__ import annotations

import os
import json
import csv
import hashlib
import logging
from pathlib import Path
import re
import tempfile
import uuid
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from functools import wraps

from graphql_jwt.backends import JSONWebTokenBackend
from graphql_jwt.exceptions import JSONWebTokenError

from .servicios import ErrorPipelineMultimodal, ServicioPipelineMultimodal
from .models import (
    DATASET_FEATURE_COLUMNS,
    DATASET_LABEL_COLUMNS,
    ResultadoAnalisis,
    TherapistDataset,
    TherapistDatasetSample,
    TrabajoAnalisis,
    validate_annotation_values,
    validate_dataset_values,
)
from .demuca_review import merge_demuca_data
from ml.tracking import log_run

EXTENSIONES_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ERROR_NO_AUTORIZADO = "No autorizado."
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_LOGGER = logging.getLogger(__name__)


def _video_extension(filename):
    """Return a fixed extension value, never the raw user-provided suffix."""
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        ".mp4": ".mp4",
        ".mov": ".mov",
        ".avi": ".avi",
        ".mkv": ".mkv",
        ".webm": ".webm",
    }.get(suffix)


def _session_id(value):
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate if _SESSION_ID_RE.fullmatch(candidate) else None


def _managed_media_path(value):
    """Resolve a stored path only when it remains inside MEDIA_ROOT."""
    if not isinstance(value, str) or not value:
        return None
    root = Path(settings.MEDIA_ROOT).resolve()
    candidate = Path(value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _safe_model_path(value):
    """Resolve model artifacts only from application-controlled directories."""
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value).resolve()
    allowed_roots = (Path(settings.BASE_DIR).resolve(), Path(settings.MEDIA_ROOT).resolve())
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        return None
    return candidate if candidate.is_file() else None


def _invalid_request(error):
    _LOGGER.warning("Invalid multimodal request: %s", error)
    return JsonResponse({"error": "invalid_request"}, status=400)


def _api_login_required(view):
    """Authenticate REST callers through Django sessions or the existing JWT flow."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            authorization = request.headers.get("Authorization", "")
            scheme, _, token = authorization.partition(" ")
            if scheme.upper() in {"JWT", "BEARER"} and token:
                try:
                    user = JSONWebTokenBackend().authenticate(request, token=token)
                except JSONWebTokenError:
                    user = None
                if user is not None:
                    request.user = user
        if not request.user.is_authenticated:
            return JsonResponse({"error": "authentication_required"}, status=401)
        return view(request, *args, **kwargs)
    return wrapped


def _json_body(request):
    try:
        value = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValidationError("invalid_json")
    if not isinstance(value, dict):
        raise ValidationError("json_object_required")
    return value


def _mlops_lineage(payload):
    if not isinstance(payload, dict):
        return {}
    mlflow_value = payload.get("mlflow")
    predictions_value = payload.get("model_predictions")
    mlflow: dict[str, Any] = dict(mlflow_value) if isinstance(mlflow_value, dict) else {}
    predictions: dict[str, Any] = dict(predictions_value) if isinstance(predictions_value, dict) else {}
    model_path = predictions.get("model_path")
    model_sha256 = ""
    path = _safe_model_path(model_path)
    if path is not None:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        model_sha256 = digest.hexdigest()
    return {
        "mlflow_run_id": str(mlflow.get("run_id") or ""),
        "mlflow_experiment": str(mlflow.get("experiment") or ""),
        "mlflow_model_name": str(predictions.get("model_type") or ""),
        "mlflow_model_version": str(predictions.get("model_version") or ""),
        "model_sha256": model_sha256,
        "dataset_hash": str(payload.get("dataset_hash") or ""),
    }


def _dataset_for_user(request, dataset_id):
    queryset = TherapistDataset.objects.all()
    if not request.user.is_staff:
        queryset = queryset.filter(owner=request.user)
    return queryset.filter(pk=dataset_id).first()


def _dataset_payload(dataset):
    samples = dataset.samples.all()
    return {
        "id": dataset.id,
        "name": dataset.name,
        "description": dataset.description,
        "status": dataset.status,
        "training_authorized": dataset.training_authorized,
        "authorized_at": dataset.authorized_at.isoformat() if dataset.authorized_at else None,
        "sample_count": samples.count(),
        "reviewed_count": samples.filter(reviewed=True).count(),
        "created_at": dataset.created_at.isoformat(),
        "updated_at": dataset.updated_at.isoformat(),
    }


def _sample_payload(sample):
    return {
        "id": sample.id,
        "session_id": sample.session_id,
        "window_id": sample.window_id,
        "features": sample.features,
        "labels": sample.labels,
        "reviewed": sample.reviewed,
        "start_time": sample.start_time,
        "end_time": sample.end_time,
        "demuca_phase": sample.demuca_phase,
        "sound_tags": sample.sound_tags,
        "movement_tags": sample.movement_tags,
        "interaction_tags": sample.interaction_tags,
        "derived_features": sample.derived_features,
        "pose_landmarks": sample.pose_landmarks,
        "artifact_payload": sample.artifact_payload,
        "training_authorized": False,
        "updated_at": sample.updated_at.isoformat(),
    }


def _annotation_values(body):
    required = ("start_time", "end_time", "demuca_phase", "sound_tags", "movement_tags", "interaction_tags")
    if any(field not in body for field in required):
        raise ValidationError("annotation window fields are required")
    tags = {field: body[field] for field in ("sound_tags", "movement_tags", "interaction_tags")}
    derived_features = body.get("derived_features", {})
    pose_landmarks = body.get("pose_landmarks", [])
    artifact_payload = body.get("artifact_payload", {})
    validate_annotation_values(body["start_time"], body["end_time"], body["demuca_phase"], tags, derived_features, pose_landmarks, artifact_payload)
    return {
        "start_time": body["start_time"], "end_time": body["end_time"],
        "demuca_phase": body["demuca_phase"].strip(), **tags,
        "derived_features": derived_features, "pose_landmarks": pose_landmarks,
        "artifact_payload": artifact_payload,
    }


@_api_login_required
@require_http_methods(["GET", "POST"])
def datasets(request):
    if request.method == "GET":
        queryset = TherapistDataset.objects.all() if request.user.is_staff else TherapistDataset.objects.filter(owner=request.user)
        return JsonResponse({"datasets": [_dataset_payload(dataset) for dataset in queryset]})
    try:
        body = _json_body(request)
        name = body.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("name is required")
        description = body.get("description", "")
        if not isinstance(description, str):
            raise ValidationError("description must be a string")
        dataset = TherapistDataset.objects.create(owner=request.user, name=name.strip(), description=description)
    except (ValidationError, IntegrityError) as error:
        return _invalid_request(error)
    return JsonResponse(_dataset_payload(dataset), status=201)


@_api_login_required
@require_GET
def dataset_detail(request, dataset_id):
    dataset = _dataset_for_user(request, dataset_id)
    if dataset is None:
        return JsonResponse({"error": "dataset_not_found"}, status=404)
    return JsonResponse({
        "dataset": _dataset_payload(dataset),
        "samples": [_sample_payload(sample) for sample in dataset.samples.all()],
        "can_authorize": request.user.is_staff,
    })


@_api_login_required
@require_POST
def create_dataset_sample(request, dataset_id):
    dataset = _dataset_for_user(request, dataset_id)
    if dataset is None:
        return JsonResponse({"error": "dataset_not_found"}, status=404)
    try:
        body = _json_body(request)
        session_id = body.get("session_id")
        window_id = body.get("window_id")
        if not isinstance(session_id, str) or not session_id.strip() or not isinstance(window_id, str) or not window_id.strip():
            raise ValidationError("session_id and window_id are required")
        validate_dataset_values(body.get("features"), body.get("labels"))
        normalized_session_id, normalized_window_id = session_id.strip(), window_id.strip()
        if TherapistDatasetSample.objects.filter(
            dataset=dataset, session_id=normalized_session_id, window_id=normalized_window_id
        ).exists():
            raise ValidationError("duplicate sample session_id and window_id")
        with transaction.atomic():
            sample = TherapistDatasetSample.objects.create(
                dataset=dataset, session_id=normalized_session_id, window_id=normalized_window_id,
                features=body["features"], labels=body["labels"],
            )
    except (ValidationError, IntegrityError) as error:
        return _invalid_request(error)
    return JsonResponse(_sample_payload(sample), status=201)


@_api_login_required
@require_POST
def create_dataset_annotation(request, dataset_id):
    dataset = _dataset_for_user(request, dataset_id)
    if dataset is None:
        return JsonResponse({"error": "dataset_not_found"}, status=404)
    try:
        body = _json_body(request)
        session_id, window_id = body.get("session_id"), body.get("window_id")
        if not isinstance(session_id, str) or not session_id.strip() or not isinstance(window_id, str) or not window_id.strip():
            raise ValidationError("session_id and window_id are required")
        annotation = _annotation_values(body)
        features = body.get("features", annotation["derived_features"])
        labels = body.get("labels", {f"visual__{annotation['demuca_phase']}": 1} if annotation["demuca_phase"] in {"MOVIMIENTO", "CONTACTO_VISUAL"} else {"visual__MOVIMIENTO": 0})
        validate_dataset_values(features, labels)
        if TherapistDatasetSample.objects.filter(dataset=dataset, session_id=session_id.strip(), window_id=window_id.strip()).exists():
            raise ValidationError("duplicate sample session_id and window_id")
        sample = TherapistDatasetSample.objects.create(
            dataset=dataset, session_id=session_id.strip(), window_id=window_id.strip(),
            features=features, labels=labels, **annotation,
        )
    except (ValidationError, IntegrityError) as error:
        return _invalid_request(error)
    return JsonResponse(_sample_payload(sample), status=201)


def _annotation_window_payload(sample):
    return {
        "id": str(sample.pk),
        "session_id": sample.session_id,
        "start_time": sample.start_time,
        "end_time": sample.end_time,
        "demuca_phase": sample.demuca_phase,
        "tags": {
            "sonido": sample.sound_tags,
            "movimiento": sample.movement_tags,
            "interaccion": sample.interaction_tags,
        },
        "landmarks": sample.pose_landmarks,
        "features": sample.derived_features,
        "created_at": sample.updated_at.isoformat(),
    }


def _annotation_dataset_for_user(request, session_id):
    name = f"Sesión {session_id} — anotaciones"
    dataset, _ = TherapistDataset.objects.get_or_create(
        owner=request.user,
        name=name,
        defaults={"description": "Ventanas anotadas desde la sesión de musicoterapia."},
    )
    return dataset


def _artifact_payload_for_session(session_id):
    result = ResultadoAnalisis.objects.filter(session_id=session_id).first()
    payload = result.resultado if result and isinstance(result.resultado, dict) else {}
    pose_landmarks = payload.get("pose_landmarks", [])
    if not isinstance(pose_landmarks, (dict, list)) or not pose_landmarks:
        configured_root = Path(os.environ.get("MULTIMODAL_PROJECT_ROOT", Path(__file__).resolve().parents[1])).resolve()
        if "/" not in session_id and "\\" not in session_id:
            roots = [configured_root, configured_root.parent, Path(settings.BASE_DIR)]
            for root in dict.fromkeys(roots):
                artifact = root / "dataset" / "dataset" / "sessions" / session_id / "processed" / "features" / "pose_landmarks.json"
                try:
                    if artifact.is_file():
                        pose_landmarks = json.loads(artifact.read_text(encoding="utf-8"))
                        break
                except (OSError, json.JSONDecodeError):
                    pose_landmarks = []
    return payload, pose_landmarks


@_api_login_required
@require_http_methods(["GET", "POST"])
def annotation_windows(request, session_id):
    dataset = _annotation_dataset_for_user(request, session_id)
    if request.method == "GET":
        samples = dataset.samples.filter(session_id=session_id).order_by("start_time", "id")
        return JsonResponse({"windows": [_annotation_window_payload(sample) for sample in samples]})
    try:
        body = _json_body(request)
        tags = body.get("tags") or {}
        normalized_tags = {
            "sound_tags": tags.get("sonido", tags.get("sound_tags", [])),
            "movement_tags": tags.get("movimiento", tags.get("movement_tags", [])),
            "interaction_tags": tags.get("interaccion", tags.get("interaction_tags", [])),
        }
        start_time = body.get("start_time")
        end_time = body.get("end_time")
        demuca_phase = body.get("demuca_phase", "")
        derived_features = body.get("features", {})
        pose_landmarks = body.get("landmarks", [])
        artifact_payload = body.get("artifact_payload", {})
        validate_annotation_values(start_time, end_time, demuca_phase, normalized_tags, derived_features, pose_landmarks, artifact_payload)
        features = {column: float(derived_features.get(column, 0.0)) for column in DATASET_FEATURE_COLUMNS}
        labels = {column: 0 for column in DATASET_LABEL_COLUMNS}
        window_id = str(body.get("window_id") or f"{session_id}_A{dataset.samples.filter(session_id=session_id).count():04d}")
        if dataset.samples.filter(session_id=session_id, window_id=window_id).exists():
            raise ValidationError("duplicate annotation window")
        sample = TherapistDatasetSample.objects.create(
            dataset=dataset,
            session_id=session_id,
            window_id=window_id,
            features=features,
            labels=labels,
            start_time=start_time,
            end_time=end_time,
            demuca_phase=demuca_phase.strip(),
            sound_tags=normalized_tags["sound_tags"],
            movement_tags=normalized_tags["movement_tags"],
            interaction_tags=normalized_tags["interaction_tags"],
            derived_features=derived_features,
            pose_landmarks=pose_landmarks,
            artifact_payload=artifact_payload,
        )
    except (ValidationError, IntegrityError) as error:
        return _invalid_request(error)
    return JsonResponse(_annotation_window_payload(sample), status=201)


@_api_login_required
@require_GET
def session_artifacts_for_user(request, session_id):
    payload, pose_landmarks = _artifact_payload_for_session(session_id)
    return JsonResponse({
        "session_id": session_id,
        "artifact_payload": payload,
        "pose_landmarks": pose_landmarks,
        "training_authorized": False,
    })


@_api_login_required
@require_GET
def session_artifacts(request, dataset_id, session_id):
    if _dataset_for_user(request, dataset_id) is None:
        return JsonResponse({"error": "dataset_not_found"}, status=404)
    result = ResultadoAnalisis.objects.filter(session_id=session_id).first()
    if result is None:
        return JsonResponse({"status": "pending", "session_id": session_id}, status=202)
    payload = result.resultado if isinstance(result.resultado, dict) else {}
    return JsonResponse({
        "session_id": session_id,
        "artifact_payload": payload,
        "pose_landmarks": payload.get("pose_landmarks", []),
        "training_authorized": False,
    })


@_api_login_required
@require_http_methods(["PATCH"])
def update_dataset_sample(request, dataset_id, sample_id):
    dataset = _dataset_for_user(request, dataset_id)
    if dataset is None:
        return JsonResponse({"error": "dataset_not_found"}, status=404)
    sample = dataset.samples.filter(pk=sample_id).first()
    if sample is None:
        return JsonResponse({"error": "sample_not_found"}, status=404)
    try:
        body = _json_body(request)
        unknown = set(body) - {"features", "labels", "reviewed", "start_time", "end_time", "demuca_phase", "sound_tags", "movement_tags", "interaction_tags", "derived_features", "pose_landmarks", "artifact_payload"}
        if unknown:
            raise ValidationError("unknown sample fields")
        features = body.get("features", sample.features)
        labels = body.get("labels", sample.labels)
        validate_dataset_values(features, labels)
        if "reviewed" in body and not isinstance(body["reviewed"], bool):
            raise ValidationError("reviewed must be boolean")
        annotation_fields = {field: body[field] for field in ("start_time", "end_time", "demuca_phase", "sound_tags", "movement_tags", "interaction_tags", "derived_features", "pose_landmarks", "artifact_payload") if field in body}
        if annotation_fields:
            merged = {field: getattr(sample, field) for field in ("start_time", "end_time", "demuca_phase", "sound_tags", "movement_tags", "interaction_tags", "derived_features", "pose_landmarks", "artifact_payload")}
            merged.update(annotation_fields)
            _annotation_values(merged)
        sample.features, sample.labels = features, labels
        if "reviewed" in body:
            sample.reviewed = body["reviewed"]
        for field, value in annotation_fields.items():
            setattr(sample, field, value)
        sample.save(update_fields=["features", "labels", "reviewed", *annotation_fields, "updated_at"])
    except ValidationError as error:
        return _invalid_request(error)
    return JsonResponse(_sample_payload(sample))


@_api_login_required
@require_POST
def export_dataset(request, dataset_id):
    dataset = _dataset_for_user(request, dataset_id)
    if dataset is None:
        return JsonResponse({"error": "dataset_not_found"}, status=404)
    samples = list(dataset.samples.all())
    directory = Path(settings.MEDIA_ROOT) / "datasets" / str(dataset.id)
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "dataset.csv"
    manifest_path = directory / "manifest.json"
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=[*DATASET_FEATURE_COLUMNS, *DATASET_LABEL_COLUMNS])
        writer.writeheader()
        for sample in samples:
            writer.writerow({**sample.features, **sample.labels})
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    manifest = {
        "dataset_id": dataset.id, "status": dataset.status, "rows": len(samples),
        "feature_columns": list(DATASET_FEATURE_COLUMNS), "label_columns": list(DATASET_LABEL_COLUMNS),
        "sha256": digest, "training_authorized": dataset.training_authorized,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    tracking = {"status": "unavailable", "reason": "tracking_not_attempted"}
    try:
        project_root = Path(os.environ.get("MULTIMODAL_PROJECT_ROOT", Path(__file__).resolve().parents[1])).resolve()
        experiment = os.environ.get("MLFLOW_EXPERIMENT", "cbm-video-pipeline")
        run_id = log_run(
            experiment_name=experiment,
            run_name=f"therapist-dataset-{dataset.pk}",
            params={"dataset_id": dataset.pk, "dataset_status": dataset.status},
            metrics={"dataset_rows": len(samples), "reviewed_rows": sum(sample.reviewed for sample in samples)},
            tags={"pipeline": "therapist-dataset-export", "training_authorized": "false"},
            artifacts=[manifest_path],
            tracking_uri=os.environ.get("MLFLOW_TRACKING_URI"),
            project_root=project_root,
            dataset_path=csv_path,
            dataset_name=f"therapist-dataset-{dataset.pk}",
            dataset_columns=tuple([*DATASET_FEATURE_COLUMNS, *DATASET_LABEL_COLUMNS]),
        )
        tracking = {"status": "tracked", "run_id": run_id, "experiment": experiment}
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        _LOGGER.warning("MLflow tracking unavailable: %s", error)
        if os.environ.get("MLFLOW_REQUIRED", "false").lower() == "true":
            return JsonResponse({"error": "mlflow_tracking_required"}, status=503)
        tracking = {"status": "unavailable", "reason": "tracking_unavailable"}
    return JsonResponse({
        "dataset_id": dataset.id,
        "download_url": f"{settings.MEDIA_URL.rstrip('/')}/datasets/{dataset.id}/dataset.csv",
        "rows": len(samples), "sha256": digest, "status": dataset.status,
        "mlflow": tracking,
    })


@_api_login_required
@require_POST
def authorize_dataset(request, dataset_id):
    """Authorize a fully reviewed dataset for a later training run."""
    if not request.user.is_staff:
        return JsonResponse({"error": "staff_authorization_required"}, status=403)
    dataset = TherapistDataset.objects.filter(pk=dataset_id).first()
    if dataset is None:
        return JsonResponse({"error": "dataset_not_found"}, status=404)
    if not dataset.samples.exists():
        return JsonResponse({"error": "dataset_has_no_samples"}, status=400)
    if dataset.samples.filter(reviewed=False).exists():
        return JsonResponse({"error": "all_samples_must_be_reviewed"}, status=400)
    dataset.training_authorized = True
    dataset.status = TherapistDataset.Status.AUTHORIZED
    dataset.authorized_by = request.user
    dataset.authorized_at = timezone.now()
    dataset.save(update_fields=["training_authorized", "status", "authorized_by", "authorized_at", "updated_at"])
    return JsonResponse(_dataset_payload(dataset))


def _autorizado(request) -> bool:
    esperado = os.environ.get("MULTIMODAL_SERVICE_KEY", "")
    if not esperado:
        return bool(getattr(settings, "DEBUG", False))
    return request.headers.get("X-Service-Key", "") == esperado


def _respuesta(cuerpo: dict, estado: int, request_id: str) -> JsonResponse:
    respuesta = JsonResponse(cuerpo, status=estado)
    respuesta["X-Request-ID"] = request_id
    return respuesta


@require_POST
def analizar_video(request):
    request_id = request.headers.get("X-Request-ID") or f"multimodal-{uuid.uuid4().hex[:12]}"
    if not _autorizado(request):
        return _respuesta({"status": "failed", "error": ERROR_NO_AUTORIZADO}, 403, request_id)
    video = request.FILES.get("video")
    if video is None:
        return _respuesta({"status": "failed", "error": "Se requiere el campo video."}, 400, request_id)
    if video.size > int(os.environ.get("MULTIMODAL_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024))):
        return _respuesta({"status": "failed", "error": "El video excede el tamaño máximo permitido."}, 413, request_id)
    extension = _video_extension(video.name)
    if extension is None:
        return _respuesta({"status": "failed", "error": "Formato de video no soportado."}, 400, request_id)

    session_id = _session_id(request.POST.get("session_id") or f"HTTP-{uuid.uuid4().hex[:12]}")
    if session_id is None:
        return _respuesta({"status": "failed", "error": "session_id inválido."}, 400, request_id)
    servicio = ServicioPipelineMultimodal.configurado()
    Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="multimodal-", dir=settings.MEDIA_ROOT) as temporal:
        entrada = Path(temporal) / f"entrada{extension}"
        with entrada.open("wb") as destino:
            for bloque in video.chunks():
                destino.write(bloque)
        try:
            cuerpo = servicio.ejecutar(entrada, session_id)
            ResultadoAnalisis.objects.create(
                session_id=session_id,
                estado=str(cuerpo.get("status", "completed")),
                resultado=cuerpo,
                request_id=request_id,
                **_mlops_lineage(cuerpo),
            )
        except ErrorPipelineMultimodal as error:
            _LOGGER.warning("Multimodal pipeline failed: %s", error)
            return _respuesta({"status": "failed", "error": "pipeline_failed"}, 502, request_id)
    estado = 422 if cuerpo.get("status") == "failed" else 200
    return _respuesta(cuerpo, estado, request_id)


@require_GET
def obtener_resultado(request, session_id: str):
    request_id = request.headers.get("X-Request-ID") or f"multimodal-{uuid.uuid4().hex[:12]}"
    if not _autorizado(request):
        return _respuesta({"status": "failed", "error": ERROR_NO_AUTORIZADO}, 403, request_id)
    resultado = ResultadoAnalisis.objects.filter(session_id=session_id).first()
    if resultado is None:
        return _respuesta({"status": "pending", "session_id": session_id}, 202, request_id)
    return _respuesta(resultado.resultado, 200, request_id)


@_api_login_required
@require_GET
def obtener_lineage_mlops(request, session_id: str):
    """Expose read-only MLflow/model lineage without exposing raw artifacts."""
    resultado = ResultadoAnalisis.objects.filter(session_id=session_id).first()
    if resultado is None:
        return JsonResponse({"error": "analysis_not_found"}, status=404)
    return JsonResponse({
        "session_id": resultado.session_id,
        "estado": resultado.estado,
        "mlflow_run_id": resultado.mlflow_run_id,
        "mlflow_experiment": resultado.mlflow_experiment,
        "mlflow_model_name": resultado.mlflow_model_name,
        "mlflow_model_version": resultado.mlflow_model_version,
        "model_sha256": resultado.model_sha256,
        "dataset_hash": resultado.dataset_hash,
        "created_at": resultado.creado_en.isoformat(),
    })


@_api_login_required
@require_GET
def listar_modelos_mlops(request):
    """List model lineage observed by Django; promotion remains outside this API."""
    resultados = ResultadoAnalisis.objects.exclude(mlflow_model_name="").order_by("-creado_en")[:100]
    return JsonResponse({"models": [{
        "session_id": item.session_id,
        "run_id": item.mlflow_run_id,
        "experiment": item.mlflow_experiment,
        "name": item.mlflow_model_name,
        "version": item.mlflow_model_version,
        "model_sha256": item.model_sha256,
        "dataset_hash": item.dataset_hash,
        "created_at": item.creado_en.isoformat(),
    } for item in resultados]})


@require_http_methods(["PATCH"])
def actualizar_demuca(request, session_id: str):
    request_id = request.headers.get("X-Request-ID") or f"multimodal-{uuid.uuid4().hex[:12]}"
    if not _autorizado(request):
        return _respuesta({"status": "failed", "error": ERROR_NO_AUTORIZADO}, 403, request_id)
    resultado = ResultadoAnalisis.objects.filter(session_id=session_id).first()
    if resultado is None:
        return _respuesta({"status": "failed", "error": "Resultado no encontrado."}, 404, request_id)
    try:
        cuerpo = json.loads(request.body.decode("utf-8"))
        incoming = cuerpo.get("demuca") if isinstance(cuerpo, dict) else None
        if not isinstance(incoming, dict):
            raise ValueError("demuca_field_required")
        resultado_actual = resultado.resultado if isinstance(resultado.resultado, dict) else {}
        demuca_actual = resultado_actual.get("demuca")
        demuca_actual = demuca_actual if isinstance(demuca_actual, dict) else {}
        datos_actuales = demuca_actual.get("data")
        datos = merge_demuca_data(datos_actuales, incoming, session_id=session_id)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _LOGGER.warning("Invalid DEMUCA update: %s", error)
        return _respuesta({"status": "failed", "error": "invalid_request"}, 400, request_id)

    actualizado = dict(resultado_actual)
    actualizado["demuca"] = {
        **demuca_actual,
        "status": "human_reviewed",
        "data": datos,
        "review_required": False,
        "human_reviewed": True,
        "ground_truth": False,
        "training_authorized": False,
    }
    resultado.resultado = actualizado
    resultado.estado = "human_reviewed"
    resultado.save(update_fields=["resultado", "estado"])
    return _respuesta(actualizado, 200, request_id)


@require_POST
def crear_trabajo(request):
    request_id = request.headers.get("X-Request-ID") or f"multimodal-{uuid.uuid4().hex[:12]}"
    if not _autorizado(request):
        return _respuesta({"status": "failed", "error": ERROR_NO_AUTORIZADO}, 403, request_id)
    video = request.FILES.get("video")
    if video is None:
        return _respuesta({"status": "failed", "error": "Se requiere el campo video."}, 400, request_id)
    extension = _video_extension(video.name)
    if extension is None:
        return _respuesta({"status": "failed", "error": "Formato de video no soportado."}, 400, request_id)
    if video.size > int(os.environ.get("MULTIMODAL_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024))):
        return _respuesta({"status": "failed", "error": "El video excede el tamaño máximo permitido."}, 413, request_id)
    session_id = _session_id(request.POST.get("session_id") or f"HTTP-{uuid.uuid4().hex[:12]}")
    if session_id is None:
        return _respuesta({"status": "failed", "error": "session_id inválido."}, 400, request_id)
    carpeta = Path(settings.MEDIA_ROOT) / "pipeline_jobs"
    carpeta.mkdir(parents=True, exist_ok=True)
    temporal = carpeta / f".upload-{uuid.uuid4().hex}{extension}"
    entrada = None
    try:
        with temporal.open("wb") as destino:
            for bloque in video.chunks():
                destino.write(bloque)
        with transaction.atomic():
            existente = (
                TrabajoAnalisis.objects.select_for_update()
                .filter(Q(request_id=request_id) | Q(session_id=session_id))
                .order_by("-actualizado_en")
                .first()
            )
            if existente is not None and existente.estado != TrabajoAnalisis.Estado.FALLIDO:
                temporary_path = _managed_media_path(str(temporal))
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
                return _respuesta(
                    {
                        "status": existente.estado,
                        "job_id": str(existente.job_id),
                        "session_id": existente.session_id,
                        "duplicado": True,
                    },
                    202,
                    request_id,
                )
            try:
                with transaction.atomic():
                    trabajo = existente or TrabajoAnalisis.objects.create(
                        session_id=session_id, request_id=request_id, archivo_path=""
                    )
            except IntegrityError:
                trabajo = (
                    TrabajoAnalisis.objects.select_for_update()
                    .filter(Q(request_id=request_id) | Q(session_id=session_id))
                    .exclude(estado=TrabajoAnalisis.Estado.FALLIDO)
                    .order_by("-actualizado_en")
                    .first()
                )
                if trabajo is None:
                    raise
                temporary_path = _managed_media_path(str(temporal))
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
                return _respuesta(
                    {
                        "status": trabajo.estado,
                        "job_id": str(trabajo.job_id),
                        "session_id": trabajo.session_id,
                        "duplicado": True,
                    },
                    202,
                    request_id,
                )
            archivo_anterior = _managed_media_path(
                existente.archivo_path if existente is not None else ""
            )
            entrada = carpeta / f"{trabajo.job_id}-{uuid.uuid4().hex}{extension}"
            os.replace(temporal, entrada)
            if existente is not None:
                trabajo.estado = TrabajoAnalisis.Estado.ENCOLADO
                trabajo.resultado = None
                trabajo.error = ""
            trabajo.request_id = request_id
            trabajo.archivo_path = str(entrada.resolve())
            trabajo.save(update_fields=["request_id", "estado", "archivo_path", "resultado", "error", "actualizado_en"])
            if archivo_anterior and archivo_anterior != entrada.resolve():
                transaction.on_commit(
                    lambda path=archivo_anterior: path.unlink(missing_ok=True),
                    robust=True,
                )
    except Exception:
        temporary_path = _managed_media_path(str(temporal))
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        input_path = _managed_media_path(str(entrada)) if entrada is not None else None
        if input_path is not None:
            input_path.unlink(missing_ok=True)
        raise
    return _respuesta({"status": "queued", "job_id": str(trabajo.job_id), "session_id": session_id}, 202, request_id)


@require_GET
def obtener_trabajo(request, job_id):
    request_id = request.headers.get("X-Request-ID") or f"multimodal-{uuid.uuid4().hex[:12]}"
    if not _autorizado(request):
        return _respuesta({"status": "failed", "error": ERROR_NO_AUTORIZADO}, 403, request_id)
    trabajo = TrabajoAnalisis.objects.filter(job_id=job_id).first()
    if trabajo is None:
        return _respuesta({"status": "failed", "error": "Trabajo no encontrado."}, 404, request_id)
    cuerpo = {"status": trabajo.estado, "job_id": str(trabajo.job_id), "session_id": trabajo.session_id}
    if trabajo.resultado is not None:
        cuerpo["result"] = trabajo.resultado
    if trabajo.error:
        cuerpo["error"] = trabajo.error
    return _respuesta(cuerpo, 200, request_id)
