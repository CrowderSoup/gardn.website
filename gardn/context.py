from __future__ import annotations

from django.conf import settings


def public_base_url() -> str:
    return settings.PUBLIC_BASE_URL
