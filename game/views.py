from __future__ import annotations

import json
from datetime import timedelta

from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from picks.models import Pick
from plants.models import UserIdentity

from .evidence import (
    ENTRY_ACTIVITY_KINDS,
    calculate_growth_stage,
    get_or_create_site_scan,
    plant_type_for_activity,
    publish_bookmark_via_micropub,
    publish_note_via_micropub,
    run_site_scan,
    seed_inventory,
    serialize_activity,
    serialize_neighbor,
)
from .models import GardenVisit, GameProfile, GardenPlot, NeighborLink, Quest, QuestProgress, SiteScan, VerifiedActivity
from .tasks import verify_published_activity


def _current_identity(request: HttpRequest) -> UserIdentity | None:
    identity_id = request.session.get("identity_id")
    if not identity_id:
        return None
    return UserIdentity.objects.filter(id=identity_id).first()


def _require_identity(request: HttpRequest) -> tuple[UserIdentity | None, JsonResponse | None]:
    identity = _current_identity(request)
    if not identity:
        return None, JsonResponse({"error": "Authentication required"}, status=401)
    return identity, None


def _get_profile(identity: UserIdentity) -> GameProfile:
    profile, _created = GameProfile.objects.get_or_create(identity=identity)
    if identity.login_method == "indieauth" and not profile.has_website:
        profile.has_website = True
        profile.save(update_fields=["has_website"])
    return profile


def _site_status_payload(scan: SiteScan) -> dict[str, object]:
    return {
        "status": scan.status,
        "issues": scan.issues,
        "last_error": scan.last_error,
        "scanned_url": scan.scanned_url,
        "last_scanned_at": scan.last_scanned_at.isoformat() if scan.last_scanned_at else None,
        "capabilities": scan.capabilities,
    }


def _garden_plot_title_max_length() -> int:
    field = GardenPlot._meta.get_field("link_title")
    model_max_length = field.max_length or 0
    try:
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(cursor, GardenPlot._meta.db_table)
    except Exception:
        return model_max_length

    for column in description:
        if column.name == field.column:
            internal_size = getattr(column, "internal_size", None)
            if isinstance(internal_size, int) and internal_size > 0:
                return min(model_max_length, internal_size)
            break
    return model_max_length


def _enqueue_published_activity_verification(activity: VerifiedActivity) -> None:
    if activity.status != VerifiedActivity.STATUS_PENDING:
        return
    if not activity.source_url:
        return
    verify_published_activity.delay(activity.id)


def _recent_verified_count(identity: UserIdentity) -> int:
    return VerifiedActivity.objects.filter(
        identity=identity,
        kind__in=ENTRY_ACTIVITY_KINDS,
        status=VerifiedActivity.STATUS_VERIFIED,
        verified_at__gte=timezone.now() - timedelta(days=7),
    ).count()


def _recent_visitor_count(identity: UserIdentity) -> int:
    return (
        GardenVisit.objects.filter(host=identity, visited_on__gte=timezone.localdate() - timedelta(days=6))
        .values("visitor_id")
        .distinct()
        .count()
    )


def _garden_health_payload(scan: SiteScan, recent_verified_count: int, recent_visitor_count: int) -> dict[str, object]:
    site_score_map = {
        SiteScan.STATUS_VERIFIED: 40,
        SiteScan.STATUS_MISSING_BLOGROLL: 32,
        SiteScan.STATUS_MISSING_MARKUP: 28,
        SiteScan.STATUS_MISSING_FEED: 24,
        SiteScan.STATUS_SCAN_FAILED: 10,
        SiteScan.STATUS_NEVER: 8,
    }
    score = min(
        100,
        site_score_map.get(scan.status, 8)
        + min(40, recent_verified_count * 10)
        + min(20, recent_visitor_count * 5),
    )
    if score >= 80:
        label = "thriving"
    elif score >= 60:
        label = "blooming"
    elif score >= 35:
        label = "steady"
    else:
        label = "fragile"
    return {
        "score": score,
        "label": label,
        "recent_verified_count": recent_verified_count,
        "recent_visitor_count": recent_visitor_count,
    }


