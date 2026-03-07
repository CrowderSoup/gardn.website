# Redis + S3 Infrastructure Improvements

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Redis-backed caching/sessions and S3-compatible object storage to improve performance, scalability, and resilience.

**Architecture:** Django's built-in Redis cache backend replaces LocMemCache for sessions, SVG caching, rate limiting, and query caching. Celery (also backed by Redis) moves synchronous external HTTP calls (Micropub, Mastodon) off the request path. `django-storages` routes static files, generated SVGs, data exports, and profile photos to S3.

**Tech Stack:** Django 5.1, `celery[redis]`, `django-storages[s3]`, `boto3`, `fakeredis` (test), `moto[s3]` (test), `pytest-mock` (test)

---

## Background: what exists today

- `picks/rate_limit.py` already calls `django.core.cache.cache.add/incr` — it silently degrades today because no real cache backend is configured (uses LocMemCache, which resets per-process). Redis fixes this automatically.
- `plants/models.py:12` — `svg_cache = models.TextField(blank=True)` stores full SVG XML in the DB row.
- SVG invalidation is scattered: `plants/views.py:131`, `harvests/views.py:139,240`, `picks/views.py:53,73` all write `svg_cache=""` or call `.update(svg_cache="")`.
- `gardn/__init__.py` is empty — safe to write Celery app setup there.
- No test directory or conftest.py exists yet. `pytest-django` is already in `[dependency-groups] dev`.

---

## Task 1: Test infrastructure + new dependencies

**Files:**
- Modify: `pyproject.toml`
- Create: `conftest.py`
- Create: `tests/__init__.py`

**Step 1: Add packages to pyproject.toml**

```toml
# In [project] dependencies:
"celery[redis]>=5.4.0",
"django-storages[s3]>=1.14.0",

# In [dependency-groups] dev:
"fakeredis>=2.26.0",
"moto[s3]>=5.0.0",
"pytest-mock>=3.14.0",
```

**Step 2: Install**

```bash
uv sync
```

Expected: packages download without errors.

**Step 3: Create conftest.py**

```python
# conftest.py
from __future__ import annotations

import pytest
from django.test import Client

from plants.models import UserIdentity


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def identity(db):
    return UserIdentity.objects.create(
        me_url="https://example.com/",
        username="testuser",
        display_name="Test User",
    )


@pytest.fixture
def authed_client(client, identity):
    session = client.session
    session["identity_id"] = identity.id
    session.save()
    return client, identity
```

**Step 4: Create tests/__init__.py**

Empty file — just `touch tests/__init__.py`.

**Step 5: Verify test setup works**

```bash
uv run pytest --co -q
```

Expected: "no tests ran" (0 collected), no import errors.

**Step 6: Commit**

```bash
git add pyproject.toml uv.lock conftest.py tests/__init__.py
git commit -m "chore: add Redis/S3/Celery deps and test infrastructure"
```

---

## Task 2: Redis cache backend + session backend

This also fixes rate limiting in `picks/rate_limit.py` as a free side-effect — it currently works per-process only (LocMemCache resets on restart).

**Files:**
- Modify: `gardn/settings.py`
- Create: `tests/test_settings.py`

**Step 1: Write the failing test**

```python
# tests/test_settings.py
import pytest
from django.core.cache import cache


@pytest.mark.django_db
def test_cache_set_and_get():
    cache.set("test_key", "hello", timeout=10)
    assert cache.get("test_key") == "hello"


@pytest.mark.django_db
def test_cache_add_and_incr():
    cache.delete("rate_key")
    assert cache.add("rate_key", 1, timeout=60) is True
    assert cache.incr("rate_key") == 2


@pytest.mark.django_db
def test_session_uses_cache_backend(client):
    # Sessions should persist without DB sessions table being used
    session = client.session
    session["foo"] = "bar"
    session.save()
    assert client.session.get("foo") == "bar"
```

**Step 2: Run to verify tests fail (or note current behavior)**

```bash
uv run pytest tests/test_settings.py -v
```

Expected: tests pass with LocMemCache but note that `cache.add` / `cache.incr` behavior is in-process only. These will still pass — the goal is confirming the infrastructure works post-switch.

**Step 3: Update settings.py**

Add after the `DATABASE_URL` block:

```python
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
```

**Step 4: Override cache in test settings**

Add to `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "gardn.settings"
python_files = ["tests.py", "test_*.py", "*_tests.py"]
```

Create `gardn/test_settings.py`:

```python
# gardn/test_settings.py
from gardn.settings import *  # noqa: F401, F403

import fakeredis

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://localhost:6379/0",
        "OPTIONS": {
            "connection_class": fakeredis.FakeConnection,
        },
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
```

Update `pyproject.toml`:

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "gardn.test_settings"
python_files = ["tests.py", "test_*.py", "*_tests.py"]
```

**Step 5: Run tests**

```bash
uv run pytest tests/test_settings.py -v
```

Expected: all 3 tests PASS.

**Step 6: Commit**

```bash
git add gardn/settings.py gardn/test_settings.py pyproject.toml tests/test_settings.py
git commit -m "feat: configure Redis cache backend and session backend"
```

---

## Task 3: Redis SVG cache (remove from database)

Replace the `svg_cache` TextField on `UserIdentity` with a Redis cache key. All reads/writes use `cache.get/set/delete("svg:{username}")`. This shrinks DB rows significantly and makes invalidation explicit.

**Files:**
- Create: `plants/migrations/0006_remove_useridentity_svg_cache.py`
- Modify: `plants/models.py`
- Modify: `plants/views.py`
- Modify: `harvests/views.py`
- Modify: `picks/views.py`
- Create: `tests/test_svg_cache.py`

**Step 1: Write failing tests**

```python
# tests/test_svg_cache.py
import pytest
from django.core.cache import cache
from django.urls import reverse

