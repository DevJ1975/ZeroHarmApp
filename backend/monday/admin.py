from datetime import timedelta

from django.contrib import admin, messages
from django.db.models import Count, Q
from django.utils import timezone

from .ai import ensure_model, is_local
from .generate import generate_week, next_week
from .models import MondayComment, MondayCommentBan, MondayEvalRun, MondayFeedback, MondayLock, MondayMinute, MondayTopic


@admin.register(MondayTopic)
class MondayTopicAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "active", "paused_reason", "times_used", "updated_at")
    list_filter = ("active", "category")
    search_fields = ("title", "slug", "hazard")
    actions = ("pause", "resume", "safety_test")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n=Count("talks", filter=Q(talks__status=MondayMinute.READY)))

    @admin.action(description="Run the safety test on the selected topics (with and without RAG)")
    def safety_test(self, request, queryset):
        import threading

        from django.db import connection

        from .eval_runner import run_eval

        topics = list(queryset[:12])

        def go():
            try:
                run_eval(topics)
            finally:
                connection.close()

        threading.Thread(target=go, daemon=True).start()
        self.message_user(request, f"Safety test started on {len(topics)} topic(s). Results appear under Monday Minute safety test runs. "
                                   "On the local model this can take a few hours. Only a run that includes all the default topics counts toward "
                                   "the safety gate; smaller runs are exploratory.")

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
    readonly_fields = ("check_log", "model", "attempts", "push_sent_at", "approved_by_person", "created_at")
    inlines = [FeedbackInline]
    actions = ("approve", "pull", "restore", "write_next_week")

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

    @admin.action(description="Approve and publish the selected talks that are waiting for approval")
    def approve(self, request, queryset):
        now = timezone.now()
        held = list(queryset.filter(status=MondayMinute.HELD).order_by("-week", "-pk"))
        # Only the newest talk may notify, and only if it is for this week or next. Older ones publish quietly, so
        # approving a backlog doesn't send a push for each.
        current_week = next_week(now) - timedelta(days=7)
        notify = 0
        for i, m in enumerate(held):
            m.status, m.approved_by_person = MondayMinute.READY, True
            if i == 0 and m.week >= current_week:
                if m.publish_at < now:
                    m.publish_at = now  # publish now, and the cron still sends the Monday push
                notify += m.push_sent_at is None
            elif m.push_sent_at is None:
                m.push_sent_at = now  # marks the push as handled so the cron skips it
            m.save(update_fields=["status", "approved_by_person", "publish_at", "push_sent_at"])
        self.message_user(request, f"Approved {len(held)} talk(s). {notify} will send a push notification; older talks publish quietly. "
                                   "Only talks waiting for approval are changed.")

    @admin.action(description="Pull the selected talks from the app")
    def pull(self, request, queryset):
        queryset.update(status=MondayMinute.PULLED)

    @admin.action(description="Restore the selected talks (only if they passed the checks)")
    def restore(self, request, queryset):
        queryset.filter(status=MondayMinute.PULLED).update(status=MondayMinute.READY, approved_by_person=True)

    @admin.action(description="Write next week's Monday Minute now")
    def write_next_week(self, request, queryset):
        week = next_week()
        if is_local():
            # On CPU this takes minutes to an hour, longer than a web request may run: do it in the background.
            import threading

            from django.db import connection

            def run():
                try:
                    if MondayLock.acquire("write"):
                        try:
                            ensure_model() and generate_week(week)
                        finally:
                            MondayLock.release("write")
                finally:
                    connection.close()

            threading.Thread(target=run, daemon=True).start()
            self.message_user(request, f"Writing {week:%b %-d} on the local model in the background. Refresh this page in a few minutes.")
            return
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
    actions = ("hide", "hide_and_ban", "show")

    @admin.display(description="Comment")
    def short(self, obj):
        return obj.body[:80]

    @admin.action(description="Hide the selected comments")
    def hide(self, request, queryset):
        queryset.update(status=MondayComment.HIDDEN, moderation="Hidden in the admin")

    @admin.action(description="Hide and stop the poster from commenting")
    def hide_and_ban(self, request, queryset):
        hashes = set(queryset.values_list("install_hash", flat=True))
        for h in hashes:
            MondayCommentBan.objects.get_or_create(install_hash=h, defaults={"reason": "Banned from the comment admin"})
        # Everything they posted comes down with them, not only the selected comments.
        hidden = MondayComment.objects.filter(install_hash__in=hashes).exclude(status=MondayComment.HIDDEN).update(
            status=MondayComment.HIDDEN, moderation="Hidden in the admin: poster banned")
        self.message_user(request, f"Stopped {len(hashes)} poster(s) from commenting and hid {hidden} of their comments.")

    @admin.action(description="Show the selected comments")
    def show(self, request, queryset):
        queryset.update(status=MondayComment.VISIBLE, moderation="")


@admin.register(MondayCommentBan)
class MondayCommentBanAdmin(admin.ModelAdmin):
    """Delete a row here to let that phone comment again."""
    list_display = ("created_at", "install_hash", "reason")
    readonly_fields = ("install_hash", "created_at")

    def has_add_permission(self, request):
        return False  # bans come from the comment list: select comments, then "Hide and stop the poster from commenting"


@admin.register(MondayEvalRun)
class MondayEvalRunAdmin(admin.ModelAdmin):
    list_display = ("created_at", "model", "rag", "strict", "status", "conclusive", "passed", "caught", "wrongly_blocked", "progress")
    list_filter = ("passed", "conclusive", "status", "model")
    readonly_fields = ("created_at", "finished_at", "model", "rag", "strict", "topics", "status", "progress", "conclusive", "passed", "verdict",
                       "catch_rate", "false_block_rate", "summary", "results")

    @admin.display(description="Caught")
    def caught(self, obj):
        return f"{obj.catch_rate:.0%}" if obj.catch_rate is not None else "–"

    @admin.display(description="Good talks blocked")
    def wrongly_blocked(self, obj):
        return f"{obj.false_block_rate:.0%}" if obj.false_block_rate is not None else "–"

    def has_add_permission(self, request):
        return False  # start one from the topics list: select topics, then "Run the safety test"
