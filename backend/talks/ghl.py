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


class GhlError(Exception):
    pass


def configured():
    return bool(settings.GHL_PRIVATE_TOKEN and settings.GHL_LOCATION_ID)


def _headers(extra=None):
    return {"Authorization": f"Bearer {settings.GHL_PRIVATE_TOKEN}", "Version": "2021-07-28", "Accept": "application/json", **(extra or {})}


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
        raise GhlError(f"{method} {path} -> {err.code}: {err.read().decode(errors='replace')[:300]}") from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise GhlError(f"{method} {path} -> {err}") from err


def fetch_text(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "ZeroHarmApp/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read().decode("utf-8", errors="replace")


def list_templates(search, page_size=50):  # GHL allows at most 50 per page
    """All email templates whose name matches `search`."""
    items, offset = [], 0
    while True:
        data = request("GET", f"/emails/locations/{settings.GHL_LOCATION_ID}/templates",
                       {"search": search, "limit": page_size, "offset": offset})
        batch = data.get("items") or data.get("templates") or []
        items.extend(batch)
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


def upsert_contact(email, first_name="", company="", tags=()):
    payload = {"locationId": settings.GHL_LOCATION_ID, "email": email, "tags": list(tags), "source": "Zero Harm app"}
    if first_name:
        payload["firstName"] = first_name
    if company:
        payload["companyName"] = company
    data = request("POST", "/contacts/upsert", body=payload)
    return (data.get("contact") or {}).get("id", "")


def add_note(contact_id, text):
    request("POST", f"/contacts/{contact_id}/notes", body={"body": text})
