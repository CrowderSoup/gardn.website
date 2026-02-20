from django.urls import path

from .views import plant_svg_view

urlpatterns = [
    path("u/<slug:username>/plant.svg", plant_svg_view, name="plant_svg"),
]
