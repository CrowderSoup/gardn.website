from __future__ import annotations

import json
import re
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from harvests.models import Harvest
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
from .models import (
    GardenDecoration,
    GardenVisit,
    GameProfile,
    GardenPlot,
    GroveMessage,
    GrovePresence,
    NeighborLink,
    Quest,
    QuestProgress,
    SiteScan,
    VerifiedActivity,
)
from .tasks import verify_published_activity

READ_LATER_TAG_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
GROVE_PRESENCE_WINDOW = timedelta(seconds=45)
GROVE_MESSAGE_LIMIT = 40
GROVE_MESSAGE_RATE_LIMIT = timedelta(seconds=5)
LIBRARY_PAGE_SIZE = 8
RECENT_LIBRARY_PAGE_SIZE = 6

APPEARANCE_SKIN_TONES = [
    {"key": "porcelain", "label": "Porcelain", "color": "#f5d9c7"},
    {"key": "sunset", "label": "Sunset", "color": "#e0b196"},
    {"key": "olive", "label": "Olive", "color": "#bf9c74"},
    {"key": "amber", "label": "Amber", "color": "#9f6a45"},
    {"key": "umbral", "label": "Umbral", "color": "#6c4734"},
]
APPEARANCE_OUTFITS = [
    {"key": "starter", "label": "Starter Kit", "description": "A practical launch-day outfit."},
]
HOMESTEAD_PATH_OPTIONS = [
    {"key": "stone", "label": "Stone Path", "min_level": 1},
    {"key": "clover", "label": "Clover Path", "min_level": 2},
    {"key": "sunbaked", "label": "Sunbaked Clay", "min_level": 2},
]
HOMESTEAD_FENCE_OPTIONS = [
    {"key": "split_rail", "label": "Split Rail", "min_level": 1},
    {"key": "hedge", "label": "Hedge Border", "min_level": 2},
    {"key": "woven", "label": "Woven Fence", "min_level": 2},
]
DECOR_OPTIONS = [
    {"key": "lantern", "label": "Lantern", "min_level": 1},
    {"key": "bench", "label": "Bench", "min_level": 1},
    {"key": "birdbath", "label": "Birdbath", "min_level": 1},
    {"key": "planter", "label": "Planter", "min_level": 1},
    {"key": "trellis", "label": "Trellis", "min_level": 3},
    {"key": "signpost", "label": "Signpost", "min_level": 3},
    {"key": "archway", "label": "Archway", "min_level": 4},
    {"key": "stone_lantern", "label": "Stone Lantern", "min_level": 4},
]
DECOR_SLOT_LABELS = {
    GardenDecoration.SLOT_NORTH_WEST: "Northwest",
    GardenDecoration.SLOT_NORTH_EAST: "Northeast",
    GardenDecoration.SLOT_SOUTH_WEST: "Southwest",
    GardenDecoration.SLOT_SOUTH_EAST: "Southeast",
    GardenDecoration.SLOT_SIGNPOST: "Signpost",
}


def _grove_chat_enabled() -> bool:
    return bool(getattr(settings, "GARDN_GROVE_CHAT_ENABLED", True))


def _default_garden_name(identity: UserIdentity) -> str:
    base = (identity.display_name or identity.username or "Gardner").strip()
    if not base:
        return "My Gardn"
    if "gardn" in base.lower():
        return base[:80]
    return f"{base}'s Gardn"[:80]


def _json_body(request: HttpRequest) -> dict[str, object]:
    if not request.body:
        return {}
    return json.loads(request.body)


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
    update_fields: list[str] = []
    if identity.login_method == "indieauth" and not profile.has_website:
        profile.has_website = True
        update_fields.append("has_website")
    if not profile.garden_name:
        profile.garden_name = _default_garden_name(identity)
        update_fields.append("garden_name")
    if update_fields:
        profile.save(update_fields=update_fields)
    return profile


def _appearance_options_payload() -> dict[str, object]:
    return {
        "body_styles": [
            {"key": key, "label": label}
            for key, label in GameProfile.BODY_STYLE_CHOICES
        ],
        "skin_tones": APPEARANCE_SKIN_TONES,
        "outfits": APPEARANCE_OUTFITS,
    }


