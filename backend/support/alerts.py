"""Telling the owner about tickets, and putting a reporter who asked for a reply into GoHighLevel.

Three jobs, all through GoHighLevel with the same token as the rest of the server:

1. A person's report (a problem, or a flagged OTIS answer): one email to the owner, tried while the phone waits
   (a few seconds at most) and, when that did not work, again by the cron. Only a problem report is a conversation:
   the person sees its status and the owner's reply under My reports. A reply on a flagged answer or a crash is a
   private note the person never sees, and the emails say so.
2. Crashes: never emailed one by one. The cron sends ONE email per run that lists every crash that is new, or
   that has now been reported 10, 100 or 1000 times. A crash loop on thousands of phones is one ticket and a
   handful of emails.
3. A reporter who gave an email and said it is OK to reply: their contact gets the tag zero-harm-support-ticket
   and a note with the ticket number and what they wrote, so a GoHighLevel workflow can pick it up.

Nothing here may break the app for the person using it or stop the cron: every function answers and never raises
(run() raises once at its end, after every part has had its turn, so the cron can show the run as failed). Nothing
is ever dropped either. Each finished step is stamped on the ticket; what is not stamped is tried again."""
import datetime as dt
import hashlib
import logging
import time

from django.conf import settings
from django.core.cache import cache, caches
from django.db.models import Q
from django.utils import timezone

from talks import ghl, owner_alerts
from talks.integrations import _note_is_there, note_mark, turn
from talks.models import split_name

from .models import Ticket

log = logging.getLogger(__name__)
QUICK = owner_alerts.QUICK   # seconds per GoHighLevel call while a phone is waiting for its answer
TAG = "zero-harm-support-ticket"
INSTANT_PER_HOUR = 10        # emails about single tickets in any one hour; reports past it wait for the cron's one list
INSTANT_PER_RUN = 3          # the cron sends this many waiting reports one by one; more than that go out as one list
LISTED_PER_EMAIL = 30        # tickets one list email names; the rest stay waiting and come in the next one
NEW_CRASHES_PER_DAY = 200    # different crashes saved in any 24 hours; past it only crashes already known are counted
NEW_CRASHES_PER_NETWORK = 20  # new kinds of crash one network may add in a day, so one caller cannot use up the 200
CRASH_STEPS = (10, 100, 1000)  # the owner hears about a crash when it is new and again when its count passes each of these
SETTLE = dt.timedelta(minutes=2)   # the cron leaves a report alone this long: its own request may still be sending
# An email GoHighLevel did not answer in time may still have arrived. The cron waits this long before sending it
# again, and then sends it in a list marked as possibly a repeat, never as a second single email.
UNSURE_WAIT = dt.timedelta(minutes=15)
CONTACT_DAYS = 2             # how long the cron keeps trying to put a reporter into GoHighLevel
CONTACTS_PER_RUN = 50
PAUSE_KEY, PAUSE_SECONDS = "support-instant-alerts-paused", 300
SYSTEMS = {"ios": "iOS", "android": "Android"}
KIND_WORDS = {Ticket.PROBLEM: "problem report", Ticket.CRASH: "crash", Ticket.ANSWER: "flagged OTIS answer"}
SOURCE_WORDS = {Ticket.OTIS: "told to OTIS", Ticket.FORM: "sent from the Report a problem form",
                Ticket.OTIS_ANSWER: "sent with Report this answer", Ticket.FROM_CRASH: "sent by the app itself"}


# ---- What goes in an email ---------------------------------------------------------------------------

def admin_link(ticket):
    """Where the owner opens the ticket, or "" when PUBLIC_URL is not set."""
    base = settings.PUBLIC_URL
    return f"{base}/admin/support/ticket/{ticket.pk}/change/" if base.startswith(("https://", "http://")) else ""


def _phone(ticket):
    """ "Pixel 8, Android 14", from whatever the phone told us. """
    system = " ".join(filter(None, [SYSTEMS.get(ticket.platform, ""), ticket.os_version]))
    return ", ".join(filter(None, [ticket.device, system])) or "not given"


