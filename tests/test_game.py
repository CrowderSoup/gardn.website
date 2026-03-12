from __future__ import annotations

import json
from unittest.mock import Mock, patch

from django.test import TestCase

from game.models import GameProfile, GardenPlot, NeighborLink, Quest, SiteScan, VerifiedActivity
from harvests.models import Harvest
from plants.models import UserIdentity


def mock_response(*, text: str = "", headers: dict | None = None, json_data: dict | None = None) -> Mock:
    response = Mock()
    response.ok = True
    response.status_code = 200
    response.reason = "OK"
    response.text = text
    response.headers = headers or {}
    response.json.return_value = json_data or {}
    response.raise_for_status.return_value = None
    return response


class GameStateAPITests(TestCase):
    def setUp(self):
        self.identity = UserIdentity.objects.create(
            me_url="https://example.com/",
            username="gardener",
            display_name="Test Gardener",
            login_method="indieauth",
        )
        self.profile = GameProfile.objects.create(
            identity=self.identity,
            display_name="Gardener",
            map_id="garden",
            tile_x=5,
            tile_y=7,
            tutorial_step=5,
            has_website=True,
        )
        self.scan = SiteScan.objects.create(
            identity=self.identity,
            status=SiteScan.STATUS_VERIFIED,
            scanned_url=self.identity.me_url,
            capabilities={
                "website_verified": True,
                "micropub_endpoint": "https://example.com/micropub",
                "has_h_feed": True,
                "has_h_entry": True,
            },
        )
        self.activity = VerifiedActivity.objects.create(
            identity=self.identity,
            kind=VerifiedActivity.KIND_PUBLISHED_ENTRY,
            status=VerifiedActivity.STATUS_VERIFIED,
            canonical_url="https://example.com/posts/hello",
            source_url="https://example.com/posts/hello",
            title="Hello garden",
        )
        session = self.client.session
        session["identity_id"] = self.identity.id
        session["micropub_endpoint"] = "https://example.com/micropub"
        session["access_token"] = "secret-token"
        session.save()

    def test_game_state_response_shape(self):
        response = self.client.get("/game/api/state/")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertIn("player", data)
        self.assertIn("site_status", data)
        self.assertIn("capabilities", data)
        self.assertIn("verified_inventory", data)
        self.assertIn("pending_inventory", data)
        self.assertIn("neighbors", data)
        self.assertIn("quests", data)

        self.assertEqual(data["player"]["map_id"], "garden")
        self.assertEqual(data["capabilities"]["micropub_endpoint"], "https://example.com/micropub")
        self.assertEqual(len(data["verified_inventory"]), 1)

    def test_game_index_authenticated(self):
        response = self.client.get("/game/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "game-container")
        self.assertContains(response, "publishNoteUrl")

    def test_game_index_unauthenticated(self):
        self.client.session.flush()
        response = self.client.get("/game/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Login to play")

    def test_site_status_endpoint_returns_scan(self):
        response = self.client.get("/game/api/site-status/")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], SiteScan.STATUS_VERIFIED)
        self.assertTrue(payload["capabilities"]["website_verified"])

    def test_unplanted_inventory_returns_verified_and_pending(self):
        VerifiedActivity.objects.create(
            identity=self.identity,
            kind=VerifiedActivity.KIND_PUBLISHED_BOOKMARK,
            status=VerifiedActivity.STATUS_PENDING,
            canonical_url="https://target.example.com/post",
            title="Pending bookmark",
        )

        response = self.client.get("/game/api/harvests/")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(len(payload["verified_inventory"]), 1)
        self.assertEqual(len(payload["pending_inventory"]), 1)

    def test_plant_seed_requires_verified_activity_id(self):
        response = self.client.post(
            "/game/api/plant/",
            data=json.dumps({"slot_x": 1, "slot_y": 2}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_plant_seed_creates_plot_from_verified_activity(self):
        response = self.client.post(
            "/game/api/plant/",
            data=json.dumps({"slot_x": 2, "slot_y": 3, "verified_activity_id": self.activity.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        plot = GardenPlot.objects.get(profile=self.profile, slot_x=2, slot_y=3)
        self.assertEqual(plot.verified_activity, self.activity)
        self.assertEqual(plot.link_url, self.activity.canonical_url)

    @patch("game.views._garden_plot_title_max_length", return_value=256)
    def test_plant_seed_truncates_titles_to_database_column_length(self, _max_length_mock):
        max_title_length = 256
        self.activity.title = "A" * 300
        self.activity.save(update_fields=["title"])

        response = self.client.post(
            "/game/api/plant/",
            data=json.dumps({"slot_x": 4, "slot_y": 1, "verified_activity_id": self.activity.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        plot = GardenPlot.objects.get(profile=self.profile, slot_x=4, slot_y=1)
        self.assertEqual(len(plot.link_title), max_title_length)
        self.assertEqual(plot.link_title, self.activity.title[:max_title_length])

    def test_harvest_endpoint_no_longer_increments_fake_counts(self):
        response = self.client.post(
            "/game/api/harvest/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        payload = json.loads(response.content)
        self.assertIn("verified site activity", payload["error"])

    def test_publish_bookmark_creates_pending_activity_and_harvest(self):
        with patch("game.evidence.requests.post") as post_mock:
            post_mock.return_value = mock_response(headers={"Location": "https://example.com/posts/bookmark-1"})
            response = self.client.post(
                "/game/api/publish/bookmark/",
                data=json.dumps({"target_url": "https://target.example.com/article", "title": "Target"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        activity = VerifiedActivity.objects.get(kind=VerifiedActivity.KIND_PUBLISHED_BOOKMARK)
        self.assertEqual(activity.status, VerifiedActivity.STATUS_PENDING)
        self.assertEqual(activity.canonical_url, "https://target.example.com/article")
        self.assertTrue(Harvest.objects.filter(identity=self.identity, url="https://target.example.com/article").exists())

    def test_publish_note_creates_pending_activity(self):
        with patch("game.evidence.requests.post") as post_mock:
            post_mock.return_value = mock_response(headers={"Location": "https://example.com/posts/note-1"})
            response = self.client.post(
                "/game/api/publish/note/",
                data=json.dumps({"title": "A note", "content": "Hello from the garden"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        activity = VerifiedActivity.objects.get(
            kind=VerifiedActivity.KIND_PUBLISHED_ENTRY,
            status=VerifiedActivity.STATUS_PENDING,
            source_url="https://example.com/posts/note-1",
        )
        self.assertEqual(activity.status, VerifiedActivity.STATUS_PENDING)
        self.assertEqual(activity.source_url, "https://example.com/posts/note-1")

    def test_complete_quest_requires_claimable_progress(self):
        response = self.client.post(
            "/game/api/quest/complete/",
            data=json.dumps({"quest_slug": "ten-links-deep"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_complete_quest_succeeds_when_requirements_met(self):
        for index in range(9):
            VerifiedActivity.objects.create(
                identity=self.identity,
                kind=VerifiedActivity.KIND_PUBLISHED_BOOKMARK,
                status=VerifiedActivity.STATUS_VERIFIED,
                canonical_url=f"https://target.example.com/{index}",
                title=f"Link {index}",
            )

        response = self.client.post(
            "/game/api/quest/complete/",
            data=json.dumps({"quest_slug": "ten-links-deep"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    @patch("game.evidence.requests.get")
    def test_scan_endpoint_creates_verified_entry_and_neighbor(self, get_mock):
        neighbor = UserIdentity.objects.create(
            me_url="https://friend.example/",
            username="friend",
            display_name="Friend",
            login_method="indieauth",
        )
        del neighbor

        home_html = """
        <html>
          <head>
            <link rel="micropub" href="/micropub" />
          </head>
          <body class="h-feed">
            <article class="h-entry">
              <a class="u-url" href="https://example.com/posts/hello">Permalink</a>
              <h1 class="p-name">Hello world</h1>
            </article>
            <a href="/blogroll/">Blogroll</a>
          </body>
        </html>
        """
        blogroll_html = """
        <html>
          <body>
            <a href="https://friend.example/">Friend</a>
          </body>
        </html>
        """
        get_mock.side_effect = [
            mock_response(text=home_html),
            mock_response(text=blogroll_html),
        ]

        response = self.client.post(
            "/game/api/scan/",
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.status, SiteScan.STATUS_VERIFIED)
        self.assertTrue(
            VerifiedActivity.objects.filter(
                identity=self.identity,
                kind=VerifiedActivity.KIND_PUBLISHED_ENTRY,
                canonical_url="https://example.com/posts/hello",
            ).exists()
        )
        self.assertTrue(
            NeighborLink.objects.filter(identity=self.identity, target_url="https://friend.example/").exists()
        )


class GameProfileAutoCreateTests(TestCase):
    def setUp(self):
        self.identity = UserIdentity.objects.create(
            me_url="https://new-user.example.com/",
            username="newuser",
            login_method="indieauth",
        )
        session = self.client.session
        session["identity_id"] = self.identity.id
        session.save()

    def test_game_profile_created_on_first_visit(self):
        self.assertFalse(GameProfile.objects.filter(identity=self.identity).exists())
        self.client.get("/game/")
        self.assertTrue(GameProfile.objects.filter(identity=self.identity).exists())

    def test_indieauth_user_has_website_set(self):
        self.client.get("/game/")
        profile = GameProfile.objects.get(identity=self.identity)
        self.assertTrue(profile.has_website)
        self.assertTrue(SiteScan.objects.filter(identity=self.identity).exists())


class QuestSeedTests(TestCase):
    def test_initial_quests_exist(self):
        slugs = [
            "ten-links-deep",
            "plant-your-flag",
            "good-neighbor",
            "write-something",
            "webring-rider",
            "deep-roots",
        ]
        for slug in slugs:
            self.assertTrue(
                Quest.objects.filter(slug=slug).exists(),
                f"Quest '{slug}' not found — check migration 0002",
            )
