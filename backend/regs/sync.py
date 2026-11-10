"""Keeps the regulation library current with the eCFR and pauses anything built on a section OSHA has changed."""
from django.db import transaction
from django.utils import timezone

from . import ecfr
from .models import RegChange, RegChunk, RegSection
from .retrieve import cited


def cited_sections() -> set[str]:
    """Every section a Monday Minute topic or an OTIS entry cites, plus the ones already in the library."""
    from monday.models import MondayTopic
    from talks.models import KbEntry

    found = set(RegSection.objects.values_list("section", flat=True))
    for t in MondayTopic.objects.all():
        text = " ".join(t.references) + " " + " ".join(f.get("cite", "") for f in t.facts)
        found |= {s for s, _ in cited(text)}
    for e in KbEntry.objects.all():
        found |= {s for s, _ in cited(f"{e.source} {e.body}")}
    return found


def pause_dependents(section: str, as_of) -> str:
    """Pauses Monday Minute topics and unpublishes OTIS entries that cite `section`. Returns what was paused."""
    from monday.models import MondayTopic
    from talks.models import KbEntry

    reason = f"OSHA changed 29 CFR {section} (eCFR {as_of}). Re-review, then turn back on."
    lines = []
    for t in MondayTopic.objects.filter(active=True):
        text = " ".join(t.references) + " " + " ".join(f.get("cite", "") for f in t.facts)
        if section in {s for s, _ in cited(text)}:
            t.active, t.paused_reason = False, reason[:200]
            t.save(update_fields=["active", "paused_reason", "updated_at"])
            lines.append(f"Monday Minute topic: {t.title}")
    for e in KbEntry.objects.filter(published=True):
        if section in {s for s, _ in cited(f"{e.source} {e.body}")}:
            e.published, e.paused_reason = False, reason[:200]
            e.save(update_fields=["published", "paused_reason", "updated_at"])
            lines.append(f"OTIS entry: {e.title}")
    return "\n".join(lines)


def sync(sections=None, fetch=ecfr.fetch_xml, latest=ecfr.latest_date) -> list[str]:
    date = latest()
    log = [f"eCFR Title 29 current as of {date}."]
    for section in sorted(sections or cited_sections()):
        try:
            heading, full, chunks = ecfr.parse(fetch(section, date), section)
        except Exception as err:  # one bad section shouldn't stop the rest
            log.append(f"{section}: could not fetch ({err})")
            continue
        new_hash = ecfr.text_hash(full)
        with transaction.atomic():
            sec, created = RegSection.objects.get_or_create(section=section)
            changed = bool(sec.text_hash) and sec.text_hash != new_hash
            if created or changed or not sec.chunks.exists():
                sec.chunks.all().delete()
                RegChunk.objects.bulk_create([
                    RegChunk(section=sec, label=label[:40], order=i, text=text, appendix=appendix)
                    for i, (label, appendix, text) in enumerate(chunks)
                ])
            if changed:
                paused = pause_dependents(section, date)
                RegChange.objects.create(section=sec, as_of=date, old_hash=sec.text_hash, new_hash=new_hash, paused=paused)
                log.append(f"{section}: CHANGED by OSHA. Paused:\n  " + (paused.replace("\n", "\n  ") or "nothing"))
            sec.heading, sec.text_hash, sec.as_of, sec.fetched_at = heading[:300], new_hash, date, timezone.now()
            sec.save()
    return log
