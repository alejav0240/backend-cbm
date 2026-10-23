import os

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin


class ServiceKeyCSRFExemptMiddleware(MiddlewareMixin):
    """Exime del chequeo CSRF solo a peticiones servicio-a-servicio con X-Service-Key válido.

    El upload worker de Next.js corre server-side y su fetch a /graphql/ no envía
    cabecera Origin ni Referer, por lo que Django (HTTPS vía SECURE_PROXY_SSL_HEADER)
    responde 403 "Referer checking failed" antes de validar el token CSRF.

    Igual que @csrf_exempt en onedrive/views.py, la confianza se basa en el secreto
    compartido (ONEDRIVE_SERVICE_KEY): si la cabecera coincide, se salta el chequeo;
    el resto de peticiones conservan la protección CSRF completa.
    """

    def process_request(self, request):
        service_keys = {
            getattr(settings, "ONEDRIVE_SERVICE_KEY", None) or os.getenv("ONEDRIVE_SERVICE_KEY"),
            os.getenv("MULTIMODAL_SERVICE_KEY"),
        }
        provided = request.headers.get("X-Service-Key", "")
        if provided and provided in service_keys:
            request._dont_enforce_csrf_checks = True
