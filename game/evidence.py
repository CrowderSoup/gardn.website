from __future__ import annotations

from collections.abc import Iterable
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse

import mf2py
import requests
from django.conf import settings
from django.db import models
from django.utils import timezone

from picks.models import Pick
from plants.models import UserIdentity

from .models import NeighborLink, SiteScan, VerifiedActivity

USER_AGENT = f"Gardn/1.0 (+{settings.PUBLIC_BASE_URL})"
BLOGROLL_KEYWORDS = (
    "blogroll",
    "following",
    "links",
    "neighbors",
    "neighbours",
    "webring",
)
ENTRY_ACTIVITY_KINDS = (
    VerifiedActivity.KIND_PUBLISHED_ENTRY,
    VerifiedActivity.KIND_PUBLISHED_BOOKMARK,
)


class _SiteHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.link_rels: list[tuple[str, str]] = []
        self.anchor_hrefs: list[str] = []
        self.iframe_srcs: list[str] = []
        self.script_srcs: list[str] = []
        self.roll_usernames: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        tag = tag.lower()
        if tag == "link":
            href = attr_map.get("href")
            for rel in attr_map.get("rel", "").split():
                if href:
                    self.link_rels.append((rel.lower(), href))
            return
        if tag == "a":
            href = attr_map.get("href", "").strip()
            if href:
                self.anchor_hrefs.append(href)
            return
        if tag == "iframe":
            src = attr_map.get("src", "").strip()
            if src:
                self.iframe_srcs.append(src)
            return
        if tag == "script":
            src = attr_map.get("src", "").strip()
            if src:
                self.script_srcs.append(src)
            return
        username = attr_map.get("data-gardn-roll", "").strip()
        if username:
            self.roll_usernames.append(username)


def _gardn_embed_from_iframe(src: str, page_url: str) -> tuple[str, str]:
    resolved = _canonical_url(src, page_url)
    if not resolved:
        return "", ""
    parsed = urlparse(resolved)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[0] != "embed":
        return "", ""
    return parts[2], parts[1]


def _page_roll_embed_usernames(page_url: str, parser: _SiteHTMLParser) -> set[str]:
    usernames = {username for username in parser.roll_usernames if username}
    for src in parser.iframe_srcs:
        embed_kind, username = _gardn_embed_from_iframe(src, page_url)
        if embed_kind == "roll" and username:
            usernames.add(username)
    return usernames


def _origin_for_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _identity_for_target_url(variants: dict[str, UserIdentity], target_url: str) -> UserIdentity | None:
    resolved = _canonical_url(target_url)
    if not resolved:
        return None
    direct = variants.get(resolved)
    if direct:
        return direct
    for variant in _url_variants(resolved):
        target = variants.get(variant)
        if target:
            return target
    return None


def _gardn_api_base_candidates(page_url: str, parser: _SiteHTMLParser) -> list[str]:
    bases: set[str] = set()

    for src in parser.iframe_srcs:
        resolved = _canonical_url(src, page_url)
        if not resolved:
            continue
        parsed = urlparse(resolved)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 3 and parts[0] == "embed":
            origin = _origin_for_url(resolved)
            if origin:
                bases.add(origin)

    for src in parser.script_srcs:
        resolved = _canonical_url(src, page_url)
        if not resolved:
            continue
        parsed = urlparse(resolved)
        if parsed.path.rstrip("/").endswith("/gardn.js"):
            origin = _origin_for_url(resolved)
            if origin:
                bases.add(origin)

    if not bases:
        bases.add(settings.PUBLIC_BASE_URL.rstrip("/"))

    return sorted(bases)


