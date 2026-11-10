"""Monday Minute: a weekly AI-written toolbox talk, separate from Zero Harm Weekly.

Every week the generator picks one topic from the CSP-reviewed topic bank, writes a talk from that topic's brief only,
checks it (hard rules plus an AI safety review in the CSP role) and publishes it Monday at 5:00 AM Pacific. Crews rate
each talk and discuss it in comments; reports from crews can pull a talk and pause its topic automatically.
"""
from django.db import models
from django.utils import timezone

PULL_AT_UNSAFE_REPORTS = 3     # "isn't safe or isn't right" reports, from different networks, that pull a talk and pause its topic
HIDE_AT_COMMENT_REPORTS = 2    # reports that hide a comment until someone looks


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
    def released(self):
        return self.filter(status=MondayMinute.READY, publish_at__lte=timezone.now())

    def with_counts(self):
        """Thumbs and comment counts in the same query, so a list of talks doesn't run three more queries per talk."""
        from django.db.models import Count, Q

        return self.annotate(
            _up=Count("feedback", filter=Q(feedback__helpful=True), distinct=True),
            _down=Count("feedback", filter=Q(feedback__helpful=False), distinct=True),
            _comments=Count("comments", filter=Q(comments__status="visible"), distinct=True),
        )


class MondayMinute(models.Model):
    READY, BLOCKED, PULLED = "ready", "blocked", "pulled"
    STATUSES = [(READY, "Ready / published"), (BLOCKED, "Blocked by the safety checks"), (PULLED, "Pulled after crew reports")]

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
    created_at = models.DateTimeField(auto_now_add=True)

    objects = MondayMinuteQuerySet.as_manager()

    class Meta:
        ordering = ["-week"]
        verbose_name = "Monday Minute"
        indexes = [models.Index(fields=["status", "publish_at"], name="mm_released")]

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


class MondayLock(models.Model):
    """Keeps two cron runs from writing the same week at once. On CPU a talk can take longer than the cron interval."""

    name = models.CharField(max_length=40, primary_key=True)
    locked_at = models.DateTimeField()

    @classmethod
    def acquire(cls, name: str, ttl=None) -> bool:
        from datetime import timedelta

        from django.db import transaction

        ttl = ttl or timedelta(hours=4)  # a crashed run frees the lock after this
        now = timezone.now()
        with transaction.atomic():
            lock, created = cls.objects.select_for_update().get_or_create(name=name, defaults={"locked_at": now})
            if not created and lock.locked_at > now - ttl:
                return False
            lock.locked_at = now
            lock.save()
            return True

    @classmethod
    def release(cls, name: str):
        cls.objects.filter(name=name).delete()


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

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Monday Minute safety test run"

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} · {self.model} · {self.status}"
