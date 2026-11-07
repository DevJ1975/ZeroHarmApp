from django.db import models
from django.utils import timezone


class ToolboxTalkQuerySet(models.QuerySet):
    def released(self):
        """Talks the app may show: published and past their Sunday send time."""
        return self.filter(published=True, needs_review=False, send_at__lte=timezone.now())


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

    def as_api(self):
        return {
            "issue": self.issue,
            "number": self.number or self.issue,
            "issue_date": self.issue_date.isoformat(),
            "month_theme": self.month_theme,
            "title": self.title,
            "story_title": self.story_title,
            "crew_question": self.crew_question,
            "body_md": self.body_md or None,
            "hero_url": self.hero_url or None,
            "pdf_url": self.pdf_url or None,
            "es": {
                "title": self.title_es,
                "story_title": self.story_title_es,
                "crew_question": self.crew_question_es,
                "body_md": self.body_md_es,
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

    issue = models.PositiveIntegerField(null=True, blank=True)
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
