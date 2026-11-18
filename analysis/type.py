import graphene
from graphene_django import DjangoObjectType

from .models import ProcessingArtifact, ProcessingRun


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

    def resolve_result(self, info):
        return self.result_json

    def resolve_metadata(self, info):
        return self.metadata_json
