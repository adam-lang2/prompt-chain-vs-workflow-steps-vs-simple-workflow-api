"""`book_tennis_court` -- agent-1's only tool in `agents/simple_workflow_api_agent.py`,
backed by `workflow_engine.BookingWorkflowEngine` (`LangGraphStepEngine`, see that
module's docstring for how it computes the current step). Takes a single
`updates` array of `{slot, value}` deltas -- any combination, in one call:
a correction to something answered earlier, the current node's answer, one
or more not-yet-reached nodes the user already answered, or several of
these at once, every slot always legal regardless of which node is
currently active; invalid values round-trip through `errors` (keyed by slot
name, see `workflow_engine.agent.SLOT_VALIDATORS`) rather than being
rejected by the tool-calling layer. The response's fields
(`current_node`/`instructions`/`current_node_slots`,
`upcoming_instructions`, `available_courts`/`note`, `booking_summary`,
`confirmation_id`/`date`/`time`, `applied`/`errors`) are present depending
on the current step.
"""
from __future__ import annotations

from typing import Any

# Kept here (not just inlined in the description string) so the description
# text and the actual enum of legal `slot` values can never drift apart.
_ALL_SLOTS: tuple[str, ...] = (
    "area",
    "date",
    "surface",
    "duration_minutes",
    "num_players",
    "indoor_outdoor",
    "selected_time",
    "court_hint",
    "skill_level",
    "equipment_rental",
    "contact_name",
    "contact_email",
    "confirmed",
)

BOOK_TENNIS_COURT_TOOL: dict[str, Any] = {
    "name": "book_tennis_court",
    "description": (
        "Report booking progress to the workflow engine and get back what to "
        "do next. `updates` is a list of {slot, value} deltas -- set only the "
        "slot(s) you just learned, any combination, in one call: a "
        "correction to something answered earlier, the current node's "
        "answer, one or more not-yet-asked nodes the user already answered, "
        "or several of these at once -- every slot is always legal to send, "
        "regardless of which node is currently active. Omit `updates` "
        "entirely on the very first call of a conversation.\n\n"
        "Slot reference (name: type -- constraint):\n"
        "- area: string -- free text, e.g. a city or neighborhood ('downtown "
        "Seattle'); it's geocoded for real, so any real-world location works\n"
        "- date: string -- ISO format, e.g. '2026-09-06'\n"
        "- surface: string -- one of hard, clay, grass, indoor_carpet, any\n"
        "- duration_minutes: number -- one of 60, 90, 120\n"
        "- num_players: number -- one of 2, 4\n"
        "- indoor_outdoor: string -- one of indoor, outdoor, either\n"
        "- selected_time: string -- HH:MM, must be one of the open times "
        "from the most recent search_availability result\n"
        "- court_hint: string -- only send alongside selected_time in the "
        "same call, if more than one court could share that exact time "
        "slot: the court's name or its surface, e.g. 'Northpark Lawn Club' "
        "or 'grass'\n"
        "- skill_level: string -- one of beginner, intermediate, advanced\n"
        "- equipment_rental: boolean -- needs a racket rented\n"
        "- contact_name: string\n"
        "- contact_email: string\n"
        "- confirmed: boolean -- set once the user has responded to the "
        "recited booking summary; true if they confirmed it, false if they "
        "said something's wrong. Only takes effect once every other slot is "
        "already filled and the summary has actually been recited.\n\n"
        "Response shape: `current_node`/`instructions` (what to do next -- "
        "follow it literally), `current_node_slots` (the slot(s) this "
        "specific node is asking about right now -- NOT an exhaustive "
        "whitelist, you can still send any other slot in the same or a "
        "later call), `upcoming_instructions` (optional lookahead questions "
        "you can ask without calling this tool again), `applied`/`errors` "
        "(which of your slots landed vs. didn't, per slot name -- fix and "
        "resend only what `errors` names), `available_courts`/`note` (the "
        "ONLY real options once availability has been searched), "
        "`booking_summary` (recite every field and get explicit confirmation "
        "before anything is reported as booked), and `confirmation_id` (the "
        "real number -- nothing is booked until you're holding this)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "updates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "slot": {"type": "string", "enum": list(_ALL_SLOTS)},
                        "value": {
                            "anyOf": [
                                {"type": "string"},
                                {"type": "number"},
                                {"type": "boolean"},
                            ]
                        },
                    },
                    "required": ["slot", "value"],
                },
            },
        },
        "required": [],
    },
}
