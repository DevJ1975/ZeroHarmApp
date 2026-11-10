import re

from django.db import models
from django.utils import timezone


class ToolboxTalkQuerySet(models.QuerySet):
    def released(self):
        """Talks past their Sunday send time (published and reviewed)."""
        return self.filter(published=True, needs_review=False, send_at__lte=timezone.now())

    def available(self):
        """Talks the app shows: every talk past its Sunday send time, plus (with TALKS_UNLOCK_EARLY) the next
        TALKS_EARLY_COUNT upcoming talks that have their text, so supervisors can prepare and run them early.
        Only the next few: opening the whole year early removes the weekly reason to come back."""
        from django.conf import settings

        now = timezone.now()
        base = self.filter(published=True, needs_review=False)
        ready = models.Q(send_at__lte=now)
        if settings.TALKS_UNLOCK_EARLY and settings.TALKS_EARLY_COUNT > 0:
            # Only talks that have their text count toward the early slots, so an empty one can't use a slot up.
            upcoming = list(base.filter(send_at__gt=now).exclude(body_md="").order_by("send_at", "pk")
                            .values_list("pk", flat=True)[: settings.TALKS_EARLY_COUNT])
            ready |= models.Q(pk__in=upcoming)
        return base.filter(ready)


def _is_answer_heading(heading: str) -> bool:
    h = heading.lower().replace("’", "'")
    return ("last week" in h and "answer" in h) or ("respuesta" in h and "semana" in h)


# A section heading: "## Title" with or without the space, any heading level, or a line that is only bold text.
_HEADING = re.compile(r"^\s*(#{1,6}\s*\S|\*\*[^*]+\*\*\s*$)")


def without_last_weeks_answer(body: str) -> str:
    """Drops the "Last week's answer" section (English or Spanish). It answers the previous issue's crew question, so a
    talk opened early must not show it before that answer goes out with the Sunday newsletter."""
    if not body:
        return body
    kept, skipping = [], False
    for line in body.strip().split("\n"):
        if _HEADING.match(line):
            skipping = _is_answer_heading(line)
        if not skipping:
            kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


class ToolboxTalk(models.Model):
    issue = models.PositiveIntegerField(primary_key=True, help_text="Zero Harm Weekly issue number")
    issue_date = models.DateField(help_text="The Monday the issue is dated")
    send_at = models.DateTimeField(help_text="Sunday 11:59 AM Pacific, the day before")
    month_theme = models.CharField(max_length=80)
    title = models.CharField(max_length=200)
    story_title = models.CharField(max_length=200)
    crew_question = models.TextField()
    body_md = models.TextField(blank=True, help_text="Full talk text. Blank lines separate paragraphs.")
    hero_url = models.URLField(blank=True)
    pdf_url = models.URLField(blank=True, help_text="Printable toolbox PDF")
    ghl_template_id = models.CharField(max_length=40, blank=True)
    number = models.PositiveIntegerField(null=True, blank=True, help_text="Issue number as printed (#01). Blank = same as issue.")
    needs_review = models.BooleanField(default=False, help_text="Held out of the app: the GHL template still has [bracketed] pre-send flags")
    review_flags = models.TextField(blank=True)
    ghl_synced_at = models.DateTimeField(null=True, blank=True)

    ES_NONE, ES_DRAFT, ES_APPROVED = "none", "draft", "approved"
    title_es = models.CharField(max_length=200, blank=True)
    story_title_es = models.CharField(max_length=200, blank=True)
    crew_question_es = models.TextField(blank=True)
    body_md_es = models.TextField(blank=True)
    spanish_status = models.CharField(
        max_length=10, default="none",
        choices=[("none", "No Spanish"), ("draft", "Draft, needs review"), ("approved", "Approved, shown in app")],
        help_text="The Español button appears only when this is Approved.",
    )
    published = models.BooleanField(default=True)
    push_sent_at = models.DateTimeField(null=True, blank=True, help_text="Set when the Sunday push goes out")
    updated_at = models.DateTimeField(auto_now=True)

    objects = ToolboxTalkQuerySet.as_manager()

    class Meta:
        ordering = ["-issue"]

    def __str__(self):
        return f"#{self.issue:02d} {self.title}"

    @property
    def early(self) -> bool:
        """Open in the app before its Sunday newsletter."""
        return self.send_at > timezone.now()

    def public_body(self, lang="en") -> str:
        """The talk text crews may see right now: without last week's answer until the talk's own send time."""
        body = (self.body_md_es if lang == "es" else self.body_md) or ""
        return without_last_weeks_answer(body) if self.early else body

    def as_api(self):
        return {
            "issue": self.issue,
            "number": self.number or self.issue,
            "issue_date": self.issue_date.isoformat(),
            "month_theme": self.month_theme,
            "title": self.title,
            "story_title": self.story_title,
            "crew_question": self.crew_question,
            "body_md": self.public_body() or None,
            "hero_url": self.hero_url or None,
            "pdf_url": self.pdf_url or None,
            "send_at": self.send_at.isoformat(),
            "early": self.early,
            "es": {
                "title": self.title_es,
                "story_title": self.story_title_es,
                "crew_question": self.crew_question_es,
                "body_md": self.public_body("es"),
            } if self.spanish_status == self.ES_APPROVED else None,
        }


