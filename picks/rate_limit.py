from __future__ import annotations

from django.core.cache import cache


def hit_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    added = cache.add(key, 1, timeout=window_seconds)
    if added:
        return False

    count = cache.incr(key)
    return count > limit
