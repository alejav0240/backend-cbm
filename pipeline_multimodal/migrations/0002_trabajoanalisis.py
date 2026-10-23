from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [("pipeline_multimodal", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="TrabajoAnalisis",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("job_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("session_id", models.CharField(db_index=True, max_length=255)),
                ("archivo_path", models.CharField(max_length=1024)),
                ("estado", models.CharField(choices=[("queued", "Encolado"), ("processing", "Procesando"), ("completed", "Completado"), ("failed", "Fallido")], default="queued", max_length=20)),
                ("resultado", models.JSONField(blank=True, null=True)),
                ("error", models.TextField(blank=True, default="")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["creado_en"]},
        ),
        migrations.AddIndex(
            model_name="trabajoanalisis",
            index=models.Index(fields=["estado", "creado_en"], name="pipeline_mu_estado_a5bafc_idx"),
        ),
    ]
