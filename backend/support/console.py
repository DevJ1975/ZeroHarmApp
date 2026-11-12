"""The content console's ticket endpoints (/api/console/tickets/). Same Bearer key, same checks and the same error
shape as the rest of the console: the helpers come from talks/console.py."""
from django.http import JsonResponse
from django.utils import timezone

from talks.console import Bad, _apply, _body, _done, _iso, choice, console_view, text

from .models import Ticket

LIST_LIMIT = 200  # tickets one list answer holds; the filters are how the owner narrows it
STATUS_FILTERS = ("open", "all") + tuple(s for s, _ in Ticket.STATUSES)
KIND_FILTERS = ("all",) + tuple(k for k, _ in Ticket.KINDS)
# What the owner may change. Everything else on a ticket came from a phone and stays as it was sent.
TICKET_CHECKS = {"status": choice([s for s, _ in Ticket.STATUSES]), "reply": text(2000), "owner_note": text(2000)}


def ticket_admin(t):
    return {
        "id": t.pk, "number": t.number, "kind": t.kind, "status": t.status, "source": t.source, "title": t.title, "text": t.text,
        "reply": t.reply, "owner_note": t.owner_note, "count": t.count, "app_version": t.app_version, "platform": t.platform,
        "os_version": t.os_version, "device": t.device, "screen": t.screen, "lang": t.lang, "name": t.name, "email": t.email,
        "may_contact": t.may_contact, "created_at": _iso(t.created_at), "updated_at": _iso(t.updated_at), "last_seen": _iso(t.last_seen),
        # Filled in only for a flagged OTIS answer.
        "question": t.question, "answer": t.answer, "model_key": t.model_key,
    }


def crash_admin(c):
    return {"created_at": _iso(c.created_at), "fatal": c.fatal, "name": c.name, "message": c.message, "stack": c.stack, "screen": c.screen,
            "app_version": c.app_version, "platform": c.platform, "os_version": c.os_version, "device": c.device}


@console_view("GET")
def tickets(request):
    """?status=open|new|in_progress|fixed|closed|all (open = new + in progress, the default) and
    ?kind=problem|crash|answer|all (all is the default). Latest activity first."""
    status = choice(STATUS_FILTERS)("status", request.GET.get("status") or "open")
    kind = choice(KIND_FILTERS)("kind", request.GET.get("kind") or "all")
    rows = Ticket.objects.all()
    if status == "open":
        rows = rows.filter(status__in=Ticket.OPEN)
    elif status != "all":
        rows = rows.filter(status=status)
    if kind != "all":
        rows = rows.filter(kind=kind)
    return JsonResponse({"tickets": [ticket_admin(t) for t in rows[:LIST_LIMIT]]})


@console_view("GET", "PATCH")
def ticket(request, pk):
    t = Ticket.objects.filter(pk=pk).first()
    if not t:
        raise Bad("No ticket with that number.", 404)
    if request.method == "PATCH":
        was = t.status
        changed = _apply(t, _body(request), TICKET_CHECKS)
        if "status" in changed and t.status == was:
            changed.remove("status")  # sent as it already was: nothing to write, see below
        if "status" in changed:
            wanted, t.status = t.status, was
            t.set_status(wanted, timezone.now())  # keeps closed_at in step with the status
            changed.append("closed_at")
        if changed:
            # Only what the owner changed. A full save would put back the count, last_seen and email stamps as they
            # were when this request read the ticket, undoing crash reports and cron work that landed in between.
            # The status and closed_at go only when the owner changed the status: a crash report that opened the
            # ticket again meanwhile is not closed again by a note.
            t.save(update_fields=[*changed, "updated_at"])
            _done("edited ticket", t.number, fields=changed)
        return JsonResponse({"ticket": ticket_admin(t)})
    return JsonResponse({"ticket": ticket_admin(t), "crashes": [crash_admin(c) for c in t.crashes.all()[:50]]})
