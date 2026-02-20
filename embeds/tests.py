from __future__ import annotations

from django.conf import settings
from django.test import TestCase

from plants.models import UserIdentity


class EmbedTests(TestCase):
    def setUp(self) -> None:
        self.user = UserIdentity.objects.create(me_url="https://a.example/", username="a")

    def test_iframe_embed_renders(self) -> None:
        response = self.client.get(
            f"/embed/{self.user.username}/plant/",
            HTTP_REFERER="https://a.example/posts/1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pick-state")
        self.assertContains(response, 'href="https://a.example/"')
        self.assertContains(response, 'alt="Plant for a.example"')

    def test_iframe_embed_rejects_other_domain(self) -> None:
        response = self.client.get(
            f"/embed/{self.user.username}/plant/",
            HTTP_REFERER="https://evil.example/steal",
        )
        self.assertEqual(response.status_code, 403)

    def test_roll_embed_renders(self) -> None:
        response = self.client.get(
            f"/embed/{self.user.username}/roll/",
            HTTP_REFERER="https://a.example/posts/1",
        )
        self.assertEqual(response.status_code, 200)

    def test_gardn_js_contains_api_url(self) -> None:
        response = self.client.get("/gardn.js")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/api/")
        self.assertContains(response, "Login to pick")

    def test_plant_json_has_origin_scoped_cors_header(self) -> None:
        response = self.client.get(
            f"/api/{self.user.username}/plant.json",
            HTTP_ORIGIN="https://a.example",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "https://a.example")
        payload = response.json()
        self.assertEqual(payload["identity_domain"], "a.example")
        self.assertEqual(payload["login_to_pick_url"], f"{settings.PUBLIC_BASE_URL}/login/?next=/u/a/")

    def test_plant_json_rejects_other_origin(self) -> None:
        response = self.client.get(
            f"/api/{self.user.username}/plant.json",
            HTTP_ORIGIN="https://evil.example",
        )
        self.assertEqual(response.status_code, 403)
