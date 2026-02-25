from __future__ import annotations

import hashlib

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, HttpResponseNotModified, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from picks.models import Pick

from .models import UserIdentity
from .svg import SVG_RENDER_VERSION, generate_svg


def _current_identity(request: HttpRequest) -> UserIdentity | None:
    identity_id = request.session.get("identity_id")
    if not identity_id:
        return None
    return UserIdentity.objects.filter(id=identity_id).first()


@require_GET
def home_view(request: HttpRequest) -> HttpResponse:
    q = request.GET.get("q", "").strip()
    if q:
        results = UserIdentity.objects.filter(
            Q(username__icontains=q) | Q(display_name__icontains=q)
        ).order_by("username")[:24]
    else:
        results = None
    recent = UserIdentity.objects.order_by("-created_at")[:12]
    popular = (
        UserIdentity.objects.annotate(pick_count=Count("incoming_picks"))
        .order_by("-pick_count")
        .filter(pick_count__gt=0)[:12]
    )
    return render(request, "plants/home.html", {
        "recent_identities": recent,
        "identity": _current_identity(request),
        "search_results": results,
        "q": q,
        "popular_identities": popular,
    })


@require_GET
def dashboard_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        return render(request, "plants/dashboard_anonymous.html", status=401)

    from harvests.models import Harvest

    micropub_endpoint = request.session.get("micropub_endpoint", "")
    can_post_to_mastodon = (
        identity.login_method == "mastodon"
        and bool(identity.mastodon_access_token)
    )

    q = request.GET.get("q", "").strip()
    harvest_qs = Harvest.objects.filter(identity=identity)
    if q:
        harvest_qs = harvest_qs.filter(
            Q(title__icontains=q) | Q(url__icontains=q) | Q(note__icontains=q) | Q(tags__icontains=q)
        )

    picks_qs = Pick.objects.filter(picker=identity).select_related("picked").order_by("-created_at")

    harvest_page = Paginator(harvest_qs, 50).get_page(request.GET.get("harvest_page"))
    picks_page = Paginator(picks_qs, 24).get_page(request.GET.get("picks_page"))
    q_param = f"&q={q}" if q else ""

    return render(request, "plants/dashboard.html", {
        "identity": identity,
        "picks_page": picks_page,
        "harvest_page": harvest_page,
        "q": q,
        "q_param": q_param,
        "micropub_endpoint": micropub_endpoint,
        "can_post_to_mastodon": can_post_to_mastodon,
    })


@require_GET
def user_profile_view(request: HttpRequest, username: str) -> HttpResponse:
    identity = get_object_or_404(UserIdentity, username=username)
    viewer = _current_identity(request)
    has_picked = False
    if viewer:
        has_picked = Pick.objects.filter(picker=viewer, picked=identity).exists()

    picks_qs = Pick.objects.filter(picker=identity).select_related("picked").order_by("-created_at")
    picks_page = Paginator(picks_qs, 24).get_page(request.GET.get("picks_page"))

    from harvests.models import Harvest

    harvest_page = None
    if identity.show_harvests_on_profile:
        harvest_page = Paginator(Harvest.objects.filter(identity=identity), 50).get_page(request.GET.get("harvest_page"))

    return render(
        request,
        "plants/user_profile.html",
        {
            "identity": identity,
            "viewer": viewer,
            "has_picked": has_picked,
            "pick_count": Pick.objects.filter(picked=identity).count(),
            "picks_page": picks_page,
            "harvest_page": harvest_page,
        },
    )


@require_POST
def profile_settings_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        return HttpResponse("Unauthorized", status=401)
    new_show_harvests = "show_harvests_on_profile" in request.POST
    new_animate_motion = "animate_plant_motion" in request.POST
    invalidate_svg = (
        identity.show_harvests_on_profile != new_show_harvests
        or identity.animate_plant_motion != new_animate_motion
    )
    identity.show_harvests_on_profile = new_show_harvests
    identity.animate_plant_motion = new_animate_motion
    if invalidate_svg:
        identity.svg_cache = ""
        identity.save(update_fields=["show_harvests_on_profile", "animate_plant_motion", "svg_cache", "updated_at"])
    else:
        identity.save(update_fields=["show_harvests_on_profile", "animate_plant_motion", "updated_at"])
    return redirect("account_settings")


@require_GET
def account_settings_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        return redirect("home")
    return render(request, "settings/settings.html", {"identity": identity})


@require_POST
def delete_account_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        return HttpResponse("Unauthorized", status=401)
    identity.delete()  # cascades Harvests, Picks
    request.session.flush()
    return redirect("home")


@require_GET
def export_data_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        return HttpResponse("Unauthorized", status=401)
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


@require_GET
def plant_svg_view(request: HttpRequest, username: str) -> HttpResponse:
    from harvests.models import Harvest

    identity = get_object_or_404(UserIdentity, username=username)
    motion_marker = f"motion:{int(identity.animate_plant_motion)}"
    render_marker = f"render:{SVG_RENDER_VERSION};{motion_marker}"
    if not identity.svg_cache or render_marker not in identity.svg_cache:
        harvest_urls = list(Harvest.objects.filter(identity=identity).values_list("url", flat=True))
        pick_count = Pick.objects.filter(Q(picker=identity) | Q(picked=identity)).count()
        svg = generate_svg(
            identity.me_url,
            harvest_urls=harvest_urls,
            motion_enabled=identity.animate_plant_motion,
            pick_count=pick_count,
        )
        identity.svg_cache = svg
        identity.save(update_fields=["svg_cache", "updated_at"])
    svg = identity.svg_cache

    etag = hashlib.sha256(svg.encode("utf-8")).hexdigest()
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponseNotModified()
        response["ETag"] = etag
        return response

    response = HttpResponse(svg, content_type="image/svg+xml")
    response["Cache-Control"] = "public, max-age=3600"
    response["ETag"] = etag
    return response
