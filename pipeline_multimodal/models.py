from django.db import models


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
