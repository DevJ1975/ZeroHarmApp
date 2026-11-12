"""Support tickets: problems people report from the app, OTIS answers they flag, and automatic crash reports.

What is kept: what the person chose to send (their words and, only if they typed them, a name and an email), the
phone's model, system and app version, the screen it happened on, and the phone known only by the salted hash of
its random install id. A problem report or a flagged answer can be linked to the person: it may carry the email they
typed, and its install hash is the same one a sign-up from that phone carries. A crash report cannot: it is stored
under a different hash of the install id (crash_hash() in api.py), the crash ticket keeps no install hash at all, and
it holds only the error and where in the app's code it happened, with web address details, ids, emails, phone
numbers and long numbers taken out before it is saved. support_prune deletes single crash reports after
SUPPORT_CRASH_KEEP_DAYS, and with them the phone model, system version and screen the ticket was first given.
What is never kept: the network address, the raw install id, coordinates, or anything from an OTIS chat. The one
exception is a single question and answer that a person flags with "Report this answer", which they send on purpose."""
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Ticket(models.Model):
    """One thing for the owner to look at. A person's report is one ticket. The same crash on the same app version
    and platform is one ticket with a count, however many phones it happens on."""

    PROBLEM, CRASH, ANSWER = "problem", "crash", "answer"
    KINDS = [(PROBLEM, "Problem a person reported"), (CRASH, "Crash (automatic)"), (ANSWER, "OTIS answer a person flagged")]
    PERSON_KINDS = (PROBLEM, ANSWER)  # sent by a person on purpose: each gets its own email to the owner

    NEW, IN_PROGRESS, FIXED, CLOSED = "new", "in_progress", "fixed", "closed"
    STATUSES = [(NEW, "New"), (IN_PROGRESS, "In progress"), (FIXED, "Fixed"), (CLOSED, "Closed")]
    OPEN = (NEW, IN_PROGRESS)
    DONE = (FIXED, CLOSED)

    OTIS, FORM, FROM_CRASH, OTIS_ANSWER = "otis", "form", "crash", "otis_answer"
    SOURCES = [(OTIS, "Told OTIS"), (FORM, "Report a problem form"), (FROM_CRASH, "Crash reporter"), (OTIS_ANSWER, "Report this answer")]

    kind = models.CharField(max_length=10, choices=KINDS, default=PROBLEM)
    status = models.CharField(max_length=12, choices=STATUSES, default=NEW)
    source = models.CharField(max_length=12, choices=SOURCES, default=FORM)
    title = models.CharField(max_length=120)
    text = models.TextField(max_length=4000, help_text="The person's own words, or the crash message.")
    reply = models.TextField(max_length=2000, blank=True, help_text=(
        "Your answer. On a problem report the person sees it in the app under My reports. On a flagged OTIS answer or a "
        "crash it is a private note: the person never sees it. Write to them by email instead, if they gave one."))
    owner_note = models.TextField(max_length=2000, blank=True, help_text="Private note for you. Never sent to the phone.")
    # Only for a flagged OTIS answer: the one question and answer the person chose to send.
    question = models.CharField(max_length=500, blank=True)
    answer = models.TextField(max_length=2000, blank=True)
    model_key = models.CharField(max_length=60, blank=True, help_text="Which OTIS model wrote the answer.")

    app_version = models.CharField(max_length=20, blank=True)
    platform = models.CharField(max_length=10, blank=True, choices=[("ios", "iPhone"), ("android", "Android")])
    os_version = models.CharField(max_length=20, blank=True)
    device = models.CharField(max_length=60, blank=True, help_text="Phone model, like Pixel 8.")
    screen = models.CharField(max_length=120, blank=True, help_text="The screen of the app it happened on.")
    lang = models.CharField(max_length=2, blank=True)
    install_hash = models.CharField(max_length=64, blank=True, help_text=(
        "Hashed random id of the phone that sent a person's report; the same hash a sign-up from that phone carries. "
        "Blank on a crash ticket."))
    client_key = models.CharField(max_length=64, blank=True, help_text="Made by the phone, so a report sent twice is saved once. Blank for a crash.")

    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    may_contact = models.BooleanField(default=False, help_text="They said it is OK to reply to them by email.")

    # Crash grouping: every report of the same crash lands on one ticket.
    fingerprint = models.CharField(max_length=64, blank=True, help_text="What makes two crashes the same one. Blank for a person's report.")
    count = models.PositiveIntegerField(default=1, help_text="How many reports of it have come in.")
    first_seen = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)
    alerted_count = models.PositiveIntegerField(default=0, help_text="The count when you were last emailed about it. 0 = not yet.")

    # Each finished step is stamped, so trying again never repeats one.
    owner_alerted_at = models.DateTimeField(null=True, blank=True, help_text="When you were emailed about it.")
    owner_alert_unsure_at = models.DateTimeField(null=True, blank=True, help_text=(
        "When an email about it was handed to GoHighLevel but no answer came back in time. It may have arrived; the cron "
        "sends it again later in a list, marked as possibly a repeat."))
    ghl_contact_id = models.CharField(max_length=40, blank=True)
    ghl_tagged_at = models.DateTimeField(null=True, blank=True)
    ghl_noted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, help_text="When you last changed it. Counting another crash does not move this.")
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["fingerprint"], condition=~Q(fingerprint=""), name="support_one_ticket_per_crash"),
            models.UniqueConstraint(fields=["install_hash", "client_key"], condition=~Q(client_key=""), name="support_one_ticket_per_report"),
        ]
        indexes = [
            models.Index(fields=["install_hash", "-created_at"], name="support_ticket_phone"),  # a phone's "My reports"
            models.Index(fields=["status", "kind"], name="support_ticket_status"),
            models.Index(fields=["owner_alerted_at"], name="support_ticket_alerted"),  # the hourly email count
            models.Index(fields=["kind", "created_at"], name="support_ticket_new"),  # how many new crashes today
        ]
        verbose_name = "support ticket"

    def __str__(self):
        return f"{self.number} {self.title}"

    @property
    def number(self):
        """What the person and the owner both call it."""
        return f"ZH-{self.pk}"

    def set_status(self, status, now=None):
        """Changes the status and keeps closed_at in step: stamped when the ticket becomes fixed or closed, cleared
        when it is opened again. Does not save."""
        if status in self.DONE and (self.status not in self.DONE or not self.closed_at):
            self.closed_at = now or timezone.now()
        elif status in self.OPEN:
            self.closed_at = None
        self.status = status


