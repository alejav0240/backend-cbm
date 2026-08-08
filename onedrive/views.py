import json
import os

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from onedrive.models import OneDriveConnection, decrypt_token


def _is_authorized(request) -> bool:
    service_key = getattr(settings, "ONEDRIVE_SERVICE_KEY", None) or os.getenv(
        "ONEDRIVE_SERVICE_KEY"
    )
    if not service_key:
        return False
    provided = request.headers.get("X-Service-Key", "")
    return provided == service_key


@csrf_exempt
@require_http_methods(["GET", "POST"])
def onedrive_token(request):
    """Endpoint de servicio para que el frontend (Next.js) lea/guarde el refresh token.

    Autenticación entre servicios mediante el header `X-Service-Key`.
    GET  -> { "refresh_token": "<descifrado>" }
    POST -> { "refresh_token": "...", "user_email": "..." } (upsert)
    """
    if not _is_authorized(request):
        return JsonResponse({"error": "No autorizado."}, status=403)

    if request.method == "POST":
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "JSON inválido."}, status=400)

        refresh_token = payload.get("refresh_token", "")
        user_email = payload.get("user_email", "")

        if not refresh_token:
            return JsonResponse({"error": "refresh_token requerido."}, status=400)

        connection = OneDriveConnection.get_active()
        if connection is None:
            connection = OneDriveConnection(is_active=True)
        connection.user_email = user_email
        connection.is_active = True
        connection.save_refresh_token(refresh_token)
        return JsonResponse({"success": True, "user_email": user_email})

    # GET
    try:
        connection = OneDriveConnection.get_active()
        if connection is None or not connection.refresh_token_encrypted:
            return JsonResponse({"refresh_token": None}, status=200)
        return JsonResponse(
            {"refresh_token": decrypt_token(connection.refresh_token_encrypted)},
            status=200,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@require_http_methods(["GET"])
def onedrive_status(request):
    """Endpoint público para que el frontend muestre el estado de la conexión."""
    connection = OneDriveConnection.get_active()
    if connection is None:
        return JsonResponse({"connected": False})
    return JsonResponse(
        {"connected": True, "user_email": connection.user_email},
        status=200,
    )
