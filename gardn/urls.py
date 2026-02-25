from django.contrib import admin
from django.urls import include, path

from plants.views import (
    account_settings_view,
    dashboard_view,
    delete_account_view,
    export_data_view,
    home_view,
    profile_settings_view,
    user_profile_view,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home_view, name="home"),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("u/<slug:username>/", user_profile_view, name="user_profile"),
    path("settings/", account_settings_view, name="account_settings"),
    path("settings/profile/", profile_settings_view, name="profile_settings"),
    path("settings/account/delete/", delete_account_view, name="delete_account"),
    path("settings/export/", export_data_view, name="export_data"),
    path("", include("indieauth_client.urls")),
    path("", include("plants.urls")),
    path("", include("picks.urls")),
    path("", include("embeds.urls")),
    path("", include("harvests.urls")),
    path("mastodon/", include("mastodon_auth.urls")),
]
