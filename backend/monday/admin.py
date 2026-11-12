import logging
import re
import threading
from datetime import timedelta

from django.contrib import admin, messages
from django.db import connection
from django.db.models import Count, Q
from django.utils import timezone

from . import eval_runner
from .ai import available as ai_available, ensure_model, is_local
from .generate import due_week, generate_week, is_late, next_week
from .models import MondayComment, MondayEvalRun, MondayFeedback, MondayLock, MondayMinute, MondayTopic

log = logging.getLogger(__name__)


def _ai_missing() -> str:
    """Why the AI can't be used at all, or "" when it is set up. Asked before any background work is promised."""
    if ai_available():
        return ""
    return f"{'LOCAL_AI_URL' if is_local() else 'ANTHROPIC_API_KEY'} is not set, so there is no AI to run this on. Nothing was started."


def _in_background(work):
    """Runs work() in a thread of this web process, because it takes longer than a web request may. A deploy or
    restart of the web service stops it. Raises if the thread cannot start, so the caller can say so."""
    def run():
        try:
            work()
        except Exception:  # nobody is waiting on this thread: without this the reason would be lost
            log.exception("Background work started in the admin failed")
        finally:
            connection.close()

    threading.Thread(target=run, daemon=True).start()


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
        topics = list(queryset[:12])
        missing = _ai_missing()
        if missing:
            self.message_user(request, missing, messages.ERROR)
            return
        # Taken here, not in the background, so a second click is refused and told why.
        if not eval_runner.claim():
            self.message_user(request, "A safety test is already running, so a second one was not started. Watch it under Monday Minute "
                                       "safety test runs. If the server restarted while it ran, it is marked as failed within "
                                       f"{eval_runner.STALE_AFTER.seconds // 60} minutes and you can start again.", messages.ERROR)
            return
        try:
            _in_background(lambda: eval_runner.run_eval(topics, claimed=True))
        except Exception as err:
            eval_runner.release()
            self.message_user(request, f"Could not start the safety test: {err}", messages.ERROR)
            return
        self.message_user(request, f"Safety test started on {len(topics)} topic(s). Results appear under Monday Minute safety test runs. "
                                   "On the local model this can take a few hours. It runs inside the web server: a deploy or restart "
                                   "stops it, and the run is then marked as failed. Only a run that includes all the default topics "
                                   "counts toward the safety gate; smaller runs are exploratory.")

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
    # gate_pending is the gate's own note to itself (set when a talk is written, cleared when it goes out): shown, not typed.
    readonly_fields = ("check_log", "model", "attempts", "push_sent_at", "approved_by_person", "gate_pending", "created_at")
    inlines = [FeedbackInline]
    actions = ("approve", "pull", "restore", "write_next_week")

    def get_queryset(self, request):
        # The same three small counts the app's list uses. This list used to join ratings and comments to the talk
        # and count distinct ids, which makes the database build ratings x comments rows per talk before counting.
        return super().get_queryset(request).select_related("topic").with_counts()

    @admin.display(description="👍", ordering="_up")
    def ups(self, obj):
        return obj._up

    @admin.display(description="👎", ordering="_down")
    def downs(self, obj):
        return obj._down

    @admin.display(description="Not safe / not right")
    def unsafe(self, obj):
        return sum(1 for r in obj.feedback.filter(helpful=False).values_list("reasons", flat=True) if "unsafe" in (r or []))

    @admin.display(description="Comments", ordering="_comments")
    def comments_count(self, obj):
        return obj._comments

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
        # Only talks that are in the app or waiting for approval. A blocked draft is not in the app, and pulling it
        # used to make it look like a talk that could be restored.
        pulled = queryset.filter(status__in=[MondayMinute.READY, MondayMinute.HELD]).update(status=MondayMinute.PULLED)
        left = queryset.count() - pulled
        self.message_user(request, f"Pulled {pulled} talk(s)." + (f" {left} left alone: only published talks and talks waiting for "
                                                                  "approval can be pulled." if left else ""))

    @admin.action(description="Restore the selected talks (only if they passed the checks)")
    def restore(self, request, queryset):
        candidates = list(queryset.filter(status=MondayMinute.PULLED))
        passed = [m.pk for m in candidates if _passed_the_checks(m)]
        restored = MondayMinute.objects.filter(pk__in=passed, status=MondayMinute.PULLED).update(status=MondayMinute.READY, approved_by_person=True)
        refused = len(candidates) - restored
        self.message_user(request, f"Restored {restored} talk(s)." + (f" {refused} stayed pulled: no talk text, or no passed safety "
                                                                      "check in the check log. If it was a blocked draft, open it "
                                                                      "and set its status back to Blocked." if refused else ""),
                          messages.WARNING if refused else messages.SUCCESS)

    @admin.action(description="Write next week's Monday Minute now")
    def write_next_week(self, request, queryset):
        # The same week the cron step would write. That is next Monday's talk, except from Monday 5:00 AM to
        # Wednesday 5:00 AM while this week's was never written: then this week's is still owed and goes out as soon
        # as it is written. Writing next week's then left the owed week to the cron alone.
        week = due_week() or next_week()
        late = is_late(week)
        missing = _ai_missing()
        if missing:
            self.message_user(request, missing, messages.ERROR)
            return
        # One writer at a time, whichever AI writes it. The lock is taken here, not in the background, so a second
        # click (or the cron) is refused and told why. On Claude this used to take no lock at all: a second click or
        # a cron run during the write paid for a second talk that the database then refused to save.
        if not MondayLock.acquire("write"):
            self.message_user(request, f"{week:%b %-d} is still being written by an earlier click or the cron, so nothing new was started. "
                                       "If the web server restarted while it was writing, that run's lock frees itself; try again later.", messages.ERROR)
            return
        owed = f" This week's talk was never written, so {week:%b %-d} is the one being written; it goes out as soon as it passes." if late else ""
        if is_local():
            # On CPU this takes minutes to an hour, longer than a web request may run: do it in the background.
            user_id = request.user.pk

            def write():
                try:
                    if not ensure_model():
                        _note(user_id, f"Monday Minute {week:%b %-d}: not written, the local model is still downloading. Try again later.")
                        return
                    m = generate_week(week, late=late)
                    if m is None:
                        _note(user_id, f"Monday Minute {week:%b %-d}: nothing written. It already has a talk, or both topic tries are used up.")
                    else:
                        _note(user_id, f"Monday Minute {week:%b %-d}: {m.get_status_display()} ({m.topic})", m)
                except Exception as err:
                    log.exception("Monday Minute %s: writing in the background failed", week)
                    _note(user_id, f"Monday Minute {week:%b %-d}: could not write it ({err})")
                finally:
                    MondayLock.release("write")

            try:
                _in_background(write)
            except Exception as err:
                MondayLock.release("write")
                self.message_user(request, f"Could not start writing {week:%b %-d}: {err}", messages.ERROR)
                return
            self.message_user(request, f"Writing {week:%b %-d} on the local model in the background. Refresh this page in a few minutes. "
                                       "How it ended, a failure included, shows under Recent actions on the admin home page. "
                                       "A deploy or restart of the web server stops it; the cron then writes it on a later run." + owed)
            return
        try:
            m = generate_week(week, late=late)
        except Exception as err:
            self.message_user(request, f"Could not write it: {err}", messages.ERROR)
            return
        finally:
            MondayLock.release("write")
        if m is None:
            self.message_user(request, f"{week:%b %-d} already has a Monday Minute, or both topic tries are used up.")
        else:
            self.message_user(request, f"{week:%b %-d}: {m.get_status_display()} ({m.topic}). Open it to read the check log." + owed)


