from django.urls import path

from .views import embed_plant_view, embed_roll_view, gardn_js_view, plant_json_view, roll_json_view

urlpatterns = [
    path("embed/<slug:username>/plant/", embed_plant_view, name="embed_plant"),
    path("embed/<slug:username>/roll/", embed_roll_view, name="embed_roll"),
    path("api/<slug:username>/plant.json", plant_json_view, name="plant_json"),
    path("api/<slug:username>/roll.json", roll_json_view, name="roll_json"),
    path("gardn.js", gardn_js_view, name="gardn_js"),
]
