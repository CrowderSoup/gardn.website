from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("harvests", "0002_harvest_tags"),
    ]

    operations = [
        migrations.AddField(
            model_name="harvest",
            name="mastodon_posted",
            field=models.BooleanField(default=False),
        ),
    ]
