"""Emails to the app's owner: one the minute someone signs up, one when someone removes their sign-up, and one
summary a day of new phones ("downloads"). They go out through GoHighLevel with the same private token as the rest of
the sync, to the address in OWNER_ALERT_EMAIL. Leave that setting blank and nothing is sent.

Nothing here may break the app for the person using it: every send answers True or False, never raises, and whatever
did not go out is picked up again by the cron."""
import datetime as dt
import logging
from collections import Counter
from html import escape
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from django.db import transaction
from django.utils import timezone

from usage.models import AppOpen, first_opens

from . import ghl
from .integrations import NEWSLETTER_TAGS, REMOVED_TAG
from .models import AppSignup, OwnerDigest, SignupRemoval

log = logging.getLogger(__name__)
PACIFIC = ZoneInfo("America/Los_Angeles")
OWNER_TAG = "zero-harm-owner"
QUICK = 4            # seconds per GoHighLevel call while a phone is waiting for its answer
DIGEST_HOUR = 7      # the daily summary goes out at the first cron run after 7:00 AM Pacific
CATCH_UP_DAYS = 3    # after an outage, send at most this many missed days
GIVE_UP_DAYS = 7     # a removal GoHighLevel still won't take after this long goes to the owner to finish by hand
TOP_PLACES = 8


def enabled():
    return bool(settings.OWNER_ALERT_EMAIL and ghl.configured())


def _owner_contact(timeout):
    """The owner's own contact in GoHighLevel, made once and tagged zero-harm-owner. The id is remembered for a day."""
    key = f"owner-alert-contact:{settings.OWNER_ALERT_EMAIL.lower()}"
    contact_id = cache.get(key)
    if not contact_id:
        contact_id = ghl.upsert_contact(settings.OWNER_ALERT_EMAIL, tags=[OWNER_TAG], source="", timeout=timeout)
        if not contact_id:
            raise ghl.GhlError("GoHighLevel returned no contact for OWNER_ALERT_EMAIL")
        cache.set(key, contact_id, 24 * 3600)
    return contact_id


def send(subject, html, timeout=30):
    """Emails the owner. True when GoHighLevel took the message."""
    if not enabled():
        return False
    try:
        ghl.send_email(_owner_contact(timeout), " ".join(subject.split())[:200], html, timeout=timeout)
        return True
    except Exception as err:  # the caller carries on; the cron tries again
        log.error("Owner alert '%s' failed: %s", subject[:60], err)
        return False


def _when(moment):
    return timezone.localtime(moment, PACIFIC).strftime("%b %-d, %Y at %-I:%M %p Pacific")


def _page(title, rows, footer):
    """A plain email: a heading, a few "Label: value" lines and a small grey footer. Values are escaped here."""
    lines = "".join(f"<p style=\"margin:0 0 6px\"><b>{escape(label)}:</b> {escape(str(value))}</p>" for label, value in rows)
    return (f"<div style=\"font-family:Arial,Helvetica,sans-serif;font-size:15px;color:#1a1a1a\"><h2 style=\"margin:0 0 12px\">{escape(title)}</h2>"
            f"{lines}<p style=\"margin:14px 0 0;color:#666;font-size:13px\">{escape(footer)}</p></div>")


# ---- New sign-up -----------------------------------------------------------------------------------

def signup_email(signup):
    """(subject, html) for the new sign-up alert. Everything the person typed is escaped."""
    rows = [("Name", signup.full_name or "(not given)"), ("Email", signup.email)]
    if signup.company:
        rows.append(("Company", signup.company))
    rows += [
        ("Signed up on", "the welcome screen" if signup.source == AppSignup.WELCOME else "the Settings screen"),
        ("When", _when(signup.created_at)),
        ("Sign-ups so far", AppSignup.objects.count()),
    ]
    footer = "They are in GoHighLevel as a lead, tagged zero-harm-weekly for the Zero Harm Weekly newsletter."
    if signup.wants_offers:
        footer += " They also said yes to news and offers."
    return f"New Zero Harm sign-up: {signup.full_name or signup.email}", _page("New Zero Harm sign-up", rows, footer)


# At most this many instant sign-up emails an hour; the rest go in the daily summary.
ALERTS_PER_HOUR = 20


def alert_signup(signup, timeout=30):
    """Sends the new sign-up email once. True when it went out now or had already gone out."""
    if signup.owner_alerted_at:
        return True
    # A burst of sign-ups (a script, or a whole site at once) must not bury the owner's inbox. Past the hourly cap the
    # sign-up is only in the daily summary.
    key = f"owner-alerts:{timezone.now():%Y%m%d%H}"
    cache.add(key, 0, 3600)
    if cache.incr(key) > ALERTS_PER_HOUR:
        AppSignup.objects.filter(pk=signup.pk).update(owner_alerted_at=timezone.now())
        return True
    if not send(*signup_email(signup), timeout=timeout):
        return False
    signup.owner_alerted_at = timezone.now()
    signup.save(update_fields=["owner_alerted_at"])
    return True


