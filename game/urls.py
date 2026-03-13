from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("", views.game_index, name="game_index"),
    path("playwright-login/", views.playwright_login, name="playwright_login"),
    path("gardens/<slug:username>/", views.shared_garden_index, name="shared_garden_index"),
    path("credits/", views.game_credits, name="game_credits"),
    path("api/state/", views.api_game_state, name="api_game_state"),
    path("api/gardens/<slug:username>/", views.api_public_garden_state, name="api_public_garden_state"),
    path("api/gardens/<slug:username>/visit/", views.api_record_garden_visit, name="api_record_garden_visit"),
    path("api/site-status/", views.api_site_status, name="api_site_status"),
    path("api/scan/", views.api_scan_site, name="api_scan_site"),
    path("api/save/", views.api_save_position, name="api_save_position"),
    path("api/profile/", views.api_update_profile, name="api_update_profile"),
    path("api/homestead/", views.api_update_homestead, name="api_update_homestead"),
    path("api/homestead/decor/", views.api_update_garden_decoration, name="api_update_garden_decoration"),
    path("api/library/", views.api_library, name="api_library"),
    path("api/grove/presence/", views.api_grove_presence, name="api_grove_presence"),
    path("api/grove/presence/heartbeat/", views.api_grove_presence_heartbeat, name="api_grove_presence_heartbeat"),
    path("api/grove/messages/", views.api_grove_messages, name="api_grove_messages"),
    path("api/grove/messages/post/", views.api_post_grove_message, name="api_post_grove_message"),
    path("api/harvest/", views.api_harvest_link, name="api_harvest_link"),
    path("api/plant/", views.api_plant_seed, name="api_plant_seed"),
    path("api/harvests/", views.api_unplanted_harvests, name="api_unplanted_harvests"),
    path("api/publish/bookmark/", views.api_publish_bookmark, name="api_publish_bookmark"),
    path("api/publish/note/", views.api_publish_note, name="api_publish_note"),
    path("api/quest/complete/", views.api_complete_quest, name="api_complete_quest"),
    path("api/tutorial/advance/", views.api_advance_tutorial, name="api_advance_tutorial"),
    path("partials/neocities-modal/", views.partial_neocities_modal, name="partial_neocities_modal"),
]
