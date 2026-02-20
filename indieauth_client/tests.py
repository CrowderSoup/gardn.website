from __future__ import annotations

import base64
import hashlib
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from gardn.utils import sanitize_user_bio_html
from .auth import discover_endpoints, fetch_hcard, generate_pkce_pair


class DiscoveryTests(SimpleTestCase):
    @patch("indieauth_client.auth.requests.get")
    def test_parses_link_headers(self, get_mock: Mock) -> None:
        response = Mock()
        response.headers = {
            "Link": '<https://auth.example/authorize>; rel="authorization_endpoint", <https://auth.example/token>; rel="token_endpoint"'
        }
        response.text = "<html></html>"
        response.raise_for_status.return_value = None
        get_mock.return_value = response

        data = discover_endpoints("https://site.example/")
        self.assertEqual(data["authorization_endpoint"], "https://auth.example/authorize")
        self.assertEqual(data["token_endpoint"], "https://auth.example/token")

    @patch("indieauth_client.auth.requests.get")
    def test_parses_html_links(self, get_mock: Mock) -> None:
        response = Mock()
        response.headers = {}
        response.text = (
            '<link href="https://auth.example/authorize" rel="authorization_endpoint">'
            '<link rel="token_endpoint" href="https://auth.example/token">'
        )
        response.raise_for_status.return_value = None
        get_mock.return_value = response

        data = discover_endpoints("https://site.example/")
        self.assertEqual(data["authorization_endpoint"], "https://auth.example/authorize")
        self.assertEqual(data["token_endpoint"], "https://auth.example/token")

    @patch("indieauth_client.auth.requests.get")
    def test_indieauth_metadata_discovery(self, get_mock: Mock) -> None:
        profile_response = Mock()
        profile_response.headers = {"Link": '<https://auth.example/.well-known/oauth-authorization-server>; rel="indieauth-metadata"'}
        profile_response.text = "<html></html>"
        profile_response.raise_for_status.return_value = None

        metadata_response = Mock()
        metadata_response.raise_for_status.return_value = None
        metadata_response.json.return_value = {
            "issuer": "https://auth.example/",
            "authorization_endpoint": "https://auth.example/authorize",
            "token_endpoint": "https://auth.example/token",
            "code_challenge_methods_supported": ["S256"],
        }

        get_mock.side_effect = [profile_response, metadata_response]

        data = discover_endpoints("https://site.example/")
        self.assertEqual(data["authorization_endpoint"], "https://auth.example/authorize")
        self.assertEqual(data["token_endpoint"], "https://auth.example/token")
        self.assertEqual(get_mock.call_count, 2)

    @patch("indieauth_client.auth.requests.get")
    def test_indieauth_metadata_via_html_link(self, get_mock: Mock) -> None:
        profile_response = Mock()
        profile_response.headers = {}
        profile_response.text = '<link rel="indieauth-metadata" href="https://auth.example/.well-known/oauth-authorization-server">'
        profile_response.raise_for_status.return_value = None

        metadata_response = Mock()
        metadata_response.raise_for_status.return_value = None
        metadata_response.json.return_value = {
            "issuer": "https://auth.example/",
            "authorization_endpoint": "https://auth.example/authorize",
            "token_endpoint": "https://auth.example/token",
            "code_challenge_methods_supported": ["S256"],
        }

        get_mock.side_effect = [profile_response, metadata_response]

        data = discover_endpoints("https://site.example/")
        self.assertEqual(data["authorization_endpoint"], "https://auth.example/authorize")
        self.assertEqual(data["token_endpoint"], "https://auth.example/token")


class PkceTests(SimpleTestCase):
    def test_pkce_pair_s256(self) -> None:
        verifier, challenge = generate_pkce_pair()
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest()).decode("utf-8").rstrip("=")
        self.assertEqual(challenge, expected)


class HCardTests(SimpleTestCase):
    @patch("indieauth_client.auth.mf2py.parse")
    def test_fetch_hcard_returns_photo_and_bio(self, parse_mock: Mock) -> None:
        parse_mock.return_value = {
            "items": [
                {
                    "type": ["h-card"],
                    "properties": {
                        "name": ["Jane Gardener"],
                        "photo": ["https://site.example/photo.jpg"],
                        "summary": ["Growing things on the web."],
                    },
                }
            ]
        }

        card = fetch_hcard("https://site.example/")
        self.assertEqual(card["display_name"], "Jane Gardener")
        self.assertEqual(card["photo_url"], "https://site.example/photo.jpg")
        self.assertEqual(card["bio"], "Growing things on the web.")

    @patch("indieauth_client.auth.mf2py.parse")
    def test_fetch_hcard_supports_structured_photo(self, parse_mock: Mock) -> None:
        parse_mock.return_value = {
            "items": [
                {
                    "type": ["h-card"],
                    "properties": {
                        "name": ["Jane Gardener"],
                        "photo": [{"value": "https://site.example/avatar.png", "alt": "Avatar"}],
                    },
                }
            ]
        }

        card = fetch_hcard("https://site.example/")
        self.assertEqual(card["photo_url"], "https://site.example/avatar.png")

    @patch("indieauth_client.auth.mf2py.parse")
    def test_fetch_hcard_falls_back_to_note_for_bio(self, parse_mock: Mock) -> None:
        parse_mock.return_value = {
            "items": [
                {
                    "type": ["h-card"],
                    "properties": {
                        "name": ["Jane Gardener"],
                        "note": ["I like compost and CSS."],
                    },
                }
            ]
        }

        card = fetch_hcard("https://site.example/")
        self.assertEqual(card["bio"], "I like compost and CSS.")

    def test_sanitize_user_bio_html_strips_scripts_but_keeps_safe_markup(self) -> None:
        raw = '<p>Hello <strong>world</strong></p><script>alert(1)</script><a href="javascript:alert(2)">x</a>'
        cleaned = sanitize_user_bio_html(raw)
        self.assertEqual(cleaned, '<p>Hello <strong>world</strong></p><a rel="nofollow noopener noreferrer">x</a>')
