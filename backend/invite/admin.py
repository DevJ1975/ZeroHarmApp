from django.contrib import admin

from .models import InviteClick


@admin.register(InviteClick)
class InviteClickAdmin(admin.ModelAdmin):
    """Look, don't touch: rows come from taps on the invite link."""
    list_display = ("day", "contact_id", "platform", "tagged_at", "contact_missing")
    list_filter = ("day", "platform", "contact_missing")
    search_fields = ("contact_id",)
    date_hierarchy = "day"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
