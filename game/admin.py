from __future__ import annotations

from django.contrib import admin

from .models import (
    GameProfile,
    GardenDecoration,
    GardenPlot,
    GroveMessage,
    GrovePresence,
    Quest,
    QuestProgress,
)


@admin.register(GameProfile)
class GameProfileAdmin(admin.ModelAdmin):
    list_display = (
        "identity",
        "garden_name",
        "gate_state",
        "homestead_level",
        "map_id",
        "tile_x",
        "tile_y",
        "tutorial_step",
        "links_harvested",
    )
    search_fields = ("identity__username", "identity__me_url")
    readonly_fields = ("created_at", "updated_at")


@admin.register(GardenPlot)
class GardenPlotAdmin(admin.ModelAdmin):
    list_display = ("profile", "slot_x", "slot_y", "plant_type", "growth_stage", "link_url")
    search_fields = ("profile__identity__username",)


@admin.register(Quest)
class QuestAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "category", "order")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(QuestProgress)
class QuestProgressAdmin(admin.ModelAdmin):
    list_display = ("profile", "quest", "status", "started_at", "completed_at")
    list_filter = ("status",)


@admin.register(GardenDecoration)
class GardenDecorationAdmin(admin.ModelAdmin):
    list_display = ("profile", "slot_key", "decor_key", "variant_key", "updated_at")
    search_fields = ("profile__identity__username", "decor_key", "slot_key")


@admin.register(GrovePresence)
class GrovePresenceAdmin(admin.ModelAdmin):
    list_display = ("identity", "current_map", "last_seen_at")
    search_fields = ("identity__username", "identity__display_name")


@admin.register(GroveMessage)
class GroveMessageAdmin(admin.ModelAdmin):
    list_display = ("identity", "content", "is_moderated", "moderated_reason", "created_at")
    list_filter = ("is_moderated",)
    search_fields = ("identity__username", "content")
