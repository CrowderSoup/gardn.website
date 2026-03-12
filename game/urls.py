from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("", views.game_index, name="game_index"),
    path("credits/", views.game_credits, name="game_credits"),
    path("api/state/", views.api_game_state, name="api_game_state"),
    path("api/site-status/", views.api_site_status, name="api_site_status"),
    path("api/scan/", views.api_scan_site, name="api_scan_site"),
    path("api/save/", views.api_save_position, name="api_save_position"),
    path("api/harvest/", views.api_harvest_link, name="api_harvest_link"),
    path("api/plant/", views.api_plant_seed, name="api_plant_seed"),
    path("api/harvests/", views.api_unplanted_harvests, name="api_unplanted_harvests"),
    path("api/publish/bookmark/", views.api_publish_bookmark, name="api_publish_bookmark"),
    path("api/publish/note/", views.api_publish_note, name="api_publish_note"),
    path("api/quest/complete/", views.api_complete_quest, name="api_complete_quest"),
    path("api/tutorial/advance/", views.api_advance_tutorial, name="api_advance_tutorial"),
    path("partials/neocities-modal/", views.partial_neocities_modal, name="partial_neocities_modal"),
]
