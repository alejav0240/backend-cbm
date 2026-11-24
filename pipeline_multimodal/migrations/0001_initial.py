from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="ResultadoAnalisis",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_id", models.CharField(db_index=True, max_length=255)),
                ("estado", models.CharField(default="completed", max_length=32)),
                ("resultado", models.JSONField()),
                ("request_id", models.CharField(blank=True, default="", max_length=128)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-creado_en"]},
        ),
        migrations.AddIndex(
            model_name="resultadoanalisis",
            index=models.Index(fields=["session_id", "-creado_en"], name="pipeline_mu_session_18ae15_idx"),
        ),
    ]