def _fetch_gardn_roll_rows(api_base: str, username: str, *, me_url: str, page_url: str) -> list[dict]:
    origin = _origin_for_url(me_url)
    if not origin:
        return []

    endpoint = f"{api_base.rstrip('/')}/api/{quote(username)}/roll.json"
    try:
        response = requests.get(
            endpoint,
            timeout=12,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
                "Origin": origin,
                "Referer": page_url,
            },
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    rows = payload.get("roll") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _parse_link_header(link_header: str) -> dict[str, str]:
    endpoints: dict[str, str] = {}
    if not link_header:
        return endpoints
    for item in link_header.split(","):
        item = item.strip()
        if "<" not in item or ">" not in item or "rel=" not in item:
            continue
        href = item[item.find("<") + 1:item.find(">")].strip()
        rel_part = item.split("rel=", 1)[1].strip().strip("\"'")
        for rel in rel_part.split():
            endpoints[rel.lower()] = href
    return endpoints


def _url_variants(url: str) -> set[str]:
    normalized = url.rstrip("/")
    if not normalized:
        return set()
    variants = {normalized, f"{normalized}/"}
    if normalized.startswith("https://"):
        http = f"http://{normalized[8:]}"
        variants.update({http, f"{http}/"})
    elif normalized.startswith("http://"):
        https = f"https://{normalized[7:]}"
        variants.update({https, f"{https}/"})
    return variants


def _canonical_url(raw: str, base_url: str | None = None) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if base_url:
        value = urljoin(base_url, value)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    return parsed._replace(path=path, params="", fragment="").geturl()


def _safe_text(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("value") or value.get("html") or value.get("url") or "").strip()
    if value is None:
        return ""
    return str(value).strip()


def _property_values(props: dict, key: str, base_url: str) -> list[str]:
    values: list[str] = []
    for value in props.get(key, []):
        text = _safe_text(value)
        if not text:
            continue
        if key in {"url", "uid", "bookmark-of"}:
            text = _canonical_url(text, base_url)
        values.append(text)
    return [value for value in values if value]


def _iter_mf2_items(items: Iterable[dict]) -> Iterable[dict]:
    for item in items:
        yield item
        children = item.get("children") or []
        if children:
            yield from _iter_mf2_items(children)


def _extract_entries(document: dict, page_url: str) -> tuple[list[dict], bool, bool, bool]:
    entries: list[dict] = []
    has_h_feed = False
    has_h_entry = False
    had_entry_without_url = False

    for item in _iter_mf2_items(document.get("items", [])):
        item_types = {value.lower() for value in item.get("type", [])}
        if "h-feed" in item_types:
            has_h_feed = True
        if "h-entry" not in item_types:
            continue

        has_h_entry = True
        props = item.get("properties", {})
        bookmark_targets = _property_values(props, "bookmark-of", page_url)
        entry_urls = _property_values(props, "url", page_url) or _property_values(props, "uid", page_url)
        source_url = entry_urls[0] if entry_urls else ""
        canonical_url = bookmark_targets[0] if bookmark_targets else source_url
        if not canonical_url:
            had_entry_without_url = True
            continue

        title = _property_values(props, "name", page_url)
        if not title:
            title = _property_values(props, "content", page_url)

        entries.append(
            {
                "kind": (
                    VerifiedActivity.KIND_PUBLISHED_BOOKMARK
                    if bookmark_targets
                    else VerifiedActivity.KIND_PUBLISHED_ENTRY
                ),
                "canonical_url": canonical_url,
                "source_url": source_url,
                "title": (title[0] if title else canonical_url)[:500],
                "metadata": {
                    "bookmark_of": bookmark_targets[0] if bookmark_targets else "",
                    "source_page": page_url,
                },
            }
        )

    return entries, has_h_feed, has_h_entry, had_entry_without_url


def _fetch_document(url: str) -> tuple[requests.Response, str, _SiteHTMLParser]:
    response = requests.get(
        url,
        timeout=12,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": USER_AGENT,
        },
    )
    response.raise_for_status()
    html = response.text
    parser = _SiteHTMLParser()
    parser.feed(html)
    return response, html, parser


def _extract_entries_from_html(html: str, page_url: str) -> tuple[list[dict], bool, bool, bool]:
    try:
        document = mf2py.parse(doc=html, url=page_url)
    except Exception:
        document = {"items": []}
    return _extract_entries(document, page_url)


