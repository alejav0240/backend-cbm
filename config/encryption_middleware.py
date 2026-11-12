import json

from django.conf import settings
from django.http import JsonResponse

from .application_encryption import (
    CONTENT_TYPE,
    decrypt_envelope,
    encrypt_payload,
    unwrap_aes_key,
)


class ApplicationEncryptionMiddleware:
    """Decrypt encrypted JSON requests and encrypt their JSON responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.APP_ENCRYPTION_ENABLED:
            return self.get_response(request)

        if request.content_type == CONTENT_TYPE:
            try:
                plaintext, aes_key = decrypt_envelope(
                    json.loads(request.body.decode("utf-8")), request.path
                )
            except (TypeError, ValueError, KeyError):
                return JsonResponse({"error": "Invalid encrypted payload"}, status=400)
            request._body = plaintext
            request.META["CONTENT_TYPE"] = "application/json"
            request._application_encryption_key = aes_key
        elif request.headers.get("X-CBM-Encrypted-Response") == "1":
            try:
                request._application_encryption_key = unwrap_aes_key(
                    request.headers["X-CBM-Response-Key"],
                    request.headers["X-CBM-Response-Key-Id"],
                )
            except (KeyError, TypeError, ValueError):
                return JsonResponse({"error": "Invalid encryption key"}, status=400)

        response = self.get_response(request)
        aes_key = getattr(request, "_application_encryption_key", None)
        content_type = response.get("Content-Type", "").split(";", 1)[0]
        if (
            aes_key is None
            or getattr(response, "streaming", False)
            or response.status_code == 204
            or content_type not in {"application/json", "application/graphql-response+json"}
        ):
            return response

        response.content = encrypt_payload(response.content, aes_key, request.path)
        response["Content-Type"] = CONTENT_TYPE
        response["Content-Length"] = str(len(response.content))
        return response
