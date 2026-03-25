from __future__ import annotations

import ipaddress
import re
import socket
import unicodedata
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

import requests

TRACKING_QUERY_KEYS = {
    "ad_id",
    "adset_id",
    "campaign_id",
    "dclid",
    "fbclid",
    "gclid",
    "igshid",
    "irclickid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref_src",
    "s_cid",
    "si",
}
COMMON_SECOND_LEVEL_DOMAINS = {"ac", "co", "com", "edu", "gov", "net", "org"}
METADATA_REQUEST_HEADERS = {
    "User-Agent": "gardn.link-harvester/1.0 (+https://gardn.website/)",
    "Accept": "text/html,application/xhtml+xml",
}
MAX_REDIRECTS = 3
MAX_FETCH_BYTES = 262_144
SPACE_RE = re.compile(r"\s+")
TAG_PART_RE = re.compile(r"[,;/|]")


@dataclass(slots=True)
class HarvestMetadata:
    url: str
    title: str = ""
    note: str = ""
    tags: list[str] = field(default_factory=list)
    fetched: bool = False


class _MetadataHTMLParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.in_title = False
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.article_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value for key, value in attrs if key and value is not None}
        lower_tag = tag.lower()

        if lower_tag == "title":
            self.in_title = True
            return

        if lower_tag == "meta":
            key = (
                attr_map.get("property")
                or attr_map.get("name")
                or attr_map.get("itemprop")
                or ""
            ).lower()
            content = _clean_text(attr_map.get("content", ""))
            if not key or not content:
                return
            if key == "article:tag":
                normalized_tag = _normalize_metadata_tag(content)
                if normalized_tag:
                    self.article_tags.append(normalized_tag)
                return
            self.meta.setdefault(key, content)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            cleaned = _clean_text(data)
            if cleaned:
                self.title_parts.append(cleaned)

    def to_metadata(self) -> HarvestMetadata:
        title = (
            self.meta.get("og:title")
            or self.meta.get("twitter:title")
            or self.meta.get("title")
            or _clean_text(" ".join(self.title_parts))
        )
        note = (
            self.meta.get("og:description")
            or self.meta.get("twitter:description")
            or self.meta.get("description")
        )
        keyword_tags = _tags_from_keyword_string(self.meta.get("keywords", ""))
        return HarvestMetadata(
            url=self.base_url,
            title=title,
            note=note,
            tags=merge_tags(keyword_tags, self.article_tags),
            fetched=bool(title or note or keyword_tags or self.article_tags),
        )


def normalize_harvest_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        return ""

    parsed = urlsplit(cleaned)
    hostname = (parsed.hostname or "").lower()
    scheme = parsed.scheme.lower()

    if not hostname or not scheme:
        return cleaned

    netloc = hostname
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth = f"{auth}:{parsed.password}"
        netloc = f"{auth}@{netloc}"

    if parsed.port:
        default_port = 80 if scheme == "http" else 443 if scheme == "https" else None
        if parsed.port != default_port:
            netloc = f"{netloc}:{parsed.port}"

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_query_param(key)
    ]
    query = urlencode(query_pairs, doseq=True)

    return urlunsplit((scheme, netloc, parsed.path, query, ""))


def guess_title_from_url(url: str) -> str:
    parsed = urlsplit(url)
    segments = [unquote(segment).strip() for segment in parsed.path.split("/") if segment.strip()]
    if segments:
        candidate = segments[-1]
    else:
        candidate = _brand_from_hostname(parsed.hostname or "")

    candidate = re.sub(r"\.[a-z0-9]{1,6}$", "", candidate, flags=re.IGNORECASE)
    candidate = SPACE_RE.sub(" ", candidate.replace("-", " ").replace("_", " ")).strip()
    if not candidate:
        return ""
    if candidate.lower() == candidate or candidate.upper() == candidate:
        return candidate.title()
    return candidate


def split_tag_string(value: str) -> list[str]:
    return [tag.strip() for tag in value.split(",") if tag.strip()]


