# Generated manually for therapist session annotation windows.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pipeline_multimodal", "0005_therapistdataset_therapistdatasetsample")]

    operations = [
        migrations.AddField(
            model_name="therapistdatasetsample",
            name="start_time",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="therapistdatasetsample",
            name="end_time",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="therapistdatasetsample",
            name="demuca_phase",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="therapistdatasetsample",
            name="sound_tags",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="therapistdatasetsample",
            name="movement_tags",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="therapistdatasetsample",
            name="interaction_tags",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="therapistdatasetsample",
            name="derived_features",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="therapistdatasetsample",
            name="pose_landmarks",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="therapistdatasetsample",
            name="artifact_payload",
            field=models.JSONField(default=dict),
        ),
    ]