def _appearance_payload(profile: GameProfile) -> dict[str, object]:
    return {
        "configured": profile.appearance_configured,
        "body_style": profile.body_style,
        "skin_tone": profile.skin_tone,
        "outfit_key": profile.outfit_key,
        "options": _appearance_options_payload(),
    }


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
    profile = _get_profile(identity)
    return {
        "username": identity.username,
        "display_name": identity.display_name or identity.username,
        "garden_name": profile.garden_name,
        "garden_url": _garden_share_url(identity),
    }


def _completed_quest_count(profile: GameProfile) -> int:
    return QuestProgress.objects.filter(profile=profile, status="complete").count()


def _calculate_homestead_level(identity: UserIdentity, profile: GameProfile) -> int:
    verified_count = VerifiedActivity.objects.filter(
        identity=identity,
        kind__in=ENTRY_ACTIVITY_KINDS,
        status=VerifiedActivity.STATUS_VERIFIED,
    ).count()
    completed_quests = _completed_quest_count(profile)

    if verified_count >= 10 and completed_quests >= 4:
        return 4
    if verified_count >= 5 and completed_quests >= 2:
        return 3
    if verified_count >= 2 or completed_quests >= 1:
        return 2
    return 1


def _sync_homestead_level(identity: UserIdentity, profile: GameProfile) -> int:
    level = _calculate_homestead_level(identity, profile)
    if profile.homestead_level != level:
        profile.homestead_level = level
        profile.save(update_fields=["homestead_level"])
    return level


def _allowed_decoration_slots(profile: GameProfile) -> list[dict[str, object]]:
    slots = [
        {"key": GardenDecoration.SLOT_NORTH_WEST, "label": DECOR_SLOT_LABELS[GardenDecoration.SLOT_NORTH_WEST]},
        {"key": GardenDecoration.SLOT_NORTH_EAST, "label": DECOR_SLOT_LABELS[GardenDecoration.SLOT_NORTH_EAST]},
    ]
    if profile.homestead_level >= 3:
        slots.extend([
            {"key": GardenDecoration.SLOT_SOUTH_WEST, "label": DECOR_SLOT_LABELS[GardenDecoration.SLOT_SOUTH_WEST]},
            {"key": GardenDecoration.SLOT_SOUTH_EAST, "label": DECOR_SLOT_LABELS[GardenDecoration.SLOT_SOUTH_EAST]},
            {"key": GardenDecoration.SLOT_SIGNPOST, "label": DECOR_SLOT_LABELS[GardenDecoration.SLOT_SIGNPOST]},
        ])
    return slots


def _available_decor_options(profile: GameProfile) -> list[dict[str, object]]:
    return [
        option for option in DECOR_OPTIONS
        if option["min_level"] <= profile.homestead_level
    ]


def _homestead_payload(profile: GameProfile) -> dict[str, object]:
    decorations = list(profile.decorations.order_by("slot_key"))
    return {
        "garden_name": profile.garden_name,
        "gate_state": profile.gate_state,
        "homestead_level": profile.homestead_level,
        "path_style": profile.path_style,
        "fence_style": profile.fence_style,
        "read_later_tag": profile.read_later_tag,
        "available_slots": _allowed_decoration_slots(profile),
        "decor_options": _available_decor_options(profile),
        "decorations": [
            {
                "slot_key": decoration.slot_key,
                "slot_label": DECOR_SLOT_LABELS.get(decoration.slot_key, decoration.slot_key),
                "decor_key": decoration.decor_key,
                "variant_key": decoration.variant_key,
            }
            for decoration in decorations
        ],
    }


def _library_base_queryset(identity: UserIdentity):
    return Harvest.objects.filter(identity=identity).order_by("-harvested_at")


def _library_summary_payload(identity: UserIdentity, profile: GameProfile) -> dict[str, object]:
    harvests = _library_base_queryset(identity)
    read_later_tag = profile.read_later_tag
    return {
        "total_count": harvests.count(),
        "recent_count": min(RECENT_LIBRARY_PAGE_SIZE, harvests.count()),
        "read_later_count": harvests.filter(tags__icontains=read_later_tag).count(),
        "read_later_tag": read_later_tag,
    }