from plants.models import UserIdentity


def svg_cache_key(username: str) -> str:
    return f"svg:{username}"


@pytest.mark.django_db
def test_svg_view_populates_cache(authed_client, mocker):
    client, identity = authed_client
    mocker.patch("plants.views.generate_svg", return_value="<svg>test</svg>")
    cache.delete(svg_cache_key(identity.username))

    response = client.get(f"/u/{identity.username}/plant.svg")

    assert response.status_code == 200
    assert cache.get(svg_cache_key(identity.username)) is not None


@pytest.mark.django_db
def test_svg_view_uses_cache(authed_client, mocker):
    client, identity = authed_client
    mock_generate = mocker.patch("plants.views.generate_svg", return_value="<svg>cached</svg>")
    cache.set(svg_cache_key(identity.username), "<svg>from-cache</svg>", timeout=3600)

    response = client.get(f"/u/{identity.username}/plant.svg")

    assert response.status_code == 200
    mock_generate.assert_not_called()
    assert b"from-cache" in response.content


@pytest.mark.django_db
def test_harvest_delete_invalidates_svg_cache(authed_client, mocker):
    from harvests.models import Harvest
    client, identity = authed_client
    harvest = Harvest.objects.create(identity=identity, url="https://example.com/article")
    cache.set(svg_cache_key(identity.username), "<svg>stale</svg>", timeout=3600)

    client.post(f"/harvest/{harvest.id}/delete/")

    assert cache.get(svg_cache_key(identity.username)) is None


@pytest.mark.django_db
def test_svg_cache_not_stored_in_db(authed_client, mocker):
    client, identity = authed_client
    mocker.patch("plants.views.generate_svg", return_value="<svg>test</svg>")
    cache.delete(svg_cache_key(identity.username))

    client.get(f"/u/{identity.username}/plant.svg")

    identity.refresh_from_db()
    assert not hasattr(identity, "svg_cache") or True  # field removed
```

**Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_svg_cache.py -v
```

Expected: FAIL — svg_cache field still in use.

**Step 3: Remove svg_cache from model**

In `plants/models.py`, delete line 12:
```python
svg_cache = models.TextField(blank=True)  # DELETE THIS LINE
```

**Step 4: Create migration**

```bash
uv run manage.py makemigrations plants --name remove_useridentity_svg_cache
```

Expected: creates `plants/migrations/0006_remove_useridentity_svg_cache.py`.

**Step 5: Apply migration**

```bash
uv run manage.py migrate
```

**Step 6: Add cache helper to plants/views.py**

At the top of `plants/views.py`, add:

```python
from django.core.cache import cache

SVG_CACHE_TIMEOUT = 3600  # 1 hour


def _svg_cache_key(username: str) -> str:
    return f"svg:{username}"
```

**Step 7: Update plant_svg_view in plants/views.py**

Replace lines 181–209 with:

```python
@require_GET
def plant_svg_view(request: HttpRequest, username: str) -> HttpResponse:
    from harvests.models import Harvest

    identity = get_object_or_404(UserIdentity, username=username)
    cache_key = _svg_cache_key(identity.username)
    svg = cache.get(cache_key)

    if svg is None:
        harvest_urls = list(Harvest.objects.filter(identity=identity).values_list("url", flat=True))
        pick_count = Pick.objects.filter(Q(picker=identity) | Q(picked=identity)).count()
        svg = generate_svg(
            identity.me_url,
            harvest_urls=harvest_urls,
            motion_enabled=identity.animate_plant_motion,
            pick_count=pick_count,
        )
        cache.set(cache_key, svg, timeout=SVG_CACHE_TIMEOUT)

    etag = hashlib.sha256(svg.encode("utf-8")).hexdigest()
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponseNotModified()
        response["ETag"] = etag
        return response

    response = HttpResponse(svg, content_type="image/svg+xml")
    response["Cache-Control"] = "public, max-age=3600"
    response["ETag"] = etag
    return response
```

**Step 8: Update profile_settings_view invalidation in plants/views.py**

Replace line 131 (`identity.svg_cache = ""`):

```python
    if invalidate_svg:
        cache.delete(_svg_cache_key(identity.username))
        identity.save(update_fields=["show_harvests_on_profile", "animate_plant_motion", "updated_at"])
    else:
        identity.save(update_fields=["show_harvests_on_profile", "animate_plant_motion", "updated_at"])
```

**Step 9: Update SVG invalidation in harvests/views.py**

Replace both occurrences of `UserIdentity.objects.filter(pk=identity.pk).update(svg_cache="")` (lines 139, 240):

```python
from django.core.cache import cache
from plants.views import _svg_cache_key

# line 139 becomes:
cache.delete(_svg_cache_key(identity.username))

# line 240 becomes:
cache.delete(_svg_cache_key(identity.username))
```

**Step 10: Update SVG invalidation in picks/views.py**

