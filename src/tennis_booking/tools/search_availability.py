"""`search_availability` -- domain tool shared by every agent architecture:
look up nearby tennis court availability for the collected preferences.
"""
from __future__ import annotations

from typing import Any

from tennis_booking.models import CourtAvailability
from tennis_booking.tools.live_courts import LiveCourtLookupError, find_nearby_courts

SEARCH_AVAILABILITY_TOOL: dict[str, Any] = {
    "name": "search_availability",
    "description": (
        "Look up nearby tennis court availability for a given area, date, "
        "surface preference, and indoor/outdoor preference. Returns courts "
        "with their open time slots and prices, sorted nearest to farthest "
        "(distance_km ascending) -- if the user just says a time without "
        "naming or otherwise distinguishing a specific court, and more than "
        "one returned court has that time open, prefer the first (closest) "
        "one rather than asking the user to disambiguate, unless the user's "
        "own wording makes clear they mean a particular court. Call this "
        "tool only after you have area, date, surface, duration, player "
        "count, and indoor/outdoor preference from the user."
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
    """Execute search_availability. Returns (tool_result_for_model, raw_courts).

    `area`/`date` are marked required in the tool schema, but a JSON Schema
    `required` list is only a hint to the model, not an enforced contract --
    a live call can still omit one. Report that back as a tool result the
    model can recover from, instead of an unhandled KeyError that kills the
    whole conversation.
    """
    missing = [f for f in ("area", "date") if not args.get(f)]
    if missing:
        return {"error": f"Missing required field(s): {', '.join(missing)}. Ask the user and try again."}, []

    try:
        courts = find_nearby_courts(
            area=args["area"],
            date=args["date"],
            surface=args.get("surface", "any"),
            indoor_outdoor=args.get("indoor_outdoor", "either"),
        )
    except LiveCourtLookupError as e:
        # Recoverable per agents/base.py's design: a bad area or a transient
        # network/service failure becomes a tool-result error the model can
        # relay and recover from, not an exception that kills the turn.
        return {"error": str(e)}, []

    result = {
        "courts": [
            {
                "court_id": c.court_id,
                "name": c.name,
                "area": c.area,
                "surface": c.surface,
                "indoor_outdoor": c.indoor_outdoor,
                "address": c.address,
                "rating": c.rating,
                "distance_km": c.distance_km,
                "open_times": [{"time": s.time, "price_usd": s.price_usd} for s in c.slots],
            }
            for c in courts
        ]
    }
    if not courts:
        result["note"] = "No courts matched. Consider asking the user to relax a preference."
    return result, courts
