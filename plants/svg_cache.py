# plants/svg_cache.py
from __future__ import annotations

from django.core.cache import cache

from plants.svg import SVG_RENDER_VERSION

SVG_CACHE_TIMEOUT = 3600  # 1 hour


def svg_cache_key(username: str) -> str:
    return f"svg:{SVG_RENDER_VERSION}:{username}"


def invalidate_svg(username: str) -> None:
    cache.delete(svg_cache_key(username))
