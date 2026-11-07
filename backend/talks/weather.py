"""Current conditions and active alerts from the US National Weather Service (free, public domain, US only)."""
import json
import urllib.request

from django.core.cache import cache

UA = {"User-Agent": "ZeroHarmApp/1.0 (https://trainovate.ai)", "Accept": "application/geo+json"}


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10) as res:
        return json.loads(res.read())


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
    """lat/lon already rounded to 2 decimals (about 1 km) by the app. Cached 10 minutes per point; nothing is stored."""
    key = f"wx:{lat:.2f},{lon:.2f}"
    hit = cache.get(key)
    if hit:
        return hit
    point = _get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")["properties"]
    place = point.get("relativeLocation", {}).get("properties", {})
    hourly = _get(point["forecastHourly"])["properties"]["periods"][0]
    temp = hourly["temperature"] if hourly.get("temperatureUnit") == "F" else round(hourly["temperature"] * 9 / 5 + 32)
    rh = (hourly.get("relativeHumidity") or {}).get("value")
    hi = heat_index_f(temp, rh) if rh is not None and temp >= 80 else None
    alerts = _get(f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}").get("features", [])
    data = {
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
    cache.set(key, data, 600)
    return data