def _discover_capabilities(me_url: str, parser: _SiteHTMLParser, response: requests.Response) -> dict[str, object]:
    endpoints = _parse_link_header(response.headers.get("Link", ""))
    for rel, href in parser.link_rels:
        endpoints.setdefault(rel, href)

    capabilities: dict[str, object] = {
        "authorization_endpoint": "",
        "token_endpoint": "",
        "micropub_endpoint": "",
        "webmention_endpoint": "",
        "has_h_feed": False,
        "has_h_entry": False,
        "roll_embed": False,
    }

    metadata_rel = endpoints.get("indieauth-metadata")
    if metadata_rel:
        metadata_url = _canonical_url(metadata_rel, me_url)
        if metadata_url:
            try:
                meta_response = requests.get(
                    metadata_url,
                    timeout=12,
                    headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                )
                meta_response.raise_for_status()
                metadata = meta_response.json()
            except Exception:
                metadata = {}
            capabilities["authorization_endpoint"] = metadata.get("authorization_endpoint", "")
            capabilities["token_endpoint"] = metadata.get("token_endpoint", "")
            capabilities["micropub_endpoint"] = metadata.get("micropub", "")

    for rel in ("authorization_endpoint", "token_endpoint", "micropub", "webmention"):
        href = endpoints.get(rel)
        if not href:
            continue
        resolved = _canonical_url(href, me_url)
        if rel == "micropub":
            capabilities["micropub_endpoint"] = capabilities["micropub_endpoint"] or resolved
        elif rel == "webmention":
            capabilities["webmention_endpoint"] = resolved
        else:
            capabilities[rel] = capabilities[rel] or resolved

    roll_embed = any("/roll/" in src for src in parser.iframe_srcs) or bool(parser.roll_usernames)
    capabilities["roll_embed"] = roll_embed
    return capabilities


def _find_activity(
    identity: UserIdentity,
    *,
    kind: str,
    canonical_url: str = "",
    source_url: str = "",
    pending_only: bool = False,
) -> VerifiedActivity | None:
    queryset = VerifiedActivity.objects.filter(identity=identity, kind=kind)
    if pending_only:
        queryset = queryset.filter(status=VerifiedActivity.STATUS_PENDING)
    url_filters = models.Q()
    if canonical_url:
        url_filters |= models.Q(canonical_url=canonical_url)
    if source_url:
        url_filters |= models.Q(source_url=source_url)
    if url_filters:
        return queryset.filter(url_filters).order_by("-updated_at").first()
    return queryset.order_by("-updated_at").first()


def register_pending_activity(
    identity: UserIdentity,
    *,
    kind: str,
    canonical_url: str = "",
    source_url: str = "",
    title: str = "",
    metadata: dict | None = None,
) -> VerifiedActivity:
    activity = _find_activity(
        identity,
        kind=kind,
        canonical_url=canonical_url,
        source_url=source_url,
        pending_only=True,
    )
    if activity is None:
        activity = VerifiedActivity(identity=identity, kind=kind)
    activity.status = VerifiedActivity.STATUS_PENDING
    activity.canonical_url = canonical_url
    activity.source_url = source_url
    activity.title = title[:500]
    activity.metadata = metadata or {}
    activity.verified_at = None
    activity.save()
    return activity


def _raise_for_status_with_body(response: requests.Response) -> None:
    if response.ok:
        return
    detail = response.text[:500] if response.text else "(empty body)"
    raise ValueError(f"{response.status_code} {response.reason}: {detail}")