def retry_signup_alerts(now=None):
    """Cron: sign-ups from the last 2 days whose alert has not gone out (GoHighLevel was down, or the alert address
    was set later). Rows younger than 2 minutes are left alone: the sign-up request itself may still be sending."""
    if not enabled():
        return 0
    now = now or timezone.now()
    waiting = AppSignup.objects.filter(owner_alerted_at__isnull=True, created_at__gte=now - dt.timedelta(days=2),
                                       created_at__lte=now - dt.timedelta(minutes=2)).order_by("created_at")[:50]
    return sum(alert_signup(s) for s in waiting)


# ---- Monday Minute comment reported ------------------------------------------------------------------

def report_email(comment):
    """(subject, html) for a reported comment. Everything the poster and reporters typed is escaped."""
    reasons = sorted({r for r in comment.reports.values_list("reason", flat=True) if r})
    rows = [("Comment", comment.body), ("Shown as", comment.display_name), ("Talk", comment.minute.title or comment.minute.topic.title),
            ("Reports so far", comment.report_count), ("Reasons given", ", ".join(reasons) or "(none)"),
            ("Now", comment.get_status_display()), ("Comment id", comment.pk)]
    footer = ("Please act within 24 hours. In the admin, open Monday Minute comments, then either show it again or use "
              "\"Hide and stop the poster from commenting\".")
    return f"Zero Harm comment reported: {comment.body[:60]}", _page("A Monday Minute comment was reported", rows, footer)


def alert_report(comment, timeout=30):
    """Emails the owner once per reported comment. True when it went out now or had already gone out. Never raises."""
    if comment.report_alerted_at:
        return True
    try:
        if not send(*report_email(comment), timeout=timeout):
            return False
        type(comment).objects.filter(pk=comment.pk).update(report_alerted_at=timezone.now())
        comment.report_alerted_at = timezone.now()
        return True
    except Exception as err:
        log.error("Report alert for comment %s failed: %s", comment.pk, err)
        return False


def retry_report_alerts(now=None):
    """Cron: reported comments from the last 3 days whose alert has not gone out."""
    if not enabled():
        return 0
    from monday.models import MondayComment
    now = now or timezone.now()
    waiting = (MondayComment.objects.select_related("minute__topic")
               .filter(report_count__gt=0, report_alerted_at__isnull=True, reports__created_at__gte=now - dt.timedelta(days=3),
                       reports__created_at__lte=now - dt.timedelta(minutes=2)).distinct().order_by("pk")[:50])
    return sum(alert_report(c) for c in waiting)


# ---- Sign-up removed from the app --------------------------------------------------------------------

def app_added_tags(removal):
    """The newsletter tags the app put on the contact: all of them, less the ones the contact already had before.
    (Sign-ups synced before this was noted have nothing noted, so all are taken to be the app's.)"""
    return [t for t in NEWSLETTER_TAGS if t not in (removal.ghl_had_tags or [])]


def _contact_is_gone(err, contact_id):
    """GoHighLevel says the contact isn't there (deleted or merged there): nothing is left to take off."""
    return err.status == 404 or (err.status in (400, 422) and bool(contact_id) and contact_id.lower() in (err.body or "").lower())


def _untag(removal, timeout):
    """The GoHighLevel step: take the app's tags off, put zero-harm-removed on, and leave a dated note."""
    if not removal.ghl_contact_id:
        # The sign-up had not saved its contact yet (GoHighLevel was down, or the sync was still running). Look the
        # email up; this never makes a contact. The app had not tagged it (a sync still running checks the row before
        # it tags, and takes its own tags back off if the row went meanwhile), so the tags on it now are the contact's own.
        contact = ghl.find_contact(removal.email, timeout=timeout)
        contact_id = str(contact.get("id") or "")[:40]
        if not contact_id:
            return
        tags_now = contact["tags"] if isinstance(contact.get("tags"), list) else ghl.contact_tags(contact_id, timeout=timeout)
        removal.ghl_contact_id, removal.ghl_had_tags = contact_id, [t for t in NEWSLETTER_TAGS if t in tags_now]
        removal.save(update_fields=["ghl_contact_id", "ghl_had_tags"])
    tags = app_added_tags(removal)
    if tags:
        ghl.remove_tags(removal.ghl_contact_id, tags, timeout=timeout)
    ghl.add_tags(removal.ghl_contact_id, [REMOVED_TAG], timeout=timeout)
    ghl.add_note(removal.ghl_contact_id, f"Removed their sign-up in the Zero Harm app on {_when(removal.created_at)}. "
                 + (f"Tags taken off: {', '.join(tags)}. " if tags else "No app tags to take off. ")
                 + "Do not add them back unless they sign up again.", timeout=timeout)


