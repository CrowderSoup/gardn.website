from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="UserIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("me_url", models.URLField(unique=True)),
                ("username", models.SlugField(max_length=64, unique=True)),
                ("display_name", models.CharField(blank=True, max_length=255)),
                ("photo_url", models.URLField(blank=True)),
                ("svg_cache", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        )
    ]
