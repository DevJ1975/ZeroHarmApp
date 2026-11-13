import re

from django.contrib import admin, messages
from django.utils import timezone

from . import alerts
from .models import CrashReport, Ticket

NUMBER = re.compile(r"(?:zh-?|#)?\s*([0-9]{1,15})", re.I)  # "ZH-12", "zh12", "#12" or "12" in the search box


class CrashReportInline(admin.StackedInline):
    """The newest reports of this crash, as the phones sent them. Look, don't touch."""
    model = CrashReport
    extra = 0
    max_num = 0
    can_delete = False
    fields = ("created_at", "fatal", "name", "message", "stack", "screen", "app_version", "platform", "os_version", "device")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    """Problems people reported, OTIS answers they flagged, and crashes the app reported by itself. Change the
    status, write a reply or keep a private note. Only on a problem report does the person see the reply (in the app,
    under My reports); on a flagged answer or a crash the reply is a private note they never see. The rest came from
    a phone and stays as it was sent."""
    list_display = ("number", "kind", "status", "title", "count", "app_version", "platform", "last_seen")
    list_display_links = ("number", "title")
    list_filter = ("status", "kind", "source", "platform", "app_version")
    search_fields = ("title", "text", "email", "name", "question", "answer")
    date_hierarchy = "last_seen"
    actions = ("mark_in_progress", "mark_fixed", "mark_closed", "send_to_ghl")
    inlines = (CrashReportInline,)
    fieldsets = (
        (None, {"fields": ("number", "kind", "source", "status", "reply", "owner_note")}),
        ("What was sent", {"fields": ("title", "text", "question", "answer", "model_key", "name", "email", "may_contact")}),
        ("The phone", {"fields": ("app_version", "platform", "os_version", "device", "screen", "lang", "install_hash")}),
        ("How often", {"fields": ("count", "first_seen", "last_seen", "alerted_count")}),
        ("Emails and GoHighLevel", {"fields": ("owner_alerted_at", "owner_alert_unsure_at", "ghl_contact_id", "ghl_tagged_at", "ghl_noted_at")}),
        ("Dates", {"fields": ("created_at", "updated_at", "closed_at")}),
    )
    # Everything but the three things the owner works with. The counts and stamps are kept by the server: typing in
    # them would send an email twice or hide a crash from the next one.
    readonly_fields = ("number", "kind", "source", "title", "text", "question", "answer", "model_key", "name", "email", "may_contact",
                       "app_version", "platform", "os_version", "device", "screen", "lang", "install_hash", "count", "first_seen",
                       "last_seen", "alerted_count", "owner_alerted_at", "owner_alert_unsure_at", "ghl_contact_id", "ghl_tagged_at", "ghl_noted_at",
                       "created_at", "updated_at", "closed_at")

    @admin.display(description="Number", ordering="id")
    def number(self, obj):
        return obj.number

    def has_add_permission(self, request):
        return False  # tickets come from phones

    def get_search_results(self, request, queryset, search_term):
        """Also finds a ticket by its number, typed the way the person or the email says it: ZH-12."""
        found, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        match = NUMBER.fullmatch(search_term.strip())
        if match:
            found = found | queryset.filter(pk=int(match.group(1)))
        return found, may_have_duplicates

    def get_form(self, request, obj=None, change=False, **kwargs):
        """The reply box says plainly whether the person will ever see what is typed in it."""
        form = super().get_form(request, obj, change=change, **kwargs)
        reply = form.base_fields.get("reply")
        if reply is not None and obj is not None:
            reply.help_text = ("The person sees this in the app under My reports." if obj.kind == Ticket.PROBLEM else
                               "Private note. The person never sees a reply on a flagged OTIS answer or a crash. Write to them by email instead, if they gave one.")
        return form

    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)
        fields = [name for name in ("reply", "owner_note") if name in form.changed_data]
        if "status" in form.changed_data:
            wanted, obj.status = obj.status, form.initial.get("status", obj.status)
            obj.set_status(wanted)  # keeps closed_at in step with the status
            fields += ["status", "closed_at"]
        # Only what the owner changed of the three things they work with. A full save would put back the count,
        # last_seen and the email stamps as they were when the form was opened, undoing crash reports and cron work
        # that landed in between; and writing an unchanged status would close again a ticket a crash report had
        # just opened.
        if fields:
            obj.save(update_fields=[*fields, "updated_at"])

    def _mark(self, request, queryset, status, word):
        now, n = timezone.now(), 0
        for ticket in queryset.exclude(status=status):
            ticket.set_status(status, now)
            ticket.save(update_fields=["status", "closed_at", "updated_at"])
            n += 1
        self.message_user(request, f"{n} marked {word}." if n else f"Those were already {word}.", messages.SUCCESS)

    @admin.action(description="Mark in progress")
    def mark_in_progress(self, request, queryset):
        self._mark(request, queryset, Ticket.IN_PROGRESS, "in progress")

    @admin.action(description="Mark fixed")
    def mark_fixed(self, request, queryset):
        self._mark(request, queryset, Ticket.FIXED, "fixed")

    @admin.action(description="Mark closed")
    def mark_closed(self, request, queryset):
        self._mark(request, queryset, Ticket.CLOSED, "closed")

    @admin.action(description="Try GoHighLevel again (reporters who said it is OK to reply)")
    def send_to_ghl(self, request, queryset):
        asked = [t for t in queryset if alerts.wants_contact(t)]
        done = sum(alerts.sync_contact(t) for t in asked)
        if not asked:
            self.message_user(request, "None of those has an email with OK to reply, so there is nobody to add to GoHighLevel.", messages.WARNING)
        elif done == len(asked):
            self.message_user(request, f"{done} in GoHighLevel, tagged {alerts.TAG} with a note.", messages.SUCCESS)
        else:
            self.message_user(request, f"{done} of {len(asked)} are in GoHighLevel. The rest failed; the web service log says why.", messages.ERROR)
