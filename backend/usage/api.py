"""The anonymous daily usage count on API v2 (/api/v2/app/open): which days a phone opened the app and roughly where.

What is kept: one row per phone per day, with the phone known only by the same salted hash Monday Minute uses, its
platform and app version, and an approximate city, state and country. What is never kept or logged: the network
address (it is used for the place lookup and the rate limit, then dropped), names, emails and coordinates.
"""
import re
import unicodedata
from typing import Literal

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema
from pydantic import Field, field_validator

from monday.api import _hash  # one salt for install ids across the whole backend
from zeroharm.net import ScopedThrottle, client_ip

from . import geo
from .models import AppOpen

router = Router(tags=["App"])

# The weather feature gives the phone "City, ST" for US points. The network lookup spells states out, so do the same
# here: otherwise "TX" and "Texas" would be two rows in the back office.
US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands",
    "AS": "American Samoa", "MP": "Northern Mariana Islands",
}
# A later open on the same day may only improve the place: unknown -> network lookup -> the phone's own location.
RANK = {"": 0, AppOpen.NETWORK: 1, AppOpen.PHONE: 2}


def _clean(value):
    """Drop control and other invisible characters and tidy the spaces. Runs before the length checks."""
    if not isinstance(value, str):
        return value
    return " ".join("".join(ch if not unicodedata.category(ch).startswith("C") else " " for ch in value).split())


class PlaceIn(Schema):
    city: str = Field(default="", max_length=80)
    region: str = Field(default="", max_length=80, description="State or region, e.g. TX or Texas")
    country: str = Field(default="", max_length=2, description="Two-letter country code, e.g. US")

    _tidy = field_validator("city", "region", "country", mode="before")(_clean)

    @field_validator("country")
    @classmethod
    def _two_letters(cls, value):
        if value and not (len(value) == 2 and value.isascii() and value.isalpha()):
            raise ValueError("Send a two-letter country code.")
        return value.upper()


class OpenIn(Schema):
    install_id: str = Field(min_length=8, max_length=80, description="Random id the app makes once per install")
    platform: Literal["ios", "android"]
    app_version: str = Field(default="", max_length=20)
    place: PlaceIn | None = Field(default=None, description="Only when the phone already knows it from the weather feature")

    _tidy = field_validator("app_version", mode="before")(_clean)

    @field_validator("place", mode="before")
    @classmethod
    def _an_object(cls, value):
        if value is not None and not isinstance(value, dict):
            raise ValueError("Send place as an object with city, region and country.")
        return value


class Ok(Schema):
    ok: bool


# A city name: letters, spaces, periods, apostrophes and hyphens. No digits, @ or markup, so an email address,
# coordinates or junk can never be stored as a "city".
CITY = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ .'’-])*$")
STATE_NAMES = {name.lower(): name for name in US_STATES.values()}


def _phone_place(sent: PlaceIn | None) -> dict | None:
    """Only what the app can really send is accepted: a US city and state from the weather feature. Anything else is
    ignored (not rejected), and the place comes from the network instead."""
    if not sent or sent.country not in ("US", "") or not CITY.match(sent.city):
        return None
    region = US_STATES.get(sent.region.upper()) or STATE_NAMES.get(sent.region.lower())
    if not region:
        return None
    return {"city": sent.city, "region": region, "country": "US", "source": AppOpen.PHONE}


def _place(request: HttpRequest, sent: PlaceIn | None) -> dict:
    """The phone's own place when it sent a valid one, otherwise an approximate place from the network address."""
    from_phone = _phone_place(sent)
    if from_phone:
        return from_phone
    found = geo.lookup(client_ip(request))  # the address goes no further than this call
    return {**found, "source": AppOpen.NETWORK if any(found.values()) else ""}


# Why a limit per network: a phone sends this once a day, so one connection (a plant's Wi-Fi, a phone carrier's shared
# address) has no reason to send more than a few dozen an hour. Without the limit, one connection could invent phone
# ids and flood the table with rows. 60 an hour keeps real crews counted and caps what a script can add.
# ScopedThrottle (zeroharm/net.py) counts per network, not per exact address: a home or mobile IPv6 connection owns a
# whole /64 and could otherwise switch addresses to dodge the limit. Its key is a salted hash, so no readable address
# sits in the cache, and the scope gives this endpoint a counter of its own.
@router.post("/open", response=Ok, throttle=[ScopedThrottle("60/h", scope="app-open")], summary="Anonymous once-a-day usage count")
def app_open(request: HttpRequest, body: OpenIn):
    """The app sends this at most once a day, and only while the person has "Anonymous usage count" switched on."""
    if not settings.USAGE_ENABLED:
        return {"ok": True}  # switched off on the server: say thanks, keep nothing
    day, install_hash = timezone.localdate(), _hash(body.install_id)
    row = AppOpen.objects.filter(day=day, install_hash=install_hash).first()
    if row and (row.source == AppOpen.PHONE or (row.source == AppOpen.NETWORK and not _phone_place(body.place))):
        return {"ok": True}  # nothing a second open could add
    place = _place(request, body.place)
    if not row:
        row, created = AppOpen.objects.get_or_create(
            day=day, install_hash=install_hash, defaults={"platform": body.platform, "app_version": body.app_version, **place})
        if created:
            return {"ok": True}
    if RANK[place["source"]] > RANK[row.source]:
        AppOpen.objects.filter(pk=row.pk).update(**place)
    return {"ok": True}
