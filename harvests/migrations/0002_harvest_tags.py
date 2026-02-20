from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("harvests", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="harvest",
            name="tags",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
