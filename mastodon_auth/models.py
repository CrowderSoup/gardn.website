from __future__ import annotations

from django.db import models


class MastodonApp(models.Model):
    instance_url = models.URLField(unique=True)  # e.g. "https://mastodon.social"
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.instance_url