Replace both occurrences of `UserIdentity.objects.filter(id__in=[viewer.id, picked.id]).update(svg_cache="")` (lines 53, 73):

```python
from django.core.cache import cache
from plants.views import _svg_cache_key

# Both lines become:
cache.delete(_svg_cache_key(viewer.username))
cache.delete(_svg_cache_key(picked.username))
```

Note: `viewer` and `picked` are already fetched as `UserIdentity` objects in this view, so `.username` is available.

**Step 11: Run tests**

```bash
uv run pytest tests/test_svg_cache.py -v
```

Expected: all 4 tests PASS.

**Step 12: Run full suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

**Step 13: Commit**

```bash
git add plants/models.py plants/views.py plants/migrations/0006_remove_useridentity_svg_cache.py harvests/views.py picks/views.py tests/test_svg_cache.py
git commit -m "feat: move SVG cache from DB to Redis, remove svg_cache column"
```

---

## Task 4: Home page query caching

`home_view` runs two expensive queries on every load — recent users and popular users (with annotation + ordering). These are identical for all visitors and safe to cache for 60 seconds.

**Files:**
- Modify: `plants/views.py`
- Create: `tests/test_home_cache.py`

**Step 1: Write failing tests**

```python
# tests/test_home_cache.py
import pytest
from django.core.cache import cache
from django.urls import reverse


@pytest.mark.django_db
def test_home_page_caches_recent_and_popular(client, mocker):
    cache.clear()
    spy_recent = mocker.spy(type(None), "__init__")  # placeholder; we'll track DB queries

    # Hit the page twice
    r1 = client.get("/")
    r2 = client.get("/")

    assert r1.status_code == 200
    assert r2.status_code == 200
    # Both render without error — cache keys populated on first hit
    assert cache.get("home:recent") is not None
    assert cache.get("home:popular") is not None


@pytest.mark.django_db
def test_home_cache_populated_after_first_request(client, identity):
    cache.clear()
    client.get("/")
    assert cache.get("home:recent") is not None


@pytest.mark.django_db
def test_home_search_bypasses_cache(client):
    cache.clear()
    r = client.get("/?q=test")
    assert r.status_code == 200
    # search results are never cached
    assert cache.get("home:recent") is None  # cache not populated during search request
```

**Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_home_cache.py -v
```

Expected: `test_home_cache_populated_after_first_request` FAILS — cache key not set.

**Step 3: Update home_view in plants/views.py**

Replace the `home_view` body:

```python
HOME_CACHE_TIMEOUT = 60  # seconds


@require_GET
def home_view(request: HttpRequest) -> HttpResponse:
    q = request.GET.get("q", "").strip()
    if q:
        results = UserIdentity.objects.filter(
            Q(username__icontains=q) | Q(display_name__icontains=q)
        ).order_by("username")[:24]
        recent = UserIdentity.objects.order_by("-created_at")[:12]
        popular = (
            UserIdentity.objects.annotate(pick_count=Count("incoming_picks"))
            .order_by("-pick_count")
            .filter(pick_count__gt=0)[:12]
        )
    else:
        results = None
        recent = cache.get("home:recent")
        if recent is None:
            recent = list(UserIdentity.objects.order_by("-created_at")[:12])
            cache.set("home:recent", recent, timeout=HOME_CACHE_TIMEOUT)
        popular = cache.get("home:popular")
        if popular is None:
            popular = list(
                UserIdentity.objects.annotate(pick_count=Count("incoming_picks"))
                .order_by("-pick_count")
                .filter(pick_count__gt=0)[:12]
            )
            cache.set("home:popular", popular, timeout=HOME_CACHE_TIMEOUT)

    return render(request, "plants/home.html", {
        "recent_identities": recent,
        "identity": _current_identity(request),
        "search_results": results,
        "q": q,
        "popular_identities": popular,
    })
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_home_cache.py -v
```

Expected: all 3 tests PASS.

**Step 5: Run full suite**

```bash
uv run pytest -v
```

**Step 6: Commit**

```bash
git add plants/views.py tests/test_home_cache.py
git commit -m "feat: cache home page recent and popular queries in Redis"
```

---

## Task 5: Celery app setup

Celery uses Redis as its message broker and result backend. This task is pure infrastructure — no tasks yet.

**Files:**
- Create: `gardn/celery.py`
- Modify: `gardn/__init__.py`
- Modify: `gardn/settings.py`

**Step 1: Add Celery settings to gardn/settings.py**

Add after the `REDIS_URL` line:

```python
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
```

Also add to `gardn/test_settings.py`:

```python
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
```

`CELERY_TASK_ALWAYS_EAGER=True` makes tasks run synchronously in tests — no worker needed.

**Step 2: Create gardn/celery.py**

```python
# gardn/celery.py
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gardn.settings")

app = Celery("gardn")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

**Step 3: Update gardn/__init__.py**

```python
# gardn/__init__.py
from .celery import app as celery_app

__all__ = ["celery_app"]
```

**Step 4: Verify Celery can inspect**

```bash
uv run celery -A gardn inspect ping --timeout 2
```

Expected: timeout or "no nodes" (no worker running) — no errors means the app loaded correctly.

**Step 5: Run full test suite**

```bash
uv run pytest -v
```

Expected: all existing tests PASS.

**Step 6: Commit**

