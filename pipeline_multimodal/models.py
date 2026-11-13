import math

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


DATASET_FEATURE_COLUMNS = (
    "audio_rms_mean",
    "audio_zcr_mean",
    "visual_motion_mean",
    "visual_motion_max",
)
DATASET_LABEL_COLUMNS = (
    "visual__MOVIMIENTO",
    "visual__MOVIMIENTO_REPETITIVO",
    "visual__CONTACTO_VISUAL",
    "visual__INTERACCION_OBJETO",
    "visual__ORIENTACION_CORPORAL",
    "audio__VOCALIZACION",
    "audio__HABLA",
    "audio__RISA",
    "audio__LLANTO",
    "audio__GRITO",
    "audio__SILENCIO",
    "audio__ACTIVIDAD_MUSICAL",
    "interaction__MIRADA",
    "interaction__GESTO",
    "interaction__TACTO",
    "interaction__IMITACION",
    "interaction__RESPUESTA",
    "interaction__ACTIVIDAD_CONJUNTA",
    "interaction__INTERACCION_MUSICAL",
    "interaction__INTERACCION_VERBAL",
)

ANNOTATION_TAG_FIELDS = ("sound_tags", "movement_tags", "interaction_tags")


def _validate_json_collection(value, field_name, depth):
    if isinstance(value, list):
        if len(value) > 2048:
            raise ValidationError(f"{field_name} contains too many items")
        for item in value:
            _validate_json_value(item, field_name, depth + 1)
        return
    if len(value) > 256:
        raise ValidationError(f"{field_name} contains too many keys")
    for key, item in value.items():
        if not isinstance(key, str) or len(key) > 128:
            raise ValidationError(f"invalid key in {field_name}")
        _validate_json_value(item, field_name, depth + 1)


def _validate_json_value(value, field_name, depth=0):
    if depth > 6:
        raise ValidationError(f"{field_name} nesting is too deep")
    if isinstance(value, bool) or value is None or isinstance(value, str):
        if isinstance(value, str) and len(value) > 4096:
            raise ValidationError(f"{field_name} string is too long")
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValidationError(f"invalid numeric value: {field_name}")
        return
    if isinstance(value, (list, dict)):
        _validate_json_collection(value, field_name, depth)
        return
    raise ValidationError(f"invalid value: {field_name}")


def _validate_annotation_window(start_time, end_time, demuca_phase):
    for name, value in (("start_time", start_time), ("end_time", end_time)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValidationError(f"{name} must be a finite non-negative number")
    if end_time <= start_time:
        raise ValidationError("end_time must be greater than start_time")
    if end_time - start_time > 24 * 60 * 60:
        raise ValidationError("annotation window is too long")
    if not isinstance(demuca_phase, str) or not demuca_phase.strip() or len(demuca_phase.strip()) > 128:
        raise ValidationError("demuca_phase must be a non-empty string")


def _validate_annotation_payloads(tags, derived_features, pose_landmarks, artifact_payload):
    if not isinstance(tags, dict) or set(tags) != set(ANNOTATION_TAG_FIELDS):
        raise ValidationError("tags must contain sound_tags, movement_tags, and interaction_tags")
    _validate_annotation_tags(tags)
    for field_name, value in (("derived_features", derived_features), ("pose_landmarks", pose_landmarks), ("artifact_payload", artifact_payload)):
        if not isinstance(value, (dict, list)):
            raise ValidationError(f"{field_name} must be an object or array")
        _validate_json_value(value, field_name)


def validate_annotation_values(start_time, end_time, demuca_phase, tags, derived_features, pose_landmarks, artifact_payload):
    _validate_annotation_window(start_time, end_time, demuca_phase)
    _validate_annotation_payloads(tags, derived_features, pose_landmarks, artifact_payload)


def _validate_annotation_tags(tags):
    for field in ANNOTATION_TAG_FIELDS:
        values = tags[field]
        if not isinstance(values, list) or len(values) > 64 or any(not isinstance(tag, str) or not tag.strip() or len(tag) > 128 for tag in values):
            raise ValidationError(f"{field} must be a list of non-empty strings")


def validate_dataset_values(features, labels):
    if not isinstance(features, dict) or not features:
        raise ValidationError("features must be a non-empty object")
    if set(features) != set(DATASET_FEATURE_COLUMNS):
        raise ValidationError("features must contain exactly the known feature columns")
    if not isinstance(labels, dict) or not labels:
        raise ValidationError("labels must be a non-empty object")
    if not set(labels).issubset(DATASET_LABEL_COLUMNS):
        raise ValidationError("labels contain an unknown label")
    _validate_feature_values(features)
    _validate_label_values(labels)


def _validate_feature_values(features):
    for name, value in features.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValidationError(f"invalid feature: {name}")


def _validate_label_values(labels):
    for name, value in labels.items():
        if isinstance(value, bool) or value not in (0, 1):
            raise ValidationError(f"invalid label: {name}")


class ResultadoAnalisis(models.Model):
    """Resultado inmutable del pipeline asociado a una sesión externa o clínica."""

    session_id = models.CharField(max_length=255, db_index=True)
    estado = models.CharField(max_length=32, default="completed")
    resultado = models.JSONField()
    request_id = models.CharField(max_length=128, blank=True, default="")
    mlflow_run_id = models.CharField(max_length=128, blank=True, default="")
    mlflow_experiment = models.CharField(max_length=255, blank=True, default="")
    mlflow_model_name = models.CharField(max_length=255, blank=True, default="")
    mlflow_model_version = models.CharField(max_length=64, blank=True, default="")
    model_sha256 = models.CharField(max_length=64, blank=True, default="")
    dataset_hash = models.CharField(max_length=64, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["session_id", "-creado_en"])]

    def __str__(self):
        return f"Análisis {self.session_id} ({self.estado})"

