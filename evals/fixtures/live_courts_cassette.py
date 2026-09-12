"""Recorded Nominatim/Overpass responses for the scripted eval suite.

`tools/live_courts.py` makes two real network calls per search
(`_geocode`, `_query_overpass`) -- appropriate for a live comparison run, but
wrong for `evals/test_scripted_booking.py`, which needs the exact same
result for the exact same query on every run so a scenario's `expected`
dict stays meaningful. `evals/conftest.py` monkeypatches those two functions
to read from here instead, for every `eval`-marked test.

Each cassette file under `evals/fixtures/live_courts/<key>.json` is a real,
one-time-recorded `{lat, lon, elements}` -- `lat`/`lon` came from a real
Nominatim geocode of the area name, `elements` from a real Overpass query
for tennis courts/sports-centres within ~5km of that point (see
`tools/live_courts.py`'s `_query_overpass` for the exact query). Recorded
2026-09-12. `ALIASES` maps each cassette to the free-text phrasings a
scenario (or a model relaying it) might plausibly pass as `area` --
matching is substring-based, same spirit as the old `mock_courts._matches_area`.
"""
from __future__ import annotations

import json
from pathlib import Path

from tennis_booking.tools.live_courts import LiveCourtLookupError

_FIXTURES_DIR = Path(__file__).parent / "live_courts"

# Deliberately generous -- a model relaying the user's area often normalizes
# or broadens it (e.g. "Golden Gate Park" -> "San Francisco"), which is
# perfectly reasonable agent behavior and shouldn't crash the eval just
# because this cassette only recorded coordinates for the specific park.
ALIASES: dict[str, tuple[str, ...]] = {
    "golden_gate_park": ("golden gate park", "san francisco"),
    "prospect_park": ("prospect park", "brooklyn"),
    "discovery_park": ("discovery park", "magnolia, seattle", "magnolia seattle", "seattle"),
    "newport_hof": ("international tennis hall of fame", "newport", "newport, rhode island"),
}


def _load(key: str) -> dict:
    with open(_FIXTURES_DIR / f"{key}.json") as f:
        return json.load(f)


_CASSETTES: dict[str, dict] = {key: _load(key) for key in ALIASES}


class UnknownCassetteArea(LiveCourtLookupError):
    """Raised when a scenario's `area` doesn't match any recorded cassette.
    Subclasses `LiveCourtLookupError` (not bare `Exception`) so it's caught
    by `search_availability.run_search_availability`'s existing except
    clause exactly like a real geocoding failure would be -- recoverable, a
    tool-result error the agent can react to -- rather than crashing the
    whole eval with an unhandled exception. Still worth checking the test
    failure it produces: it usually means either a genuinely novel area
    phrasing worth adding an alias for, or a real "agent picked an
    unreasonable area" bug.
    """


def geocode(area: str) -> tuple[float, float]:
    q = area.strip().lower()
    for key, aliases in ALIASES.items():
        if any(alias in q or q in alias for alias in aliases):
            cassette = _CASSETTES[key]
            return cassette["lat"], cassette["lon"]
    raise UnknownCassetteArea(
        f"No recorded live_courts cassette matches area {area!r}. Known cassettes: "
        f"{list(ALIASES)}. Either the scenario's area text needs an alias added "
        "above, or the model passed something unexpected -- check the test failure."
    )


def query_overpass(lat: float, lon: float) -> list[dict]:
    for cassette in _CASSETTES.values():
        if cassette["lat"] == lat and cassette["lon"] == lon:
            return cassette["elements"]
    raise UnknownCassetteArea(f"No recorded cassette for coordinates ({lat}, {lon}).")
