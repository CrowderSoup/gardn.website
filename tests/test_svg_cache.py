from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from plants.models import UserIdentity
from plants.svg_cache import svg_cache_key


class SvgCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.identity = UserIdentity.objects.create(
            me_url="https://example.com/",
            username="testuser",
            display_name="Test User",
        )
        session = self.client.session
        session["identity_id"] = self.identity.id
        session.save()

    def test_svg_view_populates_cache(self):
        cache.delete(svg_cache_key(self.identity.username))
        with patch("plants.views.generate_svg", return_value="<svg>test</svg>"):
            response = self.client.get(f"/u/{self.identity.username}/plant.svg")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(cache.get(svg_cache_key(self.identity.username)))

    def test_svg_view_uses_cache(self):
        cache.set(svg_cache_key(self.identity.username), "<svg>from-cache</svg>", timeout=3600)
        with patch("plants.views.generate_svg") as mock_generate:
            response = self.client.get(f"/u/{self.identity.username}/plant.svg")
        mock_generate.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"from-cache", response.content)

    def test_harvest_delete_invalidates_svg_cache(self):
        from harvests.models import Harvest
        harvest = Harvest.objects.create(identity=self.identity, url="https://example.com/article")
        cache.set(svg_cache_key(self.identity.username), "<svg>stale</svg>", timeout=3600)
        self.client.post(f"/harvest/{harvest.id}/delete/")
        self.assertIsNone(cache.get(svg_cache_key(self.identity.username)))

    def test_pick_invalidates_svg_cache_for_both_users(self):
        other = UserIdentity.objects.create(
            me_url="https://other.com/",
            username="otheruser",
            display_name="Other User",
        )
        cache.set(svg_cache_key(self.identity.username), "<svg>picker</svg>", timeout=3600)
        cache.set(svg_cache_key(other.username), "<svg>picked</svg>", timeout=3600)
        self.client.post(f"/pick/{other.username}/")
        self.assertIsNone(cache.get(svg_cache_key(self.identity.username)))
        self.assertIsNone(cache.get(svg_cache_key(other.username)))
