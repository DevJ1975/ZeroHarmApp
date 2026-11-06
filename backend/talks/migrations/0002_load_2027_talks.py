"""Loads all 52 issues of Zero Harm Weekly 2027 from fixtures/talks_2027.json (existing rows are left alone)."""
import json
from pathlib import Path

from django.db import migrations
from django.utils.dateparse import parse_date, parse_datetime

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "talks_2027.json"


def load(apps, schema_editor):
    Talk = apps.get_model("talks", "ToolboxTalk")
    for row in json.loads(FIXTURE.read_text(encoding="utf-8")):
        f = dict(row["fields"])
        f["issue_date"] = parse_date(f["issue_date"])
        f["send_at"] = parse_datetime(f["send_at"])
        Talk.objects.get_or_create(issue=row["pk"], defaults=f)


class Migration(migrations.Migration):
    dependencies = [("talks", "0001_initial")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
