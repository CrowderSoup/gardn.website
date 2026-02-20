from __future__ import annotations

from django.db import models


class UserIdentity(models.Model):
    me_url = models.URLField(unique=True)
    username = models.SlugField(unique=True, max_length=64)
    display_name = models.CharField(max_length=255, blank=True)
    photo_url = models.URLField(blank=True)
    bio = models.TextField(blank=True)
    svg_cache = models.TextField(blank=True)
    show_harvests_on_profile = models.BooleanField(default=False)
    animate_plant_motion = models.BooleanField(default=False)
    login_method = models.CharField(
        max_length=20,
        choices=[("indieauth", "IndieAuth"), ("mastodon", "Mastodon")],
        default="indieauth",
    )
    mastodon_handle = models.CharField(max_length=255, blank=True)
    mastodon_profile_url = models.URLField(blank=True)
    mastodon_access_token = models.TextField(blank=True)
    website_verified = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.display_name or self.me_url