class CrashReport(models.Model):
    """One crash report as a phone sent it, kept for the detail view. Only the newest few of each ticket are kept;
    the ticket's count still counts them all."""

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="crashes")
    client_key = models.CharField(max_length=64, help_text="Made by the phone, so a report sent twice is counted once.")
    created_at = models.DateTimeField(default=timezone.now, help_text="When it happened on the phone, or when it arrived.")
    fatal = models.BooleanField(default=False, help_text="The app could not carry on.")
    name = models.CharField(max_length=120)
    message = models.CharField(max_length=500, blank=True)
    stack = models.TextField(max_length=6000, blank=True)
    screen = models.CharField(max_length=120, blank=True)
    app_version = models.CharField(max_length=20, blank=True)
    platform = models.CharField(max_length=10, blank=True, choices=[("ios", "iPhone"), ("android", "Android")])
    os_version = models.CharField(max_length=20, blank=True)
    device = models.CharField(max_length=60, blank=True)
    install_hash = models.CharField(max_length=64, help_text=(
        "The phone's random id, hashed under its own label for crashes: it cannot be matched to a sign-up or a "
        "person's report."))

    class Meta:
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["install_hash", "client_key"], name="support_one_row_per_crash_report")]
        indexes = [models.Index(fields=["created_at"], name="support_crash_when")]  # the clean-up of old rows
        verbose_name = "crash report"

    def __str__(self):
        return f"{self.name}: {self.message[:60]}"


class CrashKey(models.Model):
    """That a crash report was counted, kept apart from the report itself. A ticket keeps only its newest few
    reports, so a phone that sends one again (its first answer was lost) after those were trimmed would be counted
    twice without this. support_prune deletes these after a week: no phone waits that long to send again."""

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="+")
    install_hash = models.CharField(max_length=64, help_text="The same crash-only hash as CrashReport.install_hash.")
    client_key = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["install_hash", "client_key"], name="support_count_each_crash_report_once")]
        indexes = [models.Index(fields=["created_at"], name="support_crashkey_when")]
        verbose_name = "counted crash report"
