from __future__ import annotations

import json
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from game.models import (
    GardenDecoration,
    GardenVisit,
    GameProfile,
    GardenPlot,
    GroveMessage,
    GrovePresence,
    NeighborLink,
    Quest,
    QuestProgress,
    SiteScan,
    VerifiedActivity,
)
from game.tasks import verify_published_activity
from harvests.models import Harvest
from picks.models import Pick
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
            verified_at=timezone.now(),
        )
        session = self.client.session
        session["identity_id"] = self.identity.id
        session["micropub_endpoint"] = "https://example.com/micropub"
        session["access_token"] = "secret-token"
        session.save()

    def _create_host_neighbor(self, *, gate_state: str = GameProfile.GATE_OPEN):
        host = UserIdentity.objects.create(
            me_url="https://friend.example/",
            username="friend",
            display_name="Friend",
            login_method="indieauth",
        )
        host_profile = GameProfile.objects.create(
            identity=host,
            map_id="garden",
            has_website=True,
            gate_state=gate_state,
        )
        SiteScan.objects.create(
            identity=host,
            status=SiteScan.STATUS_VERIFIED,
            scanned_url=host.me_url,
            capabilities={"website_verified": True},
        )
        NeighborLink.objects.create(
            identity=self.identity,
            target_identity=host,
            target_url=host.me_url,
            relationship=NeighborLink.RELATIONSHIP_BLOGROLL,
        )
        return host, host_profile

    def _add_verified_activities(self, count: int):
        for index in range(count):
            VerifiedActivity.objects.create(
                identity=self.identity,
                kind=VerifiedActivity.KIND_PUBLISHED_BOOKMARK,
                status=VerifiedActivity.STATUS_VERIFIED,
                canonical_url=f"https://target.example.com/{index}",
                title=f"Link {index}",
                verified_at=timezone.now(),
            )

    def _complete_quests(self, count: int):
        quests = list(Quest.objects.order_by("order", "title")[:count])
        for quest in quests:
            QuestProgress.objects.create(
                profile=self.profile,
                quest=quest,
                status="complete",
                completed_at=timezone.now(),
            )

    def test_game_state_response_shape(self):
        response = self.client.get("/game/api/state/")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertIn("player", data)
        self.assertIn("owner", data)
        self.assertIn("site_status", data)
        self.assertIn("garden_health", data)
        self.assertIn("capabilities", data)
        self.assertIn("verified_inventory", data)
        self.assertIn("pending_inventory", data)
        self.assertIn("neighbors", data)
        self.assertIn("quests", data)
        self.assertIn("appearance", data)
        self.assertIn("homestead", data)
        self.assertIn("library_summary", data)
        self.assertIn("padd_badges", data)
        self.assertIn("grove", data)
        self.assertIn("gate_state", data)

        self.assertEqual(data["player"]["map_id"], "garden")
        self.assertEqual(data["owner"]["username"], "gardener")
        self.assertEqual(data["capabilities"]["micropub_endpoint"], "https://example.com/micropub")
        self.assertEqual(data["garden_health"]["label"], "steady")
        self.assertEqual(len(data["verified_inventory"]), 1)
        self.assertEqual(data["appearance"]["body_style"], GameProfile.BODY_STYLE_ANDROGYNOUS)
        self.assertEqual(data["homestead"]["gate_state"], GameProfile.GATE_OPEN)
        self.assertEqual(data["library_summary"]["read_later_tag"], "read-later")

    def test_game_index_authenticated(self):
        response = self.client.get("/game/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "game-container")
        self.assertContains(response, "publishNoteUrl")
        self.assertContains(response, f"/game/gardens/{self.identity.username}/")

    def test_game_index_unauthenticated(self):
        self.client.session.flush()
        response = self.client.get("/game/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Login to play")

    def test_playwright_login_route_sets_session_and_profile(self):
        self.client.session.flush()

        response = self.client.get("/game/playwright-login/?username=smoke-check&map=neighbors")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/game/")

        identity = UserIdentity.objects.get(username="smoke-check")
        profile = GameProfile.objects.get(identity=identity)
        session = self.client.session

        self.assertEqual(session["identity_id"], identity.id)
        self.assertTrue(session["website_verified"])
        self.assertEqual(profile.map_id, "neighbors")
        self.assertTrue(profile.appearance_configured)
        self.assertTrue(profile.has_website)

    def test_site_status_endpoint_returns_scan(self):
        response = self.client.get("/game/api/site-status/")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], SiteScan.STATUS_VERIFIED)
        self.assertTrue(payload["capabilities"]["website_verified"])

    def test_shared_garden_index_includes_guest_launch_config(self):
        host = UserIdentity.objects.create(
            me_url="https://friend.example/",
            username="friend",
            display_name="Friend",
            login_method="indieauth",
        )

        response = self.client.get(f"/game/gardens/{host.username}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'launchMapId: "guest_garden"')
        self.assertContains(response, 'launchGuestUsername: "friend"')

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

    def test_update_profile_persists_appearance_and_read_later_tag(self):
        response = self.client.post(
            "/game/api/profile/",
            data=json.dumps(
                {
                    "body_style": GameProfile.BODY_STYLE_FEMININE,
                    "skin_tone": "amber",
                    "outfit_key": "starter",
                    "read_later_tag": "queue",
                    "appearance_configured": True,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        payload = json.loads(response.content)
        self.assertTrue(self.profile.appearance_configured)
        self.assertEqual(self.profile.body_style, GameProfile.BODY_STYLE_FEMININE)
        self.assertEqual(self.profile.skin_tone, "amber")
        self.assertEqual(self.profile.read_later_tag, "queue")
        self.assertEqual(payload["appearance"]["skin_tone"], "amber")
        self.assertEqual(payload["library_summary"]["read_later_tag"], "queue")

    def test_update_homestead_updates_name_and_gate(self):
        response = self.client.post(
            "/game/api/homestead/",
            data=json.dumps({"garden_name": "Signal Glen", "gate_state": GameProfile.GATE_CLOSED}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.garden_name, "Signal Glen")
        self.assertEqual(self.profile.gate_state, GameProfile.GATE_CLOSED)

    def test_update_homestead_rejects_locked_path_style(self):
        response = self.client.post(
            "/game/api/homestead/",
            data=json.dumps({"path_style": "clover"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)

    def test_update_garden_decoration_requires_unlocked_slot(self):
        response = self.client.post(
            "/game/api/homestead/decor/",
            data=json.dumps({"slot_key": "signpost", "decor_key": "signpost"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)

    def test_update_garden_decoration_succeeds_when_unlocked(self):
        self._add_verified_activities(4)
        self._complete_quests(2)

        response = self.client.post(
            "/game/api/homestead/decor/",
            data=json.dumps({"slot_key": "signpost", "decor_key": "signpost"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            GardenDecoration.objects.filter(profile=self.profile, slot_key="signpost", decor_key="signpost").exists()
        )

    def test_library_endpoint_filters_read_later(self):
        Harvest.objects.create(identity=self.identity, url="https://a.example/", title="Keep", tags="read-later, indie")
        Harvest.objects.create(identity=self.identity, url="https://b.example/", title="Skip", tags="done")

        response = self.client.get("/game/api/library/?view=read_later")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["total_count"], 1)
        self.assertEqual(payload["items"][0]["title"], "Keep")

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
        with patch("game.evidence.requests.post") as post_mock, patch("game.views.verify_published_activity.delay") as delay_mock:
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
        delay_mock.assert_called_once_with(activity.id)

    def test_publish_note_creates_pending_activity(self):
        with patch("game.evidence.requests.post") as post_mock, patch("game.views.verify_published_activity.delay") as delay_mock:
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
        delay_mock.assert_called_once_with(activity.id)

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

    def test_guest_garden_endpoint_requires_verified_neighbor(self):
        host = UserIdentity.objects.create(
            me_url="https://friend.example/",
            username="friend",
            display_name="Friend",
            login_method="indieauth",
        )

        response = self.client.get(f"/game/api/gardens/{host.username}/")

        self.assertEqual(response.status_code, 403)
        self.assertIn("rescan your site", json.loads(response.content)["error"])

    def test_guest_garden_endpoint_returns_host_garden(self):
        host, host_profile = self._create_host_neighbor()
        host_activity = VerifiedActivity.objects.create(
            identity=host,
            kind=VerifiedActivity.KIND_PUBLISHED_ENTRY,
            status=VerifiedActivity.STATUS_VERIFIED,
            canonical_url="https://friend.example/posts/hi",
            source_url="https://friend.example/posts/hi",
            title="Friend post",
            verified_at=timezone.now(),
        )
        GardenPlot.objects.create(
            profile=host_profile,
            slot_x=1,
            slot_y=1,
            verified_activity=host_activity,
            link_url=host_activity.canonical_url,
            link_title=host_activity.title,
            plant_type="flower",
            growth_stage=2,
        )
        response = self.client.get(f"/game/api/gardens/{host.username}/")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["owner"]["username"], "friend")
        self.assertEqual(payload["garden_health"]["recent_verified_count"], 1)
        self.assertEqual(len(payload["garden"]), 1)
        self.assertTrue(payload["visit"]["allowed"])
        self.assertEqual(payload["gate_state"], GameProfile.GATE_OPEN)
        self.assertIn("homestead", payload)

    def test_guest_garden_endpoint_rejects_closed_gate(self):
        host, _host_profile = self._create_host_neighbor(gate_state=GameProfile.GATE_CLOSED)

        response = self.client.get(f"/game/api/gardens/{host.username}/")

        self.assertEqual(response.status_code, 403)
        self.assertIn("closed", json.loads(response.content)["error"])

    def test_record_garden_visit_counts_once_per_day(self):
        host, _host_profile = self._create_host_neighbor()

        first = self.client.post(
            f"/game/api/gardens/{host.username}/visit/",
            data=json.dumps({}),
            content_type="application/json",
        )
        second = self.client.post(
            f"/game/api/gardens/{host.username}/visit/",
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(json.loads(first.content)["recorded"])
        self.assertFalse(json.loads(second.content)["recorded"])
        self.assertEqual(GardenVisit.objects.filter(host=host, visitor=self.identity).count(), 1)
        self.assertEqual(json.loads(second.content)["garden_state"]["garden_health"]["recent_visitor_count"], 1)

    def test_grove_presence_and_chat_endpoints(self):
        heartbeat = self.client.post(
            "/game/api/grove/presence/heartbeat/",
            data=json.dumps({"current_map": "neighbors"}),
            content_type="application/json",
        )
        post = self.client.post(
            "/game/api/grove/messages/post/",
            data=json.dumps({"current_map": "neighbors", "content": "Hello grove"}),
            content_type="application/json",
        )
        listing = self.client.get("/game/api/grove/presence/")
        messages = self.client.get("/game/api/grove/messages/")

        self.assertEqual(heartbeat.status_code, 200)
        self.assertEqual(post.status_code, 200)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(messages.status_code, 200)
        self.assertTrue(GrovePresence.objects.filter(identity=self.identity, current_map="neighbors").exists())
        self.assertTrue(GroveMessage.objects.filter(identity=self.identity, content="Hello grove").exists())
        self.assertEqual(len(json.loads(messages.content)["messages"]), 1)

    def test_grove_message_rate_limit(self):
        GrovePresence.objects.create(identity=self.identity, current_map="neighbors")
        first = self.client.post(
            "/game/api/grove/messages/post/",
            data=json.dumps({"current_map": "neighbors", "content": "First"}),
            content_type="application/json",
        )
        second = self.client.post(
            "/game/api/grove/messages/post/",
            data=json.dumps({"current_map": "neighbors", "content": "Second"}),
            content_type="application/json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    @patch("game.evidence.requests.get")
    def test_scan_manual_page_counts_gardn_roll_widget_as_blogroll(self, get_mock):
        neighbor = UserIdentity.objects.create(
            me_url="https://friend.example/",
            username="friend",
            display_name="Friend",
            login_method="indieauth",
        )
        Pick.objects.create(picker=self.identity, picked=neighbor)

        home_html = """
        <html>
          <body class="h-feed">
            <article class="h-entry">
              <a class="u-url" href="https://example.com/posts/hello">Permalink</a>
              <h1 class="p-name">Hello world</h1>
            </article>
          </body>
        </html>
        """
        gardn_html = """
        <html>
          <body>
            <div data-gardn-roll="gardener"></div>
            <div data-gardn-harvests="gardener"></div>
            <div data-gardn="gardener"></div>
          </body>
        </html>
        """
        get_mock.side_effect = [
            mock_response(text=home_html),
            mock_response(text=gardn_html),
        ]

        response = self.client.post(
            "/game/api/scan/",
            data=json.dumps({"page_url": "https://example.com/page/gardn/"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.status, SiteScan.STATUS_VERIFIED)
        self.assertTrue(self.scan.capabilities["roll_embed"])

        neighbor_link = NeighborLink.objects.get(
            identity=self.identity,
            target_url="https://friend.example/",
            relationship=NeighborLink.RELATIONSHIP_GARDN_ROLL,
        )
        self.assertEqual(neighbor_link.source_url, "https://example.com/page/gardn/")

    @patch("game.evidence.requests.get")
    def test_home_scan_rechecks_saved_manual_neighbor_pages(self, get_mock):
        neighbor = UserIdentity.objects.create(
            me_url="https://friend.example/",
            username="friend",
            display_name="Friend",
            login_method="indieauth",
        )
        Pick.objects.create(picker=self.identity, picked=neighbor)

        home_html = """
        <html>
          <body class="h-feed">
            <article class="h-entry">
              <a class="u-url" href="https://example.com/posts/hello">Permalink</a>
              <h1 class="p-name">Hello world</h1>
            </article>
          </body>
        </html>
        """
        gardn_html = """
        <html>
          <body>
            <div data-gardn-roll="gardener"></div>
          </body>
        </html>
        """

        def fake_get(url, *args, **kwargs):
            if url == "https://example.com/":
                return mock_response(text=home_html)
            if url == "https://example.com/page/gardn/":
                return mock_response(text=gardn_html)
            if url.endswith("/api/gardener/roll.json"):
                return mock_response(json_data={"roll": []})
            raise AssertionError(f"Unexpected URL requested during scan: {url}")

        get_mock.side_effect = fake_get

        first_response = self.client.post(
            "/game/api/scan/",
            data=json.dumps({"page_url": "https://example.com/page/gardn/"}),
            content_type="application/json",
        )
        self.assertEqual(first_response.status_code, 200)
        self.assertTrue(
            NeighborLink.objects.filter(
                identity=self.identity,
                target_url="https://friend.example/",
                relationship=NeighborLink.RELATIONSHIP_GARDN_ROLL,
            ).exists()
        )

        second_response = self.client.post(
            "/game/api/scan/",
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(second_response.status_code, 200)
        neighbor_link = NeighborLink.objects.get(
            identity=self.identity,
            target_url="https://friend.example/",
            relationship=NeighborLink.RELATIONSHIP_GARDN_ROLL,
        )
        self.assertEqual(neighbor_link.source_url, "https://example.com/page/gardn/")

        payload = json.loads(second_response.content)
        self.assertEqual(len(payload["state"]["neighbors"]), 1)
        self.assertTrue(payload["state"]["neighbors"][0]["visitable"])

    @patch("game.evidence.requests.get")
    def test_scan_manual_permalink_verifies_pending_bookmark(self, get_mock):
        pending = VerifiedActivity.objects.create(
            identity=self.identity,
            kind=VerifiedActivity.KIND_PUBLISHED_BOOKMARK,
            status=VerifiedActivity.STATUS_PENDING,
            canonical_url="https://opengameart.org/",
            source_url="https://example.com/blog/post/opengameartorg-1773380574/",
            title="OpenGameArt.org",
        )

        home_html = """
        <html>
          <body class="h-feed">
            <article class="h-entry">
              <a class="u-url" href="https://example.com/posts/hello">Permalink</a>
              <h1 class="p-name">Hello world</h1>
            </article>
          </body>
        </html>
        """
        manual_html = """
        <html>
          <body>
            <article class="h-entry">
              <a class="u-uid" href="/blog/post/opengameartorg-1773380574/" hidden></a>
              <span class="p-name" hidden>OpenGameArt.org</span>
              <a class="u-bookmark-of" href="https://opengameart.org/" hidden></a>
            </article>
          </body>
        </html>
        """
        get_mock.side_effect = [
            mock_response(text=home_html),
            mock_response(text=manual_html),
        ]

        response = self.client.post(
            "/game/api/scan/",
            data=json.dumps({"page_url": "https://example.com/blog/post/opengameartorg-1773380574/"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        pending.refresh_from_db()
        self.assertEqual(pending.status, VerifiedActivity.STATUS_VERIFIED)
        self.assertEqual(pending.source_url, "https://example.com/blog/post/opengameartorg-1773380574/")
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.status, SiteScan.STATUS_VERIFIED)

    @patch("game.evidence.requests.get")
    def test_verify_published_activity_task_promotes_pending_note(self, get_mock):
        pending = VerifiedActivity.objects.create(
            identity=self.identity,
            kind=VerifiedActivity.KIND_PUBLISHED_ENTRY,
            status=VerifiedActivity.STATUS_PENDING,
            canonical_url="https://example.com/posts/note-1",
            source_url="https://example.com/posts/note-1",
            title="Hello from the garden",
            metadata={"created_via": "micropub"},
        )

        home_html = """
        <html>
          <body class="h-feed">
            <article class="h-entry">
              <a class="u-url" href="https://example.com/posts/hello">Permalink</a>
              <h1 class="p-name">Hello world</h1>
            </article>
          </body>
        </html>
        """
        manual_html = """
        <html>
          <body>
            <article class="h-entry">
              <a class="u-url" href="https://example.com/posts/note-1">Permalink</a>
              <p class="e-content">Hello from the garden</p>
            </article>
          </body>
        </html>
        """
        get_mock.side_effect = [
            mock_response(text=home_html),
            mock_response(text=manual_html),
        ]

        verify_published_activity.delay(pending.id)

        pending.refresh_from_db()
        self.assertEqual(pending.status, VerifiedActivity.STATUS_VERIFIED)
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.status, SiteScan.STATUS_VERIFIED)


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
