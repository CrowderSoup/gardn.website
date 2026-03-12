from __future__ import annotations

from django.contrib import admin

from .models import GameProfile, GardenPlot, Quest, QuestProgress


@admin.register(GameProfile)
class GameProfileAdmin(admin.ModelAdmin):
    list_display = ("identity", "map_id", "tile_x", "tile_y", "tutorial_step", "links_harvested")
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
