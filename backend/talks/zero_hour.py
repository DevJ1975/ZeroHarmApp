"""Finds Zero Hour episodes and huddle cards in GoHighLevel Media Storage (files named ZH_E01_..., ZH_E01_Huddle_Card.pdf)."""
import datetime as dt
import re
from zoneinfo import ZoneInfo

from django.conf import settings

from . import ghl
from .models import Episode

PACIFIC = ZoneInfo("America/Los_Angeles")
VIDEO_RE = re.compile(r"^ZH_E(\d{2,3})_.*?(?:_v(\d+))?\.mp4$", re.I)
CARD_RE = re.compile(r"^ZH_E(\d{2,3})_Huddle_Card.*\.pdf$", re.I)
CDN = "https://assets.cdn.filesafe.space"


def next_thursday_5am(after=None):
    now = (after or dt.datetime.now(dt.timezone.utc)).astimezone(PACIFIC)
    days = (3 - now.weekday()) % 7 or 7
    day = (now + dt.timedelta(days=days)).date()
    return dt.datetime.combine(day, dt.time(5, 0), PACIFIC).astimezone(dt.timezone.utc)


def _stream_url(f):
    """GHL makes 360p–1080p copies of each video; the 720p one streams well on a phone."""
    for fmt in f.get("encodedFormats") or []:
        if fmt.endswith("_720p.mp4"):
            return f"{CDN}/{settings.GHL_LOCATION_ID}/media/transcoded_videos/{fmt}"
    return f.get("url", "")


def list_media(query, timeout=30):
    files, offset = [], 0
    while True:
        data = ghl.request("GET", "/medias/files", {"altType": "location", "altId": settings.GHL_LOCATION_ID, "type": "file",
                                                     "query": query, "limit": 100, "offset": offset, "sortBy": "createdAt", "sortOrder": "desc"},
                           timeout=timeout)
        batch = data.get("files") or []
        files.extend(batch)
        if len(batch) < 100:
            return files
        offset += 100


def sync_episodes(files=None, timeout=30):
    """Links each episode to its newest video and huddle card. A new episode number is created on hold
    (needs details) until its huddle card text is filled in, then it releases on the next Thursday at 5 AM Pacific.
    `timeout` is the seconds each listing call to GoHighLevel may take."""
    if files is None:
        if not ghl.configured():
            return ["GoHighLevel is not configured."]
        files = list_media("ZH_E", timeout=timeout)
    videos, cards = {}, {}
    for f in files:
        name = f.get("name", "")
        if (m := VIDEO_RE.match(name)) and f.get("contentType", "").startswith("video"):
            n, ver = int(m.group(1)), int(m.group(2) or 0)
            if n not in videos or ver > videos[n][0]:
                videos[n] = (ver, f)
        elif m := CARD_RE.match(name):
            cards.setdefault(int(m.group(1)), f)
    log = []
    for n in sorted(set(videos) | set(cards)):
        ep = Episode.objects.filter(number=n).first()
        created = ep is None
        if created:
            ep = Episode(number=n, title=f"Episode {n}", hazard="", story="", needs_details=True, release_at=next_thursday_5am())
        before = (ep.video_url, ep.video_full_url, ep.thumbnail_url, ep.card_pdf_url)
        if n in videos:
            f = videos[n][1]
            ep.video_url, ep.video_full_url = _stream_url(f), f.get("url", "")
            ep.thumbnail_url = (f.get("thumbnail") or {}).get("url", "") or ep.thumbnail_url
        if n in cards:
            ep.card_pdf_url = cards[n].get("url", "")
        # Save only real changes: every save moves updated_at, which tells every phone to reload.
        if created or (ep.video_url, ep.video_full_url, ep.thumbnail_url, ep.card_pdf_url) != before:
            ep.save()
        state = "NEW, on hold until its huddle card text is added" if ep.needs_details else "linked"
        log.append(f"EP {n:02d}: {state}{'' if n in videos else ' (no video yet)'}{'' if n in cards else ' (no huddle card PDF yet)'}")
    return log or ["No Zero Hour files found in Media Storage."]
