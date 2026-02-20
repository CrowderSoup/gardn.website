from __future__ import annotations

import hashlib

from django.http import HttpRequest, HttpResponse, HttpResponseNotModified
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from picks.models import Pick

from .models import UserIdentity
from .svg import generate_svg


def _current_identity(request: HttpRequest) -> UserIdentity | None:
    identity_id = request.session.get("identity_id")
    if not identity_id:
        return None
    return UserIdentity.objects.filter(id=identity_id).first()


@require_GET
def home_view(request: HttpRequest) -> HttpResponse:
    recent = UserIdentity.objects.order_by("-created_at")[:12]
    return render(request, "plants/home.html", {"recent_identities": recent, "identity": _current_identity(request)})


@require_GET
def dashboard_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        return render(request, "plants/dashboard_anonymous.html", status=401)

    picks = Pick.objects.filter(picker=identity).select_related("picked").order_by("-created_at")
    return render(request, "plants/dashboard.html", {"identity": identity, "picks": picks})


@require_GET
def user_profile_view(request: HttpRequest, username: str) -> HttpResponse:
    identity = get_object_or_404(UserIdentity, username=username)
    viewer = _current_identity(request)
    has_picked = False
    if viewer:
        has_picked = Pick.objects.filter(picker=viewer, picked=identity).exists()

    picks = Pick.objects.filter(picker=identity).select_related("picked").order_by("-created_at")
    return render(
        request,
        "plants/user_profile.html",
        {
            "identity": identity,
            "viewer": viewer,
            "has_picked": has_picked,
            "pick_count": Pick.objects.filter(picked=identity).count(),
            "picks": picks,
        },
    )


@require_GET
def plant_svg_view(request: HttpRequest, username: str) -> HttpResponse:
    identity = get_object_or_404(UserIdentity, username=username)
    svg = identity.svg_cache or generate_svg(identity.me_url)
    if not identity.svg_cache:
        identity.svg_cache = svg
        identity.save(update_fields=["svg_cache", "updated_at"])

    etag = hashlib.sha256(svg.encode("utf-8")).hexdigest()
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponseNotModified()
        response["ETag"] = etag
        return response

    response = HttpResponse(svg, content_type="image/svg+xml")
    response["Cache-Control"] = "public, max-age=3600"
    response["ETag"] = etag
    return response
