from __future__ import annotations

from django.test import TestCase

from .models import UserIdentity
from .svg import SVG_RENDER_VERSION, _biased_pot_style, generate_svg


class PlantTests(TestCase):
    def test_svg_endpoint_has_cache_headers(self) -> None:
        user = UserIdentity.objects.create(me_url="https://a.example/", username="a")
        response = self.client.get(f"/u/{user.username}/plant.svg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "public, max-age=3600")
        self.assertIn("ETag", response)
        self.assertNotIn("<animate", response.content.decode("utf-8"))

    def test_generate_svg_is_deterministic(self) -> None:
        harvests = ["https://example.com/one", "https://example.com/two"]
        first = generate_svg("https://a.example/", harvest_urls=harvests)
        second = generate_svg("https://a.example/", harvest_urls=list(reversed(harvests)))
        self.assertEqual(first, second)
        self.assertIn(f"render:{SVG_RENDER_VERSION};motion:0", first)
        self.assertNotIn("<animate", first)

    def test_generate_svg_can_enable_motion(self) -> None:
        svg = generate_svg("https://a.example/", harvest_urls=["https://example.com/one"], motion_enabled=True)
        self.assertIn(f"render:{SVG_RENDER_VERSION};motion:1", svg)
        self.assertIn("<animate", svg)
        self.assertIn("<animateTransform", svg)

    def test_pot_style_biases_with_activity(self) -> None:
        low_activity_style = _biased_pot_style(seed_value=7, harvest_count=1, pick_count=0)
        high_activity_style = _biased_pot_style(seed_value=7, harvest_count=10, pick_count=8)
        self.assertLessEqual(low_activity_style, 3)
        self.assertGreaterEqual(high_activity_style, 3)

    def test_endpoint_refreshes_legacy_cache(self) -> None:
        user = UserIdentity.objects.create(
            me_url="https://legacy.example/",
            username="legacy",
            svg_cache="<svg><!-- render:v1 --></svg>",
        )
        response = self.client.get(f"/u/{user.username}/plant.svg")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"render:{SVG_RENDER_VERSION}", response.content.decode("utf-8"))
        user.refresh_from_db()
        self.assertIn(f"render:{SVG_RENDER_VERSION}", user.svg_cache)

    def test_profile_settings_toggles_motion_and_invalidates_svg_cache(self) -> None:
        user = UserIdentity.objects.create(
            me_url="https://toggle.example/",
            username="toggle",
            svg_cache="<svg>cached</svg>",
        )
        session = self.client.session
        session["identity_id"] = user.id
        session.save()

        response = self.client.post(
            "/settings/profile/",
            {"animate_plant_motion": "on"},
        )
        self.assertEqual(response.status_code, 302)

        user.refresh_from_db()
        self.assertTrue(user.animate_plant_motion)
        self.assertEqual(user.svg_cache, "")
