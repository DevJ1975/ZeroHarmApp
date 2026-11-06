from django.db import models
from django.utils import timezone


class ToolboxTalkQuerySet(models.QuerySet):
    def released(self):
        """Talks the app may show: published and past their Sunday send time."""
        return self.filter(published=True, send_at__lte=timezone.now())


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
            "issue_date": self.issue_date.isoformat(),
            "month_theme": self.month_theme,
            "title": self.title,
            "story_title": self.story_title,
            "crew_question": self.crew_question,
            "body_md": self.body_md or None,
            "hero_url": self.hero_url or None,
            "pdf_url": self.pdf_url or None,
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
