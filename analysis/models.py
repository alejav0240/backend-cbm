import uuid

from django.db import models

from users.models import User


def default_external_run_id():
    return f"run-{uuid.uuid4()}"


class ProcessingRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "En cola"
        RUNNING = "running", "Procesando"
        BLOCKED_REVIEW = "blocked_review", "Esperando revisión"
        COMPLETED = "completed", "Completado"
        FAILED = "failed", "Fallido"
        CANCELLED = "cancelled", "Cancelado"

    session = models.ForeignKey(
        "therapeutic_sessions.Session",
        on_delete=models.CASCADE,
        related_name="processing_runs",
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="requested_processing_runs",
        null=True,
        blank=True,
    )
    external_run_id = models.CharField(
        max_length=120,
        unique=True,
        default=default_external_run_id,
    )
    pipeline_version = models.CharField(max_length=50, default="0.3.0")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.QUEUED)
    source_uri = models.URLField(blank=True, null=True)
    source_sha256 = models.CharField(max_length=64, blank=True, default="")
    error_code = models.CharField(max_length=120, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    result_json = models.JSONField(default=dict, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "processing_runs"
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["session", "status"]),
            models.Index(fields=["external_run_id"]),
        ]

    def __str__(self):
        return f"{self.external_run_id} — {self.session_id} — {self.status}"


class ProcessingArtifact(models.Model):
    run = models.ForeignKey(
        ProcessingRun,
        on_delete=models.CASCADE,
        related_name="artifacts",
    )
    kind = models.CharField(max_length=100)
    uri = models.TextField()
    sha256 = models.CharField(max_length=64, blank=True, default="")
    mime_type = models.CharField(max_length=120, blank=True, default="")
    size_bytes = models.BigIntegerField(blank=True, null=True)
    training_authorized = models.BooleanField(default=False)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "processing_artifacts"
        ordering = ["kind", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "kind"],
                name="unique_processing_artifact_kind_per_run",
            )
        ]

    def __str__(self):
        return f"{self.kind} — {self.run.external_run_id}"


# Import the review models so Django registers them as part of this app.
from .annotation_models import Adjudication, AnnotationCase, AnnotationReview, ParticipantAnchor  # noqa: E402,F401
