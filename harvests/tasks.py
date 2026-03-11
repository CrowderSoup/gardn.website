from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests
from celery import shared_task

logger = logging.getLogger(__name__)


def send_harvest_to_micropub(harvest_id: int, micropub_endpoint: str, access_token: str) -> bool:
    from harvests.models import Harvest

    try:
        harvest = Harvest.objects.get(id=harvest_id)
    except Harvest.DoesNotExist:
        return False

    try:
        resp = requests.post(
            micropub_endpoint,
            data={"h": "entry", "bookmark-of": harvest.url, "name": harvest.title},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except requests.RequestException:
        logger.exception("Micropub request failed for harvest %s", harvest_id)
        return False

    if resp.status_code not in (200, 201, 202):
        logger.warning(
            "Micropub request returned %s for harvest %s",
            resp.status_code,
            harvest_id,
        )
        return False

    harvest.micropub_posted = True
    harvest.save(update_fields=["micropub_posted"])
    return True


def send_harvest_to_mastodon(harvest_id: int) -> bool:
    from harvests.models import Harvest

    try:
        harvest = Harvest.objects.get(id=harvest_id)
    except Harvest.DoesNotExist:
        return False

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
    except requests.RequestException:
        logger.exception("Mastodon request failed for harvest %s", harvest_id)
        return False

    if resp.status_code not in (200, 201):
        logger.warning(
            "Mastodon request returned %s for harvest %s",
            resp.status_code,
            harvest_id,
        )
        return False

    harvest.mastodon_posted = True
    harvest.save(update_fields=["mastodon_posted"])
    return True


@shared_task
def post_to_micropub(harvest_id: int, micropub_endpoint: str, access_token: str) -> None:
    send_harvest_to_micropub(harvest_id, micropub_endpoint, access_token)


@shared_task
def post_to_mastodon(harvest_id: int) -> None:
    send_harvest_to_mastodon(harvest_id)
