from django.db import models

from clinical.models import Patient
from users.models import User

from .models import ProcessingRun


class ParticipantAnchor(models.Model):
    class Role(models.TextChoices):
        PATIENT = "patient", "Paciente"
        THERAPIST = "therapist", "Terapeuta"
        PARENT = "parent", "Padre o tutor"
        PEER = "peer", "Par"
        OBJECT = "object", "Objeto"
        UNKNOWN = "unknown", "Desconocido"

    run = models.ForeignKey(ProcessingRun, on_delete=models.CASCADE, related_name="participant_anchors")
    track_id = models.CharField(max_length=120)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.UNKNOWN)
    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True)
    therapist = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    anchor_seconds = models.DecimalField(max_digits=10, decimal_places=3)
    bounding_box = models.JSONField(default=dict, blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="reviewed_participant_anchors")
    reviewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "participant_anchors"
        constraints = [
            models.UniqueConstraint(fields=["run", "track_id"], name="unique_anchor_track_per_run")
        ]


class AnnotationCase(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        ACCEPTED = "accepted", "Aceptada"
        REJECTED = "rejected", "Rechazada"
        NEEDS_ADJUDICATION = "needs_adjudication", "Requiere adjudicación"

    run = models.ForeignKey(ProcessingRun, on_delete=models.CASCADE, related_name="annotation_cases")
    window_id = models.CharField(max_length=120)
    start_seconds = models.DecimalField(max_digits=10, decimal_places=3)
    end_seconds = models.DecimalField(max_digits=10, decimal_places=3)
    modality = models.CharField(max_length=40)
    label = models.CharField(max_length=120)
    actor_role = models.CharField(max_length=30, default="unknown")
    source = models.CharField(max_length=30, default="model")
    proposal_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "annotation_cases"
        ordering = ["start_seconds", "created_at"]
        indexes = [
            models.Index(fields=["run", "status"]),
            models.Index(fields=["run", "window_id"]),
        ]


class AnnotationReview(models.Model):
    class Decision(models.TextChoices):
        ACCEPT = "accept", "Aceptar"
        REJECT = "reject", "Rechazar"
        EDIT = "edit", "Editar"

    case = models.ForeignKey(AnnotationCase, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(User, on_delete=models.PROTECT)
    decision = models.CharField(max_length=20, choices=Decision.choices)
    label = models.CharField(max_length=120, blank=True)
    actor_role = models.CharField(max_length=30, blank=True)
    start_seconds = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    end_seconds = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    comment = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "annotation_reviews"
        constraints = [
            models.UniqueConstraint(fields=["case", "reviewer"], name="unique_review_per_case_reviewer")
        ]


class Adjudication(models.Model):
    case = models.OneToOneField(AnnotationCase, on_delete=models.CASCADE, related_name="adjudication")
    adjudicator = models.ForeignKey(User, on_delete=models.PROTECT)
    final_decision = models.CharField(max_length=20)
    final_label = models.CharField(max_length=120, blank=True)
    final_actor_role = models.CharField(max_length=30, blank=True)
    rationale = models.TextField(blank=True)
    adjudicated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "annotation_adjudications"
