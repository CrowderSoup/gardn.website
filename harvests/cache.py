from __future__ import annotations

from django.core.cache import cache
from django.db.models import Q

from .models import Harvest

HARVEST_STATS_CACHE_TIMEOUT = 3600  # 1 hour
HARVEST_STATS_CACHE_VERSION = "v1"


def harvest_stats_cache_key(identity_id: int) -> str:
    return f"harvest-stats:{HARVEST_STATS_CACHE_VERSION}:{identity_id}"


def get_harvest_stats(identity_id: int) -> dict[str, int]:
    cache_key = harvest_stats_cache_key(identity_id)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    harvests_qs = Harvest.objects.filter(identity_id=identity_id)
    total_count = harvests_qs.count()
    posted_count = harvests_qs.filter(
        Q(micropub_posted=True) | Q(mastodon_posted=True)
    ).count()

    all_tags: list[str] = []
    for tags in harvests_qs.values_list("tags", flat=True):
        all_tags.extend(tag.strip() for tag in tags.split(",") if tag.strip())

    stats = {
        "total_count": total_count,
        "posted_count": posted_count,
        "unposted_count": total_count - posted_count,
        "unique_tag_count": len(set(all_tags)),
        "health_pct": round(posted_count / total_count * 100) if total_count else 0,
    }
    cache.set(cache_key, stats, timeout=HARVEST_STATS_CACHE_TIMEOUT)
    return stats


def invalidate_harvest_stats(identity_id: int) -> None:
    cache.delete(harvest_stats_cache_key(identity_id))
