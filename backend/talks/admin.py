from django.contrib import admin, messages

from .integrations import send_talk_push, sync_signup_to_ghl
from .models import AppSignup, ToolboxTalk


@admin.register(ToolboxTalk)
class ToolboxTalkAdmin(admin.ModelAdmin):
    list_display = ("issue", "title", "month_theme", "issue_date", "send_at", "published", "has_text", "push_sent_at")
    list_filter = ("month_theme", "published")
    search_fields = ("title", "story_title", "crew_question")
    readonly_fields = ("push_sent_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("issue", "title", "story_title", "month_theme", "crew_question")}),
        ("Talk text and files", {"fields": ("body_md", "hero_url", "pdf_url")}),
        ("Schedule", {"fields": ("issue_date", "send_at", "published", "push_sent_at", "ghl_template_id", "updated_at")}),
    )
    actions = ("send_push_now",)

    @admin.display(boolean=True, description="Text added")
    def has_text(self, obj):
        return bool(obj.body_md)

    @admin.action(description="Send the push for selected talks now")
    def send_push_now(self, request, queryset):
        for talk in queryset:
            ok, detail = send_talk_push(talk)
            level = messages.SUCCESS if ok else messages.ERROR
            self.message_user(request, f"Issue {talk.issue}: {'sent' if ok else detail}", level)


@admin.register(AppSignup)
class AppSignupAdmin(admin.ModelAdmin):
    list_display = ("email", "first_name", "company", "wants_offers", "created_at", "ghl_synced_at")
    list_filter = ("wants_offers",)
    search_fields = ("email", "company")
    readonly_fields = ("ghl_contact_id", "ghl_synced_at", "created_at")
    actions = ("sync_to_ghl",)

    @admin.action(description="Sync selected sign-ups to GoHighLevel")
    def sync_to_ghl(self, request, queryset):
        synced = sum(sync_signup_to_ghl(s) for s in queryset)
        self.message_user(request, f"Synced {synced} of {queryset.count()} to GoHighLevel.")