def _passed_the_checks(m) -> bool:
    """Whether a pulled talk may go back in the app: it has its text, and its check log shows a draft that passed.
    A blocked draft is stored without text and without a pass, so this is what keeps one from being published."""
    has_text = bool(m.title.strip() and m.intro.strip() and m.points)
    return has_text and bool(re.search(r"^Attempt \d+: passed ", m.check_log, re.MULTILINE))


def _note(user_id, text, minute=None):
    """Leaves the result of background work where the owner can see it: Recent actions on the admin home page
    (and the talk's History when there is a talk). Without it a failure in the background shows nowhere."""
    from django.contrib.admin.models import CHANGE, LogEntry
    from django.contrib.contenttypes.models import ContentType

    try:
        LogEntry.objects.create(user_id=user_id, content_type=ContentType.objects.get_for_model(MondayMinute),
                                object_id=minute.pk if minute else None, object_repr=text[:200], action_flag=CHANGE,
                                change_message="Written in the background from the admin.")
    except Exception:
        log.exception("Could not record: %s", text)


@admin.register(MondayComment)
class MondayCommentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "display_name", "short", "minute", "status", "report_count", "moderation")
    list_filter = ("status",)
    search_fields = ("body", "display_name")
    # screen_failures is counted by the AI check (api._screen); typing a number in would hide or un-hide a comment by accident.
    readonly_fields = ("minute", "parent", "install_hash", "report_count", "screen_failures", "created_at")
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

    def has_add_permission(self, request):
        return False  # comments come from the app; the talk and the phone they belong to can't be typed in here


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

    def get_queryset(self, request):
        # The list and each run's page both come through here. A run whose server process was stopped by a deploy
        # or restart is marked as failed first, so the page never shows it as still running.
        eval_runner.close_stale_runs()
        return super().get_queryset(request)
