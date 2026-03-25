from __future__ import annotations

from urllib.parse import urlparse, urlencode

from django.conf import settings
from django.core.paginator import Paginator
from django.core.exceptions import ObjectDoesNotExist
from django.db import DataError
from django.db.models import Q
from django.utils import timezone
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from plants.models import UserIdentity
from plants.svg_cache import invalidate_svg

from .cache import get_harvest_stats, invalidate_harvest_stats
from .metadata import (
    fetch_url_metadata,
    guess_title_from_url,
    merge_tags,
    normalize_harvest_url,
    split_tag_string,
    tag_string,
)
from .models import Harvest
from .tasks import post_to_micropub, post_to_mastodon


def _current_identity(request: HttpRequest) -> UserIdentity | None:
    identity_id = request.session.get("identity_id")
    if not identity_id:
        return None
    return UserIdentity.objects.filter(id=identity_id).first()


def _ripeness_class(harvest: Harvest) -> str:
    age = timezone.now() - harvest.harvested_at
    is_posted = harvest.micropub_posted or harvest.mastodon_posted
    if age.days < 7:
        return "harvest--fresh"
    elif age.days < 30:
        return "harvest--ripe"
    elif not is_posted:
        return "harvest--overdue"
    return "harvest--ripe"


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _harvests_redirect_target(request: HttpRequest) -> str:
    next_url = request.POST.get("next", "").strip() or request.GET.get("next", "").strip()
    if next_url.startswith("/"):
        return next_url
    return "/harvests/"


def _read_later_tag(identity: UserIdentity) -> str:
    try:
        profile = identity.game_profile
    except ObjectDoesNotExist:
        return "read-later"
    return profile.read_later_tag or "read-later"


@require_GET
def harvests_list_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        query = urlencode({"next": request.get_full_path()})
        return redirect(f"/login/?{query}")

    q = request.GET.get("q", "").strip()
    harvests_qs = Harvest.objects.filter(identity=identity)

    if q:
        harvests_qs = harvests_qs.filter(
            Q(title__icontains=q)
            | Q(url__icontains=q)
            | Q(note__icontains=q)
            | Q(tags__icontains=q)
        )

    paginator = Paginator(harvests_qs, 24)
    page_number = request.GET.get("page", 1)
    harvest_page = paginator.get_page(page_number)

    # Annotate ripeness
    annotated = [(h, _ripeness_class(h)) for h in harvest_page]

    micropub_endpoint = request.session.get("micropub_endpoint", "")
    can_post_to_mastodon = (
        identity.login_method == "mastodon"
        and bool(identity.mastodon_access_token)
    )

    q_param = f"&{urlencode({'q': q})}" if q else ""

    context = {
        "identity": identity,
        "harvest_page": harvest_page,
        "annotated": annotated,
        "q": q,
        "q_param": q_param,
        "micropub_endpoint": micropub_endpoint,
        "can_post_to_mastodon": can_post_to_mastodon,
    }

    if request.headers.get("HX-Request"):
        return render(request, "harvests/_results.html", context)

    context.update(get_harvest_stats(identity.id))
    return render(request, "harvests/harvests_list.html", context)


@require_http_methods(["GET", "POST"])
def harvest_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        query = urlencode({"next": request.get_full_path()})
        return redirect(f"/login/?{query}")

    micropub_endpoint = request.session.get("micropub_endpoint", "")
    can_post_to_mastodon = (
        identity.login_method == "mastodon"
        and bool(identity.mastodon_access_token)
    )
    read_later_tag = _read_later_tag(identity)

    if request.method == "GET":
        url = normalize_harvest_url(request.GET.get("url", ""))
        title = request.GET.get("title", "").strip()
        note = request.GET.get("note", "").strip()
        tags = tag_string(split_tag_string(request.GET.get("tags", "")))
        title_autofilled = False

        if url and not title:
            title = guess_title_from_url(url)
            title_autofilled = bool(title)

        return render(request, "harvests/harvest_form.html", {
            "identity": identity,
            "url": url,
            "title": title,
            "title_autofilled": title_autofilled,
            "note": note,
            "tags": tags,
            "read_later_tag": read_later_tag,
            "read_later_checked": read_later_tag in split_tag_string(tags),
            "micropub_endpoint": micropub_endpoint,
            "can_post_to_mastodon": can_post_to_mastodon,
        })

    # POST
    submitted_url = request.POST.get("url", "").strip()
    url = normalize_harvest_url(submitted_url)
    submitted_title = request.POST.get("title", "").strip()
    title = submitted_title
    submitted_note = request.POST.get("note", "").strip()
    note = submitted_note
    submitted_tags = split_tag_string(request.POST.get("tags", ""))
    tags_list = submitted_tags[:]
    read_later_checked = request.POST.get("read_later") == "true"
    if read_later_checked:
        tags_list = merge_tags(tags_list, [read_later_tag])
    post_to_micropub_flag = request.POST.get("post_to_micropub") == "true"
    post_to_mastodon_flag = request.POST.get("post_to_mastodon") == "true"
    should_autofill_metadata = not submitted_title and not submitted_note and not submitted_tags

    if should_autofill_metadata and url:
        metadata = fetch_url_metadata(url)
        title = metadata.title or title
        note = metadata.note or note
        tags_list = merge_tags(tags_list, metadata.tags)

    tags = tag_string(tags_list)

    if not url or not _is_valid_url(url):
        return render(request, "harvests/harvest_form.html", {
            "identity": identity,
            "url": submitted_url,
            "title": title,
            "note": note,
            "tags": tags,
            "read_later_tag": read_later_tag,
            "read_later_checked": read_later_checked,
            "micropub_endpoint": micropub_endpoint,
            "can_post_to_mastodon": can_post_to_mastodon,
            "error": "Please enter a valid http/https URL.",
        }, status=400)

    try:
        harvest, created = Harvest.objects.get_or_create(
            identity=identity,
            url=url,
            defaults={"title": title, "note": note, "tags": tags},
        )
    except DataError:
        return render(request, "harvests/harvest_form.html", {
            "identity": identity,
            "url": url,
            "title": title,
            "note": note,
            "tags": tags,
            "read_later_tag": read_later_tag,
            "read_later_checked": read_later_checked,
            "micropub_endpoint": micropub_endpoint,
            "can_post_to_mastodon": can_post_to_mastodon,
            "error": "That link is still too long to save after cleanup. Try removing extra query parameters and save again.",
        }, status=400)

    if not created:
        update_fields: list[str] = []

        if title and (submitted_title or not harvest.title) and harvest.title != title:
            harvest.title = title
            update_fields.append("title")

        if note and (submitted_note or not harvest.note) and harvest.note != note:
            harvest.note = note
            update_fields.append("note")

        merged_existing_tags = tag_string(merge_tags(harvest.tags_list(), tags_list))
        if merged_existing_tags != harvest.tags:
            harvest.tags = merged_existing_tags
            update_fields.append("tags")

        if update_fields:
            harvest.save(update_fields=update_fields)

    invalidate_harvest_stats(identity.id)

    if post_to_micropub_flag and micropub_endpoint:
        access_token = request.session.get("access_token", "")
        post_to_micropub.delay(harvest.id, micropub_endpoint, access_token)

    if post_to_mastodon_flag and can_post_to_mastodon:
        post_to_mastodon.delay(harvest.id)

    # Invalidate SVG cache so plant regenerates with new harvest
    invalidate_svg(identity.username)

    is_popup = request.GET.get("popup") == "1"
    if is_popup:
        return render(request, "harvests/harvest_success.html", {"url": url, "title": harvest.title})

    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = "/dashboard/"
        return response

    messages.success(request, f"Harvested: {harvest.title or url}")
    return redirect("/dashboard/")


