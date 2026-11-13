"""Monday Minute: a weekly AI-written toolbox talk, separate from Zero Harm Weekly.

Every week the generator picks one topic from the CSP-reviewed topic bank, writes a talk from that topic's brief only,
checks it (hard rules plus an AI safety review in the CSP role) and publishes it Monday at 5:00 AM Pacific. Crews rate
each talk and discuss it in comments; reports from crews can pull a talk and pause its topic automatically.
"""
import logging
import threading
import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone

log = logging.getLogger(__name__)

PULL_AT_UNSAFE_REPORTS = 3     # "isn't safe or isn't right" reports, from different networks, that pull a talk and pause its topic
HIDE_AT_COMMENT_REPORTS = 2    # reports that hide a comment until someone looks

# The write lock (MondayLock). A run that holds it says "still here" every LOCK_BEAT_SECONDS; a lock nobody has
# refreshed for LOCK_TTL belongs to a run that was killed (a deploy stops the container mid-write) and is taken over.
LOCK_TTL = timedelta(minutes=5)
LOCK_BEAT_SECONDS = 60
LOCK_MAX_HOLD = timedelta(hours=4)  # a run that is alive but stuck stops refreshing after this, so it cannot hold the lock for ever
# One lock is meant to outlast LOCK_MAX_HOLD: the safety test's ("eval"). eval_runner refreshes that row itself, by
# name, for as long as the test works, because a full test on CPU can take longer than four hours.


class MondayTopic(models.Model):
    """One topic brief. The writer may use only what is in here, so keep it accurate and reviewed."""

    slug = models.SlugField(max_length=60, unique=True)
    title = models.CharField(max_length=120)
    category = models.CharField(max_length=40)
    months = models.JSONField(default=list, blank=True, help_text="Months this topic fits best (1-12). Empty = any time.")
    hazard = models.TextField()
    key_points = models.JSONField(default=list)
    must_say = models.JSONField(default=list, help_text="Lines every talk on this topic must include word for word")
    never_say = models.JSONField(default=list, help_text="Things the writer must never say on this topic")
    facts = models.JSONField(default=list, help_text='[{"text": ..., "cite": "1910.147"}], checked against the eCFR')
    story_seed = models.TextField(blank=True)
    crew_questions = models.JSONField(default=list)
    references = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    paused_reason = models.CharField(max_length=200, blank=True, help_text="Why this topic is paused. Clear it and tick Active to use it again.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "title"]
        verbose_name = "Monday Minute topic"

    def __str__(self):
        return self.title

    def brief(self):
        return {k: getattr(self, k) for k in ("title", "hazard", "key_points", "must_say", "never_say", "facts", "story_seed", "crew_questions", "references")}


class MondayMinuteQuerySet(models.QuerySet):
    def due(self, now=None):
        """Ready and past its publish time. Not the same as out: see released()."""
        return self.filter(status=MondayMinute.READY, publish_at__lte=now or timezone.now())

    def released(self):
        """Talks that are out in the app. A talk the safety gate let through when it was written (gate_pending) is
        not out until the gate has been checked once more at its publish time (gate.release_due), unless a person
        approved it."""
        return self.due().filter(models.Q(gate_pending=False) | models.Q(approved_by_person=True))

    def with_counts(self):
        """Thumbs and comment counts in the same query, so a list of talks doesn't run three more queries per talk.
        Each count is its own small subquery. Joining ratings and comments to the talk and counting distinct ids made
        the database build ratings x comments rows for every talk first: seconds per request at a few thousand ratings."""
        from django.db.models import Count, IntegerField, OuterRef, Subquery
        from django.db.models.functions import Coalesce

        def count(rows):
            per_talk = rows.filter(minute=OuterRef("pk")).order_by().values("minute").annotate(n=Count("pk")).values("n")
            return Coalesce(Subquery(per_talk, output_field=IntegerField()), 0)

        return self.annotate(
            _up=count(MondayFeedback.objects.filter(helpful=True)),
            _down=count(MondayFeedback.objects.filter(helpful=False)),
            _comments=count(MondayComment.objects.filter(status=MondayComment.VISIBLE)),
        )


class MondayMinute(models.Model):
    READY, BLOCKED, PULLED, HELD = "ready", "blocked", "pulled", "held"
    STATUSES = [(READY, "Ready / published"), (BLOCKED, "Blocked by the safety checks"), (PULLED, "Pulled after crew reports"),
                (HELD, "Waiting for approval (AI not qualified yet)")]

    week = models.DateField(help_text="The Monday this talk is for")
    publish_at = models.DateTimeField(help_text="Monday 5:00 AM Pacific")
    topic = models.ForeignKey(MondayTopic, on_delete=models.PROTECT, related_name="talks")
    title = models.CharField(max_length=120, blank=True)
    intro = models.TextField(blank=True)
    points = models.JSONField(default=list, blank=True)
    story_title = models.CharField(max_length=120, blank=True)
    story = models.TextField(blank=True)
    crew_question = models.TextField(blank=True)
    takeaway = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=BLOCKED)
    attempts = models.PositiveSmallIntegerField(default=0)
    check_log = models.TextField(blank=True, help_text="What the hard checks and the safety review said, attempt by attempt")
    model = models.CharField(max_length=60, blank=True)
    push_sent_at = models.DateTimeField(null=True, blank=True)
    approved_by_person = models.BooleanField(default=False, help_text="A person approved or restored this talk in the admin, so the safety gate leaves it alone")
    gate_pending = models.BooleanField(default=False, db_default=False, help_text="The safety gate let this talk through when it was written. It is checked once more at the moment the talk goes out, and the talk is not shown until then")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = MondayMinuteQuerySet.as_manager()

    class Meta:
        ordering = ["-week"]
        verbose_name = "Monday Minute"
        indexes = [models.Index(fields=["status", "publish_at"], name="mm_released")]
        # One talk a week, whoever writes it: two writers finishing together used to give two talks and two pushes.
        # Drafts the safety checks blocked don't count (a week may have two of those, one per topic tried).
        constraints = [models.UniqueConstraint(fields=["week"], condition=~models.Q(status="blocked"), name="one_talk_per_week")]

    def __str__(self):
        return f"{self.week:%Y-%m-%d} · {self.title or self.topic.title} ({self.status})"

    def as_api(self):
        if hasattr(self, "_up"):
            up, down, comments = self._up, self._down, self._comments
        else:
            up = self.feedback.filter(helpful=True).count()
            down = self.feedback.filter(helpful=False).count()
            comments = self.comments.filter(status=MondayComment.VISIBLE).count()
        return {
            "id": self.pk, "week": self.week.isoformat(), "published_at": self.publish_at.isoformat(),
            "topic": self.topic.title, "category": self.topic.category, "title": self.title, "intro": self.intro,
            "points": self.points, "story_title": self.story_title, "story": self.story, "crew_question": self.crew_question,
            "takeaway": self.takeaway, "references": self.topic.references, "thumbs_up": up, "thumbs_down": down,
            "comment_count": comments,
        }


