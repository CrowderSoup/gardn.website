# gardn/test_settings.py
import fakeredis

from gardn.settings import *  # noqa: F401, F403

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://localhost:6379/0",
        "OPTIONS": {
            "connection_class": fakeredis.FakeConnection,
        },
    }
}
