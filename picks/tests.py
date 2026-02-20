from __future__ import annotations

from django.test import TestCase

from plants.models import UserIdentity

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
        self.a.svg_cache = "<svg>a</svg>"
        self.a.save(update_fields=["svg_cache"])
        self.b.svg_cache = "<svg>b</svg>"
        self.b.save(update_fields=["svg_cache"])

        session = self.client.session
        session["identity_id"] = self.a.id
        session.save()

        self.client.post(f"/pick/{self.b.username}/")
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.svg_cache, "")
        self.assertEqual(self.b.svg_cache, "")

        self.a.svg_cache = "<svg>a2</svg>"
        self.a.save(update_fields=["svg_cache"])
        self.b.svg_cache = "<svg>b2</svg>"
        self.b.save(update_fields=["svg_cache"])

        self.client.post(f"/unpick/{self.b.username}/")
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.svg_cache, "")
        self.assertEqual(self.b.svg_cache, "")