class AppSignup(models.Model):
    email = models.EmailField()
    first_name = models.CharField(max_length=80, blank=True)
    company = models.CharField(max_length=120, blank=True)
    wants_offers = models.BooleanField(default=False, help_text="Separate consent for promotional messages")
    source = models.CharField(max_length=40, default="zero-harm-app")
    ghl_contact_id = models.CharField(max_length=40, blank=True)
    ghl_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email


class FeedItemQuerySet(models.QuerySet):
    def released(self):
        now = timezone.now()
        return self.filter(published=True, publish_at__lte=now).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now))


class FeedItem(models.Model):
    """Everything besides the weekly talk that GoHighLevel pushes to the app: regulatory alerts and free lead magnets."""

    ALERT, COURSE, TOOL, VIDEO, NEWSLETTER = "alert", "course", "tool", "video", "newsletter"
    KINDS = [(ALERT, "Regulatory alert"), (COURSE, "Free course"), (TOOL, "Free tool"), (VIDEO, "Video"), (NEWSLETTER, "Newsletter issue")]
    JURISDICTIONS = [("", "None"), ("federal", "Federal OSHA"), ("nevada", "Nevada"), ("las_vegas", "Las Vegas")]

    external_id = models.CharField(max_length=120, unique=True, help_text="Stable id from GoHighLevel, so re-sends update instead of duplicating")
    kind = models.CharField(max_length=20, choices=KINDS)
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True, help_text="One or two plain sentences shown on the card")
    body_md = models.TextField(blank=True, help_text="Optional detail. Blank lines separate paragraphs.")
    link_url = models.URLField(blank=True, help_text="Where the button goes (course, tool, video, source rule)")
    image_url = models.URLField(blank=True)
    jurisdiction = models.CharField(max_length=20, choices=JURISDICTIONS, blank=True)
    effective_date = models.DateField(null=True, blank=True, help_text="Alerts: the date the rule takes effect")
    publish_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    send_push = models.BooleanField(default=False)
    push_sent_at = models.DateTimeField(null=True, blank=True)
    published = models.BooleanField(default=True)
    featured = models.BooleanField(default=False, help_text="Pinned to the top of Learn")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = FeedItemQuerySet.as_manager()

    class Meta:
        ordering = ["-featured", "-publish_at"]

    def __str__(self):
        return f"[{self.get_kind_display()}] {self.title}"

    def tracked_link(self):
        """Adds src=zero-harm-app so GoHighLevel attributes the lead to the app."""
        if not self.link_url:
            return None
        sep = "&" if "?" in self.link_url else "?"
        return f"{self.link_url}{sep}src=zero-harm-app" if "src=" not in self.link_url else self.link_url

    def as_api(self):
        return {
            "id": self.pk,
            "kind": self.kind,
            "title": self.title,
            "summary": self.summary,
            "body_md": self.body_md or None,
            "link_url": self.tracked_link(),
            "image_url": self.image_url or None,
            "jurisdiction": self.get_jurisdiction_display() if self.jurisdiction else None,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "published_at": self.publish_at.isoformat(),
            "featured": self.featured,
        }


class GhlSync(models.Model):
    """A request to pull Zero Harm Weekly issues for one year out of GoHighLevel. The cron service runs pending ones."""

    year = models.PositiveIntegerField()
    status = models.CharField(max_length=20, default="pending", choices=[("pending", "Pending"), ("done", "Done"), ("failed", "Failed")])
    log = models.TextField(blank=True)
    requested_by = models.CharField(max_length=40, default="admin")
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "GoHighLevel year sync"

    def __str__(self):
        return f"{self.year} sync ({self.status})"


