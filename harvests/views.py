from __future__ import annotations

from urllib.parse import urlparse

import requests
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from plants.models import UserIdentity

from .models import Harvest


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

    if request.method == "GET":
        return render(request, "harvests/harvest_form.html", {
            "identity": identity,
            "url": request.GET.get("url", ""),
            "title": request.GET.get("title", ""),
            "micropub_endpoint": micropub_endpoint,
        })

    # POST
    url = request.POST.get("url", "").strip()
    title = request.POST.get("title", "").strip()
    note = request.POST.get("note", "").strip()
    tags = ", ".join(t.strip() for t in request.POST.get("tags", "").split(",") if t.strip())
    post_to_micropub = request.POST.get("post_to_micropub") == "true"

    if not url or not _is_valid_url(url):
        return render(request, "harvests/harvest_form.html", {
            "identity": identity,
            "url": url,
            "title": title,
            "note": note,
            "tags": tags,
            "micropub_endpoint": micropub_endpoint,
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

    micropub_warning = None
    if post_to_micropub and micropub_endpoint:
        access_token = request.session.get("access_token", "")
        try:
            resp = requests.post(
                micropub_endpoint,
                data={"h": "entry", "bookmark-of": url, "name": title},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if resp.status_code in (200, 201, 202):
                harvest.micropub_posted = True
                harvest.save(update_fields=["micropub_posted"])
            else:
                micropub_warning = f"Harvest saved, but micropub post failed (HTTP {resp.status_code})."
        except Exception as exc:
            micropub_warning = f"Harvest saved, but micropub post failed: {exc}"

    # Invalidate SVG cache so plant regenerates with new harvest
    UserIdentity.objects.filter(pk=identity.pk).update(svg_cache="")

    if micropub_warning:
        messages.warning(request, micropub_warning)

    is_popup = request.GET.get("popup") == "1"
    if is_popup:
        return render(request, "harvests/harvest_success.html", {"url": url, "title": title})

    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = "/dashboard/"
        return response

    messages.success(request, f"Harvested: {title or url}")
    return redirect("/dashboard/")


@require_GET
def bookmarklet_view(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    return render(request, "harvests/bookmarklet.html", {"identity": identity})


@require_POST
def harvest_delete_view(request: HttpRequest, harvest_id: int) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        return redirect("/login/")

    harvest = get_object_or_404(Harvest, id=harvest_id, identity=identity)
    harvest.delete()

    # Invalidate SVG cache
    UserIdentity.objects.filter(pk=identity.pk).update(svg_cache="")

    if request.headers.get("HX-Request"):
        return HttpResponse(status=200)

    messages.success(request, "Harvest deleted.")
    return redirect("/dashboard/")
