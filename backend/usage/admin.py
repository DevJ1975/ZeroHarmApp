from django.contrib import admin

from .models import AppOpen


@admin.register(AppOpen)
class AppOpenAdmin(admin.ModelAdmin):
    """Look, don't touch: rows come from phones and are cleared by usage_prune."""
    list_display = ("day", "platform", "app_version", "city", "region", "country", "source")
    list_filter = ("day", "country", "platform")
    date_hierarchy = "day"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