class SigninSheet(models.Model):
    """A completed crew sign-in sheet sent from the app. The PDF is forwarded to GoHighLevel Media Storage,
    then the copy kept here is cleared, so signatures and photos are not stored twice."""

    PROGRAMS = [("zero-harm-weekly", "Zero Harm Weekly"), ("monday-minute", "Monday Minute")]
    program = models.CharField(max_length=20, choices=PROGRAMS, default="zero-harm-weekly")
    issue = models.PositiveIntegerField(null=True, blank=True, help_text="Zero Harm Weekly issue, or the Monday Minute id")
    talk_title = models.CharField(max_length=200, blank=True)
    supervisor_name = models.CharField(max_length=120)
    supervisor_email = models.EmailField()
    company = models.CharField(max_length=120, blank=True)
    location = models.CharField(max_length=120, blank=True)
    held_on = models.DateField()
    attendee_count = models.PositiveIntegerField(default=0)
    has_group_photo = models.BooleanField(default=False)
    pdf = models.BinaryField(blank=True, editable=False)
    ghl_media_url = models.URLField(max_length=500, blank=True)
    ghl_contact_id = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=10, default="pending", choices=[("pending", "Pending"), ("synced", "Saved to GHL"), ("failed", "Failed")])
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.held_on} {self.talk_title} ({self.supervisor_email})"


class KbEntry(models.Model):
    """OTIS knowledge base entries you write and control. Released talks are added to the KB automatically."""

    title = models.CharField(max_length=200)
    body = models.TextField(help_text="Plain sentences. OTIS answers only from text like this, so keep it accurate and reviewed.")
    source = models.CharField(max_length=200, blank=True, help_text="What OTIS cites, e.g. 'OSHA 1910.147' or 'Zero Harm app help'")
    tags = models.CharField(max_length=200, blank=True, help_text="Extra search words, comma separated")
    published = models.BooleanField(default=True)
    paused_reason = models.CharField(max_length=200, blank=True, help_text="Why this entry was taken out of OTIS, e.g. OSHA changed a rule it cites")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        verbose_name = "OTIS knowledge base entry"
        verbose_name_plural = "OTIS knowledge base"

    def __str__(self):
        return self.title


class TalkSuggestion(models.Model):
    """A toolbox talk idea sent from the app."""

    STATUSES = [("new", "New"), ("planned", "Planned"), ("used", "Used in an issue"), ("declined", "Not a fit")]
    topic = models.CharField(max_length=200)
    details = models.TextField(blank=True)
    month_theme = models.CharField(max_length=80, blank=True)
    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    company = models.CharField(max_length=120, blank=True)
    may_contact = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUSES, default="new")
    used_in_issue = models.PositiveIntegerField(null=True, blank=True)
    ghl_contact_id = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.topic


class EpisodeQuerySet(models.QuerySet):
    def released(self):
        return self.filter(published=True, needs_details=False, release_at__lte=timezone.now())


class Episode(models.Model):
    """A Zero Hour audio-drama episode and its huddle card. Video and PDF are hosted in GoHighLevel Media Storage."""

    number = models.PositiveIntegerField(unique=True)
    title = models.CharField(max_length=120)
    hazard = models.CharField(max_length=120, help_text="e.g. 'Lockout / Tagout · Stored Energy'")
    story = models.TextField(help_text="The story in 30 seconds")
    zero_hour = models.CharField(max_length=20, blank=True, help_text="The clock time of the incident, e.g. 3:38 P.M.")
    chain = models.JSONField(default=list, blank=True, help_text="Where the chain could have broken (list)")
    checks_label = models.CharField(max_length=80, default="Before anyone starts")
    checks = models.JSONField(default=list, blank=True)
    stop_when = models.TextField(blank=True)
    emergency_label = models.CharField(max_length=80, default="If it goes wrong")
    emergency = models.TextField(blank=True)
    questions = models.JSONField(default=list, blank=True)
    references = models.JSONField(default=list, blank=True)
    video_url = models.URLField(max_length=500, blank=True, help_text="Streaming copy (720p)")
    video_full_url = models.URLField(max_length=500, blank=True)
    thumbnail_url = models.URLField(max_length=500, blank=True)
    card_pdf_url = models.URLField(max_length=500, blank=True, help_text="Printable huddle card")
    release_at = models.DateTimeField(help_text="Zero Hour posts Thursdays at 5:00 AM Pacific")
    published = models.BooleanField(default=True)
    needs_details = models.BooleanField(default=False, help_text="Found in GHL but the huddle card text isn't filled in yet")
    send_push = models.BooleanField(default=True)
    push_sent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EpisodeQuerySet.as_manager()

    class Meta:
        ordering = ["-number"]
        verbose_name = "Zero Hour episode"

    def __str__(self):
        return f"EP {self.number:02d} · {self.title}"

    def as_api(self):
        return {
            "number": self.number, "title": self.title, "hazard": self.hazard, "story": self.story, "zero_hour": self.zero_hour,
            "chain": self.chain, "checks_label": self.checks_label, "checks": self.checks, "stop_when": self.stop_when,
            "emergency_label": self.emergency_label, "emergency": self.emergency, "questions": self.questions,
            "references": self.references, "video_url": self.video_url or None, "thumbnail_url": self.thumbnail_url or None,
            "card_pdf_url": self.card_pdf_url or None, "released_at": self.release_at.isoformat(),
        }


