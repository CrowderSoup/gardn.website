from django.urls import path

from .views import auth_callback_view, login_start_view, logout_view

urlpatterns = [
    path("login/", login_start_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("auth/callback/", auth_callback_view, name="auth_callback"),
]