def _serialize_harvest(harvest: Harvest) -> dict[str, object]:
    return {
        "id": harvest.id,
        "url": harvest.url,
        "title": harvest.title,
        "note": harvest.note,
        "tags": harvest.tags_list(),
        "harvested_at": harvest.harvested_at.isoformat(),
    }


def _library_payload(identity: UserIdentity, profile: GameProfile, *, view: str = "recent", q: str = "", page: int = 1) -> dict[str, object]:
    queryset = _library_base_queryset(identity)
    if q:
        queryset = queryset.filter(
            Q(title__icontains=q)
            | Q(url__icontains=q)
            | Q(note__icontains=q)
            | Q(tags__icontains=q)
        )
    if view == "read_later":
        queryset = queryset.filter(tags__icontains=profile.read_later_tag)

    page_size = RECENT_LIBRARY_PAGE_SIZE if view == "recent" else LIBRARY_PAGE_SIZE
    if view == "recent":
        queryset = queryset[:18]

    total_count = queryset.count() if hasattr(queryset, "count") else len(queryset)
    total_pages = max(1, ((total_count - 1) // page_size) + 1) if total_count else 1
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    items = list(queryset[start:end])

    return {
        "view": view,
        "query": q,
        "page": page,
        "page_size": page_size,
        "total_count": total_count,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "items": [_serialize_harvest(harvest) for harvest in items],
        "summary": _library_summary_payload(identity, profile),
    }


def _padd_badges_payload(
    identity: UserIdentity,
    profile: GameProfile,
    *,
    pending_inventory_count: int,
    quests: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "seeds": pending_inventory_count,
        "library": _library_summary_payload(identity, profile)["read_later_count"],
        "quests": len([quest for quest in quests if quest["status"] == "claimable"]),
        "neighbors": NeighborLink.objects.filter(identity=identity).count(),
        "profile": 0 if profile.appearance_configured else 1,
    }


def _serialize_presence(presence: GrovePresence, viewer: UserIdentity | None = None) -> dict[str, object]:
    profile = _get_profile(presence.identity)
    return {
        "username": presence.identity.username,
        "display_name": presence.identity.display_name or presence.identity.username,
        "garden_name": profile.garden_name,
        "appearance": {
            "body_style": profile.body_style,
            "skin_tone": profile.skin_tone,
            "outfit_key": profile.outfit_key,
        },
        "is_self": bool(viewer and viewer.id == presence.identity_id),
        "last_seen_at": presence.last_seen_at.isoformat(),
    }


def _active_grove_presences(viewer: UserIdentity | None = None) -> list[dict[str, object]]:
    threshold = timezone.now() - GROVE_PRESENCE_WINDOW
    presences = GrovePresence.objects.filter(
        current_map="neighbors",
        last_seen_at__gte=threshold,
    ).select_related("identity").order_by("identity__username")
    return [_serialize_presence(presence, viewer) for presence in presences]


def _serialize_grove_message(message: GroveMessage) -> dict[str, object]:
    return {
        "id": message.id,
        "username": message.identity.username,
        "display_name": message.identity.display_name or message.identity.username,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


def _grove_summary_payload(identity: UserIdentity | None = None) -> dict[str, object]:
    return {
        "chat_enabled": _grove_chat_enabled(),
        "active_count": len(_active_grove_presences(identity)),
        "recent_message_count": GroveMessage.objects.filter(is_moderated=False).count(),
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
    if not NeighborLink.objects.filter(identity=viewer, target_identity=host).exists():
        return False
    host_profile = _get_profile(host)
    if host_profile.gate_state != GameProfile.GATE_OPEN:
        return False
    return True


def _garden_visit_block_reason(viewer: UserIdentity, host: UserIdentity) -> str:
    if viewer.id == host.id:
        return ""
    if not NeighborLink.objects.filter(identity=viewer, target_identity=host).exists():
        return "Pick this gardener and rescan your site before you can visit their garden."
    if _get_profile(host).gate_state != GameProfile.GATE_OPEN:
        return "This gardener has closed their gate for now."
    return ""


def _guest_garden_state(viewer: UserIdentity, host: UserIdentity) -> dict[str, object]:
    profile = _get_profile(host)
    _sync_homestead_level(host, profile)
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
        "appearance": _appearance_payload(profile),
        "homestead": _homestead_payload(profile),
        "gate_state": profile.gate_state,
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
    _sync_homestead_level(identity, profile)
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
    quests = _quest_progress_payload(identity, profile)

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
            "appearance_configured": profile.appearance_configured,
        },
        "owner": _garden_owner_payload(identity),
        "appearance": _appearance_payload(profile),
        "homestead": _homestead_payload(profile),
        "gate_state": profile.gate_state,
        "capabilities": scan.capabilities,
        "site_status": _site_status_payload(scan),
        "garden_health": garden_health,
        "garden": _garden_payload(profile, recent_verified_count, recent_visitor_count),
        "verified_inventory": [serialize_activity(activity) for activity in verified_inventory],
        "pending_inventory": [serialize_activity(activity) for activity in pending_inventory],
        "neighbors": [serialize_neighbor(link) for link in neighbors],
        "quests": quests,
        "library_summary": _library_summary_payload(identity, profile),
        "padd_badges": _padd_badges_payload(
            identity,
            profile,
            pending_inventory_count=len(pending_inventory),
            quests=quests,
        ),
        "grove": _grove_summary_payload(identity),
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


@require_GET
def playwright_login(request: HttpRequest) -> HttpResponse:
    if not getattr(settings, "ALLOW_PLAYWRIGHT_LOGIN", False):
        raise Http404()

    username = (request.GET.get("username") or "playwright").strip().lower()
    username = re.sub(r"[^a-z0-9-]+", "-", username).strip("-")[:64] or "playwright"
    me_url = f"https://{username}.example/"
    identity, _created = UserIdentity.objects.get_or_create(
        username=username,
        defaults={
            "me_url": me_url,
            "display_name": username.replace("-", " ").title(),
            "login_method": "indieauth",
        },
    )
    if identity.me_url != me_url:
        identity.me_url = me_url
        identity.save(update_fields=["me_url", "updated_at"])

    profile = _get_profile(identity)
    profile.map_id = (request.GET.get("map") or profile.map_id or "overworld").strip()[:32] or "overworld"
    profile.tutorial_step = max(0, min(9, int(request.GET.get("tutorial") or 9)))
    profile.has_website = True
    profile.appearance_configured = True
    profile.tile_x = int(request.GET.get("tile_x") or profile.tile_x or 8)
    profile.tile_y = int(request.GET.get("tile_y") or profile.tile_y or 8)
    profile.save(update_fields=[
        "map_id",
        "tutorial_step",
        "has_website",
        "appearance_configured",
        "tile_x",
        "tile_y",
        "updated_at",
    ])
    get_or_create_site_scan(identity)

    request.session["identity_id"] = identity.id
    request.session["website_verified"] = True
    return redirect(request.GET.get("next") or "/game/")


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
    block_reason = _garden_visit_block_reason(identity, host)
    if block_reason:
        return JsonResponse(
            {"error": block_reason},
            status=403,
        )
    return JsonResponse(_guest_garden_state(identity, host))


@require_POST
def api_record_garden_visit(request: HttpRequest, username: str) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    host = get_object_or_404(UserIdentity, username=username)
    block_reason = _garden_visit_block_reason(identity, host)
    if block_reason:
        return JsonResponse(
            {"error": block_reason},
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

    data = _json_body(request)
    profile = _get_profile(identity)
    profile.map_id = data.get("map_id", profile.map_id)
    profile.tile_x = data.get("tile_x", profile.tile_x)
    profile.tile_y = data.get("tile_y", profile.tile_y)
    profile.save(update_fields=["map_id", "tile_x", "tile_y"])
    GrovePresence.objects.update_or_create(
        identity=identity,
        defaults={"current_map": profile.map_id},
    )
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

    data = _json_body(request)
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
def api_update_profile(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    data = _json_body(request)
    profile = _get_profile(identity)
    update_fields: list[str] = []
    valid_body_styles = {key for key, _label in GameProfile.BODY_STYLE_CHOICES}
    valid_skin_tones = {option["key"] for option in APPEARANCE_SKIN_TONES}
    valid_outfits = {option["key"] for option in APPEARANCE_OUTFITS}

    if "body_style" in data:
        body_style = str(data.get("body_style", "")).strip()
        if body_style not in valid_body_styles:
            return JsonResponse({"error": "Invalid body_style"}, status=400)
        profile.body_style = body_style
        update_fields.append("body_style")

    if "skin_tone" in data:
        skin_tone = str(data.get("skin_tone", "")).strip()
        if skin_tone not in valid_skin_tones:
            return JsonResponse({"error": "Invalid skin_tone"}, status=400)
        profile.skin_tone = skin_tone
        update_fields.append("skin_tone")

    if "outfit_key" in data:
        outfit_key = str(data.get("outfit_key", "")).strip()
        if outfit_key not in valid_outfits:
            return JsonResponse({"error": "Invalid outfit_key"}, status=400)
        profile.outfit_key = outfit_key
        update_fields.append("outfit_key")

    if "read_later_tag" in data:
        read_later_tag = str(data.get("read_later_tag", "")).strip().lower()
        if not READ_LATER_TAG_RE.match(read_later_tag):
            return JsonResponse({"error": "read_later_tag must be 1-64 chars of a-z, 0-9, - or _"}, status=400)
        profile.read_later_tag = read_later_tag
        update_fields.append("read_later_tag")

    if update_fields or data.get("appearance_configured"):
        if not profile.appearance_configured:
            profile.appearance_configured = True
            update_fields.append("appearance_configured")
        profile.save(update_fields=sorted(set(update_fields)))

    return JsonResponse(
        {
            "ok": True,
            "appearance": _appearance_payload(profile),
            "homestead": _homestead_payload(profile),
            "library_summary": _library_summary_payload(identity, profile),
        }
    )


@require_POST
def api_update_homestead(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    data = _json_body(request)
    profile = _get_profile(identity)
    _sync_homestead_level(identity, profile)
    update_fields: list[str] = []

    if "garden_name" in data:
        garden_name = str(data.get("garden_name", "")).strip()
        if not garden_name:
            return JsonResponse({"error": "garden_name required"}, status=400)
        profile.garden_name = garden_name[:80]
        update_fields.append("garden_name")

    if "gate_state" in data:
        gate_state = str(data.get("gate_state", "")).strip()
        valid_gate_states = {key for key, _label in GameProfile.GATE_STATE_CHOICES}
        if gate_state not in valid_gate_states:
            return JsonResponse({"error": "Invalid gate_state"}, status=400)
        profile.gate_state = gate_state
        update_fields.append("gate_state")

    if "path_style" in data:
        path_style = str(data.get("path_style", "")).strip()
        valid_paths = {option["key"]: option for option in HOMESTEAD_PATH_OPTIONS}
        if path_style not in valid_paths:
            return JsonResponse({"error": "Invalid path_style"}, status=400)
        if valid_paths[path_style]["min_level"] > profile.homestead_level:
            return JsonResponse({"error": "That path style unlocks later"}, status=409)
        profile.path_style = path_style
        update_fields.append("path_style")

    if "fence_style" in data:
        fence_style = str(data.get("fence_style", "")).strip()
        valid_fences = {option["key"]: option for option in HOMESTEAD_FENCE_OPTIONS}
        if fence_style not in valid_fences:
            return JsonResponse({"error": "Invalid fence_style"}, status=400)
        if valid_fences[fence_style]["min_level"] > profile.homestead_level:
            return JsonResponse({"error": "That fence style unlocks later"}, status=409)
        profile.fence_style = fence_style
        update_fields.append("fence_style")

    if update_fields:
        profile.save(update_fields=sorted(set(update_fields)))

    return JsonResponse({"ok": True, "homestead": _homestead_payload(profile), "gate_state": profile.gate_state})


@require_POST
def api_update_garden_decoration(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    data = _json_body(request)
    profile = _get_profile(identity)
    _sync_homestead_level(identity, profile)
    slot_key = str(data.get("slot_key", "")).strip()
    decor_key = str(data.get("decor_key", "")).strip()
    variant_key = str(data.get("variant_key", "")).strip()
    allowed_slots = {slot["key"] for slot in _allowed_decoration_slots(profile)}
    if slot_key not in allowed_slots:
        return JsonResponse({"error": "That decor slot is not unlocked"}, status=409)

    if not decor_key:
        profile.decorations.filter(slot_key=slot_key).delete()
        return JsonResponse({"ok": True, "homestead": _homestead_payload(profile)})

    decor_options = {option["key"]: option for option in _available_decor_options(profile)}
    if decor_key not in decor_options:
        return JsonResponse({"error": "That decor item is not unlocked"}, status=409)

    GardenDecoration.objects.update_or_create(
        profile=profile,
        slot_key=slot_key,
        defaults={"decor_key": decor_key, "variant_key": variant_key[:32]},
    )
    return JsonResponse({"ok": True, "homestead": _homestead_payload(profile)})


@require_GET
def api_library(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    profile = _get_profile(identity)
    view = request.GET.get("view", "recent").strip() or "recent"
    if view not in {"recent", "all", "read_later"}:
        return JsonResponse({"error": "Invalid library view"}, status=400)
    query = request.GET.get("q", "").strip()
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return JsonResponse({"error": "Invalid page"}, status=400)
    return JsonResponse(_library_payload(identity, profile, view=view, q=query, page=page))


@require_GET
def api_grove_presence(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err
    return JsonResponse({"ok": True, "presences": _active_grove_presences(identity), "grove": _grove_summary_payload(identity)})


@require_POST
def api_grove_presence_heartbeat(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    profile = _get_profile(identity)
    data = _json_body(request)
    current_map = str(data.get("current_map", profile.map_id or "overworld")).strip() or "overworld"
    GrovePresence.objects.update_or_create(identity=identity, defaults={"current_map": current_map})
    return JsonResponse({"ok": True, "presences": _active_grove_presences(identity), "grove": _grove_summary_payload(identity)})


@require_GET
def api_grove_messages(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err
    del identity
    if not _grove_chat_enabled():
        return JsonResponse({"ok": True, "enabled": False, "messages": []})
    messages = list(
        GroveMessage.objects.filter(is_moderated=False)
        .select_related("identity")[:GROVE_MESSAGE_LIMIT]
    )
    return JsonResponse(
        {
            "ok": True,
            "enabled": True,
            "messages": [_serialize_grove_message(message) for message in reversed(messages)],
        }
    )


@require_POST
def api_post_grove_message(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err
    if not _grove_chat_enabled():
        return JsonResponse({"error": "Neighbor Grove chat is currently disabled"}, status=503)

    profile = _get_profile(identity)
    data = _json_body(request)
    current_map = str(data.get("current_map", profile.map_id or "")).strip()
    if current_map != "neighbors" and profile.map_id != "neighbors":
        return JsonResponse({"error": "You need to be in Neighbor Grove to chat"}, status=409)

    content = str(data.get("content", "")).strip()
    if not content:
        return JsonResponse({"error": "Message content required"}, status=400)
    if len(content) > GroveMessage._meta.get_field("content").max_length:
        return JsonResponse({"error": "Message too long"}, status=400)

    last_message = GroveMessage.objects.filter(identity=identity).order_by("-created_at").first()
    if last_message and (timezone.now() - last_message.created_at) < GROVE_MESSAGE_RATE_LIMIT:
        return JsonResponse({"error": "You are sending messages too quickly"}, status=429)

    GrovePresence.objects.update_or_create(identity=identity, defaults={"current_map": "neighbors"})
    message = GroveMessage.objects.create(identity=identity, content=content)
    messages = list(
        GroveMessage.objects.filter(is_moderated=False)
        .select_related("identity")[:GROVE_MESSAGE_LIMIT]
    )
    return JsonResponse(
        {
            "ok": True,
            "message": _serialize_grove_message(message),
            "messages": [_serialize_grove_message(item) for item in reversed(messages)],
        }
    )


@require_POST
def api_publish_bookmark(request: HttpRequest) -> JsonResponse:
    identity, err = _require_identity(request)
    if err:
        return err

    micropub_endpoint = request.session.get("micropub_endpoint", "")
    access_token = request.session.get("access_token", "")
    if not micropub_endpoint or not access_token:
        return JsonResponse({"error": "Micropub is not available for this account"}, status=400)

    data = _json_body(request)
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

    data = _json_body(request)
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

    data = _json_body(request)
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
        data = _json_body(request)
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

    data = _json_body(request)
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