```bash
git add gardn/celery.py gardn/__init__.py gardn/settings.py gardn/test_settings.py
git commit -m "feat: add Celery app with Redis broker"
```

---

## Task 6: Async Micropub and Mastodon posting

Move the blocking `requests.post()` calls for Micropub and Mastodon out of the request/response cycle into Celery tasks. The view returns immediately; if the task fails, the failure is recorded on the `Harvest` model.

**Files:**
- Create: `harvests/tasks.py`
- Modify: `harvests/views.py`
- Create: `tests/test_harvest_tasks.py`

**Step 1: Write failing tests**

```python
# tests/test_harvest_tasks.py
import pytest
from unittest.mock import patch, MagicMock

from harvests.models import Harvest
from plants.models import UserIdentity


@pytest.fixture
def harvest(db, identity):
    return Harvest.objects.create(
        identity=identity,
        url="https://example.com/article",
        title="Test Article",
    )


@pytest.mark.django_db
def test_post_to_micropub_success(harvest):
    from harvests.tasks import post_to_micropub

    mock_response = MagicMock(status_code=201)
    with patch("harvests.tasks.requests.post", return_value=mock_response) as mock_post:
        post_to_micropub(harvest.id, "https://micropub.example.com/", "token123")

    harvest.refresh_from_db()
    assert harvest.micropub_posted is True
    mock_post.assert_called_once()


@pytest.mark.django_db
def test_post_to_micropub_failure(harvest):
    from harvests.tasks import post_to_micropub

    mock_response = MagicMock(status_code=500)
    with patch("harvests.tasks.requests.post", return_value=mock_response):
        post_to_micropub(harvest.id, "https://micropub.example.com/", "token123")

    harvest.refresh_from_db()
    assert harvest.micropub_posted is False


@pytest.mark.django_db
def test_post_to_mastodon_success(harvest):
    from harvests.tasks import post_to_mastodon

    identity = harvest.identity
    identity.login_method = "mastodon"
    identity.mastodon_access_token = "tok"
    identity.mastodon_profile_url = "https://mastodon.social/@user"
    identity.save()

    mock_response = MagicMock(status_code=200)
    with patch("harvests.tasks.requests.post", return_value=mock_response):
        post_to_mastodon(harvest.id)

    harvest.refresh_from_db()
    assert harvest.mastodon_posted is True


@pytest.mark.django_db
def test_harvest_view_dispatches_tasks(authed_client, mocker):
    client, identity = authed_client
    identity.login_method = "indieauth"
    identity.save()

    session = client.session
    session["micropub_endpoint"] = "https://micropub.example.com/"
    session["access_token"] = "token123"
    session.save()

    mock_task = mocker.patch("harvests.views.post_to_micropub.delay")

    client.post("/harvest/", {
        "url": "https://example.com/new-article",
        "title": "New",
        "post_to_micropub": "true",
    })

    mock_task.assert_called_once()
```

**Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_harvest_tasks.py -v
```

Expected: ImportError — `harvests.tasks` doesn't exist.

**Step 3: Create harvests/tasks.py**

```python
# harvests/tasks.py
from __future__ import annotations

from urllib.parse import urlparse

import requests
from celery import shared_task


