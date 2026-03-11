from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from plants.models import UserIdentity
from plants.svg_cache import invalidate_svg

from .models import Harvest
from .tasks import (
    post_to_mastodon,
    post_to_micropub,
    send_harvest_to_mastodon,
    send_harvest_to_micropub,
)


def _current_identity(request: HttpRequest) -> UserIdentity | None:
    identity_id = request.session.get("identity_id")
    if not identity_id:
        return None
    return UserIdentity.objects.filter(id=identity_id).first()


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


@require_http_methods(["GET", "POST"])
def harvest_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        from urllib.parse import urlencode
        query = urlencode({"next": request.get_full_path()})
        return redirect(f"/login/?{query}")

    micropub_endpoint = request.session.get("micropub_endpoint", "")
    can_post_to_mastodon = (
        identity.login_method == "mastodon"
        and bool(identity.mastodon_access_token)
    )

    if request.method == "GET":
        return render(request, "harvests/harvest_form.html", {
            "identity": identity,
            "url": request.GET.get("url", ""),
            "title": request.GET.get("title", ""),
            "micropub_endpoint": micropub_endpoint,
            "can_post_to_mastodon": can_post_to_mastodon,
        })

    # POST
    url = request.POST.get("url", "").strip()
    title = request.POST.get("title", "").strip()
    note = request.POST.get("note", "").strip()
    tags = ", ".join(t.strip() for t in request.POST.get("tags", "").split(",") if t.strip())
    post_to_micropub_flag = request.POST.get("post_to_micropub") == "true"
    post_to_mastodon_flag = request.POST.get("post_to_mastodon") == "true"

    if not url or not _is_valid_url(url):
        return render(request, "harvests/harvest_form.html", {
            "identity": identity,
            "url": url,
            "title": title,
            "note": note,
            "tags": tags,
            "micropub_endpoint": micropub_endpoint,
            "can_post_to_mastodon": can_post_to_mastodon,
            "error": "Please enter a valid http/https URL.",
        }, status=400)

    harvest, created = Harvest.objects.get_or_create(
        identity=identity,
        url=url,
        defaults={"title": title, "note": note, "tags": tags},
    )
    if not created:
        harvest.title = title
        harvest.note = note
        harvest.tags = tags
        harvest.save(update_fields=["title", "note", "tags"])

    if post_to_micropub_flag and micropub_endpoint:
        access_token = request.session.get("access_token", "")
        post_to_micropub.delay(harvest.id, micropub_endpoint, access_token)

    if post_to_mastodon_flag and can_post_to_mastodon:
        post_to_mastodon.delay(harvest.id)

    # Invalidate SVG cache so plant regenerates with new harvest
    invalidate_svg(identity.username)

    is_popup = request.GET.get("popup") == "1"
    if is_popup:
        return render(request, "harvests/harvest_success.html", {"url": url, "title": title})

    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = "/dashboard/"
        return response

    messages.success(request, f"Harvested: {title or url}")
    return redirect("/dashboard/")


@require_POST
def harvest_post_view(request: HttpRequest, harvest_id: int) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        return HttpResponse("Unauthorized", status=401)

    harvest = get_object_or_404(Harvest, id=harvest_id, identity=identity)
    target = request.POST.get("target", "")
    micropub_endpoint = request.session.get("micropub_endpoint", "")
    can_post_to_mastodon = (
        identity.login_method == "mastodon"
        and bool(identity.mastodon_access_token)
    )

    posted = False
    if target == "micropub" and micropub_endpoint:
        access_token = request.session.get("access_token", "")
        posted = send_harvest_to_micropub(harvest.id, micropub_endpoint, access_token)
    elif target == "mastodon" and can_post_to_mastodon:
        posted = send_harvest_to_mastodon(harvest.id)

    if request.headers.get("HX-Request"):
        if not posted:
            return HttpResponse('<span class="subtle harvest-posted harvest-posted-error">could not post</span>')
        if target == "mastodon":
            return HttpResponse('<span class="subtle harvest-posted">posted to mastodon</span>')
        return HttpResponse('<span class="subtle harvest-posted">posted</span>')

    messages.success(request, "Posted successfully.")
    return redirect("/dashboard/")


@require_GET
def bookmarklet_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    return render(request, "harvests/bookmarklet.html", {"identity": identity, "public_base_url": settings.PUBLIC_BASE_URL})


@require_POST
def harvest_delete_view(request: HttpRequest, harvest_id: int) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        return redirect("/login/")

    harvest = get_object_or_404(Harvest, id=harvest_id, identity=identity)
    harvest.delete()

    # Invalidate SVG cache
    invalidate_svg(identity.username)

    if request.headers.get("HX-Request"):
        return HttpResponse(status=200)

    messages.success(request, "Harvest deleted.")
    return redirect("/dashboard/")