def publish_bookmark_via_micropub(
    identity: UserIdentity,
    *,
    micropub_endpoint: str,
    access_token: str,
    target_url: str,
    title: str = "",
) -> VerifiedActivity:
    canonical_target = _canonical_url(target_url)
    if not canonical_target:
        raise ValueError("A valid target URL is required")

    response = requests.post(
        micropub_endpoint,
        timeout=12,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        data={
            "h": "entry",
            "bookmark-of": canonical_target,
            "name": title,
        },
    )
    _raise_for_status_with_body(response)
    source_url = _canonical_url(response.headers.get("Location", ""))

    from harvests.models import Harvest

    harvest, created = Harvest.objects.get_or_create(
        identity=identity,
        url=canonical_target,
        defaults={"title": title, "micropub_posted": True},
    )
    if not created:
        update_fields: list[str] = []
        if title and harvest.title != title:
            harvest.title = title
            update_fields.append("title")
        if not harvest.micropub_posted:
            harvest.micropub_posted = True
            update_fields.append("micropub_posted")
        if update_fields:
            harvest.save(update_fields=update_fields)

    return register_pending_activity(
        identity,
        kind=VerifiedActivity.KIND_PUBLISHED_BOOKMARK,
        canonical_url=canonical_target,
        source_url=source_url,
        title=title or canonical_target,
        metadata={"created_via": "micropub"},
    )


def publish_note_via_micropub(
    identity: UserIdentity,
    *,
    micropub_endpoint: str,
    access_token: str,
    content: str,
    title: str = "",
) -> VerifiedActivity:
    preview = content.strip()
    if not preview:
        raise ValueError("Post content is required")

    response = requests.post(
        micropub_endpoint,
        timeout=12,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        data={
            "h": "entry",
            "name": title,
            "content": preview,
        },
    )
    _raise_for_status_with_body(response)
    source_url = _canonical_url(response.headers.get("Location", ""))

    return register_pending_activity(
        identity,
        kind=VerifiedActivity.KIND_PUBLISHED_ENTRY,
        canonical_url=source_url,
        source_url=source_url,
        title=(title or preview[:80]).strip(),
        metadata={"created_via": "micropub", "preview": preview[:160]},
    )


def upsert_verified_activity(
    identity: UserIdentity,
    *,
    kind: str,
    canonical_url: str = "",
    source_url: str = "",
    title: str = "",
    metadata: dict | None = None,
    status: str = VerifiedActivity.STATUS_VERIFIED,
) -> VerifiedActivity:
    activity = _find_activity(identity, kind=kind, canonical_url=canonical_url, source_url=source_url)
    if activity is None and status == VerifiedActivity.STATUS_VERIFIED:
        activity = _find_activity(
            identity,
            kind=kind,
            canonical_url=canonical_url,
            source_url=source_url,
            pending_only=True,
        )
    if activity is None:
        activity = VerifiedActivity(identity=identity, kind=kind)
    activity.status = status
    activity.canonical_url = canonical_url
    activity.source_url = source_url
    activity.title = title[:500]
    activity.metadata = metadata or {}
    activity.verified_at = timezone.now() if status == VerifiedActivity.STATUS_VERIFIED else None
    activity.save()
    return activity


def serialize_activity(activity: VerifiedActivity) -> dict[str, object]:
    return {
        "id": activity.id,
        "kind": activity.kind,
        "status": activity.status,
        "canonical_url": activity.canonical_url,
        "source_url": activity.source_url,
        "title": activity.title,
        "metadata": activity.metadata,
        "verified_at": activity.verified_at.isoformat() if activity.verified_at else None,
    }


def serialize_neighbor(link: NeighborLink) -> dict[str, object]:
    target = link.target_identity
    return {
        "id": link.id,
        "relationship": link.relationship,
        "target_url": link.target_url,
        "source_url": link.source_url,
        "username": target.username if target else "",
        "display_name": (target.display_name if target else "") or (target.username if target else link.target_url),
        "visitable": bool(target),
        "verified_at": link.verified_at.isoformat() if link.verified_at else None,
    }


def _activity_kind_for_plot(activity: VerifiedActivity | None, fallback_url: str) -> str:
    if activity and activity.kind == VerifiedActivity.KIND_PUBLISHED_BOOKMARK:
        return "vine"
    if activity and activity.kind == VerifiedActivity.KIND_PUBLISHED_ENTRY:
        return "flower"
    if fallback_url:
        return "tree"
    return "default"


