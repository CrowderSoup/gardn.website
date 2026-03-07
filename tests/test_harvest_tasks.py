from unittest.mock import MagicMock, patch

from django.test import TestCase

from harvests.models import Harvest
from plants.models import UserIdentity


class HarvestTaskTests(TestCase):
    def setUp(self):
        self.identity = UserIdentity.objects.create(
            me_url="https://example.com/",
            username="testuser",
            display_name="Test User",
        )
        self.harvest = Harvest.objects.create(
            identity=self.identity,
            url="https://example.com/article",
            title="Test Article",
        )
        session = self.client.session
        session["identity_id"] = self.identity.id
        session.save()

    def test_post_to_micropub_success(self):
        from harvests.tasks import post_to_micropub
        mock_response = MagicMock(status_code=201)
        with patch("harvests.tasks.requests.post", return_value=mock_response) as mock_post:
            post_to_micropub(self.harvest.id, "https://micropub.example.com/", "token123")
        self.harvest.refresh_from_db()
        self.assertTrue(self.harvest.micropub_posted)
        mock_post.assert_called_once()

    def test_post_to_micropub_failure(self):
        from harvests.tasks import post_to_micropub
        mock_response = MagicMock(status_code=500)
        with patch("harvests.tasks.requests.post", return_value=mock_response):
            post_to_micropub(self.harvest.id, "https://micropub.example.com/", "token123")
        self.harvest.refresh_from_db()
        self.assertFalse(self.harvest.micropub_posted)

    def test_post_to_mastodon_success(self):
        from harvests.tasks import post_to_mastodon
        self.identity.login_method = "mastodon"
        self.identity.mastodon_access_token = "tok"
        self.identity.mastodon_profile_url = "https://mastodon.social/@user"
        self.identity.save()
        mock_response = MagicMock(status_code=200)
        with patch("harvests.tasks.requests.post", return_value=mock_response):
            post_to_mastodon(self.harvest.id)
        self.harvest.refresh_from_db()
        self.assertTrue(self.harvest.mastodon_posted)

    def test_harvest_view_dispatches_micropub_task(self):
        self.identity.login_method = "indieauth"
        self.identity.save()
        session = self.client.session
        session["micropub_endpoint"] = "https://micropub.example.com/"
        session["access_token"] = "token123"
        session.save()
        with patch("harvests.views.post_to_micropub.delay") as mock_task:
            self.client.post("/harvest/", {
                "url": "https://example.com/new-article",
                "title": "New",
                "post_to_micropub": "true",
            })
        mock_task.assert_called_once()

    def test_harvest_post_view_dispatches_micropub(self):
        session = self.client.session
        session["micropub_endpoint"] = "https://micropub.example.com/"
        session["access_token"] = "token123"
        session.save()
        with patch("harvests.views.post_to_micropub.delay") as mock_task:
            self.client.post(f"/harvest/{self.harvest.id}/post/", {"target": "micropub"})
        mock_task.assert_called_once()

    def test_harvest_post_view_dispatches_mastodon(self):
        self.identity.login_method = "mastodon"
        self.identity.mastodon_access_token = "tok"
        self.identity.mastodon_profile_url = "https://mastodon.social/@user"
        self.identity.save()
        with patch("harvests.views.post_to_mastodon.delay") as mock_task:
            self.client.post(f"/harvest/{self.harvest.id}/post/", {"target": "mastodon"})
        mock_task.assert_called_once()
