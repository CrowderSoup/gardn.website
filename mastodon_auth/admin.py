from django.contrib import admin

from .models import MastodonApp


@admin.register(MastodonApp)
class MastodonAppAdmin(admin.ModelAdmin):
    list_display = ["instance_url", "client_id", "created_at"]
    search_fields = ["instance_url"]
