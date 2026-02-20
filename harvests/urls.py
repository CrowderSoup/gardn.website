from django.urls import path

from . import views

urlpatterns = [
    path("harvest/", views.harvest_view, name="harvest"),
    path("harvest/bookmarklet/", views.bookmarklet_view, name="harvest_bookmarklet"),
    path("harvest/<int:harvest_id>/delete/", views.harvest_delete_view, name="harvest_delete"),
]
