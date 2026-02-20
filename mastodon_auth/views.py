from __future__ import annotations

from urllib.parse import urlparse

from django.contrib import messages
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from gardn.utils import sanitize_user_bio_html, slug_from_me_url
from plants.models import UserIdentity

from .auth import (
    build_auth_url,
    check_website_link,
    exchange_code,
    get_account_info,
    get_or_register_app,
    parse_handle,
    random_state,
)


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


@require_http_methods(["POST"])
def mastodon_login_start(request: HttpRequest) -> HttpResponse:
    handle = request.POST.get("handle", "").strip()
    if not handle:
        messages.error(request, "Please enter a Mastodon handle.")
        return redirect("/login/")

    try:
        instance_url, _username = parse_handle(handle)
        app = get_or_register_app(instance_url)
        state = random_state()
        request.session["mastodon_pending"] = {
            "state": state,
            "instance_url": instance_url,
        }
        return redirect(build_auth_url(app, instance_url, state))
    except Exception as exc:
        messages.error(request, f"Could not start Mastodon login: {exc}")
        return redirect("/login/")


@require_GET
def mastodon_callback(request: HttpRequest) -> HttpResponse:
    pending = request.session.get("mastodon_pending")
    if not pending:
        messages.error(request, "Missing Mastodon session state.")
        return redirect("/login/")

    incoming_state = request.GET.get("state")
    code = request.GET.get("code")
    if not incoming_state or incoming_state != pending.get("state") or not code:
        messages.error(request, "Invalid Mastodon callback state.")
        return redirect("/login/")

    instance_url = pending["instance_url"]

    try:
        app = get_or_register_app(instance_url)
        token_data = exchange_code(app, instance_url, code)
        access_token = token_data["access_token"]
        profile = get_account_info(instance_url, access_token)
    except Exception as exc:
        messages.error(request, f"Mastodon login failed: {exc}")
        return redirect("/login/")

    mastodon_profile_url = profile.get("url", "").strip()
    if not mastodon_profile_url:
        messages.error(request, "Could not retrieve Mastodon profile URL.")
        return redirect("/login/")

    acct = profile.get("acct", "")
    # acct may be just "user" on the home instance; normalise to user@instance
    if "@" not in acct:
        parsed = urlparse(instance_url)
        acct = f"{acct}@{parsed.netloc}"
    mastodon_handle = acct

    # Look up existing identity by Mastodon profile URL first (handles re-login after
    # website verification, when me_url has been updated to the website URL).
    identity = UserIdentity.objects.filter(mastodon_profile_url=mastodon_profile_url).first()
    if not identity:
        # New Mastodon user — create with profile URL as initial me_url.
        # get_or_create on me_url handles the unlikely race condition.
        identity, _created = UserIdentity.objects.get_or_create(
            me_url=mastodon_profile_url,
            defaults={
                "username": slug_from_me_url(mastodon_profile_url),
                "login_method": "mastodon",
                "mastodon_profile_url": mastodon_profile_url,
                "website_verified": False,
            },
        )

    already_verified = identity.website_verified

    identity.display_name = (profile.get("display_name") or "")[:255]
    identity.photo_url = profile.get("avatar") or ""
    identity.bio = sanitize_user_bio_html((profile.get("note") or "")[:5000])[:4000]
    identity.mastodon_handle = mastodon_handle
    identity.mastodon_access_token = access_token
    identity.mastodon_profile_url = mastodon_profile_url
    identity.login_method = "mastodon"
    identity.save(update_fields=[
        "display_name", "photo_url", "bio", "mastodon_handle",
        "mastodon_access_token", "mastodon_profile_url", "login_method",
        "updated_at",
    ])

    request.session["identity_id"] = identity.id
    request.session["me"] = identity.me_url
    request.session["website_verified"] = already_verified
    del request.session["mastodon_pending"]

    if already_verified:
        return redirect("/dashboard/")
    return redirect("/mastodon/verify-website/")


@require_http_methods(["GET", "POST"])
def verify_website_view(request: HttpRequest) -> HttpResponse:
    identity_id = request.session.get("identity_id")
    if not identity_id:
        return redirect("/login/")

    identity = UserIdentity.objects.filter(id=identity_id).first()
    if not identity or identity.login_method != "mastodon":
        return redirect("/login/")

    if request.method == "GET":
        return render(request, "mastodon_auth/verify_website.html", {
            "identity": identity,
            "mastodon_profile_url": identity.mastodon_profile_url,
        })

    website_url = request.POST.get("website_url", "").strip()
    if not website_url or not _is_valid_url(website_url):
        return render(request, "mastodon_auth/verify_website.html", {
            "identity": identity,
            "mastodon_profile_url": identity.mastodon_profile_url,
            "website_url": website_url,
            "error": "Please enter a valid http/https URL.",
        }, status=400)

    if check_website_link(website_url, identity.mastodon_profile_url):
        candidate_username = slug_from_me_url(website_url)
        existing = UserIdentity.objects.filter(
            Q(me_url=website_url) | Q(username=candidate_username)
        ).exclude(id=identity.id).first()
        if existing:
            # Merge: an account for this website already exists (e.g. IndieAuth).
            # Copy Mastodon credentials onto it and discard the temp identity.
            # Reassign any related data just in case (normally the temp identity is fresh).
            existing.mastodon_handle = identity.mastodon_handle
            existing.mastodon_profile_url = identity.mastodon_profile_url
            existing.mastodon_access_token = identity.mastodon_access_token
            existing.website_verified = True
            existing.save(update_fields=[
                "mastodon_handle", "mastodon_profile_url", "mastodon_access_token",
                "website_verified", "updated_at",
            ])
            identity.harvests.all().update(identity=existing)
            identity.outgoing_picks.all().update(picker=existing)
            identity.incoming_picks.all().update(picked=existing)
            identity.delete()
            identity = existing
        else:
            identity.me_url = website_url
            identity.username = slug_from_me_url(website_url)
            identity.website_verified = True
            identity.save(update_fields=["me_url", "username", "website_verified", "updated_at"])

        request.session["identity_id"] = identity.id
        request.session["me"] = identity.me_url
        request.session["website_verified"] = True
        messages.success(request, "Website verified! Welcome to Gardn.")
        return redirect("/dashboard/")

    return render(request, "mastodon_auth/verify_website.html", {
        "identity": identity,
        "mastodon_profile_url": identity.mastodon_profile_url,
        "website_url": website_url,
        "error": (
            f'Could not find <link rel="me" href="{identity.mastodon_profile_url}"> '
            f"on {website_url}. Make sure you've added it to your page's &lt;head&gt; "
            "and that the page is publicly accessible."
        ),
    }, status=400)