def _identity_variant_map(owner: UserIdentity) -> dict[str, UserIdentity]:
    base_url = settings.PUBLIC_BASE_URL.rstrip("/")
    variants: dict[str, UserIdentity] = {}
    for identity in UserIdentity.objects.exclude(id=owner.id):
        urls = set(_url_variants(identity.me_url))
        if identity.username:
            urls.update(_url_variants(f"{base_url}/u/{identity.username}/"))
        for variant in urls:
            variants[variant] = identity
    return variants


def _collect_blogroll_links(
    owner: UserIdentity,
    *,
    me_url: str,
    home_html: str,
    home_parser: _SiteHTMLParser,
    manual_page_url: str = "",
    prefetched_pages: dict[str, tuple[str, _SiteHTMLParser]] | None = None,
) -> tuple[list[dict], bool]:
    pages: dict[str, tuple[str, _SiteHTMLParser]] = {
        me_url: (home_html, home_parser),
    }
    if prefetched_pages:
        pages.update(prefetched_pages)

    variants = _identity_variant_map(owner)
    discovered: list[dict] = []

    candidate_pages = {me_url}
    owner_origin = _origin_for_url(me_url)
    existing_source_pages = (
        NeighborLink.objects.filter(identity=owner)
        .exclude(source_url="")
        .values_list("source_url", flat=True)
    )
    for source_url in existing_source_pages:
        resolved_source = _canonical_url(source_url, me_url)
        if not resolved_source or _origin_for_url(resolved_source) != owner_origin:
            continue
        candidate_pages.add(resolved_source)
    for href in home_parser.anchor_hrefs:
        lowered = href.lower()
        if any(keyword in lowered for keyword in BLOGROLL_KEYWORDS):
            resolved = _canonical_url(href, me_url)
            if resolved:
                candidate_pages.add(resolved)
    if manual_page_url:
        resolved_manual = _canonical_url(manual_page_url, me_url)
        if resolved_manual:
            candidate_pages.add(resolved_manual)

    for page_url in sorted(candidate_pages):
        if page_url not in pages:
            try:
                _response, html, parser = _fetch_document(page_url)
            except Exception:
                continue
            pages[page_url] = (html, parser)

        _html, parser = pages[page_url]
        for href in parser.anchor_hrefs:
            resolved = _canonical_url(href, page_url)
            if not resolved:
                continue
            target = variants.get(resolved) or next(
                (variants.get(variant) for variant in _url_variants(resolved) if variants.get(variant)),
                None,
            )
            if target is None:
                continue
            discovered.append(
                {
                    "relationship": NeighborLink.RELATIONSHIP_BLOGROLL,
                    "source_url": page_url,
                    "target_identity": target,
                    "target_url": target.me_url,
                    "metadata": {"discovered_from": page_url},
                }
            )

    roll_embed_pages: set[str] = set()
    for page_url, (_html, parser) in pages.items():
        if owner.username and owner.username in _page_roll_embed_usernames(page_url, parser):
            roll_embed_pages.add(page_url)
            for api_base in _gardn_api_base_candidates(page_url, parser):
                for row in _fetch_gardn_roll_rows(api_base, owner.username, me_url=me_url, page_url=page_url):
                    target_url = _canonical_url(_safe_text(row.get("me_url") or row.get("profile_url")))
                    if not target_url:
                        continue
                    discovered.append(
                        {
                            "relationship": NeighborLink.RELATIONSHIP_GARDN_ROLL,
                            "source_url": page_url,
                            "target_identity": _identity_for_target_url(variants, target_url),
                            "target_url": target_url,
                            "metadata": {
                                "discovered_from": "gardn_roll_api",
                                "embed_page": page_url,
                                "api_base": api_base,
                                "target_username": _safe_text(row.get("username")),
                            },
                        }
                    )

    if roll_embed_pages:
        picks = list(Pick.objects.filter(picker=owner).select_related("picked"))
        for page_url in sorted(roll_embed_pages):
            for pick in picks:
                discovered.append(
                    {
                        "relationship": NeighborLink.RELATIONSHIP_GARDN_ROLL,
                        "source_url": page_url,
                        "target_identity": pick.picked,
                        "target_url": pick.picked.me_url,
                        "metadata": {
                            "discovered_from": "gardn_roll_embed",
                            "embed_page": page_url,
                        },
                    }
                )

    deduped: dict[tuple[str, str], dict] = {}
    for link in discovered:
        deduped[(link["target_url"], link["relationship"])] = link
    return list(deduped.values()), bool(roll_embed_pages)