def merge_tags(*tag_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    for group in tag_groups:
        for raw_tag in group:
            tag = raw_tag.strip()
            if not tag:
                continue
            lowered = tag.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            merged.append(tag)

    return merged


def tag_string(tags: list[str]) -> str:
    return ", ".join(merge_tags(tags))


def fetch_url_metadata(url: str) -> HarvestMetadata:
    normalized_url = normalize_harvest_url(url)
    fallback = HarvestMetadata(
        url=normalized_url,
        title=guess_title_from_url(normalized_url),
        tags=_default_tags_for_url(normalized_url),
        fetched=False,
    )
    if not normalized_url:
        return fallback

    current_url = normalized_url

    with requests.Session() as session:
        for _ in range(MAX_REDIRECTS + 1):
            if not _is_safe_fetch_target(current_url):
                return fallback

            try:
                with session.get(
                    current_url,
                    headers=METADATA_REQUEST_HEADERS,
                    timeout=(3.05, 5),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    if 300 <= response.status_code < 400 and response.headers.get("Location"):
                        current_url = normalize_harvest_url(
                            urljoin(current_url, response.headers["Location"].strip())
                        )
                        continue

                    final_url = normalize_harvest_url(response.url or current_url)
                    if "text/html" not in response.headers.get("Content-Type", "").lower():
                        return HarvestMetadata(
                            url=final_url,
                            title=guess_title_from_url(final_url),
                            tags=_default_tags_for_url(final_url),
                            fetched=False,
                        )

                    content = bytearray()
                    for chunk in response.iter_content(chunk_size=16_384):
                        if not chunk:
                            continue
                        content.extend(chunk)
                        if len(content) >= MAX_FETCH_BYTES:
                            break

                    encoding = response.encoding or "utf-8"
                    html = bytes(content).decode(encoding, errors="replace")
            except requests.RequestException:
                return fallback

            parser = _MetadataHTMLParser(final_url)
            parser.feed(html)
            parsed = parser.to_metadata()
            tags = merge_tags(parsed.tags, _default_tags_for_url(final_url))
            return HarvestMetadata(
                url=final_url,
                title=parsed.title or guess_title_from_url(final_url),
                note=parsed.note,
                tags=tags,
                fetched=parsed.fetched,
            )

    return fallback


def _clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", unescape(value or "")).strip()


def _is_tracking_query_param(key: str) -> bool:
    lowered = key.strip().lower()
    return lowered.startswith("utm_") or lowered in TRACKING_QUERY_KEYS


def _is_safe_fetch_target(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = parsed.hostname
    if not hostname or hostname.endswith(".local") or hostname == "localhost":
        return False

    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except OSError:
        return False

    for info in infos:
        candidate = info[4][0].split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False

    return True


def _tags_from_keyword_string(value: str) -> list[str]:
    tags: list[str] = []
    for part in TAG_PART_RE.split(value):
        tag = _normalize_metadata_tag(part)
        if tag:
            tags.append(tag)
    return merge_tags(tags)


def _default_tags_for_url(url: str) -> list[str]:
    brand_tag = _normalize_metadata_tag(_brand_from_hostname(urlsplit(url).hostname or ""))
    return [brand_tag] if brand_tag else []


def _brand_from_hostname(hostname: str) -> str:
    labels = [label for label in hostname.lower().split(".") if label and label != "www"]
    if len(labels) >= 3 and labels[-1] in {"uk", "au", "jp"} and labels[-2] in COMMON_SECOND_LEVEL_DOMAINS:
        return labels[-3]
    if len(labels) >= 2:
        return labels[-2]
    return labels[0] if labels else ""


def _normalize_metadata_tag(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    ascii_value = ascii_value.lower().strip()
    ascii_value = re.sub(r"[^a-z0-9_-]+", "-", ascii_value)
    ascii_value = re.sub(r"-{2,}", "-", ascii_value).strip("-_")
    if not ascii_value:
        return ""
    if len(ascii_value) > 32:
        return ascii_value[:32].rstrip("-_")
    return ascii_value
