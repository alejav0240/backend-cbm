import graphene
from graphene_django import DjangoObjectType

from .models import ProcessingArtifact, ProcessingRun
from .pipeline import result_semantic_status


class PipelineStageType(graphene.ObjectType):
    id = graphene.String(required=True)
    label = graphene.String(required=True)
    status = graphene.String(required=True)
    progress = graphene.Int(required=True)
    message = graphene.String()
    started_at = graphene.String()
    finished_at = graphene.String()
    duration_ms = graphene.Int()
    artifact_kinds = graphene.List(graphene.String, required=True)


class ProcessingArtifactType(DjangoObjectType):
    class Meta:
        model = ProcessingArtifact
        fields = (
            "id",
            "kind",
            "uri",
            "sha256",
            "mime_type",
            "size_bytes",
            "training_authorized",
            "metadata_json",
            "created_at",
        )

    metadata = graphene.JSONString()

    def resolve_metadata(self, info):
        return self.metadata_json


class ProcessingRunType(DjangoObjectType):
    class Meta:
        model = ProcessingRun
        fields = (
            "id",
            "session",
            "external_run_id",
            "pipeline_version",
            "status",
            "source_uri",
            "source_sha256",
            "error_code",
            "error_message",
            "requested_at",
            "started_at",
            "finished_at",
            "updated_at",
            "artifacts",
        )

    result = graphene.JSONString()
    metadata = graphene.JSONString()
    pipeline_stages = graphene.List(PipelineStageType, required=True)
    semantic_status = graphene.String(required=True)
    review_required = graphene.Boolean(required=True)

    def resolve_result(self, info):
        return self.result_json

    def resolve_metadata(self, info):
        return self.metadata_json

    def resolve_pipeline_stages(self, info):
        result = self.result_json if isinstance(self.result_json, dict) else {}
        stages = [dict(stage) for stage in result.get("pipeline_stages", [])]
        if not stages:
            return stages

        # La aceptación clínica DEMUCA cierra human_review. La revisión de
        # eventos para el dataset es una cola independiente y no debe bloquear
        # el pipeline clínico.
        from evaluations.models import ScaleEvaluation

        reviewed_at = (
            ScaleEvaluation.objects.filter(
                session_id=self.session_id,
                scale__name__icontains="demuca",
                review_status="accepted",
            )
            .order_by("-reviewed_at")
            .values_list("reviewed_at", flat=True)
            .first()
        )
        if reviewed_at is None:
            return stages

        for stage in stages:
            if stage.get("id") == "human_review" and stage.get("status") != "completed":
                stage.update(
                    status="completed",
                    progress=100,
                    finished_at=reviewed_at.isoformat(),
                    message="Evaluación DEMUCA aceptada por el especialista.",
                )
        return stages

    def resolve_semantic_status(self, info):
        return result_semantic_status(self.result_json)

    def resolve_review_required(self, info):
        result = self.result_json if isinstance(self.result_json, dict) else {}
        demuca = result.get("demuca")
        from evaluations.models import ScaleEvaluation

        demuca_accepted = ScaleEvaluation.objects.filter(
            session_id=self.session_id,
            scale__name__icontains="demuca",
            review_status="accepted",
        ).exists()
        if demuca_accepted:
            return False

        return bool(
            result.get("review_required", False)
            or (
                isinstance(demuca, dict)
                and demuca.get("review_required") is True
            )
            or result_semantic_status(result)
            in {"provisional_evidence", "provisional", "draft", "unavailable"}
        )