@shared_task
def post_to_micropub(harvest_id: int, micropub_endpoint: str, access_token: str) -> None:
    from harvests.models import Harvest

    try:
        harvest = Harvest.objects.get(id=harvest_id)
    except Harvest.DoesNotExist:
        return

    try:
        resp = requests.post(
            micropub_endpoint,
            data={"h": "entry", "bookmark-of": harvest.url, "name": harvest.title},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.status_code in (200, 201, 202):
            harvest.micropub_posted = True
            harvest.save(update_fields=["micropub_posted"])
    except Exception:
        pass


@shared_task
def post_to_mastodon(harvest_id: int) -> None:
    from harvests.models import Harvest

    try:
        harvest = Harvest.objects.get(id=harvest_id)
    except Harvest.DoesNotExist:
        return

    identity = harvest.identity
    parsed = urlparse(identity.mastodon_profile_url)
    instance_url = f"{parsed.scheme}://{parsed.netloc}"

    parts = []
    if harvest.title:
        parts.append(f'"{harvest.title}"')
    parts.append(harvest.url)
    if harvest.note:
        parts.append(f"\n{harvest.note}")
    tags = harvest.tags_list()
    if tags:
        parts.append("\n" + " ".join(f"#{t}" for t in tags))
    status_text = "\n".join(parts)

    try:
        resp = requests.post(
            f"{instance_url}/api/v1/statuses",
            json={"status": status_text, "visibility": "public"},
            headers={"Authorization": f"Bearer {identity.mastodon_access_token}"},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            harvest.mastodon_posted = True
            harvest.save(update_fields=["mastodon_posted"])
    except Exception:
        pass
```

**Step 4: Update harvests/views.py harvest_view to dispatch tasks**

Replace the synchronous Micropub block (lines 100–115) and Mastodon block (lines 117–136) in `harvest_view`:

```python
from harvests.tasks import post_to_micropub, post_to_mastodon

# Replace the micropub block:
    if post_to_micropub_flag and micropub_endpoint:
        access_token = request.session.get("access_token", "")
        post_to_micropub.delay(harvest.id, micropub_endpoint, access_token)

# Replace the mastodon block:
    if post_to_mastodon_flag and can_post_to_mastodon:
        post_to_mastodon.delay(harvest.id)
```

Also remove the `micropub_warning` and `mastodon_warning` variables and their `messages.warning()` calls from this view — failures are now silent at the task level. Remove the `if micropub_warning:` and `if mastodon_warning:` blocks.

Rename `post_to_micropub` and `post_to_mastodon` boolean variables to `post_to_micropub_flag` and `post_to_mastodon_flag` to avoid name collision with the imported tasks.

**Step 5: Update harvest_post_view similarly**

The `harvest_post_view` (line 160) handles re-posting existing harvests. Apply the same pattern:

```python
# Replace the micropub block in harvest_post_view:
    if target == "micropub" and micropub_endpoint:
        access_token = request.session.get("access_token", "")
        post_to_micropub.delay(harvest.id, micropub_endpoint, access_token)
        posted = True

# Replace the mastodon block:
    elif target == "mastodon" and can_post_to_mastodon:
        post_to_mastodon.delay(harvest.id)
        posted = True
```

Remove the `warning` variable and adjust the HTMX/redirect responses to assume success (the task is queued).

**Step 6: Run tests**

```bash
uv run pytest tests/test_harvest_tasks.py -v
```

Expected: all 4 tests PASS (tasks run eagerly in tests due to `CELERY_TASK_ALWAYS_EAGER=True`).

**Step 7: Run full suite**

```bash
uv run pytest -v
```

**Step 8: Commit**

```bash
git add harvests/tasks.py harvests/views.py tests/test_harvest_tasks.py
git commit -m "feat: move Micropub/Mastodon posting to async Celery tasks"
```

> **Deployment note:** A Celery worker process must be started alongside gunicorn:
> ```bash
> celery -A gardn worker --loglevel=info
> ```

---

## Task 7: S3 static files

Replace WhiteNoise static file serving with S3 + optional CDN. WhiteNoise stays active as a fallback when `AWS_STORAGE_BUCKET_NAME` is not set (dev/CI).

**Files:**
- Modify: `gardn/settings.py`
- Create: `tests/test_static_storage.py`

**Step 1: Write test**

```python
# tests/test_static_storage.py
import pytest
from django.conf import settings


def test_static_storage_uses_s3_when_configured(settings):
    settings.AWS_STORAGE_BUCKET_NAME = "my-bucket"
    settings.AWS_S3_ENDPOINT_URL = "https://s3.example.com"

    # Re-import to check backend selection logic
    from gardn.settings import _get_staticfiles_backend
    assert _get_staticfiles_backend() == "storages.backends.s3boto3.S3StaticStorage"


def test_static_storage_falls_back_to_whitenoise(settings):
    settings.AWS_STORAGE_BUCKET_NAME = ""

    from gardn.settings import _get_staticfiles_backend
    assert _get_staticfiles_backend() == "whitenoise.storage.CompressedManifestStaticFilesStorage"
```

**Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_static_storage.py -v
```

Expected: AttributeError — `_get_staticfiles_backend` doesn't exist.

**Step 3: Update gardn/settings.py**

Replace the static files block (lines 107–110) with:

```python
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "")
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL", "")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN", "")
AWS_DEFAULT_ACL = "public-read"
AWS_S3_FILE_OVERWRITE = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]


def _get_staticfiles_backend() -> str:
    if AWS_STORAGE_BUCKET_NAME:
        return "storages.backends.s3boto3.S3StaticStorage"
    return "whitenoise.storage.CompressedManifestStaticFilesStorage"


STORAGES = {
    "staticfiles": {"BACKEND": _get_staticfiles_backend()},
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}
```

Also remove the now-redundant line:
```python
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_static_storage.py -v
```

Expected: PASS.

**Step 5: Run full suite**

```bash
uv run pytest -v
```

**Step 6: Commit**

```bash
git add gardn/settings.py tests/test_static_storage.py
git commit -m "feat: route static files to S3 when AWS_STORAGE_BUCKET_NAME is set"
```

> **Deployment:** Run `uv run manage.py collectstatic` to upload statics to S3.

---

## Task 8: SVGs to S3 (serve via redirect)

After generating an SVG, upload it to S3 as `svgs/{username}.svg`. Store the public S3 URL in Redis. `plant_svg_view` does a 302 redirect to the S3 URL instead of serving the SVG itself, offloading all SVG delivery to S3/CDN.

Invalidation: delete the S3 object and the Redis cache key. The next request regenerates and re-uploads.

**Files:**
- Create: `plants/s3_svg.py`
- Modify: `plants/views.py`
- Create: `tests/test_s3_svg.py`

**Step 1: Write failing tests**

```python
# tests/test_s3_svg.py
import pytest
from unittest.mock import patch, MagicMock
from django.core.cache import cache


@pytest.mark.django_db
def test_svg_view_redirects_to_s3_when_configured(authed_client, settings, mocker):
    client, identity = authed_client
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
    cache.delete(f"svg:{identity.username}")

    mocker.patch("plants.views.generate_svg", return_value="<svg>test</svg>")
    mocker.patch("plants.s3_svg.upload_svg_to_s3", return_value="https://s3.example.com/svgs/testuser.svg")

    response = client.get(f"/u/{identity.username}/plant.svg")

    assert response.status_code == 302
    assert "s3.example.com" in response["Location"]


@pytest.mark.django_db
def test_svg_view_serves_directly_without_s3(authed_client, settings, mocker):
    client, identity = authed_client
    settings.AWS_STORAGE_BUCKET_NAME = ""
    cache.delete(f"svg:{identity.username}")

    mocker.patch("plants.views.generate_svg", return_value="<svg>test</svg>")

    response = client.get(f"/u/{identity.username}/plant.svg")

    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"


@pytest.mark.django_db
def test_s3_upload_svg(settings):
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
    settings.AWS_S3_ENDPOINT_URL = "https://s3.example.com"

    from plants.s3_svg import upload_svg_to_s3

    mock_client = MagicMock()
    mock_client.put_object.return_value = {}
    with patch("plants.s3_svg.boto3.client", return_value=mock_client):
        url = upload_svg_to_s3("testuser", "<svg>hello</svg>")

    mock_client.put_object.assert_called_once()
    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs["Key"] == "svgs/testuser.svg"
    assert call_kwargs["ContentType"] == "image/svg+xml"
    assert "testuser" in url
```

**Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_s3_svg.py -v
```

Expected: ImportError — `plants.s3_svg` doesn't exist.

**Step 3: Create plants/s3_svg.py**

```python
# plants/s3_svg.py
from __future__ import annotations

import boto3
from django.conf import settings


def upload_svg_to_s3(username: str, svg_content: str) -> str:
    """Upload SVG to S3 and return the public URL."""
    client = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )
    key = f"svgs/{username}.svg"
    client.put_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
        Body=svg_content.encode("utf-8"),
        ContentType="image/svg+xml",
        CacheControl="public, max-age=3600",
        ACL="public-read",
    )
    if settings.AWS_S3_CUSTOM_DOMAIN:
        return f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{key}"
    if settings.AWS_S3_ENDPOINT_URL:
        base = settings.AWS_S3_ENDPOINT_URL.rstrip("/")
        return f"{base}/{settings.AWS_STORAGE_BUCKET_NAME}/{key}"
    return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{key}"


