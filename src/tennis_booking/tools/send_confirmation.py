"""`send_confirmation` -- domain tool shared by every agent architecture,
ported from the standalone `tennis-booking` project's `tools/email.py` and
adapted to this project's dict-schema tool convention. Sends (mocks sending)
a booking-confirmation email once `book_court` has produced a real
confirmation_id -- added so a completed booking looks like a real one end to
end, not just a bare confirmation number.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

SEND_CONFIRMATION_TOOL: dict[str, Any] = {
    "name": "send_confirmation",
    "description": (
        "Send the booking confirmation email to the user. Call only after "
        "book_court has returned a real confirmation_id -- never before, "
        "and never fabricate one."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "contact_email": {"type": "string"},
            "confirmation_id": {"type": "string"},
            "court_name": {"type": "string"},
            "area": {"type": "string"},
            "date": {"type": "string", "description": "ISO date, e.g. '2026-09-06'."},
            "time": {"type": "string", "description": "HH:MM"},
        },
        "required": ["contact_email", "confirmation_id", "court_name", "area", "date", "time"],
    },
}


def run_send_confirmation(args: dict) -> dict:
    return {
        "status": "email_sent",
        "recipient": args.get("contact_email"),
        "confirmation_id": args.get("confirmation_id"),
        "timestamp": datetime.now().isoformat(),
        "preview": (
            f"Booking Confirmation\n\n"
            f"Reference: {args.get('confirmation_id')}\n"
            f"Court: {args.get('court_name')}\n"
            f"Area: {args.get('area')}\n"
            f"Date: {args.get('date')}\n"
            f"Time: {args.get('time')}\n\n"
            f"Your booking is confirmed. See you on the court!"
        ),
    }