def _removal_footer(removal):
    if AppSignup.objects.filter(email__iexact=removal.email).exists():
        return "They removed their sign-up in the app and have since signed up again, so GoHighLevel was left as it is."
    if not removal.ghl_contact_id:
        return ("They removed their sign-up in the app. Their name and email are deleted from the app's server. "
                "They had not reached GoHighLevel yet, so nothing changed there.")
    tags, kept = app_added_tags(removal), [t for t in NEWSLETTER_TAGS if t in (removal.ghl_had_tags or [])]
    text = "They removed their sign-up in the app. Their name and email are deleted from the app's server, and in GoHighLevel "
    text += f"the tags {', '.join(tags)} are off and zero-harm-removed is on." if tags else "zero-harm-removed is on."
    if kept:
        text += f" They had {', '.join(kept)} before signing up in the app, so those were left on."
    return text


def _give_up(removal, err, timeout):
    """GoHighLevel has refused the removal for GIVE_UP_DAYS. The owner is asked to finish it by hand, then the row goes,
    so the person's name and email are not kept here any longer."""
    tags = app_added_tags(removal)
    rows = [("Name", removal.name or "(not given)"), ("Email", removal.email), ("Asked on", _when(removal.created_at)),
            ("GoHighLevel contact id", removal.ghl_contact_id or "(not known, look them up by email)"),
            ("Take these tags off by hand", ", ".join(tags) or "(none)"), ("Then add", REMOVED_TAG), ("Last error", str(err)[:200])]
    footer = (f"GoHighLevel would not take this removal for {GIVE_UP_DAYS} days, so the app has stopped trying and deleted the "
              "request from its server. Please make the tag changes above in GoHighLevel yourself.")
    if not send(f"Zero Harm removal needs finishing by hand: {removal.email}", _page("Removal to finish by hand", rows, footer), timeout=timeout):
        log.error("Removal %s given up after %s days and the owner could not be told. Contact id: %s", removal.pk, GIVE_UP_DAYS,
                  removal.ghl_contact_id or "unknown")
    removal.delete()
    return True


def finish_removal(removal, timeout=30, now=None):
    """Runs the removal while holding its row, so a sign-up of the same email waits until it is done instead of
    racing it (the sign-up then adds its tags back on top). Never raises."""
    try:
        with transaction.atomic():
            locked = SignupRemoval.objects.select_for_update().filter(pk=removal.pk).first()
            if locked is None:
                return True  # called off: they signed up again
            return _finish_removal(locked, timeout, now)
    except Exception as err:
        log.error("Removal %s could not be finished: %s", removal.pk, err)
        return False


def _finish_removal(removal, timeout=30, now=None):
    """Does what is left of a removal: take the app's newsletter tags off the GoHighLevel contact (never tags it
    already had), mark it removed with a dated note, and tell the owner. The row is deleted once nothing is left.
    True when it is finished."""
    now = now or timezone.now()
    if not removal.ghl_done_at:
        if AppSignup.objects.filter(email__iexact=removal.email).exists():
            pass  # they signed up again: the new sign-up's tags must stay
        elif ghl.configured():
            SignupRemoval.objects.filter(pk=removal.pk).update(attempts=F("attempts") + 1, last_tried_at=now)
            try:
                _untag(removal, timeout)
            except ghl.GhlError as err:
                if not _contact_is_gone(err, removal.ghl_contact_id):
                    log.error("Removal %s in GoHighLevel failed: %s", removal.pk, err)
                    if removal.created_at <= now - dt.timedelta(days=GIVE_UP_DAYS):
                        return _give_up(removal, err, timeout)
                    return False
            except Exception as err:
                log.error("Removal %s in GoHighLevel failed: %s", removal.pk, err)
                return False
        elif removal.ghl_contact_id:
            return False  # GoHighLevel settings missing: keep it until they are back
        removal.ghl_done_at = now
        SignupRemoval.objects.filter(pk=removal.pk).update(ghl_done_at=now)
    if enabled() and not removal.owner_alerted_at:
        rows = [("Name", removal.name or "(not given)"), ("Email", removal.email), ("When", _when(removal.created_at)),
                ("Sign-ups now", AppSignup.objects.count())]
        if not send(f"Zero Harm removal request: {removal.email}", _page("Sign-up removed", rows, _removal_footer(removal)), timeout=timeout):
            return False
    removal.delete()
    return True


