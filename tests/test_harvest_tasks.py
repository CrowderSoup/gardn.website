from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase

from harvests.cache import get_harvest_stats, harvest_stats_cache_key
from harvests.metadata import HarvestMetadata, normalize_harvest_url
from harvests.models import Harvest
from plants.models import UserIdentity


class HarvestTaskTests(TestCase):
    def setUp(self):
        cache.clear()
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
        self.assertIsNone(cache.get(harvest_stats_cache_key(self.identity.id)))

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
        self.assertIsNone(cache.get(harvest_stats_cache_key(self.identity.id)))

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

    def test_create_normalizes_tracking_heavy_urls(self):
        noisy_url = (
            "https://www.lochby.com/products/field-sling"
            "?utm_medium=paid"
            "&utm_id=120237860626400310"
            "&utm_content=120242479939950310"
            "&utm_term=120242470451640310"
            "&utm_campaign=120237860626400310"
            "&utm_source=facebook"
            "&campaign_id=120237860626400310"
            "&ad_id=120242479939950310"
            "&variant=42713130434596"
        )
        normalized_url = normalize_harvest_url(noisy_url)

        with patch(
            "harvests.views.fetch_url_metadata",
            return_value=HarvestMetadata(
                url=normalized_url,
                title="Field Sling",
                note="Waxed canvas everyday sling.",
                tags=["lochby"],
                fetched=True,
            ),
        ):
            response = self.client.post("/harvest/", {"url": noisy_url, "title": ""})

        self.assertRedirects(response, "/dashboard/", fetch_redirect_response=False)
        saved = Harvest.objects.exclude(id=self.harvest.id).get()
        self.assertEqual(saved.url, normalized_url)
        self.assertEqual(
            saved.url,
            "https://www.lochby.com/products/field-sling?variant=42713130434596",
        )
        self.assertEqual(saved.title, "Field Sling")
        self.assertEqual(saved.note, "Waxed canvas everyday sling.")
        self.assertEqual(saved.tags, "lochby")

    def test_create_read_later_checkbox_adds_tag(self):
        response = self.client.post(
            "/harvest/",
            {
                "url": "https://example.com/read-next",
                "title": "Read next",
                "tags": "bags",
                "read_later": "true",
            },
        )

        self.assertRedirects(response, "/dashboard/", fetch_redirect_response=False)
        saved = Harvest.objects.exclude(id=self.harvest.id).get()
        self.assertEqual(saved.tags, "bags, read-later")

    def test_duplicate_save_keeps_existing_metadata_when_new_submit_is_blank(self):
        with patch(
            "harvests.views.fetch_url_metadata",
            return_value=HarvestMetadata(url=self.harvest.url),
        ):
            response = self.client.post(
                "/harvest/",
                {"url": self.harvest.url, "title": "", "note": "", "tags": ""},
            )

        self.assertRedirects(response, "/dashboard/", fetch_redirect_response=False)
        self.harvest.refresh_from_db()
        self.assertEqual(self.harvest.title, "Test Article")
        self.assertEqual(self.harvest.note, "")
        self.assertEqual(self.harvest.tags, "")

    def test_metadata_endpoint_returns_json_payload(self):
        with patch(
            "harvests.views.fetch_url_metadata",
            return_value=HarvestMetadata(
                url="https://example.com/story",
                title="Example Story",
                note="A short summary.",
                tags=["example", "story"],
                fetched=True,
            ),
        ):
            response = self.client.get("/harvest/metadata/?url=https://example.com/story")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "url": "https://example.com/story",
                "title": "Example Story",
                "note": "A short summary.",
                "tags": ["example", "story"],
                "fetched": True,
                "read_later_tag": "read-later",
            },
        )


class HarvestEditViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.identity = UserIdentity.objects.create(
            me_url="https://example.com/",
            username="testuser",
            display_name="Test User",
        )
        self.harvest = Harvest.objects.create(
            identity=self.identity,
            url="https://example.com/article",
            title="Original Title",
            note="Original note",
            tags="python, web",
        )
        session = self.client.session
        session["identity_id"] = self.identity.id
        session.save()

    def test_edit_get_returns_modal_html(self):
        response = self.client.get(f"/harvest/{self.harvest.id}/edit/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Original Title")
        self.assertContains(response, "form")

    def test_edit_get_requires_login(self):
        self.client.session.flush()
        response = self.client.get(f"/harvest/{self.harvest.id}/edit/")
        self.assertRedirects(
            response,
            f"/login/?next=/harvest/{self.harvest.id}/edit/",
            fetch_redirect_response=False,
        )

    def test_edit_get_404_other_user(self):
        other = UserIdentity.objects.create(
            me_url="https://other.com/", username="other"
        )
        session = self.client.session
        session["identity_id"] = other.id
        session.save()
        response = self.client.get(f"/harvest/{self.harvest.id}/edit/")
        self.assertEqual(response.status_code, 404)

    def test_edit_post_updates_harvest(self):
        response = self.client.post(
            f"/harvest/{self.harvest.id}/edit/",
            {
                "title": "Updated Title",
                "note": "Updated note",
                "tags": "python, django",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.harvest.refresh_from_db()
        self.assertEqual(self.harvest.title, "Updated Title")
        self.assertEqual(self.harvest.note, "Updated note")
        self.assertEqual(self.harvest.tags, "python, django")

    def test_edit_post_returns_card_html(self):
        response = self.client.post(
            f"/harvest/{self.harvest.id}/edit/",
            {
                "title": "New Title",
                "note": "",
                "tags": "",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Title")

    def test_edit_post_without_htmx_redirects_to_harvests(self):
        response = self.client.post(f"/harvest/{self.harvest.id}/edit/", {
            "title": "New Title",
            "note": "",
            "tags": "",
            "next": "/harvests/",
        })
        self.assertRedirects(response, "/harvests/", fetch_redirect_response=False)

    def test_edit_post_invalidates_cached_stats(self):
        get_harvest_stats(self.identity.id)
        self.assertIsNotNone(cache.get(harvest_stats_cache_key(self.identity.id)))

        self.client.post(
            f"/harvest/{self.harvest.id}/edit/",
            {"title": "Updated Title", "note": "", "tags": "python, django"},
            HTTP_HX_REQUEST="true",
        )

        self.assertIsNone(cache.get(harvest_stats_cache_key(self.identity.id)))


class HarvestsListViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.identity = UserIdentity.objects.create(
            me_url="https://example.com/",
            username="testuser",
            display_name="Test User",
        )
        Harvest.objects.create(
            identity=self.identity,
            url="https://example.com/one",
            title="Python Tips",
            tags="python, web",
        )
        Harvest.objects.create(
            identity=self.identity,
            url="https://example.com/two",
            title="Django Guide",
            tags="django",
        )
        session = self.client.session
        session["identity_id"] = self.identity.id
        session.save()

    def test_list_requires_login(self):
        self.client.session.flush()
        response = self.client.get("/harvests/")
        self.assertRedirects(response, "/login/?next=/harvests/", fetch_redirect_response=False)

    def test_list_returns_200(self):
        response = self.client.get("/harvests/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Python Tips")
        self.assertContains(response, "Django Guide")

    def test_list_search_filters_by_title(self):
        response = self.client.get("/harvests/?q=Python")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Python Tips")
        self.assertNotContains(response, "Django Guide")

    def test_list_search_filters_by_tag(self):
        response = self.client.get("/harvests/?q=django")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django Guide")
        self.assertNotContains(response, "Python Tips")

    def test_list_htmx_returns_partial(self):
        response = self.client.get(
            "/harvests/?q=Python",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        # Partial should not contain the full page sidebar
        self.assertNotContains(response, "seeds planted")
        self.assertContains(response, "Python Tips")

    def test_list_garden_stats_in_context(self):
        response = self.client.get("/harvests/")
        self.assertIn("total_count", response.context)
        self.assertIn("posted_count", response.context)
        self.assertIn("unposted_count", response.context)
        self.assertIn("unique_tag_count", response.context)
        self.assertIn("health_pct", response.context)

    def test_list_htmx_does_not_compute_sidebar_stats(self):
        with patch("harvests.views.get_harvest_stats") as mock_stats:
            response = self.client.get("/harvests/?q=Python", HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        mock_stats.assert_not_called()

    def test_list_full_page_uses_cached_stats(self):
        get_harvest_stats(self.identity.id)
        with patch("harvests.cache.Harvest.objects.filter") as mock_filter:
            response = self.client.get("/harvests/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(mock_filter.call_count, 1)

    def test_list_shows_updated_stats_after_cache_invalidation(self):
        get_harvest_stats(self.identity.id)
        Harvest.objects.create(
            identity=self.identity,
            url="https://example.com/three",
            title="New Seed",
            tags="newtag",
        )
        cache.delete(harvest_stats_cache_key(self.identity.id))

        response = self.client.get("/harvests/")
        self.assertEqual(response.context["total_count"], 3)
        self.assertEqual(response.context["unique_tag_count"], 4)


class HarvestMutationFallbackTests(TestCase):
    def setUp(self):
        cache.clear()
        self.identity = UserIdentity.objects.create(
            me_url="https://example.com/",
            username="testuser",
            display_name="Test User",
            login_method="mastodon",
            mastodon_access_token="tok",
            mastodon_profile_url="https://mastodon.social/@user",
        )
        self.harvest = Harvest.objects.create(
            identity=self.identity,
            url="https://example.com/article",
            title="Article",
            tags="python, web",
        )
        session = self.client.session
        session["identity_id"] = self.identity.id
        session["micropub_endpoint"] = "https://micropub.example.com/"
        session["access_token"] = "token123"
        session.save()

    def test_post_without_htmx_redirects_to_harvests(self):
        with patch("harvests.views.post_to_micropub.delay"):
            response = self.client.post(
                f"/harvest/{self.harvest.id}/post/",
                {"target": "micropub", "next": "/harvests/"},
            )
        self.assertRedirects(response, "/harvests/", fetch_redirect_response=False)

    def test_delete_without_htmx_redirects_to_harvests(self):
        response = self.client.post(
            f"/harvest/{self.harvest.id}/delete/",
            {"next": "/harvests/"},
        )
        self.assertRedirects(response, "/harvests/", fetch_redirect_response=False)

    def test_delete_requires_login_with_next(self):
        self.client.session.flush()
        response = self.client.post(f"/harvest/{self.harvest.id}/delete/")
        self.assertRedirects(
            response,
            f"/login/?next=/harvest/{self.harvest.id}/delete/",
            fetch_redirect_response=False,
        )

    def test_create_invalidates_cached_stats(self):
        get_harvest_stats(self.identity.id)
        self.assertIsNotNone(cache.get(harvest_stats_cache_key(self.identity.id)))

        self.client.post(
            "/harvest/",
            {"url": "https://example.com/new", "title": "New"},
        )

        self.assertIsNone(cache.get(harvest_stats_cache_key(self.identity.id)))

    def test_delete_invalidates_cached_stats(self):
        get_harvest_stats(self.identity.id)
        self.assertIsNotNone(cache.get(harvest_stats_cache_key(self.identity.id)))

        self.client.post(f"/harvest/{self.harvest.id}/delete/", HTTP_HX_REQUEST="true")

        self.assertIsNone(cache.get(harvest_stats_cache_key(self.identity.id)))
