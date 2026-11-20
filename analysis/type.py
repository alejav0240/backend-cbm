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
        return result.get("pipeline_stages", [])

    def resolve_semantic_status(self, info):
        return result_semantic_status(self.result_json)

    def resolve_review_required(self, info):
        result = self.result_json if isinstance(self.result_json, dict) else {}
        return bool(result.get("review_required", False))
