from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from plants.models import UserIdentity

from .models import Pick
from .rate_limit import hit_rate_limit


def _current_identity(request: HttpRequest) -> UserIdentity | None:
    identity_id = request.session.get("identity_id")
    if not identity_id:
        return None
    return UserIdentity.objects.filter(id=identity_id).first()


def _throttled(request: HttpRequest, user: UserIdentity) -> bool:
    ip = request.META.get("REMOTE_ADDR", "unknown")
    return hit_rate_limit(f"pick-ip:{ip}", 30, 60) or hit_rate_limit(f"pick-user:{user.id}", 30, 60)


def _render_pick_state(request: HttpRequest, viewer: UserIdentity | None, picked: UserIdentity) -> HttpResponse:
    has_picked = bool(viewer and Pick.objects.filter(picker=viewer, picked=picked).exists())
    context = {
        "picked_identity": picked,
        "viewer": viewer,
        "has_picked": has_picked,
        "pick_count": Pick.objects.filter(picked=picked).count(),
    }
    template = "picks/_pick_button.html" if request.htmx else "picks/pick_state_full.html"
    return render(request, template, context)


@require_POST
def pick_view(request: HttpRequest, username: str) -> HttpResponse:
    viewer = _current_identity(request)
    picked = get_object_or_404(UserIdentity, username=username)
    if not viewer:
        response = _render_pick_state(request, None, picked)
        response.status_code = 401
        return response

    if _throttled(request, viewer):
        response = _render_pick_state(request, viewer, picked)
        response.status_code = 429
        return response

    if viewer.id != picked.id:
        Pick.objects.get_or_create(picker=viewer, picked=picked)
        UserIdentity.objects.filter(id__in=[viewer.id, picked.id]).update(svg_cache="")

    return _render_pick_state(request, viewer, picked)


@require_POST
def unpick_view(request: HttpRequest, username: str) -> HttpResponse:
    viewer = _current_identity(request)
    picked = get_object_or_404(UserIdentity, username=username)
    if not viewer:
        response = _render_pick_state(request, None, picked)
        response.status_code = 401
        return response

    if _throttled(request, viewer):
        response = _render_pick_state(request, viewer, picked)
        response.status_code = 429
        return response

    Pick.objects.filter(picker=viewer, picked=picked).delete()
    UserIdentity.objects.filter(id__in=[viewer.id, picked.id]).update(svg_cache="")
    return _render_pick_state(request, viewer, picked)