# ---- OTIS on-device AI: rollout, pinned model files, opt-in feedback -----------------------------

class OtisRollout(models.Model):
    """One row of switches the phones read in their OTIS manifest. Edit it in the admin; no app update needed."""

    ios_enabled = models.BooleanField(default=True, help_text="Turn OTIS off on iPhone and iPad")
    android_enabled = models.BooleanField(default=True, help_text="Turn OTIS off on Android")
    min_app_version = models.CharField(max_length=20, blank=True, help_text="Older app versions are asked to update before using OTIS, e.g. 1.2.0")
    feedback_enabled = models.BooleanField(default=True, help_text="Accept 'Was this helpful?' ratings from people who opted in")
    message = models.CharField(max_length=200, blank=True, help_text="Shown when OTIS is off. Blank = 'OTIS is taking a short break.'")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "OTIS rollout"
        verbose_name_plural = "OTIS rollout"

    def __str__(self):
        return "OTIS rollout switches"

    @classmethod
    def current(cls):
        return cls.objects.order_by("pk").first() or cls()


class OtisModelRelease(models.Model):
    """A pinned copy of the model files the phones download. With none active, phones use the library's built-in model."""

    PLATFORMS = [("ios", "iPhone / iPad"), ("android", "Android")]
    BACKENDS = [("mlx", "MLX (Apple)"), ("coreml", "Core ML (Apple)"), ("xnnpack", "XNNPACK (CPU, any phone)"), ("vulkan", "Vulkan (Android GPU)")]

    key = models.SlugField(max_length=60, unique=True, help_text="Stable id, e.g. qwen3-1.7b-mlx-int4-2026-11. Change it to make phones download again.")
    label = models.CharField(max_length=80, help_text="What the setup screen calls it, e.g. OTIS standard")
    platform = models.CharField(max_length=10, choices=PLATFORMS)
    backend = models.CharField(max_length=10, choices=BACKENDS, help_text="The phone only gets a release its app build can run")
    min_memory_gb = models.DecimalField(max_digits=4, decimal_places=1, default=0, help_text="Phones with at least this much memory. The biggest match wins.")
    model_url = models.URLField(max_length=500, help_text="HTTPS link to the .pte file")
    tokenizer_url = models.URLField(max_length=500, help_text="HTTPS link to tokenizer.json")
    tokenizer_config_url = models.URLField(max_length=500, help_text="HTTPS link to tokenizer_config.json")
    size_mb = models.PositiveIntegerField(help_text="Download size shown on the setup screen")
    active = models.BooleanField(default=False)
    notes = models.TextField(blank=True, help_text="What you tested this on")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["platform", "-min_memory_gb"]
        verbose_name = "OTIS model release"

    def __str__(self):
        return f"{self.get_platform_display()} · {self.label} ({self.key})"

    def clean(self):
        from django.core.exceptions import ValidationError

        for field in ("model_url", "tokenizer_url", "tokenizer_config_url"):
            if not getattr(self, field).startswith("https://"):
                raise ValidationError({field: "Use an HTTPS link."})


class OtisFeedback(models.Model):
    """A 'Was this helpful?' rating from someone who turned on Help improve OTIS. No name, email or device id."""

    helpful = models.BooleanField()
    question = models.TextField(blank=True, help_text="Only sent when the person also chose to share their question")
    source_ids = models.JSONField(default=list, blank=True, help_text="Which knowledge base passages OTIS used")
    model_key = models.CharField(max_length=60, blank=True)
    platform = models.CharField(max_length=10, blank=True)
    app_version = models.CharField(max_length=20, blank=True)
    lang = models.CharField(max_length=2, default="en")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "OTIS feedback"
        verbose_name_plural = "OTIS feedback"

    def __str__(self):
        return f"{'Helpful' if self.helpful else 'Not helpful'} · {self.created_at:%Y-%m-%d}"
