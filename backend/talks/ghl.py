"""Small GoHighLevel API client (standard library only). Uses the private-integration token in GHL_PRIVATE_TOKEN."""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import uuid

from django.conf import settings

log = logging.getLogger(__name__)
BASE = "https://services.leadconnectorhq.com"
USER_AGENT = "ZeroHarmApp/1.0"


class GhlError(Exception):
    """A failed call. `status` is the HTTP code (0 when GoHighLevel could not be reached) and `body` what it answered."""

    def __init__(self, message, status=0, body=""):
        super().__init__(message)
        self.status, self.body = status, body


def configured():
    return bool(settings.GHL_PRIVATE_TOKEN and settings.GHL_LOCATION_ID)


def _headers(extra=None):
    # GoHighLevel sits behind Cloudflare, which refuses Python's default "Python-urllib" client name with a 403
    # (error 1010) before the token is even looked at. A named client gets through.
    return {
        "Authorization": f"Bearer {settings.GHL_PRIVATE_TOKEN}",
        "Version": "2021-07-28",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        **(extra or {}),
    }


def request(method, path, query=None, body=None, raw=None, content_type="application/json", timeout=30):
    url = BASE + path + (("?" + urllib.parse.urlencode(query)) if query else "")
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    headers = _headers({"Content-Type": content_type} if data is not None else None)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            text = res.read()
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as err:
        text = err.read().decode(errors="replace")[:300]
        raise GhlError(f"{method} {path} -> {err.code}: {text}", status=err.code, body=text) from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise GhlError(f"{method} {path} -> {err}") from err


def fetch_text(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read().decode("utf-8", errors="replace")


def list_templates(search, page_size=50):  # GHL allows at most 50 per page
    """All email templates whose name matches `search`.

    GoHighLevel lists them at /emails/builder under "builders" (the older /emails/locations/<id>/templates
    address answers 404). Each one carries "lastUpdated"; it is copied to "updatedAt", which the year sync
    uses to pick the newest of two templates for the same issue."""
    items, offset = [], 0
    while True:
        data = request("GET", "/emails/builder",
                       {"locationId": settings.GHL_LOCATION_ID, "name": search, "limit": page_size, "offset": offset})
        batch = data.get("builders") or []
        items.extend({**t, "updatedAt": t.get("updatedAt") or t.get("lastUpdated") or ""} for t in batch)
        if len(batch) < page_size:
            return items
        offset += page_size


def upload_media(filename, content, mime="application/pdf"):
    """Uploads bytes to Media Storage. Returns the file's URL."""
    boundary = uuid.uuid4().hex
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"name\"\r\n\r\n{filename}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    data = request("POST", "/medias/upload-file", raw=b"".join(parts), content_type=f"multipart/form-data; boundary={boundary}", timeout=60)
    url = data.get("url") or data.get("fileUrl")
    if not url:
        raise GhlError(f"Upload returned no URL: {str(data)[:200]}")
    return url


def upsert_contact(email, first_name="", company="", tags=(), last_name="", source="Zero Harm app", timeout=30):
    """Creates or updates the contact, then adds the tags. The tags are added in a second call on purpose: tags sent
    with the upsert itself replace every tag the contact already has, which would take a person off the newsletter."""
    payload = {"locationId": settings.GHL_LOCATION_ID, "email": email}
    if source:
        payload["source"] = source
    if first_name:
        payload["firstName"] = first_name
    if last_name:
        payload["lastName"] = last_name
    if company:
        payload["companyName"] = company
    data = request("POST", "/contacts/upsert", body=payload, timeout=timeout)
    contact_id = (data.get("contact") or {}).get("id", "")
    if contact_id and tags:
        add_tags(contact_id, tags, timeout=timeout)
    return contact_id


def contact_tags(contact_id, timeout=30):
    """The tags on one contact."""
    return list((request("GET", f"/contacts/{contact_id}", timeout=timeout).get("contact") or {}).get("tags") or [])


def find_contact(email, timeout=30):
    """The contact with this email, or {} when there is none. Only looks: unlike the upsert, it never makes a contact."""
    data = request("GET", "/contacts/search/duplicate", {"locationId": settings.GHL_LOCATION_ID, "email": email}, timeout=timeout)
    return data.get("contact") or {}


def add_tags(contact_id, tags, timeout=30):
    request("POST", f"/contacts/{contact_id}/tags", body={"tags": list(tags)}, timeout=timeout)


def remove_tags(contact_id, tags, timeout=30):
    request("DELETE", f"/contacts/{contact_id}/tags", body={"tags": list(tags)}, timeout=timeout)


def add_note(contact_id, text, timeout=30):
    request("POST", f"/contacts/{contact_id}/notes", body={"body": text}, timeout=timeout)


def send_email(contact_id, subject, html, timeout=30):
    """Sends one email to a contact through GoHighLevel's Conversations API (the location's own email sender)."""
    request("POST", "/conversations/messages", body={"type": "Email", "contactId": contact_id, "subject": subject, "html": html}, timeout=timeout)
