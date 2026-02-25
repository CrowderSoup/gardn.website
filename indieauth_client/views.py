from __future__ import annotations

from urllib.parse import urlencode, urljoin

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from gardn.utils import sanitize_user_bio_html, slug_from_me_url
from plants.models import UserIdentity

from .auth import (
    build_authorization_url,
    canonicalize_me_url,
    discover_endpoints,
    exchange_code_for_token,
    fetch_hcard,
    generate_pkce_pair,
    random_state,
    verify_code_at_auth_endpoint,
)


@require_http_methods(["GET", "POST"])
def login_start_view(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return render(request, "auth/login.html", {"next_url": request.GET.get("next", "/dashboard/")})

    next_url = request.POST.get("next", "/dashboard/")
    me_raw = request.POST.get("me", "")

    try:
        me = canonicalize_me_url(me_raw)
        endpoints = discover_endpoints(me)
        verifier, challenge = generate_pkce_pair()
        state = random_state()
        redirect_uri = urljoin(settings.PUBLIC_BASE_URL, "/auth/callback/")
        client_id = settings.PUBLIC_BASE_URL + "/"
        # Only request scope when there is a token endpoint; otherwise this is
        # an identity-only flow and the authorization endpoint redeems the code.
        has_token_endpoint = "token_endpoint" in endpoints
        auth_url = build_authorization_url(
            authorization_endpoint=endpoints["authorization_endpoint"],
            me=me,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=challenge,
            scope="profile create" if has_token_endpoint else "profile",
        )
    except Exception as exc:
        messages.error(request, f"Could not start IndieAuth: {exc}")
        return render(request, "auth/login.html", {"next_url": next_url, "me": me_raw}, status=400)

    request.session["indieauth_pending"] = {
        "me": me,
        "state": state,
        "code_verifier": verifier,
        "authorization_endpoint": endpoints["authorization_endpoint"],
        "token_endpoint": endpoints.get("token_endpoint", ""),
        "micropub_endpoint": endpoints.get("micropub", ""),
        "next": next_url,
    }
    return redirect(auth_url)


@require_GET
def auth_callback_view(request: HttpRequest) -> HttpResponse:
    pending = request.session.get("indieauth_pending")
    if not pending:
        messages.error(request, "Missing IndieAuth session state")
        return redirect("login")

    incoming_state = request.GET.get("state")
    code = request.GET.get("code")
    if not incoming_state or incoming_state != pending.get("state") or not code:
        messages.error(request, "Invalid IndieAuth callback state")
        return redirect("login")

    redirect_uri = urljoin(settings.PUBLIC_BASE_URL, "/auth/callback/")
    client_id = settings.PUBLIC_BASE_URL + "/"

    try:
        if pending.get("token_endpoint"):
            token_payload = exchange_code_for_token(
                token_endpoint=pending["token_endpoint"],
                code=code,
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_verifier=pending["code_verifier"],
            )
        else:
            token_payload = verify_code_at_auth_endpoint(
                authorization_endpoint=pending["authorization_endpoint"],
                code=code,
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_verifier=pending["code_verifier"],
            )
    except Exception as exc:
        messages.error(request, f"Token exchange failed: {exc}")
        return redirect("login")

    me = canonicalize_me_url(token_payload.get("me") or pending["me"])

    identity, created = UserIdentity.objects.get_or_create(
        me_url=me,
        defaults={"username": slug_from_me_url(me)},
    )
    if not created and not identity.username:
        identity.username = slug_from_me_url(me)

    token_profile = token_payload.get("profile")
    if token_profile and isinstance(token_profile, dict):
        identity.display_name = str(token_profile.get("name", ""))[:255]
        identity.photo_url = str(token_profile.get("photo", ""))
    else:
        card = fetch_hcard(me)
        if card:
            identity.display_name = card.get("display_name", "")[:255]
            identity.photo_url = card.get("photo_url", "")
            identity.bio = sanitize_user_bio_html(card.get("bio", "")[:5000])[:4000]
    identity.save(update_fields=["username", "display_name", "photo_url", "bio", "updated_at"])

    request.session["identity_id"] = identity.id
    request.session["me"] = identity.me_url
    request.session["access_token"] = token_payload.get("access_token", "")
    request.session["micropub_endpoint"] = pending.get("micropub_endpoint", "")
    request.session["website_verified"] = True

    next_url = pending.get("next") or "/dashboard/"
    del request.session["indieauth_pending"]
    return redirect(next_url)


@require_GET
def logout_view(request: HttpRequest) -> HttpResponse:
    request.session.flush()
    query = urlencode({"next": "/dashboard/"})
    return redirect(f"/login/?{query}")