def retry_removals(now=None):
    """Cron: removals that could not be finished when they were asked for (GoHighLevel was down). The ones tried
    longest ago go first, so a few that keep failing can't hold up newer ones."""
    now = now or timezone.now()
    waiting = (SignupRemoval.objects.filter(created_at__lte=now - dt.timedelta(minutes=2))
               .order_by(F("last_tried_at").asc(nulls_first=True), "created_at")[:20])
    return sum(finish_removal(r, now=now) for r in waiting)


# ---- Daily summary of new phones ("downloads") -------------------------------------------------------

def _place(city, region, country):
    if city and region:
        return f"{city}, {region}"
    return city or region or country or None


def digest_numbers(day):
    """What happened on one Pacific calendar day. A "new phone" is a phone whose first-ever counted open was that day."""
    new = list(first_opens(day, day).values_list("platform", "city", "region", "country"))
    places = Counter(_place(c, r, k) for _, c, r, k in new)
    unknown = places.pop(None, 0)
    ranked = sorted(places.items(), key=lambda kv: (-kv[1], kv[0]))
    start = dt.datetime.combine(day, dt.time.min, tzinfo=PACIFIC)
    return {
        "day": day,
        "new_phones": len(new),
        "ios": sum(1 for row in new if row[0] == "ios"),
        "android": sum(1 for row in new if row[0] == "android"),
        "places": ranked[:TOP_PLACES],
        "other_places": sum(n for _, n in ranked[TOP_PLACES:]),
        "unknown_places": unknown,
        "signups": AppSignup.objects.filter(created_at__gte=start, created_at__lt=start + dt.timedelta(days=1)).count(),
        "active": AppOpen.objects.filter(day=day).count(),
        "total_phones": AppOpen.objects.values("install_hash").distinct().count(),
        "total_signups": AppSignup.objects.count(),
    }


def _count(n, one, many):
    return f"{n} {one if n == 1 else many}"


def digest_email(n, today=None):
    """(subject, html) for one day's summary."""
    yesterday = n["day"] == (today or timezone.localdate()) - dt.timedelta(days=1)
    label = "yesterday" if yesterday else f"{n['day']:%b %-d}"
    subject = f"Zero Harm {label}: {_count(n['new_phones'], 'new phone', 'new phones')}, {_count(n['signups'], 'sign-up', 'sign-ups')}"
    places = [f"{name} ({count})" for name, count in n["places"]]
    if n["other_places"]:
        places.append(f"other places ({n['other_places']})")
    if n["unknown_places"]:
        places.append(f"unknown ({n['unknown_places']})")
    rows = [("New phones", f"{n['new_phones']} ({n['ios']} iPhone, {n['android']} Android)")]
    if places:
        rows.append(("Where the new phones are", ", ".join(places)))
    rows += [
        ("New sign-ups", n["signups"]),
        ("Phones active that day", n["active"]),
        ("All phones so far", n["total_phones"]),
        ("All sign-ups so far", n["total_signups"]),
    ]
    footer = ("Counts are for the calendar day in Pacific time. A new phone is one that opened the app for the first time, which is the closest "
              "thing to a download the app can see. People who switched off the daily usage count are not included. Places are approximate.")
    return subject, _page(f"Zero Harm on {n['day']:%A, %B %-d, %Y}", rows, footer)


def send_due_digests(now=None):
    """Cron: after 7:00 AM Pacific, send the summary for yesterday, plus up to 2 earlier days that were missed. Each
    day is written down once it is sent (or skipped because nothing happened), so it never goes out twice."""
    lines = []
    if not enabled():
        return lines
    local = timezone.localtime(now or timezone.now(), PACIFIC)
    if local.hour < DIGEST_HOUR:
        return lines
    for back in range(CATCH_UP_DAYS, 0, -1):  # oldest first
        day = local.date() - dt.timedelta(days=back)
        if OwnerDigest.objects.filter(day=day).exists():
            continue
        n = digest_numbers(day)
        sent = False
        if n["new_phones"] or n["signups"]:
            if not send(*digest_email(n, today=local.date())):
                lines.append(f"Owner summary for {day}: FAILED, will retry")
                continue
            sent = True
        OwnerDigest.objects.create(day=day, sent=sent, new_phones=n["new_phones"], signups=n["signups"])
        lines.append(f"Owner summary for {day}: {'sent' if sent else 'nothing to report'}")
    return lines