def _sync_neighbor_links(identity: UserIdentity, links: list[dict]) -> list[NeighborLink]:
    now = timezone.now()
    current_keys = {(link["target_url"], link["relationship"]) for link in links}
    existing = NeighborLink.objects.filter(identity=identity)
    for neighbor in existing:
        key = (neighbor.target_url, neighbor.relationship)
        if key not in current_keys:
            neighbor.delete()

    saved: list[NeighborLink] = []
    for link in links:
        neighbor, _created = NeighborLink.objects.update_or_create(
            identity=identity,
            target_url=link["target_url"],
            relationship=link["relationship"],
            defaults={
                "target_identity": link["target_identity"],
                "source_url": link["source_url"],
                "metadata": link["metadata"],
                "verified_at": now,
            },
        )
        upsert_verified_activity(
            identity,
            kind=VerifiedActivity.KIND_BLOGROLL_LINK,
            canonical_url=neighbor.target_url,
            source_url=neighbor.source_url,
            title=(neighbor.target_identity.display_name if neighbor.target_identity else neighbor.target_url)
            or neighbor.target_url,
            metadata={
                "relationship": neighbor.relationship,
                "target_username": neighbor.target_identity.username if neighbor.target_identity else "",
            },
        )
        saved.append(neighbor)
    return saved


def get_or_create_site_scan(identity: UserIdentity) -> SiteScan:
    scan, _created = SiteScan.objects.get_or_create(identity=identity)
    return scan