def delete_svg_from_s3(username: str) -> None:
    """Delete SVG from S3 (called on cache invalidation)."""
    if not settings.AWS_STORAGE_BUCKET_NAME:
        return
    client = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )
    client.delete_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=f"svgs/{username}.svg",
    )
```

**Step 4: Update plant_svg_view in plants/views.py**

```python
from django.conf import settings
from django.http import HttpResponseRedirect

@require_GET
def plant_svg_view(request: HttpRequest, username: str) -> HttpResponse:
    from harvests.models import Harvest

    identity = get_object_or_404(UserIdentity, username=username)
    cache_key = _svg_cache_key(identity.username)

    if settings.AWS_STORAGE_BUCKET_NAME:
        s3_url = cache.get(cache_key)
        if s3_url is None:
            harvest_urls = list(Harvest.objects.filter(identity=identity).values_list("url", flat=True))
            pick_count = Pick.objects.filter(Q(picker=identity) | Q(picked=identity)).count()
            svg = generate_svg(
                identity.me_url,
                harvest_urls=harvest_urls,
                motion_enabled=identity.animate_plant_motion,
                pick_count=pick_count,
            )
            from plants.s3_svg import upload_svg_to_s3
            s3_url = upload_svg_to_s3(identity.username, svg)
            cache.set(cache_key, s3_url, timeout=SVG_CACHE_TIMEOUT)
        return HttpResponseRedirect(s3_url)

    # No S3: serve directly from Redis cache
    svg = cache.get(cache_key)
    if svg is None:
        harvest_urls = list(Harvest.objects.filter(identity=identity).values_list("url", flat=True))
        pick_count = Pick.objects.filter(Q(picker=identity) | Q(picked=identity)).count()
        svg = generate_svg(
            identity.me_url,
            harvest_urls=harvest_urls,
            motion_enabled=identity.animate_plant_motion,
            pick_count=pick_count,
        )
        cache.set(cache_key, svg, timeout=SVG_CACHE_TIMEOUT)

    etag = hashlib.sha256(svg.encode("utf-8")).hexdigest()
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponseNotModified()
        response["ETag"] = etag
        return response

    response = HttpResponse(svg, content_type="image/svg+xml")
    response["Cache-Control"] = "public, max-age=3600"
    response["ETag"] = etag
    return response
```

**Step 5: Update _invalidate_svg helper**

Create a shared helper to consolidate invalidation logic — currently scattered across 3 files. Add to `plants/views.py`:

```python
def _invalidate_svg(username: str) -> None:
    cache.delete(_svg_cache_key(username))
    if settings.AWS_STORAGE_BUCKET_NAME:
        from plants.s3_svg import delete_svg_from_s3
        delete_svg_from_s3(username)
```

Update all invalidation call sites in `plants/views.py`, `harvests/views.py`, `picks/views.py` to call `_invalidate_svg(username)` instead of `cache.delete(...)`.

**Step 6: Run tests**

```bash
uv run pytest tests/test_s3_svg.py tests/test_svg_cache.py -v
```

Expected: all tests PASS.

**Step 7: Run full suite**

```bash
uv run pytest -v
```

**Step 8: Commit**

```bash
git add plants/s3_svg.py plants/views.py harvests/views.py picks/views.py tests/test_s3_svg.py
git commit -m "feat: upload SVGs to S3 and serve via redirect when S3 is configured"
```

---

## Task 9: Async data export to S3

`export_data_view` currently streams JSON synchronously. Move it to a Celery task that generates the export, uploads it to S3, and returns a presigned URL (valid 1 hour). Without S3, fall back to the current streaming behavior.

**Files:**
- Create: `plants/tasks.py`
- Modify: `plants/views.py`
- Create: `tests/test_export.py`

**Step 1: Write failing tests**

```python
# tests/test_export.py
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.django_db
def test_export_streams_json_without_s3(authed_client, settings):
    settings.AWS_STORAGE_BUCKET_NAME = ""
    client, identity = authed_client

    response = client.get("/settings/export/")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert b'"username"' in response.content


