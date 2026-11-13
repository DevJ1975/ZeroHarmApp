"""Taps on the invite link the owner sends from GoHighLevel (/get/?c={{contact.id}}). No network address or browser
details are kept: only which GHL contact tapped, on which kind of phone, and on which day."""
from django.db import models
from django.utils import timezone


class InviteClick(models.Model):
    """A GoHighLevel contact tapped the invite link on this day. One row per contact per day, however often they tap."""
    IOS, ANDROID, OTHER = "ios", "android", "other"
    PLATFORMS = [(IOS, "iPhone or iPad"), (ANDROID, "Android"), (OTHER, "Other (computer or unknown)")]

    contact_id = models.CharField(max_length=40, help_text="The GoHighLevel contact id from the link")
    day = models.DateField(default=timezone.localdate)
    platform = models.CharField(max_length=10, choices=PLATFORMS)
    created_at = models.DateTimeField(auto_now_add=True)
    tagged_at = models.DateTimeField(null=True, blank=True, help_text="When GoHighLevel took the tag (or said the contact doesn't exist). Blank = not yet; the cron retries for 2 days.")
    contact_missing = models.BooleanField(default=False, help_text="GoHighLevel said there is no such contact, so there was nothing to tag")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["contact_id", "day"], name="one_invite_click_per_contact_per_day")]
        indexes = [models.Index(fields=["created_at"], name="invite_click_created")]

    def __str__(self):
        return f"{self.day} {self.contact_id} {self.platform}"
