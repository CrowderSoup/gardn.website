from __future__ import annotations

from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


class LoginRequiredSessionMiddleware:
    PUBLIC_PREFIXES = (
        "/login/",
        "/auth/",
        "/mastodon/",
        "/embed/",
        "/u/",
        "/api/",
        "/gardn.js",
        "/static/",
        "/admin/",
        "/harvest/bookmarklet/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path == "/":
            return self.get_response(request)

        if any(request.path.startswith(prefix) for prefix in self.PUBLIC_PREFIXES):
            return self.get_response(request)

        if request.session.get("identity_id"):
            # Mastodon users who haven't verified their website must go to verify page
            if (not request.session.get("website_verified", True)
                    and request.path != "/mastodon/verify-website/"):
                return redirect("/mastodon/verify-website/")
            return self.get_response(request)

        query = urlencode({"next": request.get_full_path()})
        return redirect(f"/login/?{query}")
