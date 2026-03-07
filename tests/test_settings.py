from django.core.cache import cache
from django.test import TestCase


class CacheBackendTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_cache_set_and_get(self):
        cache.set("test_key", "hello", timeout=10)
        self.assertEqual(cache.get("test_key"), "hello")

    def test_cache_add_and_incr(self):
        cache.delete("rate_key")
        self.assertTrue(cache.add("rate_key", 1, timeout=60))
        self.assertEqual(cache.incr("rate_key"), 2)

    def test_session_uses_cache_backend(self):
        session = self.client.session
        session["foo"] = "bar"
        session.save()
        self.assertEqual(self.client.session.get("foo"), "bar")