def run_site_scan(identity: UserIdentity, manual_page_url: str = "") -> SiteScan:
    scan = get_or_create_site_scan(identity)
    now = timezone.now()

    try:
        response, html, parser = _fetch_document(identity.me_url)
    except Exception as exc:
        scan.status = SiteScan.STATUS_SCAN_FAILED
        scan.scanned_url = identity.me_url
        scan.capabilities = {
            "website_verified": identity.website_verified,
            "authorization_endpoint": "",
            "token_endpoint": "",
            "micropub_endpoint": "",
            "webmention_endpoint": "",
            "has_h_feed": False,
            "has_h_entry": False,
            "roll_embed": False,
        }
        scan.issues = ["scan_failed"]
        scan.last_error = str(exc)
        scan.last_scanned_at = now
        scan.save(
            update_fields=[
                "status",
                "scanned_url",
                "capabilities",
                "issues",
                "last_error",
                "last_scanned_at",
                "updated_at",
            ]
        )
        return scan

    entries, has_h_feed, has_h_entry, had_entry_without_url = _extract_entries_from_html(html, identity.me_url)
    capabilities = _discover_capabilities(identity.me_url, parser, response)
    capabilities["website_verified"] = identity.website_verified
    capabilities["has_h_feed"] = has_h_feed
    capabilities["has_h_entry"] = has_h_entry
    prefetched_pages: dict[str, tuple[str, _SiteHTMLParser]] = {}
    manual_page_has_entries = False
    resolved_manual_page_url = _canonical_url(manual_page_url, identity.me_url) if manual_page_url else ""

    if resolved_manual_page_url and resolved_manual_page_url != identity.me_url:
        try:
            _manual_response, manual_html, manual_parser = _fetch_document(resolved_manual_page_url)
        except Exception:
            manual_html = ""
        else:
            prefetched_pages[resolved_manual_page_url] = (manual_html, manual_parser)
            manual_entries, manual_has_h_feed, manual_has_h_entry, manual_had_entry_without_url = _extract_entries_from_html(
                manual_html,
                resolved_manual_page_url,
            )
            entries.extend(manual_entries)
            manual_page_has_entries = manual_has_h_feed or manual_has_h_entry
            has_h_feed = has_h_feed or manual_has_h_feed
            has_h_entry = has_h_entry or manual_has_h_entry
            had_entry_without_url = had_entry_without_url or manual_had_entry_without_url
            capabilities["has_h_feed"] = has_h_feed
            capabilities["has_h_entry"] = has_h_entry

    upsert_verified_activity(
        identity,
        kind=VerifiedActivity.KIND_SITE_VERIFIED,
        canonical_url=identity.me_url,
        source_url=identity.me_url,
        title=identity.display_name or identity.username or identity.me_url,
        metadata={"website_verified": identity.website_verified},
    )

    for entry in entries:
        upsert_verified_activity(
            identity,
            kind=entry["kind"],
            canonical_url=entry["canonical_url"],
            source_url=entry["source_url"],
            title=entry["title"],
            metadata=entry["metadata"],
        )

    blogroll_links, has_roll_embed = _collect_blogroll_links(
        identity,
        me_url=identity.me_url,
        home_html=html,
        home_parser=parser,
        manual_page_url=manual_page_url,
        prefetched_pages=prefetched_pages,
    )
    capabilities["roll_embed"] = bool(capabilities["roll_embed"] or has_roll_embed)
    neighbors = _sync_neighbor_links(identity, blogroll_links)

    issues: list[str] = []
    if has_h_entry and had_entry_without_url:
        issues.append("missing_markup")
    if not has_h_entry and not has_h_feed:
        issues.append("missing_feed")
    if manual_page_url and not neighbors and not manual_page_has_entries:
        issues.append("missing_blogroll")

    if "missing_blogroll" in issues and not has_h_entry and not has_h_feed:
        status = SiteScan.STATUS_MISSING_FEED
    elif "missing_blogroll" in issues:
        status = SiteScan.STATUS_MISSING_BLOGROLL
    elif "missing_markup" in issues:
        status = SiteScan.STATUS_MISSING_MARKUP
    elif "missing_feed" in issues:
        status = SiteScan.STATUS_MISSING_FEED
    else:
        status = SiteScan.STATUS_VERIFIED

    scan.status = status
    scan.scanned_url = identity.me_url
    scan.capabilities = capabilities
    scan.issues = issues
    scan.last_error = ""
    scan.last_scanned_at = now
    scan.save(
        update_fields=[
            "status",
            "scanned_url",
            "capabilities",
            "issues",
            "last_error",
            "last_scanned_at",
            "updated_at",
        ]
    )
    return scan


def seed_inventory(identity: UserIdentity) -> tuple[list[VerifiedActivity], list[VerifiedActivity]]:
    planted_ids = set(
        identity.game_profile.garden_plots.exclude(verified_activity_id=None).values_list("verified_activity_id", flat=True)
    ) if hasattr(identity, "game_profile") else set()
    verified = list(
        VerifiedActivity.objects.filter(
            identity=identity,
            kind__in=ENTRY_ACTIVITY_KINDS,
            status=VerifiedActivity.STATUS_VERIFIED,
        )
        .exclude(id__in=planted_ids)
        .order_by("-verified_at", "-created_at")
    )
    pending = list(
        VerifiedActivity.objects.filter(
            identity=identity,
            kind__in=ENTRY_ACTIVITY_KINDS,
            status=VerifiedActivity.STATUS_PENDING,
        ).order_by("-created_at")
    )
    return verified, pending


def calculate_growth_stage(plot, recent_verified_count: int = 0, recent_visitor_count: int = 0) -> int:
    planted_at = plot.planted_at or getattr(plot, "last_watered", None) or getattr(plot, "updated_at", None)
    if not planted_at:
        return 0
    age_days = max(0, (timezone.now() - planted_at).days)
    stage = min(4, age_days // 2 + 1)
    if recent_verified_count:
        stage = min(4, stage + 1)
    if recent_visitor_count:
        stage = min(4, stage + 1)
    return stage


def plant_type_for_activity(activity: VerifiedActivity | None, fallback_url: str = "") -> str:
    return _activity_kind_for_plot(activity, fallback_url)
