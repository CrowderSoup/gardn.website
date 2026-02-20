from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("plants", "0003_useridentity_show_harvests_on_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="useridentity",
            name="login_method",
            field=models.CharField(
                choices=[("indieauth", "IndieAuth"), ("mastodon", "Mastodon")],
                default="indieauth",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="useridentity",
            name="mastodon_handle",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="useridentity",
            name="mastodon_profile_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="useridentity",
            name="mastodon_access_token",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="useridentity",
            name="website_verified",
            field=models.BooleanField(default=True),
        ),
    ]