@require_GET
def harvest_metadata_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    url = normalize_harvest_url(request.GET.get("url", ""))
    if not url or not _is_valid_url(url):
        return JsonResponse({"error": "Please enter a valid http/https URL."}, status=400)

    metadata = fetch_url_metadata(url)
    return JsonResponse({
        "url": metadata.url,
        "title": metadata.title,
        "note": metadata.note,
        "tags": metadata.tags,
        "fetched": metadata.fetched,
        "read_later_tag": _read_later_tag(identity),
    })


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
        post_to_micropub.delay(harvest.id, micropub_endpoint, access_token)
        posted = True
    elif target == "mastodon" and can_post_to_mastodon:
        post_to_mastodon.delay(harvest.id)
        posted = True

    if request.headers.get("HX-Request"):
        if not posted:
            return HttpResponse('<span class="subtle harvest-posted harvest-posted-error">could not post</span>')
        if target == "mastodon":
            return HttpResponse('<span class="subtle harvest-posted">posted to mastodon</span>')
        return HttpResponse('<span class="subtle harvest-posted">posted</span>')

    messages.success(request, "Posted successfully.")
    return redirect(_harvests_redirect_target(request))


@require_http_methods(["GET", "POST"])
def harvest_edit_view(request: HttpRequest, harvest_id: int) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        query = urlencode({"next": request.get_full_path()})
        return redirect(f"/login/?{query}")

    harvest = get_object_or_404(Harvest, id=harvest_id, identity=identity)

    if request.method == "GET":
        return render(request, "harvests/harvest_edit_modal.html", {
            "harvest": harvest,
        })

    # POST — save and return updated card
    title = request.POST.get("title", "").strip()
    note = request.POST.get("note", "").strip()
    tags = ", ".join(t.strip() for t in request.POST.get("tags", "").split(",") if t.strip())

    harvest.title = title
    harvest.note = note
    harvest.tags = tags
    harvest.save(update_fields=["title", "note", "tags"])
    invalidate_harvest_stats(identity.id)

    micropub_endpoint = request.session.get("micropub_endpoint", "")
    can_post_to_mastodon = (
        identity.login_method == "mastodon"
        and bool(identity.mastodon_access_token)
    )
    ripeness = _ripeness_class(harvest)

    if not request.headers.get("HX-Request"):
        messages.success(request, "Harvest updated.")
        return redirect(_harvests_redirect_target(request))

    return render(request, "harvests/_harvest_card.html", {
        "harvest": harvest,
        "micropub_endpoint": micropub_endpoint,
        "can_post_to_mastodon": can_post_to_mastodon,
        "ripeness": ripeness,
        "close_modal": True,
    })


@require_GET
def bookmarklet_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    return render(request, "harvests/bookmarklet.html", {"identity": identity, "public_base_url": settings.PUBLIC_BASE_URL})


@require_POST
def harvest_delete_view(request: HttpRequest, harvest_id: int) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        query = urlencode({"next": request.get_full_path()})
        return redirect(f"/login/?{query}")

    harvest = get_object_or_404(Harvest, id=harvest_id, identity=identity)
    harvest.delete()
    invalidate_harvest_stats(identity.id)

    # Invalidate SVG cache
    invalidate_svg(identity.username)

    if request.headers.get("HX-Request"):
        return HttpResponse(status=200)

    messages.success(request, "Harvest deleted.")
    return redirect(_harvests_redirect_target(request))
