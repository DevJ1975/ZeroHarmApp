"""Loads Zero Hour episodes 1-4 and their huddle cards (text from the Claude Design cards, media from GHL Media Storage)."""
import json
from pathlib import Path

from django.db import migrations
from django.utils.dateparse import parse_datetime

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "zero_hour.json"


def load(apps, schema_editor):
    Episode = apps.get_model("talks", "Episode")
    for row in json.loads(FIXTURE.read_text(encoding="utf-8")):
        row = dict(row)
        row["release_at"] = parse_datetime(row["release_at"])
        row["push_sent_at"] = parse_datetime(row["push_sent_at"]) if row.get("push_sent_at") else None
        Episode.objects.get_or_create(number=row.pop("number"), defaults=row)


class Migration(migrations.Migration):
    dependencies = [("talks", "0006_zero_hour_episodes")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
