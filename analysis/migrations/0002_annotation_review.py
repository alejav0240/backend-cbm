import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AnnotationCase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("window_id", models.CharField(max_length=120)),
                ("start_seconds", models.DecimalField(decimal_places=3, max_digits=10)),
                ("end_seconds", models.DecimalField(decimal_places=3, max_digits=10)),
                ("modality", models.CharField(max_length=40)),
                ("label", models.CharField(max_length=120)),
                ("actor_role", models.CharField(default="unknown", max_length=30)),
                ("source", models.CharField(default="model", max_length=30)),
                ("proposal_json", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("pending", "Pendiente"), ("accepted", "Aceptada"), ("rejected", "Rechazada"), ("needs_adjudication", "Requiere adjudicación")], default="pending", max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="annotation_cases", to="analysis.processingrun")),
            ],
            options={
                "db_table": "annotation_cases",
                "ordering": ["start_seconds", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="ParticipantAnchor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("track_id", models.CharField(max_length=120)),
                ("role", models.CharField(choices=[("patient", "Paciente"), ("therapist", "Terapeuta"), ("parent", "Padre o tutor"), ("peer", "Par"), ("object", "Objeto"), ("unknown", "Desconocido")], default="unknown", max_length=30)),
                ("anchor_seconds", models.DecimalField(decimal_places=3, max_digits=10)),
                ("bounding_box", models.JSONField(blank=True, default=dict)),
                ("confidence", models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True)),
                ("reviewed_at", models.DateTimeField(auto_now=True)),
                ("patient", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="clinical.patient")),
                ("reviewed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reviewed_participant_anchors", to=settings.AUTH_USER_MODEL)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participant_anchors", to="analysis.processingrun")),
                ("therapist", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "participant_anchors",
            },
        ),
        migrations.CreateModel(
            name="AnnotationReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("decision", models.CharField(choices=[("accept", "Aceptar"), ("reject", "Rechazar"), ("edit", "Editar")], max_length=20)),
                ("label", models.CharField(blank=True, max_length=120)),
                ("actor_role", models.CharField(blank=True, max_length=30)),
                ("start_seconds", models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ("end_seconds", models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ("comment", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(auto_now_add=True)),
                ("case", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to="analysis.annotationcase")),
                ("reviewer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "annotation_reviews",
            },
        ),
        migrations.CreateModel(
            name="Adjudication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("final_decision", models.CharField(max_length=20)),
                ("final_label", models.CharField(blank=True, max_length=120)),
                ("final_actor_role", models.CharField(blank=True, max_length=30)),
                ("rationale", models.TextField(blank=True)),
                ("adjudicated_at", models.DateTimeField(auto_now_add=True)),
                ("adjudicator", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("case", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="adjudication", to="analysis.annotationcase")),
            ],
            options={
                "db_table": "annotation_adjudications",
            },
        ),
        migrations.AddIndex(
            model_name="annotationcase",
            index=models.Index(fields=["run", "status"], name="annotation_c_run_id_3f04b6_idx"),
        ),
        migrations.AddIndex(
            model_name="annotationcase",
            index=models.Index(fields=["run", "window_id"], name="annotation_c_run_id_90a2c8_idx"),
        ),
        migrations.AddConstraint(
            model_name="annotationcase",
            constraint=models.UniqueConstraint(fields=("run", "window_id", "label"), name="unique_annotation_case_label_window"),
        ),
        migrations.AddConstraint(
            model_name="annotationreview",
            constraint=models.UniqueConstraint(fields=("case", "reviewer"), name="unique_review_per_case_reviewer"),
        ),
        migrations.AddConstraint(
            model_name="participantanchor",
            constraint=models.UniqueConstraint(fields=("run", "track_id"), name="unique_anchor_track_per_run"),
        ),
    ]
