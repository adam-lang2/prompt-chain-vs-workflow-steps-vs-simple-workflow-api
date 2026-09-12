"""Live tennis-court lookup: real geocoding + OpenStreetMap court data,
ported from the standalone `tennis-booking` project's `tools/courts.py` and
adapted to this project's `CourtAvailability`/`TimeSlot` shape so it can drop
straight into `search_availability`'s tool-action step without changing
anything downstream (ask_time, confirm_booking, book_court, scoring, ...).

Unlike `mock_courts.py` (a small fixed directory of 9 courts across 4 named
areas, purely so pytest assertions stay stable), this module makes two real
network calls per search: Nominatim to geocode whatever free-text area the
user gave, then the Overpass API to find actual tennis courts/sports centres
near that point. That makes `area` genuinely free text (not one of a fixed
enum) and means results -- names, addresses, distances -- are real, at the
cost of the search no longer being deterministic or offline.

Per-slot open/closed availability has no live-data equivalent (no public API
exposes real booking calendars for these venues), so it's still the same
deterministic hash of (court_id, date, time) `mock_courts.py` uses -- kept
here rather than duplicated, see `_slot_is_open`/`CANDIDATE_TIMES` there.
"""
from __future__ import annotations

import httpx
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

from tennis_booking.mock_courts import CANDIDATE_TIMES, _slot_is_open
from tennis_booking.models import CourtAvailability, TimeSlot

_SEARCH_RADIUS_DEGREES = 0.05  # ~5km
_MAX_RESULTS = 10
_GEOCODE_TIMEOUT_SECONDS = 10
_OVERPASS_TIMEOUT_SECONDS = 10
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# OSM's `surface` tag records the literal paving material (concrete, asphalt,
# tartan, acrylic, paved, artificial_turf, ...), not this app's coarser
# hard/clay/grass/indoor_carpet vocabulary -- real venues are almost never
# tagged "hard" outright, so passing the raw tag straight through would make
# a `surface="hard"` filter match nothing. Anything not recognized here
# (including an absent tag) buckets to "hard", the overwhelmingly common
# real-world case.
_SURFACE_TAG_TO_APP_SURFACE: dict[str, str] = {
    "clay": "clay",
    "grass": "grass",
    "carpet": "indoor_carpet",
    "indoor_carpet": "indoor_carpet",
}


def _normalize_surface(raw_tag: str | None) -> str:
    return _SURFACE_TAG_TO_APP_SURFACE.get((raw_tag or "").lower(), "hard")


class LiveCourtLookupError(Exception):
    """Raised for a recoverable lookup failure (bad location, no results,
    network error) -- callers turn this into a tool-result `error` field
    rather than letting it propagate and kill the conversation, per
    `agents/base.py`'s design (see `tools/search_availability.py`).
    """


def _geocode(area: str) -> tuple[float, float]:
    geolocator = Nominatim(user_agent="tennis_booking_eval_agent")
    try:
        result = geolocator.geocode(area, timeout=_GEOCODE_TIMEOUT_SECONDS)
    except Exception as e:  # geopy raises its own exception hierarchy for timeouts/service errors
        raise LiveCourtLookupError(f"Could not look up location {area!r}: {e}") from e
    if not result:
        raise LiveCourtLookupError(f"Could not find a location matching {area!r}.")
    return result.latitude, result.longitude


def _query_overpass(lat: float, lon: float) -> list[dict]:
    r = _SEARCH_RADIUS_DEGREES
    bbox = (lat - r, lon - r, lat + r, lon + r)
    query = f"""[out:json];
(
  node["leisure"="pitch"]["sport"="tennis"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
  way["leisure"="pitch"]["sport"="tennis"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
  node["amenity"="sports_centre"]["sport"="tennis"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
  way["amenity"="sports_centre"]["sport"="tennis"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
);
out center;
"""
    try:
        response = httpx.post(
            _OVERPASS_URL,
            data=query,
            timeout=_OVERPASS_TIMEOUT_SECONDS,
            headers={"User-Agent": "tennis-booking-eval-agent"},
        )
        response.raise_for_status()
        return response.json().get("elements", [])
    except httpx.HTTPError as e:
        raise LiveCourtLookupError(f"Court lookup service failed: {e}") from e


def _open_times_for(court_id: str, date: str) -> list[str]:
    return [t for t in CANDIDATE_TIMES if _slot_is_open(court_id, date, t)]


def find_nearby_courts(
    area: str,
    date: str,
    surface: str = "any",
    indoor_outdoor: str = "either",
) -> list[CourtAvailability]:
    """Geocode `area`, look up real nearby tennis venues via Overpass, filter
    by `surface`/`indoor_outdoor` (best-effort -- OSM rarely tags surface,
    and has no indoor/outdoor flag at all: `amenity=sports_centre` is treated
    as indoor, `leisure=pitch` as outdoor), and attach deterministic mock
    time slots per matching court for `date`. Raises `LiveCourtLookupError`
    on a recoverable failure (bad area, network error, no venues found) --
    callers should catch it and surface `.args[0]` as a tool-result error.
    """
    lat, lon = _geocode(area)
    elements = _query_overpass(lat, lon)

    candidates: list[tuple[float, dict, str, str]] = []
    for element in elements:
        tags = element.get("tags", {})
        center = element.get("center") or {"lat": element.get("lat"), "lon": element.get("lon")}
        if not center or center.get("lat") is None:
            continue

        element_surface = _normalize_surface(tags.get("surface"))
        element_indoor_outdoor = "indoor" if tags.get("amenity") == "sports_centre" else "outdoor"
        if surface not in ("any", None) and element_surface != surface:
            continue
        if indoor_outdoor not in ("either", None) and element_indoor_outdoor != indoor_outdoor:
            continue

        distance_km = round(geodesic((lat, lon), (center["lat"], center["lon"])).kilometers, 2)
        candidates.append((distance_km, element, element_surface, element_indoor_outdoor))

    if not candidates:
        raise LiveCourtLookupError(
            f"No tennis courts found near {area!r} matching the requested surface/indoor-outdoor preference."
        )

    candidates.sort(key=lambda c: c[0])

    results: list[CourtAvailability] = []
    for distance_km, element, element_surface, element_indoor_outdoor in candidates[:_MAX_RESULTS]:
        tags = element.get("tags", {})
        court_id = f"osm_{element['id']}"
        price_per_hour = round(25.0 + 10.0 * distance_km, 2)
        open_times = _open_times_for(court_id, date)
        if not open_times:
            continue
        slots = [TimeSlot(time=t, price_usd=price_per_hour) for t in open_times]
        results.append(
            CourtAvailability(
                court_id=court_id,
                name=tags.get("name", "Tennis Court"),
                area=area,
                surface=element_surface,
                indoor_outdoor=element_indoor_outdoor,
                slots=slots,
                address=tags.get("addr:full", area),
                rating=round(4.0 + (0.5 if tags.get("website") else 0.0), 1),
                distance_km=distance_km,
            )
        )

    return results
