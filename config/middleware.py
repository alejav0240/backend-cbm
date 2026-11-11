import os
import json
import secrets

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from graphql import GraphQLError, parse
from graphql.language.ast import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    OperationDefinitionNode,
)


SERVICE_OPERATIONS = frozenset(
    {
        "marcarSubidaEnProgreso",
        "completarSubidaSesion",
    }
)


def _contains_service_operation(node, fragments, visited_fragments=None):
    visited_fragments = visited_fragments or set()
    if isinstance(node, FieldNode) and node.name.value in SERVICE_OPERATIONS:
        return True

    selection_set = getattr(node, "selection_set", None)
    if not selection_set:
        return False

    for child in selection_set.selections:
        if isinstance(child, FragmentSpreadNode):
            fragment_name = child.name.value
            if fragment_name in visited_fragments:
                continue
            fragment = fragments.get(fragment_name)
            if fragment and _contains_service_operation(
                fragment,
                fragments,
                visited_fragments | {fragment_name},
            ):
                return True
        elif _contains_service_operation(child, fragments, visited_fragments):
            return True
    return False


def _is_service_operation(query, operation_name=None):
    if not isinstance(query, str) or not query.strip():
        return False
    try:
        document = parse(query)
    except (GraphQLError, TypeError):
        return False
    operations = [
        definition
        for definition in document.definitions
        if isinstance(definition, OperationDefinitionNode)
    ]
    fragments = {
        definition.name.value: definition
        for definition in document.definitions
        if isinstance(definition, FragmentDefinitionNode) and definition.name
    }
    if operation_name is not None:
        if not isinstance(operation_name, str):
            return False
        operations = [
            operation
            for operation in operations
            if operation.name and operation.name.value == operation_name
        ]
    elif len(operations) != 1:
        return False

    return len(operations) == 1 and _contains_service_operation(operations[0], fragments)


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
        if request.path != "/graphql/":
            return

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
            return

        if not isinstance(payload, dict) or not _is_service_operation(
            payload.get("query"),
            payload.get("operationName"),
        ):
            return

        service_keys = {
            getattr(settings, "ONEDRIVE_SERVICE_KEY", None) or os.getenv("ONEDRIVE_SERVICE_KEY"),
            os.getenv("MULTIMODAL_SERVICE_KEY"),
        }
        provided = request.headers.get("X-Service-Key", "")
        if provided and any(
            key and secrets.compare_digest(provided, key) for key in service_keys
        ):
            request._dont_enforce_csrf_checks = True