def _lines_of(text, limit=40):
    """A person's text as email paragraphs, one per line they wrote, so line breaks survive."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    return lines[:limit] + (["(cut here; the rest is on the ticket)"] if len(lines) > limit else [])


def _reporter(ticket):
    who = f"{ticket.email} ({ticket.name})" if ticket.email and ticket.name else ticket.email or ticket.name
    if ticket.email and ticket.may_contact:
        return f"Reply to: {who}. They said it is OK to reply."
    if ticket.email:
        return f"From: {who}. They did not say it is OK to reply."
    return f"From: {who}. No email given." if who else "No name or email given."


def ticket_email(ticket):
    """(subject, lines) for the email about one person's report. notify() escapes every line."""
    lines = [f"Ticket {ticket.number}: a {KIND_WORDS[ticket.kind]}, {SOURCE_WORDS.get(ticket.source, ticket.source)}."]
    if ticket.kind == Ticket.ANSWER:
        lines += ["The question they asked OTIS:", *(_lines_of(ticket.question) or ["(not sent)"]),
                  "What OTIS answered:", *(_lines_of(ticket.answer) or ["(not sent)"]), "Their note:", *_lines_of(ticket.text)]
        if ticket.model_key:
            lines.append(f"OTIS model: {ticket.model_key}")
    else:
        lines += ["What they wrote:", *_lines_of(ticket.text)]
    lines += [
        f"App version: {ticket.app_version or 'not given'}. Phone: {_phone(ticket)}."
        + (f" Screen: {ticket.screen}." if ticket.screen else "") + (f" Language: {ticket.lang}." if ticket.lang else ""),
        f"When: {owner_alerts._when(ticket.created_at)}. Times reported: {ticket.count}.",
        _reporter(ticket),
    ]
    link = admin_link(ticket)
    if link:
        lines.append(f"Open it: {link}")
    if ticket.kind == Ticket.PROBLEM:
        lines.append("Change its status or write a reply in the admin or the content console. The person sees the status and your reply in the app, under My reports.")
    else:
        lines.append("A flagged answer is not shown to the person in the app. A reply you write on it is a private note they never see. "
                     "To answer them, write to them by email, if they gave one and said it is OK.")
    what = "OTIS answer flagged" if ticket.kind == Ticket.ANSWER else "problem report"
    return f"Zero Harm {what} {ticket.number}: {ticket.title}", lines


def _list_line(ticket, about):
    link = admin_link(ticket)
    return f"{ticket.number}, {about}" + (f" Open it: {link}" if link else "")


def _slot_key(what, tickets, now):
    """The once-only key for a list email: the same list in the same quarter hour is sent once, even if two cron
    runs overlap. It changes every quarter hour, so a list is never held back for long by a key left behind."""
    listed = ",".join(f"{t.pk}:{t.count}" for t in tickets)
    return f"support-{what}:{int(now.timestamp()) // 900}:{hashlib.sha256(listed.encode()).hexdigest()[:16]}"


LIST_TIMEOUT = 30  # seconds per GoHighLevel call for the cron's list emails
MAYBE_SENT = " (This one may have reached you already: GoHighLevel was too slow to answer when it was first sent.)"


def _notify_list(subject, lines, key, tickets):
    """Sends one list email. True when it went out. When GoHighLevel used up the whole wait without answering, the
    email may have arrived anyway: the listed tickets are marked unsure, so the next cron runs leave them alone for
    UNSURE_WAIT and then list them again marked as possibly a repeat, not as if they were new. A refusal comes back
    at once and marks nothing."""
    started = time.monotonic()
    if owner_alerts.notify(subject, lines, key=key, timeout=LIST_TIMEOUT):
        return True
    if time.monotonic() - started >= LIST_TIMEOUT:
        Ticket.objects.filter(pk__in=[t.pk for t in tickets]).update(owner_alert_unsure_at=timezone.now())
    return False


