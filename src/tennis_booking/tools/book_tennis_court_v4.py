"""`book_tennis_court` v4 -- used by `agents/a2a_fsm_api.py`, backed by
`fsm_agent.FSMAgent`. Replaces v3's flat object of ~13 optional properties
with a single `updates` array of `{slot, value}` deltas. This is a genuine
shape change, not just a rename: JSON Schema can't express a discriminated
union keyed on a sibling property (`value`'s type/enum depending on
`slot`'s value), so `updates[].value` is typed loosely (string | number |
boolean) and each slot's real type/enum/format constraint -- previously
enforced by v3's per-property JSON Schema enums -- is now checked by a
server-side validator in `fsm_agent.agent.SLOT_VALIDATORS` instead. An
invalid value round-trips through `errors` (keyed by slot name) rather than
being rejected by the tool-calling layer itself; the tradeoff for that lost
schema-level guarantee is a single flat update vocabulary that scales to
more slots without the schema growing a new top-level property each time.

Everything else about the contract is unchanged from v3: any combination of
slots per call (a correction to something answered earlier, the current
node's answer, one or more not-yet-reached nodes the user already answered,
or several of these at once), same closed slot set, same `FSMAgent`
backend -- now `LangGraphStepEngine` (`langgraph.graph.StateGraph`), see
`fsm_agent/step_engine_langgraph.py`. The response shape's top-level step-identity
fields are renamed (`step`/`instruction` -> `current_node`/`instructions`,
see `fsm_agent.agent._node_payload`) and gain `current_node_slots`; every
other response field (`upcoming_instructions`, `available_courts`/`note`,
`booking_summary`, `confirmation_id`/`date`/`time`, `applied`/`errors`)
carries over from v3 unchanged in name and trigger condition.
"""
from __future__ import annotations

from typing import Any

from tennis_booking.mock_courts import KNOWN_AREAS

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

BOOK_TENNIS_COURT_TOOL_V4: dict[str, Any] = {
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
        f"- area: string -- one of {sorted(KNOWN_AREAS)}\n"
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
