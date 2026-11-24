from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline_multimodal", "0007_resultadoanalisis_dataset_hash_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="therapistdataset",
            name="training_authorized",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="therapistdataset",
            name="authorized_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="therapistdataset",
            name="authorized_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="authorized_therapist_datasets",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="therapistdataset",
            name="status",
            field=models.CharField(
                choices=[("draft", "Draft"), ("authorized", "Authorized")],
                default="draft",
                max_length=32,
            ),
        ),
    ]
