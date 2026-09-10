"""`book_court` -- domain tool shared by every agent architecture: book a
specific court/time for the user once they've confirmed a booking summary.
"""
from __future__ import annotations

import uuid
from typing import Any

from tennis_booking.mock_courts import find_listing

BOOK_COURT_TOOL: dict[str, Any] = {
    "name": "book_court",
    "description": (
        "Book a specific tennis court time slot for the user. Call only "
        "after the user has picked a court/time from search_availability "
        "results and confirmed the booking."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "court_id": {"type": "string"},
            "date": {"type": "string"},
            "time": {"type": "string", "description": "HH:MM"},
            "duration_minutes": {"type": "integer", "enum": [60, 90, 120]},
            "num_players": {"type": "integer"},
            "skill_level": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]},
            "equipment_rental": {"type": "boolean", "description": "Needs a racket rented."},
            "contact_name": {"type": "string"},
            "contact_email": {"type": "string"},
        },
        "required": [
            "court_id",
            "date",
            "time",
            "duration_minutes",
            "num_players",
            "skill_level",
            "equipment_rental",
            "contact_name",
            "contact_email",
        ],
    },
}


def run_book_court(args: dict) -> dict:
    listing = find_listing(args["court_id"])
    confirmation_id = f"TC-{uuid.uuid4().hex[:8].upper()}"
    return {
        "confirmed": True,
        "confirmation_id": confirmation_id,
        "court_name": listing.name if listing else args["court_id"],
        **args,
    }
