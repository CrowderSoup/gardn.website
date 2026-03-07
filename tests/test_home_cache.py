from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from plants.models import UserIdentity


class HomeCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_home_cache_populated_after_first_request(self):
        self.client.get("/")
        self.assertIsNotNone(cache.get("home:recent"))
        self.assertIsNotNone(cache.get("home:popular"))

    def test_home_cache_used_on_second_request(self):
        self.client.get("/")  # populates cache
        with CaptureQueriesContext(connection) as ctx:
            self.client.get("/")  # should use cache
        query_sqls = [q["sql"] for q in ctx.captured_queries]
        home_queries = [sql for sql in query_sqls if "useridentity" in sql.lower()]
        self.assertEqual(
            len(home_queries), 0,
            f"Expected no useridentity queries on cache hit, got: {home_queries}",
        )

    def test_home_search_reads_from_cache(self):
        identity = UserIdentity.objects.create(
            me_url="https://example.com/",
            username="testuser",
            display_name="Test User",
        )
        cache.set("home:recent", [identity], timeout=60)
        cache.set("home:popular", [], timeout=60)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get("/?q=test")
        self.assertEqual(response.status_code, 200)
        query_sqls = [q["sql"] for q in ctx.captured_queries]
        useridentity_queries = [sql for sql in query_sqls if "useridentity" in sql.lower()]
        # Expect exactly 1: the search query. Cache hit means no extra recent/popular queries.
        self.assertEqual(
            len(useridentity_queries), 1,
            f"Expected only the search query, got {len(useridentity_queries)}: {useridentity_queries}",
        )
        self.assertIn("like", useridentity_queries[0].lower())
