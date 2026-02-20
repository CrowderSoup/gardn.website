from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("plants", "0002_useridentity_bio"),
    ]

    operations = [
        migrations.CreateModel(
            name="Harvest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("url", models.URLField()),
                ("title", models.CharField(blank=True, max_length=500)),
                ("note", models.TextField(blank=True)),
                ("micropub_posted", models.BooleanField(default=False)),
                ("harvested_at", models.DateTimeField(auto_now_add=True)),
                (
                    "identity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="harvests",
                        to="plants.useridentity",
                    ),
                ),
            ],
            options={
                "ordering": ["-harvested_at"],
                "unique_together": {("identity", "url")},
            },
        ),
    ]