@pytest.mark.django_db
def test_export_returns_presigned_url_with_s3(authed_client, settings, mocker):
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
    client, identity = authed_client

    mock_url = "https://s3.example.com/exports/testuser.json?signature=abc"
    mocker.patch("plants.tasks.generate_and_upload_export.delay")
    mocker.patch("plants.views.generate_and_upload_export.delay", return_value=None)

    # The view should redirect or return a "preparing" page
    response = client.get("/settings/export/")

    # With S3, the view should either redirect to the presigned URL or show a waiting page
    assert response.status_code in (200, 302)


@pytest.mark.django_db
def test_generate_and_upload_export_task(identity, settings):
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
    settings.AWS_S3_ENDPOINT_URL = "https://s3.example.com"

    from plants.tasks import generate_and_upload_export

    mock_client = MagicMock()
    mock_client.put_object.return_value = {}
    mock_client.generate_presigned_url.return_value = "https://s3.example.com/presigned"

    with patch("plants.tasks.boto3.client", return_value=mock_client):
        url = generate_and_upload_export(identity.id)

    assert url == "https://s3.example.com/presigned"
    mock_client.put_object.assert_called_once()
```

**Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_export.py -v
```

Expected: ImportError — `plants.tasks` doesn't exist.

**Step 3: Create plants/tasks.py**

```python
# plants/tasks.py
from __future__ import annotations

import json
from datetime import datetime

import boto3
from celery import shared_task
from django.conf import settings


@shared_task
def generate_and_upload_export(identity_id: int) -> str:
    """Generate JSON export, upload to S3, return presigned URL."""
    from plants.models import UserIdentity
    from harvests.models import Harvest
    from picks.models import Pick

    identity = UserIdentity.objects.get(id=identity_id)
    harvests = list(Harvest.objects.filter(identity=identity).values(
        "url", "title", "note", "tags", "harvested_at"
    ))
    picks = list(Pick.objects.filter(picker=identity).select_related("picked").values(
        "picked__username", "picked__me_url", "created_at"
    ))
    data = {
        "username": identity.username,
        "me_url": identity.me_url,
        "display_name": identity.display_name,
        "harvests": harvests,
        "picks": picks,
    }
    json_bytes = json.dumps(data, indent=2, default=str).encode("utf-8")

    client = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )
    key = f"exports/{identity.username}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json"
    client.put_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
        Body=json_bytes,
        ContentType="application/json",
        ContentDisposition=f'attachment; filename="gardn-export-{identity.username}.json"',
    )
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": key},
        ExpiresIn=3600,
    )
```

**Step 4: Update export_data_view in plants/views.py**

```python
@require_GET
def export_data_view(request: HttpRequest) -> HttpResponse:
    from django.conf import settings as django_settings

    identity = _current_identity(request)
    if not identity:
        return HttpResponse("Unauthorized", status=401)

    if django_settings.AWS_STORAGE_BUCKET_NAME:
        from plants.tasks import generate_and_upload_export
        presigned_url = generate_and_upload_export.delay(identity.id).get(timeout=30)
        return redirect(presigned_url)

    # Fallback: stream directly
    from harvests.models import Harvest
    harvests = list(Harvest.objects.filter(identity=identity).values(
        "url", "title", "note", "tags", "harvested_at"
    ))
    picks = list(Pick.objects.filter(picker=identity).select_related("picked").values(
        "picked__username", "picked__me_url", "created_at"
    ))
    data = {
        "username": identity.username,
        "me_url": identity.me_url,
        "display_name": identity.display_name,
        "harvests": harvests,
        "picks": picks,
    }
    response = JsonResponse(data, json_dumps_params={"indent": 2, "default": str})
    response["Content-Disposition"] = f'attachment; filename="gardn-export-{identity.username}.json"'
    return response
```

**Step 5: Run tests**

```bash
uv run pytest tests/test_export.py -v
```

Expected: all tests PASS.

**Step 6: Run full suite**

```bash
uv run pytest -v
```

**Step 7: Commit**

```bash
git add plants/tasks.py plants/views.py tests/test_export.py
git commit -m "feat: async export to S3 with presigned download URL"
```

---

## Task 10: Profile photo mirroring to S3

`UserIdentity.photo_url` stores an external URL (from Mastodon or IndieAuth). If that external host goes down, profile images break site-wide. On login, fetch the photo and store it in S3. Replace `photo_url` with the S3 URL in the session/identity.

The fetch happens in both `indieauth_client/views.py` (IndieAuth login) and `mastodon_auth/views.py` (Mastodon login).

**Files:**
- Create: `plants/photo_mirror.py`
- Modify: `indieauth_client/views.py`
- Modify: `mastodon_auth/views.py`
- Create: `tests/test_photo_mirror.py`