def _garden_share_url(identity: UserIdentity) -> str:
    return reverse("shared_garden_index", args=[identity.username])


def _garden_owner_payload(identity: UserIdentity) -> dict[str, object]:
    return {
        "username": identity.username,
        "display_name": identity.display_name or identity.username,
        "garden_url": _garden_share_url(identity),
    }


def _garden_payload(profile: GameProfile, recent_verified_count: int, recent_visitor_count: int = 0) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for plot in profile.garden_plots.select_related("verified_activity").order_by("slot_y", "slot_x"):
        activity = plot.verified_activity
        payload.append(
            {
                "slot_x": plot.slot_x,
                "slot_y": plot.slot_y,
                "verified_activity_id": activity.id if activity else None,
                "link_url": activity.canonical_url if activity and activity.canonical_url else plot.link_url,
                "link_title": activity.title if activity and activity.title else plot.link_title,
                "plant_type": plot.plant_type or plant_type_for_activity(activity, plot.link_url),
                "growth_stage": calculate_growth_stage(plot, recent_verified_count, recent_visitor_count),
                "status": activity.status if activity else VerifiedActivity.STATUS_LEGACY,
                "kind": activity.kind if activity else "",
            }
        )
    return payload


def _can_visit_garden(viewer: UserIdentity, host: UserIdentity) -> bool:
    if viewer.id == host.id:
        return True
    return NeighborLink.objects.filter(identity=viewer, target_identity=host).exists()


def _guest_garden_state(viewer: UserIdentity, host: UserIdentity) -> dict[str, object]:
    profile = _get_profile(host)
    scan = get_or_create_site_scan(host)
    recent_verified_count = _recent_verified_count(host)
    recent_visitor_count = _recent_visitor_count(host)
    already_visited_today = False
    if viewer.id != host.id:
        already_visited_today = GardenVisit.objects.filter(
            host=host,
            visitor=viewer,
            visited_on=timezone.localdate(),
        ).exists()
    return {
        "owner": _garden_owner_payload(host),
        "site_status": _site_status_payload(scan),
        "garden_health": _garden_health_payload(scan, recent_verified_count, recent_visitor_count),
        "garden": _garden_payload(profile, recent_verified_count, recent_visitor_count),
        "visit": {
            "allowed": _can_visit_garden(viewer, host),
            "already_visited_today": already_visited_today,
        },
    }


def _quest_progress_payload(identity: UserIdentity, profile: GameProfile) -> list[dict[str, object]]:
    completed = {
        progress.quest.slug: progress
        for progress in QuestProgress.objects.filter(profile=profile, status="complete").select_related("quest")
    }

    verified_entry_count = VerifiedActivity.objects.filter(
        identity=identity,
        kind__in=ENTRY_ACTIVITY_KINDS,
        status=VerifiedActivity.STATUS_VERIFIED,
    ).count()
    neighbor_count = NeighborLink.objects.filter(identity=identity).count()
    outgoing_pick_count = Pick.objects.filter(picker=identity).count()
    planted_count = profile.garden_plots.count()
    recent_verified_count = VerifiedActivity.objects.filter(
        identity=identity,
        kind__in=ENTRY_ACTIVITY_KINDS,
        status=VerifiedActivity.STATUS_VERIFIED,
        verified_at__gte=timezone.now() - timedelta(days=7),
    ).count()
    oldest_plot_days = 0
    oldest_plot = profile.garden_plots.exclude(planted_at=None).order_by("planted_at").first()
    if oldest_plot and oldest_plot.planted_at:
        oldest_plot_days = (timezone.now() - oldest_plot.planted_at).days

    quest_metrics: dict[str, tuple[int, int]] = {
        "ten-links-deep": (verified_entry_count, 10),
        "plant-your-flag": (1 if profile.has_website else 0, 1),
        "good-neighbor": (neighbor_count or outgoing_pick_count, 3),
        "write-something": (verified_entry_count, 1),
        "webring-rider": (neighbor_count, 1),
        "deep-roots": (min(7, oldest_plot_days if recent_verified_count else 0), 7),
    }

    payload: list[dict[str, object]] = []
    for quest in Quest.objects.order_by("order", "title"):
        current, target = quest_metrics.get(quest.slug, (0, 1))
        is_complete = quest.slug in completed
        claimable = current >= target and not is_complete
        payload.append(
            {
                "slug": quest.slug,
                "title": quest.title,
                "description": quest.description,
                "category": quest.category,
                "status": "complete" if is_complete else ("claimable" if claimable else "active"),
                "progress": current,
                "target": target,
                "npc_id": quest.npc_id,
            }
        )
    return payload


