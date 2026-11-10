"""Approximate place (city, state, country) for a network address, from a MaxMind-format city database on disk.

The address is only looked up here. It is never stored or logged. When the database file or the maxminddb package is
missing, or the address is private or malformed, the answer is blank and nothing is raised.
"""
import ipaddress
import re
import os
import threading

from django.conf import settings

BLANK = {"country": "", "region": "", "city": ""}
_lock = threading.Lock()
_reader = None
_reader_path = None  # the path _reader was opened from (or failed to open from), so each path is tried once per process


def _open(path):
    import maxminddb

    return maxminddb.open_database(path)


def _get_reader():
    """The database reader, opened once per process. gunicorn runs one process with 8 threads, hence the lock."""
    global _reader, _reader_path
    path = str(settings.GEOIP_DB_PATH or "")
    if _reader_path == path:
        return _reader
    with _lock:
        if _reader_path != path:
            reader = None
            if path and os.path.exists(path):
                try:
                    reader = _open(path)
                except Exception:  # package not installed, or a damaged file: carry on without places
                    reader = None
            _reader, _reader_path = reader, path
    return _reader


def reset():
    """Forget the open database, so the next lookup opens the file again (used after geo_update and in tests)."""
    global _reader, _reader_path
    with _lock:
        if _reader is not None:
            try:
                _reader.close()
            except Exception:
                pass
        _reader, _reader_path = None, None


def available() -> bool:
    """True when a database is in use. The back office shows the DB-IP credit line only then."""
    return _get_reader() is not None


def _name(node) -> str:
    names = node.get("names") if isinstance(node, dict) else None
    return str(names.get("en") or "")[:80] if isinstance(names, dict) else ""


def lookup(ip) -> dict:
    """{"country": "US", "region": "Texas", "city": "Houston"}, with blanks for whatever isn't known. Never raises."""
    try:
        address = ipaddress.ip_address(str(ip or "").strip())
        if not address.is_global:  # private, loopback, link-local and reserved ranges have no place
            return dict(BLANK)
        reader = _get_reader()
        if reader is None:
            return dict(BLANK)
        record = reader.get(str(address))
        if not isinstance(record, dict):
            return dict(BLANK)
        country = str((record.get("country") or {}).get("iso_code") or "").upper()
        subdivisions = record.get("subdivisions") or []
        return {
            "country": country if len(country) == 2 and country.isalpha() else "",
            "region": _name(subdivisions[0]) if subdivisions else "",
            # Some city databases add a district in brackets ("New York (Manhattan)"). Drop it so one city is one row.
            "city": re.sub(r"\s*\([^)]*\)\s*$", "", _name(record.get("city") or {})),
        }
    except Exception:
        return dict(BLANK)
