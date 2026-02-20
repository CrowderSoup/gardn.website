from __future__ import annotations

from django.test import TestCase

from .models import UserIdentity


class PlantTests(TestCase):
    def test_svg_endpoint_has_cache_headers(self) -> None:
        user = UserIdentity.objects.create(me_url="https://a.example/", username="a")
        response = self.client.get(f"/u/{user.username}/plant.svg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "public, max-age=3600")
        self.assertIn("ETag", response)