def _game_state(identity: UserIdentity) -> dict[str, object]:
    profile = _get_profile(identity)
    scan = get_or_create_site_scan(identity)
    verified_inventory, pending_inventory = seed_inventory(identity)
    recent_verified_count = _recent_verified_count(identity)
    recent_visitor_count = _recent_visitor_count(identity)
    neighbors = list(
        NeighborLink.objects.filter(identity=identity)
        .select_related("target_identity")
        .order_by("relationship", "target_url")
    )
    garden_health = _garden_health_payload(scan, recent_verified_count, recent_visitor_count)

    return {
        "player": {
            "display_name": profile.display_name or identity.display_name or identity.username,
            "username": identity.username,
            "map_id": profile.map_id,
            "tile_x": profile.tile_x,
            "tile_y": profile.tile_y,
            "tutorial_step": profile.tutorial_step,
            "has_website": profile.has_website,
            "links_harvested": len(verified_inventory),
            "seeds_planted": profile.garden_plots.count(),
            "pending_count": len(pending_inventory),
            "neighbor_count": len(neighbors),
            "recent_verified_count": recent_verified_count,
            "recent_visitor_count": recent_visitor_count,
        },
        "owner": _garden_owner_payload(identity),
        "capabilities": scan.capabilities,
        "site_status": _site_status_payload(scan),
        "garden_health": garden_health,
        "garden": _garden_payload(profile, recent_verified_count, recent_visitor_count),
        "verified_inventory": [serialize_activity(activity) for activity in verified_inventory],
        "pending_inventory": [serialize_activity(activity) for activity in pending_inventory],
        "neighbors": [serialize_neighbor(link) for link in neighbors],
        "quests": _quest_progress_payload(identity, profile),
    }


def game_index(request: HttpRequest) -> HttpResponse:
    identity = _current_identity(request)
    if not identity:
        return render(request, "game/login_prompt.html")

    profile = _get_profile(identity)
    get_or_create_site_scan(identity)
    return render(
        request,
        "game/index.html",
        {
            "profile": profile,
            "share_garden_url": _garden_share_url(profile.identity),
            "launch_map_id": "",
            "launch_guest_username": "",
        },
    )


def shared_garden_index(request: HttpRequest, username: str) -> HttpResponse:
    host = get_object_or_404(UserIdentity, username=username)
    identity = _current_identity(request)
    if not identity:
        return render(request, "game/login_prompt.html")

    profile = _get_profile(identity)
    get_or_create_site_scan(identity)
    launch_map_id = ""
    launch_guest_username = ""
    if identity.id != host.id:
        launch_map_id = "guest_garden"
        launch_guest_username = host.username
    return render(
        request,
        "game/index.html",
        {
            "profile": profile,
            "share_garden_url": _garden_share_url(profile.identity),
            "launch_map_id": launch_map_id,
            "launch_guest_username": launch_guest_username,
        },
    )