# ---- One person's report -----------------------------------------------------------------------------

def emails_last_hour(now=None):
    """How many support emails went to the owner in the last hour. Counted from the tickets themselves, so the web
    server and the cron, which share no memory, share this count. A list email stamps all its tickets with the same
    moment, so it counts as the one email it was."""
    since = (now or timezone.now()) - dt.timedelta(hours=1)
    return Ticket.objects.filter(owner_alerted_at__gt=since).order_by().values("owner_alerted_at").distinct().count()


def alert_ticket(ticket, timeout=30):
    """Emails the owner about one person's report, once. True when it went out now or had already gone out. False
    leaves the ticket waiting for the cron: owner alerts are off, GoHighLevel did not take it, or this hour's
    single-ticket emails are used up (then it goes out in the cron's list, never dropped). Never raises."""
    try:
        if ticket.owner_alerted_at:
            return True
        if ticket.kind not in Ticket.PERSON_KINDS or not owner_alerts.enabled():
            return False  # a crash is never emailed by itself: it goes in the cron's one crash email
        waiting_phone = timeout <= QUICK
        if waiting_phone and cache.get(PAUSE_KEY):
            return False  # GoHighLevel did not answer a moment ago: don't make this phone wait for it as well
        if emails_last_hour() >= INSTANT_PER_HOUR:
            return False
        if ticket.owner_alert_unsure_at:
            return False  # it may have reached the owner already: only the cron's list sends it again, marked as such
        started = time.monotonic()
        if not owner_alerts.notify(*ticket_email(ticket), key=f"support-ticket:{ticket.pk}", timeout=timeout):
            if waiting_phone:
                cache.set(PAUSE_KEY, 1, PAUSE_SECONDS)
            if time.monotonic() - started >= timeout:
                # Used up the whole wait: GoHighLevel may have taken the email and answered too late. A refusal comes
                # back at once. Marked, so it is not sent again as a second email of its own.
                now = timezone.now()
                Ticket.objects.filter(pk=ticket.pk, owner_alert_unsure_at__isnull=True).update(owner_alert_unsure_at=now)
                ticket.owner_alert_unsure_at = now
            return False
        now = timezone.now()
        # update(), not save(): the stamp is bookkeeping and must not move updated_at, which the phone shows.
        Ticket.objects.filter(pk=ticket.pk, owner_alerted_at__isnull=True).update(owner_alerted_at=now)
        ticket.owner_alerted_at = now
        return True
    except Exception:
        log.exception("Support: the owner email for ticket %s failed", ticket.pk)
        return False


def send_waiting_reports(now=None):
    """Cron: people's reports the owner has not been emailed about (GoHighLevel was down, the alert address was set
    later, or the hour's single emails were used up). A few go out one by one. More than a few go out as one list,
    oldest first, and what does not fit waits for the next run. A ticket the owner has already picked up in the admin
    (no longer New) needs no email. Returns how many tickets the owner has now been told about."""
    now = now or timezone.now()
    if not owner_alerts.enabled():
        return 0
    waiting = (Ticket.objects.filter(kind__in=Ticket.PERSON_KINDS, status=Ticket.NEW, owner_alerted_at__isnull=True,
                                     created_at__lte=now - SETTLE)
               .exclude(owner_alert_unsure_at__gt=now - UNSURE_WAIT).order_by("created_at", "pk"))
    total = waiting.count()
    if not total:
        return 0
    unsure = waiting.filter(owner_alert_unsure_at__isnull=False).exists()
    if not unsure and total <= min(INSTANT_PER_RUN, INSTANT_PER_HOUR - emails_last_hour()):
        return sum(alert_ticket(t) for t in waiting)
    listed = list(waiting[:LISTED_PER_EMAIL])
    lines = ["These reports from the app are waiting for you. They are listed together so your inbox is not filled with one email each."]
    for t in listed:
        words = " ".join(t.text.split())
        about = (f"{KIND_WORDS[t.kind]} from {owner_alerts._when(t.created_at)}, app {t.app_version or 'version not given'} on {_phone(t)}: "
                 f"{words[:300]}{'...' if len(words) > 300 else ''}")
        if t.owner_alert_unsure_at:
            about += MAYBE_SENT
        lines.append(_list_line(t, about))
    if total > len(listed):
        lines.append(f"{total - len(listed)} more are waiting. They come in the next email, in about 15 minutes.")
    lines.append("Each one is in the admin under Support tickets, and in the content console under Tickets. "
                 "A reply reaches the person in the app only on a problem report. On a flagged answer it is a private note they never see.")
    subject = f"Zero Harm: {total} {'report' if total == 1 else 'reports'} waiting"
    if not _notify_list(subject, lines, _slot_key("reports", listed, now), listed):
        return 0
    return Ticket.objects.filter(pk__in=[t.pk for t in listed], owner_alerted_at__isnull=True).update(owner_alerted_at=timezone.now())


