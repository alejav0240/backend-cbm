import os

import graphene
from django.conf import settings
from graphql import GraphQLError

from config.utils import get_db_id
from therapeutic_sessions.models import Session
from users.models import Notification


def _is_authorized(info) -> bool:
    service_key = getattr(settings, "ONEDRIVE_SERVICE_KEY", None) or os.getenv(
        "ONEDRIVE_SERVICE_KEY"
    )
    if not service_key:
        return False
    provided = info.context.headers.get("X-Service-Key", "")
    return provided == service_key


def _get_session(session_id: str) -> Session:
    real_id = get_db_id(session_id)
    if not real_id:
        raise GraphQLError("ID de sesión inválido o no proporcionado.")
    try:
        return Session.objects.get(pk=real_id)
    except Session.DoesNotExist:
        raise GraphQLError(f"Sesión {real_id} no encontrada.")


class MarcarSubidaEnProgreso(graphene.Mutation):
    """Marca una sesión con `video_status = subiendo`.

    Se invoca desde el worker de Next.js apenas comienza a subir la grabación.
    No crea notificaciones.
    """

    class Arguments:
        session_id = graphene.ID(required=True)

    success = graphene.Boolean()

    def mutate(self, info, session_id):
        if not _is_authorized(info):
            raise GraphQLError("No autorizado.")
        session = _get_session(session_id)
        session.video_status = Session.VideoStatus.SUBIENDO
        session.save(update_fields=["video_status", "updated_at"])
        return MarcarSubidaEnProgreso(success=True)


class CompletarSubidaSesion(graphene.Mutation):
    """Marca una sesión como subida (o con fallo) desde el worker de Next.js.

    Autenticación entre servicios mediante el header `X-Service-Key`.
    Actualiza `Session.video_url` / `Session.video_status` y crea la
    notificación para el terapeuta con tipo y metadatos (para acciones
    como "Reintentar" desde la campana).
    """

    class Arguments:
        session_id = graphene.ID(required=True)
        video_url = graphene.String()
        storage = graphene.String()
        ok = graphene.Boolean(required=True)
        message = graphene.String()
        job_id = graphene.String()

    success = graphene.Boolean()

    def mutate(
        self, info, session_id, ok, video_url=None, storage=None, message=None, job_id=None
    ):
        if not _is_authorized(info):
            raise GraphQLError("No autorizado.")

        session = _get_session(session_id)

        if ok and video_url:
            session.video_url = video_url
            session.video_status = Session.VideoStatus.SUBIDO
            session.save(update_fields=["video_url", "video_status", "updated_at"])
        elif not ok:
            session.video_status = Session.VideoStatus.FALLO
            session.save(update_fields=["video_status", "updated_at"])

        paciente = session.patient
        nombre_paciente = (
            f"{paciente.first_name} {paciente.last_name}".strip()
            if paciente
            else "su paciente"
        )

        metadatos = {"sessionId": session_id}
        if job_id:
            metadatos["jobId"] = job_id

        if ok:
            destino = "OneDrive"
            if storage == "r2":
                destino = "Cloudflare R2"
            elif storage == "local":
                destino = "almacenamiento local"
            texto = f"La grabación de la sesión de {nombre_paciente} fue subida correctamente a {destino}."
            tipo = "subida_exitosa"
        else:
            texto = (
                message
                or f"No se pudo subir la grabación de la sesión de {nombre_paciente}."
            )
            tipo = "subida_fallo"

        Notification.objects.create(
            user=session.therapist, message=texto, tipo=tipo, metadatos=metadatos
        )

        return CompletarSubidaSesion(success=True)
