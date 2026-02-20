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