# ---- Crashes -----------------------------------------------------------------------------------------

def new_crashes_today(now=None):
    """How many different crashes were first seen in the last 24 hours."""
    return Ticket.objects.filter(kind=Ticket.CRASH, created_at__gt=(now or timezone.now()) - dt.timedelta(days=1)).count()


def network_limit_key(now):
    """Set (in the shared cache) on a day one network was turned away for sending too many new kinds of crash."""
    return f"support-crash-network-limit:{now:%Y-%m-%d}"


def send_crash_limit_notice(now=None):
    """Cron: one email a day while a limit on new kinds of crash is turning reports away, sent whether or not there
    is a crash to list. Without it the owner would hear of the limit only inside a crash email, and once the made-up
    crashes had been listed there would be none. True when a notice went out now."""
    now = now or timezone.now()
    full = new_crashes_today(now) >= NEW_CRASHES_PER_DAY
    one_network = bool(caches["shared"].get(network_limit_key(now)))
    if not (full or one_network):
        return False
    if full:
        lines = [f"{NEW_CRASHES_PER_DAY} different kinds of crash have come in over the last day. An app makes a few dozen at most, so "
                 "someone may be sending made-up reports.",
                 "Until the number drops, the server turns away crashes of a new kind. Phones keep those reports and send them again "
                 "later, so a real one is late, not lost. Crashes already in the admin keep counting."]
    else:
        lines = [f"One network sent more than {NEW_CRASHES_PER_NETWORK} new kinds of crash today. Its new kinds are "
                 "turned away until tomorrow. Other networks can still send new ones. Phones keep those reports and send them again later.",
                 "Crashes already in the admin keep counting."]
    lines.append("Look at the newest crash tickets in the admin under Support tickets. A made-up one stops counting against the limit "
                 "24 hours after it came in. You get this email at most once a day while it lasts.")
    subject = "Zero Harm: new crash reports are being turned away"
    return owner_alerts.notify(subject, lines, key=f"support-crash-limit:{now:%Y-%m-%d}:{'all' if full else 'network'}", timeout=30)


def crashes_to_report(now=None):
    """Open crash tickets the owner should hear about now: new ones (never emailed, or closed and back again), and
    ones whose count has passed 10, 100 or 1000 since the last email. Most reported first. One whose last crash
    email GoHighLevel was too slow to answer waits UNSURE_WAIT first: that email may have arrived."""
    grown = Q()
    for step in CRASH_STEPS:
        grown |= Q(alerted_count__lt=step, count__gte=step)
    return (Ticket.objects.filter(kind=Ticket.CRASH, status__in=Ticket.OPEN).filter(Q(alerted_count=0) | grown)
            .exclude(owner_alert_unsure_at__gt=(now or timezone.now()) - UNSURE_WAIT).order_by("-count", "pk"))


