from django.contrib import admin
from django.urls import include, path

from plants.views import dashboard_view, home_view, profile_settings_view, user_profile_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home_view, name="home"),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("u/<slug:username>/", user_profile_view, name="user_profile"),
    path("settings/profile/", profile_settings_view, name="profile_settings"),
    path("", include("indieauth_client.urls")),
    path("", include("plants.urls")),
    path("", include("picks.urls")),
    path("", include("embeds.urls")),
    path("", include("harvests.urls")),
    path("mastodon/", include("mastodon_auth.urls")),
]