class MondayFeedback(models.Model):
    """Thumbs up or down from a phone. One per phone per talk (the phone's random install id, stored hashed)."""

    REASONS = [("unsafe", "Something in it isn't safe or isn't right"), ("not_my_site", "Doesn't fit my site"),
               ("confusing", "Confusing"), ("too_long", "Too long"), ("too_basic", "Too basic")]
    minute = models.ForeignKey(MondayMinute, on_delete=models.CASCADE, related_name="feedback")
    install_hash = models.CharField(max_length=64)
    helpful = models.BooleanField()
    reasons = models.JSONField(default=list, blank=True)
    note = models.CharField(max_length=300, blank=True, help_text="Optional detail sent with a thumbs down")
    platform = models.CharField(max_length=10, blank=True)
    network_hash = models.CharField(max_length=64, blank=True, help_text="Hashed network address, so one connection can't pull a talk alone")
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["minute", "install_hash"], name="one_vote_per_phone")]
        verbose_name = "Monday Minute rating"

    def __str__(self):
        return f"{'👍' if self.helpful else '👎'} {self.minute}"


class MondayComment(models.Model):
    """A crew comment or reply, shown to everyone once moderation passes."""

    VISIBLE, PENDING, HIDDEN = "visible", "pending", "hidden"
    STATUSES = [(VISIBLE, "Visible"), (PENDING, "Waiting for moderation"), (HIDDEN, "Hidden")]
    minute = models.ForeignKey(MondayMinute, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies")
    display_name = models.CharField(max_length=40, default="Crew member")
    body = models.TextField(max_length=500)
    install_hash = models.CharField(max_length=64, help_text="Hashed random id of the phone, for blocking and limits. Not a person.")
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    moderation = models.CharField(max_length=300, blank=True, help_text="Why moderation hid it, if it did")
    report_count = models.PositiveSmallIntegerField(default=0)
    report_alerted_at = models.DateTimeField(null=True, blank=True, help_text="When the owner was emailed about the first report")
    screen_failures = models.PositiveSmallIntegerField(default=0, db_default=0, help_text="Times the AI check could not give an answer for this comment. After a few it is hidden for a person to look at")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Monday Minute comment"
        indexes = [models.Index(fields=["minute", "status", "created_at"], name="mm_comments")]

    def __str__(self):
        return f"{self.display_name}: {self.body[:60]}"


class MondayCommentReport(models.Model):
    comment = models.ForeignKey(MondayComment, on_delete=models.CASCADE, related_name="reports")
    install_hash = models.CharField(max_length=64)
    reason = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["comment", "install_hash"], name="one_report_per_phone")]


