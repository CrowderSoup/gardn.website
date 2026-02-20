from __future__ import annotations

from django.db import models

from plants.models import UserIdentity


class Pick(models.Model):
    picker = models.ForeignKey(UserIdentity, on_delete=models.CASCADE, related_name="outgoing_picks")
    picked = models.ForeignKey(UserIdentity, on_delete=models.CASCADE, related_name="incoming_picks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["picker", "picked"], name="unique_picker_pair")]

    def __str__(self) -> str:
        return f"{self.picker_id}->{self.picked_id}"
