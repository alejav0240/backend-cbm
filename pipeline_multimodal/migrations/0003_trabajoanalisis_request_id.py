from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pipeline_multimodal", "0002_trabajoanalisis")]

    operations = [
        migrations.AddField(
            model_name="trabajoanalisis",
            name="request_id",
            field=models.CharField(blank=True, max_length=128, null=True, unique=True),
        ),
    ]
