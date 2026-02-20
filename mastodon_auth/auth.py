from __future__ import annotations

import secrets
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests
from django.conf import settings

from .models import MastodonApp


def parse_handle(handle: str) -> tuple[str, str]:
    """Parse @user@instance.social or user@instance.social or https://instance.social/@user.
    Returns (instance_url, username).
    """
    handle = handle.strip()

    # URL form: https://instance.social/@user
    if handle.startswith("http://") or handle.startswith("https://"):
        parsed = urlparse(handle)
        instance_url = f"{parsed.scheme}://{parsed.netloc}"
        username = parsed.path.lstrip("/@")
        return instance_url, username

    # Handle form: @user@instance or user@instance
    parts = handle.lstrip("@").split("@")
    if len(parts) == 2:
        username, instance = parts
        return f"https://{instance}", username

    raise ValueError(f"Cannot parse Mastodon handle: {handle!r}")


def get_or_register_app(instance_url: str) -> MastodonApp:
    """Look up cached MastodonApp or register a new one via POST /api/v1/apps."""
    instance_url = instance_url.rstrip("/")
    app = MastodonApp.objects.filter(instance_url=instance_url).first()
    if app:
        return app

    redirect_uri = f"{settings.PUBLIC_BASE_URL}/mastodon/callback/"
    resp = requests.post(
        f"{instance_url}/api/v1/apps",
        data={
            "client_name": "Gardn",
            "redirect_uris": redirect_uri,
            "scopes": "read:accounts write:statuses",
            "website": settings.PUBLIC_BASE_URL,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return MastodonApp.objects.create(
        instance_url=instance_url,
        client_id=data["client_id"],
        client_secret=data["client_secret"],
    )


def build_auth_url(app: MastodonApp, instance_url: str, state: str) -> str:
    """Build OAuth2 authorization URL with CSRF state."""
    instance_url = instance_url.rstrip("/")
    redirect_uri = f"{settings.PUBLIC_BASE_URL}/mastodon/callback/"
    params = (
        f"?client_id={app.client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=read:accounts+write:statuses"
        f"&state={state}"
    )
    return f"{instance_url}/oauth/authorize{params}"


def exchange_code(app: MastodonApp, instance_url: str, code: str) -> dict:
    """POST /oauth/token to exchange code for access_token."""
    instance_url = instance_url.rstrip("/")
    redirect_uri = f"{settings.PUBLIC_BASE_URL}/mastodon/callback/"
    resp = requests.post(
        f"{instance_url}/oauth/token",
        data={
            "client_id": app.client_id,
            "client_secret": app.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code": code,
            "scope": "read:accounts write:statuses",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_account_info(instance_url: str, access_token: str) -> dict:
    """GET /api/v1/accounts/verify_credentials."""
    instance_url = instance_url.rstrip("/")
    resp = requests.get(
        f"{instance_url}/api/v1/accounts/verify_credentials",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


class _LinkRelMeParser(HTMLParser):
    """Collect all <link rel="me" href="..."> and <a rel="me" href="..."> values from an HTML document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.me_hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() not in ("link", "a"):
            return
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        rel = attr_dict.get("rel", "").lower().split()
        if "me" in rel:
            href = attr_dict.get("href", "").strip()
            if href:
                self.me_hrefs.append(href)


def _url_variants(url: str) -> list[str]:
    """Return a small set of URL variants to compare against (trailing slash, http/https)."""
    url = url.rstrip("/")
    variants = {url, url + "/"}
    if url.startswith("https://"):
        http = "http://" + url[8:]
        variants.add(http)
        variants.add(http + "/")
    elif url.startswith("http://"):
        https = "https://" + url[7:]
        variants.add(https)
        variants.add(https + "/")
    return list(variants)


def check_website_link(website_url: str, mastodon_profile_url: str) -> bool:
    """Fetch website_url and look for <link rel="me"> or <a rel="me"> pointing to MASTODON_URL."""
    try:
        resp = requests.get(website_url, timeout=15, headers={"User-Agent": "Gardn/1.0"})
        resp.raise_for_status()
    except Exception:
        return False

    parser = _LinkRelMeParser()
    parser.feed(resp.text)

    target_variants = set(_url_variants(mastodon_profile_url))
    for href in parser.me_hrefs:
        for variant in _url_variants(href):
            if variant in target_variants:
                return True
    return False


def random_state() -> str:
    return secrets.token_urlsafe(24)
