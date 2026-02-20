from django.urls import path

from .views import mastodon_callback, mastodon_login_start, verify_website_view

urlpatterns = [
    path("login/", mastodon_login_start, name="mastodon_login"),
    path("callback/", mastodon_callback, name="mastodon_callback"),
    path("verify-website/", verify_website_view, name="mastodon_verify_website"),
]
