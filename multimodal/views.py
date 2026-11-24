"""Endpoint HTTP que adapta una subida multipart al caso de uso ML."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST


def _autorizado(request) -> bool:
    esperado = os.environ.get("MULTIMODAL_SERVICE_KEY", "")
    if not esperado:
        return bool(getattr(settings, "DEBUG", False))
    return request.headers.get("X-Service-Key", "") == esperado


def _limite_bytes() -> int:
    return int(os.environ.get("MULTIMODAL_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))


EXTENSIONES_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _ruta_proyecto() -> Path:
    configurada = os.environ.get("MULTIMODAL_PROJECT_ROOT")
    return Path(configurada).resolve() if configurada else Path(settings.BASE_DIR).parent


def _python_ml() -> Path:
    configurado = os.environ.get("MULTIMODAL_PYTHON")
    if configurado:
        return Path(configurado).resolve()
    return _ruta_proyecto() / "dataset" / ".venv" / "bin" / "python"


@require_POST
def analizar_video(request):
    request_id = request.headers.get("X-Request-ID") or f"multimodal-{uuid.uuid4().hex[:12]}"
    if not _autorizado(request):
        respuesta = JsonResponse({"status": "failed", "error": "No autorizado."}, status=403)
        respuesta["X-Request-ID"] = request_id
        return respuesta
    video = request.FILES.get("video")
    if video is None:
        respuesta = JsonResponse({"status": "failed", "error": "Se requiere el campo video."}, status=400)
        respuesta["X-Request-ID"] = request_id
        return respuesta
    if video.size > _limite_bytes():
        respuesta = JsonResponse({"status": "failed", "error": "El video excede el tamaño máximo permitido."}, status=413)
        respuesta["X-Request-ID"] = request_id
        return respuesta
    extension = Path(video.name).suffix.lower()
    if extension not in EXTENSIONES_VIDEO:
        respuesta = JsonResponse({"status": "failed", "error": "Formato de video no soportado."}, status=400)
        respuesta["X-Request-ID"] = request_id
        return respuesta

    session_id = request.POST.get("session_id") or f"HTTP-{uuid.uuid4().hex[:12]}"
    raiz = _ruta_proyecto()
    python_ml = _python_ml()
    if not python_ml.is_file():
        respuesta = JsonResponse({"status": "failed", "error": "Entorno ML no disponible."}, status=503)
        respuesta["X-Request-ID"] = request_id
        return respuesta

    Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="multimodal-", dir=settings.MEDIA_ROOT) as temporal:
        entrada = Path(temporal) / f"entrada{extension}"
        with entrada.open("wb") as destino:
            for bloque in video.chunks():
                destino.write(bloque)
        comando = [
            str(python_ml), str(raiz / "ml" / "analyze_video.py"), str(entrada),
            "--session-id", session_id, "--project-root", str(raiz),
        ]
        try:
            resultado = subprocess.run(
                comando, cwd=raiz, check=False, capture_output=True, text=True,
                timeout=int(os.environ.get("MULTIMODAL_TIMEOUT_SECONDS", "1800")),
            )
        except subprocess.TimeoutExpired:
            respuesta = JsonResponse({"status": "failed", "error": "El análisis excedió el tiempo límite."}, status=504)
            respuesta["X-Request-ID"] = request_id
            return respuesta

    if resultado.returncode != 0:
        try:
            cuerpo = json.loads(resultado.stdout or "{}")
        except json.JSONDecodeError:
            cuerpo = {"status": "failed", "error": resultado.stderr.strip() or "Falló el análisis multimodal."}
        respuesta = JsonResponse(cuerpo, status=422)
        respuesta["X-Request-ID"] = request_id
        return respuesta
    try:
        cuerpo = json.loads(resultado.stdout)
    except json.JSONDecodeError:
        respuesta = JsonResponse({"status": "failed", "error": "El analizador no devolvió JSON válido."}, status=502)
        respuesta["X-Request-ID"] = request_id
        return respuesta
    respuesta = JsonResponse(cuerpo, status=200)
    respuesta["X-Request-ID"] = request_id
    return respuesta
