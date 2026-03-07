# harvests/tasks.py
from __future__ import annotations

from urllib.parse import urlparse

import requests
from celery import shared_task

from .cache import invalidate_harvest_stats


@shared_task
def post_to_micropub(harvest_id: int, micropub_endpoint: str, access_token: str) -> None:
    from harvests.models import Harvest

    try:
        harvest = Harvest.objects.get(id=harvest_id)
    except Harvest.DoesNotExist:
        return

    try:
        resp = requests.post(
            micropub_endpoint,
            data={"h": "entry", "bookmark-of": harvest.url, "name": harvest.title},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.status_code in (200, 201, 202):
            harvest.micropub_posted = True
            harvest.save(update_fields=["micropub_posted"])
            invalidate_harvest_stats(harvest.identity_id)
    except Exception:
        pass


@shared_task
def post_to_mastodon(harvest_id: int) -> None:
    from harvests.models import Harvest

    try:
        harvest = Harvest.objects.get(id=harvest_id)
    except Harvest.DoesNotExist:
        return

    identity = harvest.identity
    parsed = urlparse(identity.mastodon_profile_url)
    instance_url = f"{parsed.scheme}://{parsed.netloc}"

    parts = []
    if harvest.title:
        parts.append(f'"{harvest.title}"')
    parts.append(harvest.url)
    if harvest.note:
        parts.append(f"\n{harvest.note}")
    tags = harvest.tags_list()
    if tags:
        parts.append("\n" + " ".join(f"#{t}" for t in tags))
    status_text = "\n".join(parts)

    try:
        resp = requests.post(
            f"{instance_url}/api/v1/statuses",
            json={"status": status_text, "visibility": "public"},
            headers={"Authorization": f"Bearer {identity.mastodon_access_token}"},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            harvest.mastodon_posted = True
            harvest.save(update_fields=["mastodon_posted"])
            invalidate_harvest_stats(harvest.identity_id)
    except Exception:
        pass
