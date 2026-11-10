"""Where and how much the app is used: one anonymous row per phone per day. No names, emails, coordinates or network addresses."""
from django.db import models


class AppOpen(models.Model):
    """A phone opened the app on this day. The phone is known only by the hash of its random install id."""
    PHONE, NETWORK = "phone", "network"
    SOURCES = [(PHONE, "Phone's approximate location"), (NETWORK, "Network address lookup")]

    day = models.DateField()
    install_hash = models.CharField(max_length=64, help_text="Hashed random id of the phone. Not a person.")
    platform = models.CharField(max_length=10, choices=[("ios", "iPhone"), ("android", "Android")])
    app_version = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, blank=True, help_text="Two-letter country code")
    region = models.CharField(max_length=80, blank=True, help_text="State or region")
    city = models.CharField(max_length=80, blank=True)
    source = models.CharField(max_length=10, blank=True, choices=SOURCES, help_text="Where the place came from. Blank when it isn't known.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-day", "-id"]
        constraints = [models.UniqueConstraint(fields=["day", "install_hash"], name="one_open_per_phone_per_day")]
        indexes = [models.Index(fields=["day"], name="usage_open_day")]
        verbose_name = "app open"

    def __str__(self):
        return f"{self.day} {self.platform} {self.city or self.region or self.country or 'unknown place'}"
