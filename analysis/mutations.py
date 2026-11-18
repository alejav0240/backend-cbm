import hmac
import os
import uuid
from datetime import datetime, timezone

import graphene
from django.conf import settings
from django.utils import timezone as django_timezone
from graphql import GraphQLError

from config.utils import get_db_id, module_permission_required, user_can_access_session
from therapeutic_sessions.models import Session

from .models import ProcessingArtifact, ProcessingRun
from .type import ProcessingRunType


def _get_session(info, session_id):
    db_session_id = get_db_id(session_id)
    if not db_session_id:
        raise GraphQLError("ID de sesión inválido.")

    try:
        session = Session.objects.get(pk=db_session_id)
    except Session.DoesNotExist as error:
        raise GraphQLError("Sesión no encontrada.") from error

    if not (info.context.user.is_staff or info.context.user.is_superuser):
        if not user_can_access_session(info.context.user, session.pk):
            raise GraphQLError("No autorizado.")
    return session


def _service_authorized(info):
    expected = getattr(settings, "ML_SERVICE_API_KEY", "") or os.getenv("ML_SERVICE_API_KEY", "")
    received = info.context.headers.get("X-ML-Service-Key", "")
    return bool(expected) and hmac.compare_digest(received, expected)


class CreateProcessingRun(graphene.Mutation):
    class Arguments:
        session_id = graphene.ID(required=True)
        pipeline_version = graphene.String(default_value="0.3.0")
        source_uri = graphene.String()
        metadata = graphene.JSONString()

    processing_run = graphene.Field(ProcessingRunType)

    @module_permission_required("sesiones", action="change")
    def mutate(self, info, session_id, pipeline_version="0.3.0", source_uri=None, metadata=None):
        session = _get_session(info, session_id)
        processing_run = ProcessingRun.objects.create(
            session=session,
            requested_by=info.context.user,
            external_run_id=f"run-{uuid.uuid4()}",
            pipeline_version=pipeline_version,
            source_uri=source_uri or session.video_url,
            metadata_json=metadata if isinstance(metadata, dict) else {},
        )
        return CreateProcessingRun(processing_run=processing_run)


class UpdateProcessingRun(graphene.Mutation):
    class Arguments:
        external_run_id = graphene.String(required=True)
        status = graphene.String(required=True)
        result = graphene.JSONString()
        source_sha256 = graphene.String()
        error_code = graphene.String()
        error_message = graphene.String()
        artifacts = graphene.JSONString()

    processing_run = graphene.Field(ProcessingRunType)

    def mutate(
        self,
        info,
        external_run_id,
        status,
        result=None,
        source_sha256=None,
        error_code=None,
        error_message=None,
        artifacts=None,
    ):
        if not _service_authorized(info):
            raise GraphQLError("Servicio ML no autorizado.")

        try:
            processing_run = ProcessingRun.objects.get(external_run_id=external_run_id)
        except ProcessingRun.DoesNotExist as error:
            raise GraphQLError("ProcessingRun no encontrado.") from error

        valid_statuses = {choice for choice, _ in ProcessingRun.Status.choices}
        if status not in valid_statuses:
            raise GraphQLError(f"Estado de procesamiento inválido: {status}")

        now = django_timezone.now()
        processing_run.status = status
        if status == ProcessingRun.Status.RUNNING and processing_run.started_at is None:
            processing_run.started_at = now
        if status in {
            ProcessingRun.Status.COMPLETED,
            ProcessingRun.Status.FAILED,
            ProcessingRun.Status.CANCELLED,
        }:
            processing_run.finished_at = now
        if result is not None:
            processing_run.result_json = result
        if source_sha256 is not None:
            processing_run.source_sha256 = source_sha256
        if error_code is not None:
            processing_run.error_code = error_code
        if error_message is not None:
            processing_run.error_message = error_message
        processing_run.save()

        if isinstance(artifacts, list):
            for payload in artifacts:
                if not isinstance(payload, dict) or not payload.get("kind") or not payload.get("uri"):
                    continue
                ProcessingArtifact.objects.update_or_create(
                    run=processing_run,
                    kind=payload["kind"],
                    defaults={
                        "uri": payload["uri"],
                        "sha256": payload.get("sha256"),
                        "mime_type": payload.get("mime_type"),
                        "size_bytes": payload.get("size_bytes"),
                        "training_authorized": payload.get("training_authorized") is True,
                        "metadata_json": payload.get("metadata", {}),
                    },
                )

        return UpdateProcessingRun(processing_run=processing_run)


class Mutation(graphene.ObjectType):
    create_processing_run = CreateProcessingRun.Field()
    update_processing_run = UpdateProcessingRun.Field()