@require_GET
def api_game_state(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err
    return JsonResponse(_game_state(identity))


@require_GET
def api_public_garden_state(request: HttpRequest, username: str) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    host = get_object_or_404(UserIdentity, username=username)
    if not _can_visit_garden(identity, host):
        return JsonResponse(
            {"error": "Pick this gardener and rescan your site before you can visit their garden."},
            status=403,
        )
    return JsonResponse(_guest_garden_state(identity, host))


@require_POST
def api_record_garden_visit(request: HttpRequest, username: str) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    host = get_object_or_404(UserIdentity, username=username)
    if not _can_visit_garden(identity, host):
        return JsonResponse(
            {"error": "Pick this gardener and rescan your site before you can visit their garden."},
            status=403,
        )

    recorded = False
    if identity.id != host.id:
        _visit, recorded = GardenVisit.objects.get_or_create(
            host=host,
            visitor=identity,
            visited_on=timezone.localdate(),
            defaults={"source": GardenVisit.SOURCE_NEIGHBOR_GROVE},
        )

    return JsonResponse(
        {
            "ok": True,
            "recorded": recorded,
            "garden_state": _guest_garden_state(identity, host),
        }
    )


@require_POST
def api_save_position(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    data = json.loads(request.body)
    profile = _get_profile(identity)
    profile.map_id = data.get("map_id", profile.map_id)
    profile.tile_x = data.get("tile_x", profile.tile_x)
    profile.tile_y = data.get("tile_y", profile.tile_y)
    profile.save(update_fields=["map_id", "tile_x", "tile_y"])
    return JsonResponse({"ok": True})


@require_POST
def api_harvest_link(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err
    state = _game_state(identity)
    return JsonResponse(
        {
            "ok": False,
            "error": "Harvests now come from verified site activity. Publish to your site or run a scan.",
            "verified_inventory": state["verified_inventory"],
            "pending_inventory": state["pending_inventory"],
        },
        status=409,
    )


@require_GET
def api_unplanted_harvests(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    verified_inventory, pending_inventory = seed_inventory(identity)
    return JsonResponse(
        {
            "verified_inventory": [serialize_activity(activity) for activity in verified_inventory],
            "pending_inventory": [serialize_activity(activity) for activity in pending_inventory],
            "harvests": [serialize_activity(activity) for activity in verified_inventory],
        }
    )


@require_POST
def api_scan_site(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    data = json.loads(request.body or "{}")
    manual_page_url = data.get("page_url", "").strip()
    scan = run_site_scan(identity, manual_page_url=manual_page_url)
    state = _game_state(identity)
    return JsonResponse({"ok": True, "site_status": _site_status_payload(scan), "state": state})


@require_GET
def api_site_status(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    scan = get_or_create_site_scan(identity)
    return JsonResponse(_site_status_payload(scan))


@require_POST
def api_publish_bookmark(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    micropub_endpoint = request.session.get("micropub_endpoint", "")
    access_token = request.session.get("access_token", "")
    if not micropub_endpoint or not access_token:
        return JsonResponse({"error": "Micropub is not available for this account"}, status=400)

    data = json.loads(request.body)
    try:
        activity = publish_bookmark_via_micropub(
            identity,
            micropub_endpoint=micropub_endpoint,
            access_token=access_token,
            target_url=data.get("target_url", ""),
            title=data.get("title", ""),
        )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    _enqueue_published_activity_verification(activity)
    return JsonResponse({"ok": True, "activity": serialize_activity(activity)})


@require_POST
def api_publish_note(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    micropub_endpoint = request.session.get("micropub_endpoint", "")
    access_token = request.session.get("access_token", "")
    if not micropub_endpoint or not access_token:
        return JsonResponse({"error": "Micropub is not available for this account"}, status=400)

    data = json.loads(request.body)
    try:
        activity = publish_note_via_micropub(
            identity,
            micropub_endpoint=micropub_endpoint,
            access_token=access_token,
            content=data.get("content", ""),
            title=data.get("title", ""),
        )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    _enqueue_published_activity_verification(activity)
    return JsonResponse({"ok": True, "activity": serialize_activity(activity)})


@require_POST
def api_plant_seed(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    data = json.loads(request.body)
    activity_id = data.get("verified_activity_id")
    if not activity_id:
        return JsonResponse({"error": "verified_activity_id required"}, status=400)

    profile = _get_profile(identity)
    activity = get_object_or_404(
        VerifiedActivity,
        id=activity_id,
        identity=identity,
        kind__in=ENTRY_ACTIVITY_KINDS,
        status=VerifiedActivity.STATUS_VERIFIED,
    )
    already_planted = GardenPlot.objects.filter(profile=profile, verified_activity=activity).exists()
    if already_planted:
        return JsonResponse({"error": "That verified activity is already planted"}, status=409)

    max_title_length = _garden_plot_title_max_length()
    plot_title = (activity.title or activity.canonical_url)[:max_title_length]

    plot, _created = GardenPlot.objects.update_or_create(
        profile=profile,
        slot_x=data["slot_x"],
        slot_y=data["slot_y"],
        defaults={
            "verified_activity": activity,
            "link_url": activity.canonical_url,
            "link_title": plot_title,
            "plant_type": plant_type_for_activity(activity, activity.canonical_url),
            "growth_stage": 1,
            "planted_at": timezone.now(),
        },
    )
    return JsonResponse({"ok": True, "plot_id": plot.id})


@require_POST
def api_advance_tutorial(request: HttpRequest) -> HttpResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    profile = _get_profile(identity)

    if request.content_type and "application/json" in request.content_type:
        data = json.loads(request.body)
        step = data.get("step", profile.tutorial_step + 1)
        neocities_url = data.get("neocities_url", "")
    else:
        step = int(request.POST.get("step", profile.tutorial_step + 1))
        neocities_url = request.POST.get("neocities_url", "")

    profile.tutorial_step = step
    if neocities_url:
        profile.neocities_username = neocities_url
        profile.has_website = True
        profile.save(update_fields=["tutorial_step", "neocities_username", "has_website"])
    else:
        profile.save(update_fields=["tutorial_step"])

    if request.htmx:
        return render(
            request,
            "game/partials/tutorial_step_done.html",
            {"profile": profile},
        )
    return JsonResponse({"ok": True, "tutorial_step": profile.tutorial_step})


@require_POST
def api_complete_quest(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    data = json.loads(request.body)
    profile = _get_profile(identity)
    quest_slug = data.get("quest_slug")
    if not quest_slug:
        return JsonResponse({"error": "quest_slug required"}, status=400)

    claimable_quests = {quest["slug"]: quest for quest in _quest_progress_payload(identity, profile)}
    quest_state = claimable_quests.get(quest_slug)
    if quest_state is None:
        return JsonResponse({"error": "Quest not found"}, status=404)
    if quest_state["status"] not in {"claimable", "complete"}:
        return JsonResponse({"error": "Quest requirements not met"}, status=409)

    quest = get_object_or_404(Quest, slug=quest_slug)
    progress, _created = QuestProgress.objects.get_or_create(profile=profile, quest=quest)
    if progress.status != "complete":
        progress.status = "complete"
        progress.completed_at = timezone.now()
        progress.progress_data = {"progress": quest_state["progress"], "target": quest_state["target"]}
        progress.save(update_fields=["status", "completed_at", "progress_data"])

    return JsonResponse({"ok": True, "quest_slug": quest_slug})


def partial_neocities_modal(request: HttpRequest) -> HttpResponse:
    return render(request, "game/partials/neocities_modal.html")


def game_credits(request: HttpRequest) -> HttpResponse:
    return render(request, "game/credits.html")
