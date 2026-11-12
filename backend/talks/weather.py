"""Current conditions and active alerts from the US National Weather Service (free, public domain, US only)."""
import json
import time
import urllib.request

from django.core.cache import cache

UA = {"User-Agent": "ZeroHarmApp/1.0 (https://trainovate.ai)", "Accept": "application/geo+json"}
# One lookup is three requests to the weather service, one after the other, while the phone waits (it gives up after
# 10 seconds) and one of the server's 8 threads is held. Each used to get 10 seconds, 30 in all.
CALL_SECONDS = 4     # the most one request may wait
LOOKUP_SECONDS = 9   # the most the three may wait together
FRESH_SECONDS = 600  # how long an answer is served from the cache
FAILED_SECONDS = 120  # how long a point whose lookup failed is not tried again


def _get(url, timeout=CALL_SECONDS):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as res:
        return json.loads(res.read())


def _key(lat, lon):
    return f"wx:{lat:.2f},{lon:.2f}"


def cached(lat, lon):
    """The answer for this point if it was looked up in the last 10 minutes, else None. Costs nothing."""
    return cache.get(_key(lat, lon)) or None


def failed_lately(lat, lon):
    """True when a lookup of this point failed in the last two minutes. The caller then answers "unavailable" without
    asking again, so an outage of the weather service (or a point it has no forecast for) is not hammered."""
    return bool(cache.get("wx-failed:" + _key(lat, lon)))


def heat_index_f(t, rh):
    """NWS Rothfusz heat index (°F). Below 80°F the simple form is used, as NWS does."""
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    if (simple + t) / 2 < 80:
        return round(simple)
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 0.00683783 * t * t
          - 0.05481717 * rh * rh + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
    if rh < 13 and 80 <= t <= 112:
        hi -= ((13 - rh) / 4) * ((17 - abs(t - 95)) / 17) ** 0.5
    elif rh > 85 and 80 <= t <= 87:
        hi += ((rh - 85) / 10) * ((87 - t) / 5)
    return round(hi)


def conditions(lat, lon):
    """lat/lon already rounded to 2 decimals (about 1 km) by the app. Cached 10 minutes per point; nothing is stored.
    A lookup that fails raises, and the point is remembered as failed for two minutes (see failed_lately)."""
    hit = cached(lat, lon)
    if hit:
        return hit
    try:
        data = _look_up(lat, lon)
    except Exception:
        cache.set("wx-failed:" + _key(lat, lon), True, FAILED_SECONDS)
        raise
    cache.set(_key(lat, lon), data, FRESH_SECONDS)
    return data


def _look_up(lat, lon):
    """The three requests to the weather service. Together they wait at most LOOKUP_SECONDS."""
    deadline = time.monotonic() + LOOKUP_SECONDS

    def get(url):
        left = deadline - time.monotonic()
        if left < 0.5:
            raise TimeoutError("the weather service took too long")
        return _get(url, timeout=min(CALL_SECONDS, left))

    point = get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")["properties"]
    place = point.get("relativeLocation", {}).get("properties", {})
    hourly = get(point["forecastHourly"])["properties"]["periods"][0]
    temp = hourly["temperature"] if hourly.get("temperatureUnit") == "F" else round(hourly["temperature"] * 9 / 5 + 32)
    rh = (hourly.get("relativeHumidity") or {}).get("value")
    hi = heat_index_f(temp, rh) if rh is not None and temp >= 80 else None
    alerts = get(f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}").get("features", [])
    return {
        "place": ", ".join(p for p in (place.get("city"), place.get("state")) if p),
        "temp_f": temp,
        "summary": hourly.get("shortForecast", ""),
        "heat_index_f": hi,
        "wind": hourly.get("windSpeed", ""),
        # Heat illness risk rises from a heat index of 91°F (NWS / OSHA heat guidance); 32°F and below brings cold stress.
        "hazard": "heat" if (hi or temp) >= 91 else "cold" if temp <= 32 else None,
        "alerts": [{"event": a["properties"].get("event"), "severity": a["properties"].get("severity"),
                    "headline": a["properties"].get("headline")} for a in alerts[:3]],
    }
