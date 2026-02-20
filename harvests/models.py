from __future__ import annotations

from django.db import models

from plants.models import UserIdentity


class Harvest(models.Model):
    identity = models.ForeignKey(UserIdentity, on_delete=models.CASCADE, related_name="harvests")
    url = models.URLField()
    title = models.CharField(max_length=500, blank=True)
    note = models.TextField(blank=True)
    tags = models.CharField(max_length=500, blank=True)
    micropub_posted = models.BooleanField(default=False)
    harvested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-harvested_at"]
        unique_together = [("identity", "url")]

    def __str__(self) -> str:
        return self.title or self.url

    def tags_list(self) -> list[str]:
        return [t.strip() for t in self.tags.split(",") if t.strip()]
