from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    BlogPost = apps.get_model("marketing", "BlogPost")
    for post in BlogPost.objects.order_by("created_at", "pk"):
        base_slug = slugify(post.title) or f"articulo-{post.pk}"
        candidate = base_slug
        suffix = 2
        while BlogPost.objects.filter(slug=candidate).exclude(pk=post.pk).exists():
            candidate = f"{base_slug}-{suffix}"
            suffix += 1
        BlogPost.objects.filter(pk=post.pk).update(slug=candidate)


class Migration(migrations.Migration):
    dependencies = [
        ("marketing", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="blogpost",
            name="slug",
            field=models.SlugField(
                blank=True,
                max_length=280,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
    ]
