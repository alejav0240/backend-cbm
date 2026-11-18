import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def default_external_run_id():
    return f"run-{uuid.uuid4()}"


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("therapeutic_sessions", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessingRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_run_id", models.CharField(default=default_external_run_id, max_length=120, unique=True)),
                ("pipeline_version", models.CharField(default="0.3.0", max_length=50)),
                ("status", models.CharField(choices=[("queued", "En cola"), ("running", "Procesando"), ("blocked_review", "Esperando revisión"), ("completed", "Completado"), ("failed", "Fallido"), ("cancelled", "Cancelado")], default="queued", max_length=30)),
                ("source_uri", models.URLField(blank=True, null=True)),
                ("source_sha256", models.CharField(blank=True, max_length=64, null=True)),
                ("error_code", models.CharField(blank=True, max_length=120, null=True)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("result_json", models.JSONField(blank=True, default=dict)),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="requested_processing_runs", to=settings.AUTH_USER_MODEL)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="processing_runs", to="therapeutic_sessions.session")),
            ],
            options={
                "db_table": "processing_runs",
                "ordering": ["-requested_at"],
            },
        ),
        migrations.CreateModel(
            name="ProcessingArtifact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(max_length=100)),
                ("uri", models.TextField()),
                ("sha256", models.CharField(blank=True, max_length=64, null=True)),
                ("mime_type", models.CharField(blank=True, max_length=120, null=True)),
                ("size_bytes", models.BigIntegerField(blank=True, null=True)),
                ("training_authorized", models.BooleanField(default=False)),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="artifacts", to="analysis.processingrun")),
            ],
            options={
                "db_table": "processing_artifacts",
                "ordering": ["kind", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="processingrun",
            index=models.Index(fields=["session", "status"], name="processing_r_session_9e9a99_idx"),
        ),
        migrations.AddIndex(
            model_name="processingrun",
            index=models.Index(fields=["external_run_id"], name="processing_r_extern_9c1a0c_idx"),
        ),
        migrations.AddConstraint(
            model_name="processingartifact",
            constraint=models.UniqueConstraint(fields=("run", "kind"), name="unique_processing_artifact_kind_per_run"),
        ),
    ]
