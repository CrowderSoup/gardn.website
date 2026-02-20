from __future__ import annotations

from urllib.parse import quote, urlparse

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_GET

from picks.models import Pick
from plants.models import UserIdentity


def _session_identity(request: HttpRequest) -> UserIdentity | None:
    identity_id = request.session.get("identity_id")
    if not identity_id:
        return None
    return UserIdentity.objects.filter(id=identity_id).first()


def _host_from_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return (parsed.hostname or "").lower()


def _request_embed_host(request: HttpRequest) -> str:
    # JS embeds send Origin; iframe embeds typically provide Referer.
    return _host_from_url(request.headers.get("Origin")) or _host_from_url(request.headers.get("Referer"))


def _host_allowed(embed_host: str, owner_host: str) -> bool:
    if not embed_host or not owner_host:
        return False
    return embed_host == owner_host or embed_host.endswith(f".{owner_host}")


def _embed_allowed(request: HttpRequest, identity: UserIdentity) -> bool:
    viewer = _session_identity(request)
    if viewer and viewer.id == identity.id:
        return True

    return _host_allowed(_request_embed_host(request), _host_from_url(identity.me_url))


@require_GET
@xframe_options_exempt
def embed_plant_view(request: HttpRequest, username: str) -> HttpResponse:
    identity = get_object_or_404(UserIdentity, username=username)
    if not _embed_allowed(request, identity):
        return HttpResponse("Forbidden: embed domain not allowed", status=403)
    viewer = _session_identity(request)
    has_picked = bool(viewer and Pick.objects.filter(picker=viewer, picked=identity).exists())
    return render(
        request,
        "embeds/embed_plant.html",
        {
            "identity": identity,
            "identity_domain": _host_from_url(identity.me_url),
            "viewer": viewer,
            "has_picked": has_picked,
            "pick_count": Pick.objects.filter(picked=identity).count(),
            "public_base": settings.PUBLIC_BASE_URL,
        },
    )


@require_GET
@xframe_options_exempt
def embed_roll_view(request: HttpRequest, username: str) -> HttpResponse:
    identity = get_object_or_404(UserIdentity, username=username)
    if not _embed_allowed(request, identity):
        return HttpResponse("Forbidden: embed domain not allowed", status=403)
    picks = Pick.objects.filter(picker=identity).select_related("picked").order_by("-created_at")
    return render(request, "embeds/embed_roll.html", {"identity": identity, "picks": picks, "public_base": settings.PUBLIC_BASE_URL})


@require_GET
def plant_json_view(request: HttpRequest, username: str) -> JsonResponse:
    identity = get_object_or_404(UserIdentity, username=username)
    origin = request.headers.get("Origin", "")
    if not _embed_allowed(request, identity):
        return JsonResponse({"detail": "Forbidden: embed domain not allowed"}, status=403)
    viewer = _session_identity(request)
    has_picked = bool(viewer and Pick.objects.filter(picker=viewer, picked=identity).exists())
    response = JsonResponse(
        {
            "username": identity.username,
            "me_url": identity.me_url,
            "identity_domain": _host_from_url(identity.me_url),
            "display_name": identity.display_name,
            "plant_svg_url": f"{settings.PUBLIC_BASE_URL}/u/{identity.username}/plant.svg",
            "profile_url": f"{settings.PUBLIC_BASE_URL}/u/{identity.username}/",
            "login_to_pick_url": f"{settings.PUBLIC_BASE_URL}/login/?next={quote(f'/u/{identity.username}/')}",
            "pick_count": Pick.objects.filter(picked=identity).count(),
            "has_picked": has_picked,
        }
    )
    if origin and _host_allowed(_host_from_url(origin), _host_from_url(identity.me_url)):
        response["Access-Control-Allow-Origin"] = origin
        response["Vary"] = "Origin"
    return response


@require_GET
def roll_json_view(request: HttpRequest, username: str) -> JsonResponse:
    identity = get_object_or_404(UserIdentity, username=username)
    origin = request.headers.get("Origin", "")
    if not _embed_allowed(request, identity):
        return JsonResponse({"detail": "Forbidden: embed domain not allowed"}, status=403)
    rows = [
        {
            "username": row.picked.username,
            "me_url": row.picked.me_url,
            "display_name": row.picked.display_name,
            "plant_svg_url": f"{settings.PUBLIC_BASE_URL}/u/{row.picked.username}/plant.svg",
            "profile_url": f"{settings.PUBLIC_BASE_URL}/u/{row.picked.username}/",
            "picked_at": row.created_at.isoformat(),
        }
        for row in Pick.objects.filter(picker=identity).select_related("picked").order_by("-created_at")
    ]
    response = JsonResponse({"username": identity.username, "roll": rows})
    if origin and _host_allowed(_host_from_url(origin), _host_from_url(identity.me_url)):
        response["Access-Control-Allow-Origin"] = origin
        response["Vary"] = "Origin"
    return response


@require_GET
def gardn_js_view(request: HttpRequest) -> HttpResponse:
    js = render(request, "embeds/gardn.js", {"public_base": settings.PUBLIC_BASE_URL}).content
    return HttpResponse(js, content_type="application/javascript")
