"""The official text of every OSHA section Zero Harm cites, from the eCFR, kept current by a weekly sync.

Used for retrieval (RAG): the Monday Minute safety reviewer checks talks against these paragraphs, and OTIS can answer
from them. When OSHA amends a section, the sync records a RegChange and pauses what depends on it until re-reviewed.
"""
from django.db import models


class RegSection(models.Model):
    section = models.CharField(max_length=20, primary_key=True, help_text="e.g. 1910.147")
    heading = models.CharField(max_length=300, blank=True)
    text_hash = models.CharField(max_length=64, blank=True, help_text="Hash of the full text, to notice amendments")
    as_of = models.DateField(null=True, blank=True, help_text="eCFR date the text is current to")
    fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["section"]
        verbose_name = "OSHA section"

    def __str__(self):
        return f"29 CFR {self.section} {self.heading}".strip()


class RegChunk(models.Model):
    """One top-level paragraph of a section, e.g. 1910.147(d), split further when long."""

    section = models.ForeignKey(RegSection, on_delete=models.CASCADE, related_name="chunks")
    label = models.CharField(max_length=40, help_text="e.g. (d), or 'Appendix A'")
    order = models.PositiveIntegerField()
    text = models.TextField()
    appendix = models.BooleanField(default=False, help_text="Appendix text: used by the reviewer, not sent to phones")

    class Meta:
        ordering = ["section", "order"]

    def __str__(self):
        return f"{self.citation}: {self.text[:60]}"

    @property
    def citation(self):
        return f"29 CFR {self.section_id}{self.label if self.label.startswith('(') else ' ' + self.label}"


class RegChange(models.Model):
    """OSHA changed a section we cite. Dependent Monday Minute topics and OTIS entries were paused."""

    section = models.ForeignKey(RegSection, on_delete=models.CASCADE, related_name="changes")
    detected_at = models.DateTimeField(auto_now_add=True)
    as_of = models.DateField(null=True, blank=True)
    old_hash = models.CharField(max_length=64, blank=True)
    new_hash = models.CharField(max_length=64)
    paused = models.TextField(blank=True, help_text="What was paused because of this change")
    reviewed = models.BooleanField(default=False, help_text="Tick once the affected topics and entries are re-reviewed and turned back on")

    class Meta:
        ordering = ["-detected_at"]
        verbose_name = "OSHA amendment"

    def __str__(self):
        return f"29 CFR {self.section_id} changed (eCFR {self.as_of})"
