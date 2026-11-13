from django.contrib import admin

from .models import RegChange, RegChunk, RegSection


class ChunkInline(admin.TabularInline):
    model = RegChunk
    extra = 0
    fields = ("label", "appendix", "text")
    readonly_fields = fields
    can_delete = False


@admin.register(RegSection)
class RegSectionAdmin(admin.ModelAdmin):
    list_display = ("section", "heading", "as_of", "fetched_at")
    search_fields = ("section", "heading")
    readonly_fields = ("section", "heading", "text_hash", "as_of", "fetched_at")
    inlines = [ChunkInline]

    def has_add_permission(self, request):
        # Sections come from the eCFR sync (regs_sync). Every field is read-only, so the Add page had nothing to
        # fill in and could only end in a server error.
        return False


@admin.register(RegChange)
class RegChangeAdmin(admin.ModelAdmin):
    list_display = ("section", "as_of", "detected_at", "reviewed")
    list_filter = ("reviewed",)
    readonly_fields = ("section", "as_of", "detected_at", "old_hash", "new_hash", "paused")

    def has_add_permission(self, request):
        return False  # written by the sync when OSHA amends a section; the Add page could only end in a server error
