from django.db import models
from django.db.models import Q


class ResultadoAnalisis(models.Model):
    """Resultado inmutable del pipeline asociado a una sesión externa o clínica."""

    session_id = models.CharField(max_length=255, db_index=True)
    estado = models.CharField(max_length=32, default="completed")
    resultado = models.JSONField()
    request_id = models.CharField(max_length=128, blank=True, default="")
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