def send_crash_rollup(now=None):
    """Cron: ONE email for every crash worth telling the owner about, however many there are and however many phones
    sent them. Returns how many crash tickets it covered."""
    now = now or timezone.now()
    if not owner_alerts.enabled():
        return 0
    send_crash_limit_notice(now)
    due = crashes_to_report(now)
    total = due.count()
    if not total:
        return 0
    listed = list(due[:LISTED_PER_EMAIL])
    new = sum(1 for t in listed if not t.alerted_count)
    lines = ["The app sent these error reports by itself. They hold no names, emails or anything a person typed, and nothing "
             "that links them to a person. A reply you write on a crash ticket is a private note: nobody sees it."]
    for t in listed:
        state = "new" if not t.alerted_count else f"now {t.count} reports, up from {t.alerted_count} when you were last told"
        about = (f"{state}: {t.title}. Reported {t.count} {'time' if t.count == 1 else 'times'}, app {t.app_version or 'version not given'} "
                 f"on {_phone(t)}" + (f", first on the screen {t.screen}" if t.screen else "")
                 + f". First seen {owner_alerts._when(t.first_seen)}, last seen {owner_alerts._when(t.last_seen)}.")
        if t.owner_alert_unsure_at:
            about += MAYBE_SENT
        lines.append(_list_line(t, about))
    if total > len(listed):
        lines.append(f"{total - len(listed)} more crashes are waiting. They come in the next email, in about 15 minutes.")
    if new_crashes_today(now) >= NEW_CRASHES_PER_DAY:
        lines.append(f"{NEW_CRASHES_PER_DAY} different crashes have come in over the last day. That is far more than an app produces by itself, "
                     "so new kinds are turned away until the number drops. Phones keep those reports and send them again later. "
                     "The ones listed in the admin keep counting.")
    lines.append("You hear about a crash when it is new and again when it has been reported 10, 100 and 1000 times. "
                 "Mark it Fixed to stop hearing about it on that app version. Mark it Closed and it opens again if it comes back.")
    growing = len(listed) - new
    subject = "Zero Harm crashes: " + ", ".join(filter(None, [f"{new} new" if new else "", f"{growing} growing" if growing else ""]))
    if not _notify_list(subject, lines, _slot_key("crashes", listed, now), listed):
        return 0
    stamp = timezone.now()
    for t in listed:
        # The count as it was read: reports that came in while the email was going still count toward the next step.
        # A crash is emailed again at each step, so the unsure mark goes once an email about it has gone out.
        t.alerted_count, t.owner_alerted_at, t.owner_alert_unsure_at = max(t.count, 1), stamp, None
    Ticket.objects.bulk_update(listed, ["alerted_count", "owner_alerted_at", "owner_alert_unsure_at"])  # one statement: all of them or none
    return len(listed)


# ---- The reporter's contact in GoHighLevel -------------------------------------------------------------

def wants_contact(ticket):
    return bool(ticket.kind in Ticket.PERSON_KINDS and ticket.email and ticket.may_contact)


def _nothing_to_take_off(err):
    """GoHighLevel refused to remove the tag because it is not there. Sign-in, permission and rate-limit answers are
    real failures and are tried again."""
    return 400 <= err.status < 500 and err.status not in (401, 403, 408, 429)


def contact_note(ticket, mark):
    lines = [f"Zero Harm support ticket {ticket.number} ({KIND_WORDS[ticket.kind]}, {SOURCE_WORDS.get(ticket.source, ticket.source)})"]
    if ticket.kind == Ticket.ANSWER:
        lines += [f"Question to OTIS: {ticket.question[:500] or '(not sent)'}", f"OTIS answered: {ticket.answer[:1200] or '(not sent)'}",
                  f"Their note: {ticket.text[:1500]}"]
    else:
        lines.append(f"What they wrote: {ticket.text[:2500]}")
    lines += [f"App: {ticket.app_version or 'version not given'} on {_phone(ticket)}", f"When: {owner_alerts._when(ticket.created_at)}",
              "OK to reply: yes", f"Ref: {mark}"]
    return "\n".join(lines)


