from django.contrib import admin

from .models import Harvest


@admin.register(Harvest)
class HarvestAdmin(admin.ModelAdmin):
    list_display = ["identity", "title", "url", "micropub_posted", "harvested_at"]
    list_filter = ["micropub_posted"]
    search_fields = ["url", "title", "note", "tags", "identity__username"]
    raw_id_fields = ["identity"]