class MondayCommentBan(models.Model):
    """A phone that may no longer comment. Set from the comment admin ("Hide and stop the poster from commenting")."""

    install_hash = models.CharField(max_length=64, unique=True)
    reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Monday Minute comment ban"

    def __str__(self):
        return f"Ban {self.install_hash[:8]} ({self.created_at:%b %-d, %Y})"


class MondayLock(models.Model):
    """Keeps two runs from writing the same week at once. On CPU a talk can take longer than the cron interval.

    The lock has an owner and a heartbeat. acquire() starts a small background thread that refreshes locked_at every
    LOCK_BEAT_SECONDS for as long as this process holds the lock. If the process is killed (every deploy stops the
    container, and no `finally` runs then) the refreshing stops with it and the next run takes the lock over once it is
    LOCK_TTL old: minutes, where a fixed 4-hour expiry used to block writing for the rest of the evening.
    release() only frees a lock this process holds, so a run that finishes late can't free another run's lock."""

    name = models.CharField(max_length=40, primary_key=True)
    locked_at = models.DateTimeField(help_text="Last time the run holding the lock said it was still working")
    owner = models.CharField(max_length=40, blank=True, db_default="", help_text="Random id of the run holding the lock")

    _held = {}                      # lock name -> (owner id, stop signal) for the locks this process holds
    _held_guard = threading.Lock()

    @classmethod
    def acquire(cls, name: str, ttl=None) -> bool:
        from django.db import transaction

        ttl = ttl or LOCK_TTL  # a killed run frees the lock after this
        now = timezone.now()
        owner = uuid.uuid4().hex
        with transaction.atomic():
            lock, created = cls.objects.select_for_update().get_or_create(name=name, defaults={"locked_at": now, "owner": owner})
            if not created:
                if lock.locked_at > now - ttl:
                    return False
                lock.locked_at, lock.owner = now, owner
                lock.save()
        cls._start_heartbeat(name, owner)
        return True

    @classmethod
    def release(cls, name: str):
        """Frees the lock if this process holds it. Does nothing otherwise: the row then belongs to another run."""
        with cls._held_guard:
            owner, stop = cls._held.pop(name, ("", None))
        if stop:
            stop.set()
        if owner:
            cls.objects.filter(name=name, owner=owner).delete()

    @classmethod
    def beat(cls, name: str, owner: str) -> bool:
        """Says "still working". False when the lock is no longer ours (it went stale and another run took it)."""
        return bool(cls.objects.filter(name=name, owner=owner).update(locked_at=timezone.now()))

    @classmethod
    def _start_heartbeat(cls, name: str, owner: str):
        from django.db import connection

        stop = threading.Event()
        with cls._held_guard:
            _, earlier = cls._held.get(name, ("", None))
            if earlier:
                earlier.set()  # this process lost that lock to the expiry and has now taken it again
            cls._held[name] = (owner, stop)
        give_up_at = timezone.now() + LOCK_MAX_HOLD

        def run():
            while not stop.wait(LOCK_BEAT_SECONDS) and timezone.now() < give_up_at:
                try:
                    if not cls.beat(name, owner):
                        log.warning("Monday Minute lock %s: another run took it over while this one was still working", name)
                        return
                except Exception:  # a database blip must not end the heartbeat; the next beat tries again
                    log.exception("Monday Minute lock %s: could not refresh it", name)
                finally:
                    connection.close()  # this thread's own connection: don't keep one open between beats

        threading.Thread(target=run, name=f"monday-lock-{name}", daemon=True).start()


class MondayEvalRun(models.Model):
    """One run of the reviewer safety test (planted mistakes vs faithful talks), with and without RAG."""

    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    model = models.CharField(max_length=60)
    topics = models.JSONField(default=list)
    status = models.CharField(max_length=10, default="running", choices=[("running", "Running"), ("done", "Done"), ("failed", "Failed")])
    progress = models.CharField(max_length=40, blank=True)
    summary = models.TextField(blank=True)
    results = models.JSONField(default=dict, blank=True)
    # The setup this run qualifies (see gate.py) and how it did against the bar.
    rag = models.BooleanField(default=True)
    strict = models.BooleanField(default=False)
    passed = models.BooleanField(default=False)
    catch_rate = models.FloatField(null=True, blank=True)
    false_block_rate = models.FloatField(null=True, blank=True)
    verdict = models.CharField(max_length=300, blank=True)
    conclusive = models.BooleanField(default=False, help_text="Big and clean enough to count toward the safety gate. Other runs are exploratory.")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Monday Minute safety test run"

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} · {self.model} · {self.status}"
