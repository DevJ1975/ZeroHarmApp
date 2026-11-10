from django.contrib import admin, messages
from django.db.models import Count, Q
from django.utils import timezone

from .generate import generate_week, next_week
from .models import MondayComment, MondayFeedback, MondayMinute, MondayTopic


@admin.register(MondayTopic)
class MondayTopicAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "active", "paused_reason", "times_used", "updated_at")
    list_filter = ("active", "category")
    search_fields = ("title", "slug", "hazard")
    actions = ("pause", "resume")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n=Count("talks", filter=Q(talks__status=MondayMinute.READY)))

    @admin.display(description="Used", ordering="n")
    def times_used(self, obj):
        return obj.n

    @admin.action(description="Pause the selected topics")
    def pause(self, request, queryset):
        queryset.update(active=False, paused_reason="Paused in the admin")

    @admin.action(description="Resume the selected topics")
    def resume(self, request, queryset):
        queryset.update(active=True, paused_reason="")


class FeedbackInline(admin.TabularInline):
    model = MondayFeedback
    extra = 0
    can_delete = False
    fields = ("helpful", "reasons", "note", "platform", "created_at")
    readonly_fields = fields


@admin.register(MondayMinute)
class MondayMinuteAdmin(admin.ModelAdmin):
    list_display = ("week", "title", "topic", "status", "attempts", "ups", "downs", "unsafe", "comments_count")
    list_filter = ("status", "topic__category")
    readonly_fields = ("check_log", "model", "attempts", "push_sent_at", "created_at")
    inlines = [FeedbackInline]
    actions = ("pull", "restore", "write_next_week")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("topic").annotate(
            u=Count("feedback", filter=Q(feedback__helpful=True), distinct=True),
            d=Count("feedback", filter=Q(feedback__helpful=False), distinct=True),
            c=Count("comments", filter=Q(comments__status=MondayComment.VISIBLE), distinct=True),
        )

    @admin.display(description="👍", ordering="u")
    def ups(self, obj):
        return obj.u

    @admin.display(description="👎", ordering="d")
    def downs(self, obj):
        return obj.d

    @admin.display(description="Not safe / not right")
    def unsafe(self, obj):
        return sum(1 for r in obj.feedback.filter(helpful=False).values_list("reasons", flat=True) if "unsafe" in (r or []))

    @admin.display(description="Comments", ordering="c")
    def comments_count(self, obj):
        return obj.c

    @admin.action(description="Pull the selected talks from the app")
    def pull(self, request, queryset):
        queryset.update(status=MondayMinute.PULLED)

    @admin.action(description="Restore the selected talks (only if they passed the checks)")
    def restore(self, request, queryset):
        queryset.filter(status=MondayMinute.PULLED).update(status=MondayMinute.READY)

    @admin.action(description="Write next week's Monday Minute now")
    def write_next_week(self, request, queryset):
        week = next_week()
        try:
            m = generate_week(week)
        except Exception as err:
            self.message_user(request, f"Could not write it: {err}", messages.ERROR)
            return
        if m is None:
            self.message_user(request, f"{week:%b %-d} already has a Monday Minute, or both topic tries are used up.")
        else:
            self.message_user(request, f"{week:%b %-d}: {m.get_status_display()} ({m.topic}). Open it to read the check log.")


@admin.register(MondayComment)
class MondayCommentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "display_name", "short", "minute", "status", "report_count", "moderation")
    list_filter = ("status",)
    search_fields = ("body", "display_name")
    readonly_fields = ("minute", "parent", "install_hash", "report_count", "created_at")
    actions = ("hide", "show")

    @admin.display(description="Comment")
    def short(self, obj):
        return obj.body[:80]

    @admin.action(description="Hide the selected comments")
    def hide(self, request, queryset):
        queryset.update(status=MondayComment.HIDDEN, moderation="Hidden in the admin")

    @admin.action(description="Show the selected comments")
    def show(self, request, queryset):
        queryset.update(status=MondayComment.VISIBLE, moderation="")
