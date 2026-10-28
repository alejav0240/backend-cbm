"""HTTP adapter for the multimodal pipeline module."""

from __future__ import annotations

import os
import json
from pathlib import Path
import tempfile
import uuid

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .servicios import ErrorPipelineMultimodal, ServicioPipelineMultimodal
from .models import ResultadoAnalisis, TrabajoAnalisis
from .demuca_review import merge_demuca_data

EXTENSIONES_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


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
        return _respuesta({"status": "failed", "error": "No autorizado."}, 403, request_id)
    video = request.FILES.get("video")
    if video is None:
        return _respuesta({"status": "failed", "error": "Se requiere el campo video."}, 400, request_id)
    if video.size > int(os.environ.get("MULTIMODAL_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024))):
        return _respuesta({"status": "failed", "error": "El video excede el tamaño máximo permitido."}, 413, request_id)
    extension = Path(video.name).suffix.lower()
    if extension not in EXTENSIONES_VIDEO:
        return _respuesta({"status": "failed", "error": "Formato de video no soportado."}, 400, request_id)

    session_id = request.POST.get("session_id") or f"HTTP-{uuid.uuid4().hex[:12]}"
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
            )
        except ErrorPipelineMultimodal as error:
            return _respuesta({"status": "failed", "error": str(error)}, 502, request_id)
    estado = 422 if cuerpo.get("status") == "failed" else 200
    return _respuesta(cuerpo, estado, request_id)


@require_GET
def obtener_resultado(request, session_id: str):
    request_id = request.headers.get("X-Request-ID") or f"multimodal-{uuid.uuid4().hex[:12]}"
    if not _autorizado(request):
        return _respuesta({"status": "failed", "error": "No autorizado."}, 403, request_id)
    resultado = ResultadoAnalisis.objects.filter(session_id=session_id).first()
    if resultado is None:
        return _respuesta({"status": "pending", "session_id": session_id}, 202, request_id)
    return _respuesta(resultado.resultado, 200, request_id)


@require_http_methods(["PATCH"])
def actualizar_demuca(request, session_id: str):
    request_id = request.headers.get("X-Request-ID") or f"multimodal-{uuid.uuid4().hex[:12]}"
    if not _autorizado(request):
        return _respuesta({"status": "failed", "error": "No autorizado."}, 403, request_id)
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
        return _respuesta({"status": "failed", "error": str(error)}, 400, request_id)

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
        return _respuesta({"status": "failed", "error": "No autorizado."}, 403, request_id)
    video = request.FILES.get("video")
    if video is None:
        return _respuesta({"status": "failed", "error": "Se requiere el campo video."}, 400, request_id)
    extension = Path(video.name).suffix.lower()
    if extension not in EXTENSIONES_VIDEO:
        return _respuesta({"status": "failed", "error": "Formato de video no soportado."}, 400, request_id)
    if video.size > int(os.environ.get("MULTIMODAL_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024))):
        return _respuesta({"status": "failed", "error": "El video excede el tamaño máximo permitido."}, 413, request_id)
    session_id = request.POST.get("session_id") or f"HTTP-{uuid.uuid4().hex[:12]}"
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
                temporal.unlink(missing_ok=True)
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
                temporal.unlink(missing_ok=True)
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
            archivo_anterior = existente.archivo_path if existente is not None else ""
            entrada = carpeta / f"{trabajo.job_id}-{uuid.uuid4().hex}{extension}"
            os.replace(temporal, entrada)
            if existente is not None:
                trabajo.estado = TrabajoAnalisis.Estado.ENCOLADO
                trabajo.resultado = None
                trabajo.error = ""
            trabajo.request_id = request_id
            trabajo.archivo_path = str(entrada)
            trabajo.save(update_fields=["request_id", "estado", "archivo_path", "resultado", "error", "actualizado_en"])
            if archivo_anterior and archivo_anterior != str(entrada):
                transaction.on_commit(
                    lambda path=archivo_anterior: Path(path).unlink(missing_ok=True),
                    robust=True,
                )
    except Exception:
        temporal.unlink(missing_ok=True)
        if entrada is not None:
            entrada.unlink(missing_ok=True)
        raise
    return _respuesta({"status": "queued", "job_id": str(trabajo.job_id), "session_id": session_id}, 202, request_id)


@require_GET
def obtener_trabajo(request, job_id):
    request_id = request.headers.get("X-Request-ID") or f"multimodal-{uuid.uuid4().hex[:12]}"
    if not _autorizado(request):
        return _respuesta({"status": "failed", "error": "No autorizado."}, 403, request_id)
    trabajo = TrabajoAnalisis.objects.filter(job_id=job_id).first()
    if trabajo is None:
        return _respuesta({"status": "failed", "error": "Trabajo no encontrado."}, 404, request_id)
    cuerpo = {"status": trabajo.estado, "job_id": str(trabajo.job_id), "session_id": trabajo.session_id}
    if trabajo.resultado is not None:
        cuerpo["result"] = trabajo.resultado
    if trabajo.error:
        cuerpo["error"] = trabajo.error
    return _respuesta(cuerpo, 200, request_id)
