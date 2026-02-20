from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlparse

import mf2py
import requests


class _LinkTagParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "link":
            return
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        rels = attr_map.get("rel", "").split()
        href = attr_map.get("href")
        if href:
            for rel in rels:
                self.links.append((rel.lower(), href))


def canonicalize_me_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("me URL is required")
    if not value.startswith(("https://", "http://")):
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed")
    if not parsed.netloc:
        raise ValueError("Invalid me URL")

    path = parsed.path or "/"
    return parsed._replace(path=path, params="", query="", fragment="").geturl()


def _parse_link_header(link_header: str) -> dict[str, str]:
    endpoints: dict[str, str] = {}
    if not link_header:
        return endpoints
    for item in link_header.split(","):
        match = re.search(r"""<([^>]+)>\s*;\s*rel=[\"']?([^\"';]+)[\"']?""", item)
        if not match:
            continue
        href, rel = match.group(1), match.group(2)
        for rel_token in rel.split():
            endpoints[rel_token.strip().lower()] = href.strip()
    return endpoints


def discover_endpoints(me_url: str, timeout: int = 8) -> dict[str, str]:
    response = requests.get(me_url, timeout=timeout, headers={"Accept": "text/html,application/xhtml+xml"})
    response.raise_for_status()

    # HTTP Link header takes precedence over HTML <link> elements
    endpoints = _parse_link_header(response.headers.get("Link", ""))

    parser = _LinkTagParser()
    parser.feed(response.text)
    for rel, href in parser.links:
        endpoints.setdefault(rel, href)

    resolved: dict[str, str] = {}

    # IndieAuth spec: check for indieauth-metadata first (modern discovery)
    metadata_rel = endpoints.get("indieauth-metadata")
    if metadata_rel:
        metadata_url = urljoin(me_url, metadata_rel)
        meta_response = requests.get(metadata_url, timeout=timeout, headers={"Accept": "application/json"})
        meta_response.raise_for_status()
        meta = meta_response.json()
        for key in ["authorization_endpoint", "token_endpoint", "userinfo_endpoint"]:
            if key in meta:
                resolved[key] = meta[key]

    # Fall back to legacy direct link discovery for backward compatibility
    for key in ["authorization_endpoint", "token_endpoint", "micropub", "microsub"]:
        if key in endpoints and key not in resolved:
            resolved[key] = urljoin(me_url, endpoints[key])

    if "authorization_endpoint" not in resolved:
        raise ValueError("Could not discover required IndieAuth endpoints")
    return resolved


def generate_pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(48)).decode("utf-8").rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest()).decode("utf-8").rstrip("=")
    return verifier, challenge


def build_authorization_url(
    authorization_endpoint: str,
    me: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scope: str = "",
) -> str:
    params: dict[str, str] = {
        "me": me,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if scope:
        params["scope"] = scope
    return f"{authorization_endpoint}?{urlencode(params)}"


def _raise_for_status_with_body(response: requests.Response) -> None:
    """Like raise_for_status() but includes the response body in the exception message."""
    if response.ok:
        return
    try:
        detail = response.json()
    except Exception:
        detail = response.text[:500] if response.text else "(empty body)"
    raise requests.HTTPError(
        f"{response.status_code} {response.reason} — {detail}",
        response=response,
    )


def exchange_code_for_token(
    token_endpoint: str,
    code: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict:
    response = requests.post(
        token_endpoint,
        timeout=8,
        headers={"Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
    )
    _raise_for_status_with_body(response)
    payload = response.json()
    if not payload.get("access_token"):
        raise ValueError("Token response missing access_token")
    return payload


def verify_code_at_auth_endpoint(
    authorization_endpoint: str,
    code: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict:
    """Redeem a code at the authorization endpoint for identity-only (no token) flows."""
    response = requests.post(
        authorization_endpoint,
        timeout=8,
        headers={"Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
    )
    _raise_for_status_with_body(response)
    payload = response.json()
    if not payload.get("me"):
        raise ValueError("Authorization response missing 'me'")
    return payload


def fetch_hcard(me_url: str) -> dict[str, str]:
    def _read_prop(props: dict, key: str) -> str:
        first = (props.get(key) or [""])[0]
        if isinstance(first, dict):
            raw = first.get("value") or first.get("url") or ""
            return str(raw)
        return str(first)

    try:
        parsed = mf2py.parse(url=me_url)
    except Exception:
        return {}

    for item in parsed.get("items", []):
        if "h-card" not in item.get("type", []):
            continue
        props = item.get("properties", {})
        name = _read_prop(props, "name")
        photo = _read_prop(props, "photo")
        summary = _read_prop(props, "summary")
        note = _read_prop(props, "note")
        bio = summary or note
        return {"display_name": name, "photo_url": photo, "bio": bio}
    return {}


def random_state() -> str:
    return secrets.token_urlsafe(24)
