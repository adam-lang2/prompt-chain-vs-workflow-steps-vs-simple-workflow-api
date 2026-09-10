"""`search_availability` -- domain tool shared by every agent architecture:
look up nearby tennis court availability for the collected preferences.
"""
from __future__ import annotations

from typing import Any

from tennis_booking.mock_courts import search_availability as _search_availability
from tennis_booking.models import CourtAvailability

SEARCH_AVAILABILITY_TOOL: dict[str, Any] = {
    "name": "search_availability",
    "description": (
        "Look up nearby tennis court availability for a given area, date, "
        "surface preference, and indoor/outdoor preference. Returns courts "
        "with their open time slots and prices. Call this only after you "
        "have area, date, surface, duration, player count, and "
        "indoor/outdoor preference from the user."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "area": {"type": "string", "description": "City or neighborhood, e.g. 'downtown'."},
            "date": {"type": "string", "description": "ISO date, e.g. '2026-09-06'."},
            "surface": {
                "type": "string",
                "enum": ["hard", "clay", "grass", "indoor_carpet", "any"],
            },
            "indoor_outdoor": {
                "type": "string",
                "enum": ["indoor", "outdoor", "either"],
            },
        },
        "required": ["area", "date", "surface", "indoor_outdoor"],
    },
}


def run_search_availability(args: dict) -> tuple[dict, list[CourtAvailability]]:
    """Execute search_availability. Returns (tool_result_for_model, raw_courts)."""
    courts = _search_availability(
        area=args["area"],
        date=args["date"],
        surface=args.get("surface", "any"),
        indoor_outdoor=args.get("indoor_outdoor", "either"),
    )
    result = {
        "courts": [
            {
                "court_id": c.court_id,
                "name": c.name,
                "area": c.area,
                "surface": c.surface,
                "indoor_outdoor": c.indoor_outdoor,
                "open_times": [{"time": s.time, "price_usd": s.price_usd} for s in c.slots],
            }
            for c in courts
        ]
    }
    if not courts:
        result["note"] = "No courts matched. Consider asking the user to relax a preference."
    return result, courts
