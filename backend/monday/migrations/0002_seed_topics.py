"""Loads the CSP-reviewed Monday Minute topic bank (monday/topics.json). Existing topics, including admin edits, are kept."""
import json
from pathlib import Path

from django.db import migrations

FIELDS = ("title", "category", "months", "hazard", "key_points", "must_say", "never_say", "facts", "story_seed", "crew_questions", "references")


def seed(apps, schema_editor):
    MondayTopic = apps.get_model("monday", "MondayTopic")
    bank = json.loads((Path(__file__).resolve().parent.parent / "topics.json").read_text())
    for b in bank:
        MondayTopic.objects.get_or_create(slug=b["slug"], defaults={k: b[k] for k in FIELDS})


def unseed(apps, schema_editor):
    MondayTopic = apps.get_model("monday", "MondayTopic")
    bank = json.loads((Path(__file__).resolve().parent.parent / "topics.json").read_text())
    MondayTopic.objects.filter(slug__in=[b["slug"] for b in bank], talks__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("monday", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
