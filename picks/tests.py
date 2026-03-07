from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase

from plants.models import UserIdentity
from plants.svg_cache import svg_cache_key

from .models import Pick


class PickTests(TestCase):
    def setUp(self) -> None:
        self.a = UserIdentity.objects.create(me_url="https://a.example/", username="a")
        self.b = UserIdentity.objects.create(me_url="https://b.example/", username="b")

    def test_pick_idempotent(self) -> None:
        session = self.client.session
        session["identity_id"] = self.a.id
        session.save()

        self.client.post(f"/pick/{self.b.username}/")
        self.client.post(f"/pick/{self.b.username}/")

        self.assertEqual(Pick.objects.filter(picker=self.a, picked=self.b).count(), 1)

    def test_htmx_returns_fragment(self) -> None:
        session = self.client.session
        session["identity_id"] = self.a.id
        session.save()

        response = self.client.post(f"/pick/{self.b.username}/", HTTP_HX_REQUEST="true")
        self.assertContains(response, 'id="pick-state"')
        self.assertTemplateUsed(response, "picks/_pick_button.html")

    def test_pick_and_unpick_invalidate_svg_cache_for_both_users(self) -> None:
        cache.set(svg_cache_key(self.a.username), "<svg>a</svg>", timeout=3600)
        cache.set(svg_cache_key(self.b.username), "<svg>b</svg>", timeout=3600)

        session = self.client.session
        session["identity_id"] = self.a.id
        session.save()

        self.client.post(f"/pick/{self.b.username}/")
        self.assertIsNone(cache.get(svg_cache_key(self.a.username)))
        self.assertIsNone(cache.get(svg_cache_key(self.b.username)))

        cache.set(svg_cache_key(self.a.username), "<svg>a2</svg>", timeout=3600)
        cache.set(svg_cache_key(self.b.username), "<svg>b2</svg>", timeout=3600)

        self.client.post(f"/unpick/{self.b.username}/")
        self.assertIsNone(cache.get(svg_cache_key(self.a.username)))
        self.assertIsNone(cache.get(svg_cache_key(self.b.username)))