class TrabajoAnalisis(models.Model):
    class Estado(models.TextChoices):
        ENCOLADO = "queued", "Encolado"
        PROCESANDO = "processing", "Procesando"
        COMPLETADO = "completed", "Completado"
        FALLIDO = "failed", "Fallido"

    job_id = models.UUIDField(default=__import__("uuid").uuid4, unique=True, editable=False)
    session_id = models.CharField(max_length=255, db_index=True)
    request_id = models.CharField(max_length=128, blank=True, null=True, unique=True)
    archivo_path = models.CharField(max_length=1024)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ENCOLADO)
    resultado = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["creado_en"]
        indexes = [models.Index(fields=["estado", "creado_en"])]
        constraints = [
            models.UniqueConstraint(
                fields=["session_id"],
                condition=Q(estado__in=["queued", "processing"]),
                name="pipeline_active_session_unique",
            )
        ]


class TherapistDataset(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        AUTHORIZED = "authorized", "Authorized"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="therapist_datasets")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    training_authorized = models.BooleanField(default=False)
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authorized_therapist_datasets",
    )
    authorized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]


class TherapistDatasetSample(models.Model):
    dataset = models.ForeignKey(TherapistDataset, on_delete=models.CASCADE, related_name="samples")
    session_id = models.CharField(max_length=255)
    window_id = models.CharField(max_length=255)
    features = models.JSONField()
    labels = models.JSONField()
    reviewed = models.BooleanField(default=False)
    start_time = models.FloatField(null=True, blank=True)
    end_time = models.FloatField(null=True, blank=True)
    demuca_phase = models.CharField(max_length=128, blank=True, default="")
    sound_tags = models.JSONField(default=list)
    movement_tags = models.JSONField(default=list)
    interaction_tags = models.JSONField(default=list)
    derived_features = models.JSONField(default=dict)
    pose_landmarks = models.JSONField(default=list)
    artifact_payload = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["dataset", "session_id", "window_id"], name="dataset_sample_session_window_unique"),
        ]

    def clean(self):
        validate_dataset_values(self.features, self.labels)
        if self.start_time is not None or self.end_time is not None:
            validate_annotation_values(
                self.start_time, self.end_time, self.demuca_phase,
                {
                    "sound_tags": self.sound_tags,
                    "movement_tags": self.movement_tags,
                    "interaction_tags": self.interaction_tags,
                },
                self.derived_features, self.pose_landmarks, self.artifact_payload,
            )
