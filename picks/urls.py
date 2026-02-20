from django.urls import path

from .views import pick_view, unpick_view

urlpatterns = [
    path("pick/<slug:username>/", pick_view, name="pick"),
    path("unpick/<slug:username>/", unpick_view, name="unpick"),
]