def sync_contact(ticket, timeout=30):
    """Puts the reporter into GoHighLevel in three steps, each stamped when done so a retry starts where the last try
    stopped: (1) make or find their contact, (2) take the tag off and put it back on, so a "tag added" workflow
    fires for every ticket and not only a person's first, (3) add a note with the ticket number and what they
    wrote. Only for a person who gave an email and said it is OK to reply. True when all three are done."""
    try:
        if not (wants_contact(ticket) and ghl.configured()):
            return False
        row = Ticket.objects.filter(pk=ticket.pk)
        if not ticket.ghl_contact_id:
            first, last = split_name(ticket.name)
            contact = str(ghl.upsert_contact(ticket.email, first, last_name=last, timeout=timeout) or "")[:40]
            if not contact:
                raise ghl.GhlError("GoHighLevel returned no contact")
            ticket.ghl_contact_id = contact
            row.update(ghl_contact_id=contact)
        contact = ticket.ghl_contact_id
        if not ticket.ghl_tagged_at:
            try:
                ghl.remove_tags(contact, [TAG], timeout=timeout)
            except ghl.GhlError as err:
                if not _nothing_to_take_off(err):
                    raise
            ghl.add_tags(contact, [TAG], timeout=timeout)
            ticket.ghl_tagged_at = timezone.now()
            row.update(ghl_tagged_at=ticket.ghl_tagged_at)
        if not ticket.ghl_noted_at:
            # A note is the one call that is not safe to repeat. It carries a mark, and a retry looks for the mark
            # first: the note may be on the contact already, with only its answer lost on the way back.
            mark = note_mark("ticket", ticket.pk)
            if not _note_is_there(contact, mark, timeout):
                ghl.add_note(contact, contact_note(ticket, mark), timeout=timeout)
            ticket.ghl_noted_at = timezone.now()
            row.update(ghl_noted_at=ticket.ghl_noted_at)
        return True
    except Exception as err:
        log.error("Support: ticket %s to GoHighLevel failed: %s", ticket.pk, err)
        return False


def sync_waiting_contacts(now=None):
    """Cron: reporters from the last 2 days who are not fully in GoHighLevel yet, at most 50 a run. Each run takes
    the next stretch of the list, so a few that keep failing cannot keep the others from being tried."""
    now = now or timezone.now()
    if not ghl.configured():
        return 0
    waiting = (Ticket.objects.filter(kind__in=Ticket.PERSON_KINDS, may_contact=True, ghl_noted_at__isnull=True,
                                     created_at__gte=now - dt.timedelta(days=CONTACT_DAYS)).exclude(email="").order_by("created_at", "pk"))
    done = 0
    for pk in turn(waiting, CONTACTS_PER_RUN, now):
        ticket = Ticket.objects.filter(pk=pk, ghl_noted_at__isnull=True).first()  # as it is now
        done += bool(ticket and sync_contact(ticket))
    return done


# ---- The cron's one call -------------------------------------------------------------------------------

def run(now=None, say=None):
    """Everything the cron does for support, every 15 minutes: reports whose email did not go out, the one crash
    email, and reporters not yet in GoHighLevel. `say` gets one plain line per thing done (the cron prints them).
    A part that fails is logged with its traceback and the other parts still run; then this raises, so the cron
    shows the step as failed. Returns {"reports": n, "crashes": n, "contacts": n}."""
    now = now or timezone.now()
    parts = (("reports", send_waiting_reports, "{} reports emailed to the owner late"),
             ("crashes", send_crash_rollup, "the owner was emailed about {} crashes"),
             ("contacts", sync_waiting_contacts, "{} reporters added to GoHighLevel"))
    done, failed = {}, []
    for name, part, line in parts:
        try:
            done[name] = part(now)
        except Exception:
            log.exception("Support: the '%s' part of the cron step failed. The other parts still run.", name)
            done[name] = 0
            failed.append(name)
        if done[name] and say:
            say(f"Support: {line.format(done[name])}")
    if failed:
        raise RuntimeError(f"Support: {', '.join(failed)} failed (traceback in the log above)")
    return done