**Step 1: Read the login views to understand where photo_url is set**

```bash
# Read both login views to find where photo_url is assigned
grep -n "photo_url" indieauth_client/views.py mastodon_auth/views.py
```

**Step 2: Write failing tests**

```python
# tests/test_photo_mirror.py
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.django_db
def test_mirror_photo_uploads_to_s3(identity, settings):
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
    settings.AWS_S3_ENDPOINT_URL = "https://s3.example.com"

    from plants.photo_mirror import mirror_photo_to_s3

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"PNG_BYTES"
    mock_response.headers = {"Content-Type": "image/png"}

    mock_s3 = MagicMock()
    mock_s3.put_object.return_value = {}

    with patch("plants.photo_mirror.requests.get", return_value=mock_response):
        with patch("plants.photo_mirror.boto3.client", return_value=mock_s3):
            url = mirror_photo_to_s3(identity.username, "https://external.example.com/photo.png")

    assert "testuser" in url
    mock_s3.put_object.assert_called_once()


@pytest.mark.django_db
def test_mirror_photo_returns_original_on_failure(identity, settings):
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"

    from plants.photo_mirror import mirror_photo_to_s3

    with patch("plants.photo_mirror.requests.get", side_effect=Exception("network error")):
        url = mirror_photo_to_s3(identity.username, "https://external.example.com/photo.png")

    assert url == "https://external.example.com/photo.png"


@pytest.mark.django_db
def test_mirror_photo_skips_when_no_s3(identity, settings):
    settings.AWS_STORAGE_BUCKET_NAME = ""

    from plants.photo_mirror import mirror_photo_to_s3

    url = mirror_photo_to_s3(identity.username, "https://external.example.com/photo.png")

    assert url == "https://external.example.com/photo.png"
```

**Step 3: Run to confirm failure**

```bash
uv run pytest tests/test_photo_mirror.py -v
```

Expected: ImportError — `plants.photo_mirror` doesn't exist.

**Step 4: Create plants/photo_mirror.py**

```python
# plants/photo_mirror.py
from __future__ import annotations

import boto3
import requests
from django.conf import settings


def mirror_photo_to_s3(username: str, original_url: str) -> str:
    """
    Fetch a photo from original_url and upload to S3.
    Returns the S3 URL on success, original_url on any failure.
    Falls through immediately if S3 is not configured.
    """
    if not settings.AWS_STORAGE_BUCKET_NAME or not original_url:
        return original_url

    try:
        resp = requests.get(original_url, timeout=10)
        if resp.status_code != 200:
            return original_url

        content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        ext_map = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
            "image/webp": "webp",
            "image/avif": "avif",
        }
        ext = ext_map.get(content_type, "jpg")
        key = f"photos/{username}.{ext}"

        client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL or None,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
        client.put_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key,
            Body=resp.content,
            ContentType=content_type,
            ACL="public-read",
        )

        if settings.AWS_S3_CUSTOM_DOMAIN:
            return f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{key}"
        if settings.AWS_S3_ENDPOINT_URL:
            base = settings.AWS_S3_ENDPOINT_URL.rstrip("/")
            return f"{base}/{settings.AWS_STORAGE_BUCKET_NAME}/{key}"
        return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{key}"

    except Exception:
        return original_url
```

**Step 5: Find where photo_url is set in login views**

```bash
grep -n "photo_url" indieauth_client/views.py mastodon_auth/views.py
```

**Step 6: Add mirror_photo_to_s3 call at each login photo_url assignment**

In each login view, find the line that sets `identity.photo_url = <external_url>` and wrap it:

```python
from plants.photo_mirror import mirror_photo_to_s3

# Replace:
identity.photo_url = fetched_photo_url
# With:
identity.photo_url = mirror_photo_to_s3(identity.username, fetched_photo_url)
```

The exact lines will be visible from the grep output in Step 5. Apply to both `indieauth_client/views.py` and `mastodon_auth/views.py`.

**Step 7: Run tests**

```bash
uv run pytest tests/test_photo_mirror.py -v
```

Expected: all 3 tests PASS.

**Step 8: Run full suite**

```bash
uv run pytest -v
```

**Step 9: Commit**

```bash
git add plants/photo_mirror.py indieauth_client/views.py mastodon_auth/views.py tests/test_photo_mirror.py
git commit -m "feat: mirror profile photos to S3 on login"
```

---

## Deployment checklist

New environment variables required:

| Variable | Purpose | Example |
|---|---|---|
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery broker (defaults to REDIS_URL) | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery results (defaults to REDIS_URL) | `redis://localhost:6379/0` |
| `AWS_STORAGE_BUCKET_NAME` | S3 bucket name | `gardn-assets` |
| `AWS_S3_ENDPOINT_URL` | S3-compatible endpoint (leave blank for AWS) | `https://s3.us-east-1.amazonaws.com` |
| `AWS_ACCESS_KEY_ID` | S3 credentials | |
| `AWS_SECRET_ACCESS_KEY` | S3 credentials | |
| `AWS_S3_CUSTOM_DOMAIN` | CDN domain (optional) | `cdn.gardn.dev` |

New processes to run:

```bash
# Celery worker (alongside gunicorn)
celery -A gardn worker --loglevel=info

# First deploy: upload static files to S3
uv run manage.py collectstatic --noinput
```
