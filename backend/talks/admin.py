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


from django.utils import timezone as _tz

from .ghl_sync import sync_year
from .integrations import send_feed_push, sync_sheet_to_ghl
from .models import FeedItem, GhlSync, SigninSheet
from .translate import draft_spanish


def _draft_spanish(modeladmin, request, queryset):
    for talk in queryset:
        try:
            draft_spanish(talk)
            modeladmin.message_user(request, f"Issue {talk.issue}: Spanish drafted. Review it, then approve.")
        except Exception as err:
            modeladmin.message_user(request, f"Issue {talk.issue}: {err}", messages.ERROR)


def _approve_spanish(modeladmin, request, queryset):
    ready = queryset.exclude(body_md_es="").exclude(title_es="")
    n = ready.update(spanish_status="approved")
    modeladmin.message_user(request, f"Approved Spanish for {n} talk(s). The Español button now shows for them.")


_draft_spanish.short_description = "Draft Spanish translation (needs review)"
_approve_spanish.short_description = "Approve Spanish (show the Español button)"
ToolboxTalkAdmin.actions = ("send_push_now", _draft_spanish, _approve_spanish)
ToolboxTalkAdmin.list_display = ("issue", "number", "title", "issue_date", "send_at", "published", "needs_review", "spanish_status", "push_sent_at")
ToolboxTalkAdmin.list_filter = ("month_theme", "published", "needs_review", "spanish_status")
ToolboxTalkAdmin.readonly_fields = ("push_sent_at", "updated_at", "ghl_synced_at", "review_flags")
ToolboxTalkAdmin.fieldsets = (
    (None, {"fields": ("issue", "number", "title", "story_title", "month_theme", "crew_question")}),
    ("Talk text and files", {"fields": ("body_md", "hero_url", "pdf_url")}),
    ("Review", {"fields": ("needs_review", "review_flags", "ghl_synced_at"),
                "description": "Synced issues with [bracketed] pre-send flags are held. Fix the template in GHL and sync again, or untick Needs review once it is checked."}),
    ("Español", {"fields": ("spanish_status", "title_es", "story_title_es", "crew_question_es", "body_md_es")}),
    ("Schedule", {"fields": ("issue_date", "send_at", "published", "push_sent_at", "ghl_template_id", "updated_at")}),
)


@admin.register(FeedItem)
class FeedItemAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "jurisdiction", "publish_at", "published", "featured", "send_push", "push_sent_at")
    list_filter = ("kind", "jurisdiction", "published", "featured")
    search_fields = ("title", "summary", "external_id")
    readonly_fields = ("push_sent_at", "created_at", "updated_at")
    actions = ("push_now",)

    @admin.action(description="Send the push for selected items now")
    def push_now(self, request, queryset):
        for item in queryset:
            ok, detail = send_feed_push(item)
            self.message_user(request, f"{item.title}: {'sent' if ok else detail}", messages.SUCCESS if ok else messages.ERROR)


@admin.register(GhlSync)
class GhlSyncAdmin(admin.ModelAdmin):
    list_display = ("year", "status", "requested_by", "created_at", "finished_at")
    readonly_fields = ("status", "log", "requested_by", "created_at", "finished_at")
    fields = ("year", "status", "log", "requested_by", "created_at", "finished_at")
    actions = ("run_now",)

    @admin.action(description="Run the selected syncs now")
    def run_now(self, request, queryset):
        for job in queryset:
            job.log = "\n".join(sync_year(job.year))
            job.status, job.finished_at = "done", _tz.now()
            job.save()
            self.message_user(request, f"{job.year}: done. Open it to read the log.")


@admin.register(SigninSheet)
class SigninSheetAdmin(admin.ModelAdmin):
    list_display = ("held_on", "talk_title", "supervisor_email", "attendee_count", "has_group_photo", "status")
    list_filter = ("status", "has_group_photo")
    search_fields = ("supervisor_email", "talk_title", "company")
    readonly_fields = [f.name for f in SigninSheet._meta.fields if f.name != "pdf"]
    actions = ("retry",)

    @admin.action(description="Retry saving to GoHighLevel")
    def retry(self, request, queryset):
        n = sum(sync_sheet_to_ghl(s) for s in queryset.exclude(status="synced"))
        self.message_user(request, f"Saved {n} sheet(s) to GoHighLevel.")
