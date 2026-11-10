"""Loads the reviewed regulation text (eCFR, current as of 2026-11-06) so retrieval works from the first deploy.
The weekly sync (python manage.py regs_sync) then keeps it current and flags amendments."""
import gzip
import json
from pathlib import Path

from django.db import migrations


def seed(apps, schema_editor):
    RegSection = apps.get_model("regs", "RegSection")
    RegChunk = apps.get_model("regs", "RegChunk")
    data = json.loads(gzip.decompress((Path(__file__).resolve().parent.parent / "seed.json.gz").read_bytes()))
    for s in data:
        sec, created = RegSection.objects.get_or_create(section=s["section"], defaults={
            "heading": s["heading"][:300], "text_hash": s["hash"], "as_of": s["as_of"]})
        if created:
            RegChunk.objects.bulk_create([
                RegChunk(section=sec, label=c["label"][:40], order=i, text=c["text"], appendix=c["appendix"])
                for i, c in enumerate(s["chunks"])
            ])


class Migration(migrations.Migration):
    dependencies = [("regs", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
