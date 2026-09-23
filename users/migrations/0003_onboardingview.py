from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_setting_notification_metadatos_notification_tipo"),
    ]

    operations = [
        migrations.CreateModel(
            name="OnboardingView",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("view_key", models.CharField(max_length=255)),
                ("completed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="onboarding_views",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "onboarding_views",
                "ordering": ["view_key"],
            },
        ),
        migrations.AddConstraint(
            model_name="onboardingview",
            constraint=models.UniqueConstraint(
                fields=("user", "view_key"),
                name="unique_user_onboarding_view",
            ),
        ),
    ]
