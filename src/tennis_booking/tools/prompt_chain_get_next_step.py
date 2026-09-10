"""`get_next_step` -- used by `agents/prompt_chain_agent.py`. Backed by a
real persistent store (`ConversationStore` below -- a stand-in for e.g.
Redis or a DB table in production) keyed by a `conversation_id` that's fixed
for the life of the conversation and given to the model once, in the system
prompt. The tool call then carries only conversation_id plus whatever fields
the user just gave; the tool result carries only the next instruction. No
state ever round-trips through the model's context -- a growing "state"
payload echoed back on every call would otherwise get baked into message
history and re-billed on every subsequent API call for the rest of the
conversation.
"""
from __future__ import annotations

import uuid
from typing import Any

from tennis_booking.workflow_engine.state import BookingState
from tennis_booking.workflow_steps import next_step_for

GET_NEXT_STEP_TOOL: dict[str, Any] = {
    "name": "get_next_step",
    "description": (
        "Report any new tennis-booking details the user just gave you (only "
        "the fields you just learned -- previously reported fields are "
        "remembered for you server-side, keyed by conversation_id), and get "
        "back the single next step of the workflow to execute. ALWAYS pass "
        "your conversation_id (given to you once in the system prompt) so "
        "the server can find your booking-in-progress -- never omit it and "
        "never invent a different one. Call this at the start of every turn "
        "before deciding what to say or do, instead of guessing your "
        "progress from the conversation history. Pass "
        "summary_confirmed=true once you've recited the booking summary and "
        "the user has confirmed it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "conversation_id": {
                "type": "string",
                "description": "Your fixed conversation id from the system prompt. Required on every call.",
            },
            "area": {"type": "string"},
            "date": {"type": "string"},
            "surface": {
                "type": "string",
                "enum": ["hard", "clay", "grass", "indoor_carpet", "any"],
            },
            "duration_minutes": {"type": "integer", "enum": [60, 90, 120]},
            "num_players": {"type": "integer"},
            "indoor_outdoor": {"type": "string", "enum": ["indoor", "outdoor", "either"]},
            "selected_court_id": {"type": "string"},
            "selected_time": {"type": "string"},
            "skill_level": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]},
            "equipment_rental": {"type": "boolean", "description": "Needs a racket rented."},
            "contact_name": {"type": "string"},
            "contact_email": {"type": "string"},
            "summary_confirmed": {
                "type": "boolean",
                "description": "True once the user has confirmed the recited booking summary.",
            },
        },
        "required": ["conversation_id"],
    },
}


class ConversationStore:
    """Stand-in for a persistent backing store (Redis, a DB table, etc. in a
    real deployment) keyed by conversation_id. This is what lets
    `NextStepTool`'s wire payload stay tiny: the durable BookingState lives
    here, server-side, looked up by id -- it is never serialized into the
    model's context.
    """

    def __init__(self):
        self._states: dict[str, BookingState] = {}

    def create(self) -> tuple[str, BookingState]:
        conversation_id = uuid.uuid4().hex
        state = BookingState()
        self._states[conversation_id] = state
        return conversation_id, state

    def get(self, conversation_id: str) -> BookingState:
        try:
            return self._states[conversation_id]
        except KeyError:
            raise KeyError(f"Unknown conversation_id: {conversation_id!r}")

class NextStepTool:
    """get_next_step()'s implementation: server-side progress tracking via
    `ConversationStore`, with a wire payload that never carries the booking
    state. The model passes only its conversation_id plus whatever fields it
    just learned; the tool responds with only the next instruction -- no
    "state": {...} blob, so nothing here grows as the booking fills in.
    """

    def __init__(self, store: ConversationStore):
        self.store = store

    def run(self, args: dict) -> dict:
        args = dict(args)
        conversation_id = args.pop("conversation_id", None)
        if not conversation_id:
            return {"error": "conversation_id is required on every get_next_step call"}
        try:
            state = self.store.get(conversation_id)
        except KeyError as e:
            return {"error": str(e)}

        for field_name, value in args.items():
            if value not in (None, ""):
                setattr(state, field_name, value)

        step = next_step_for(state)
        if step is None:
            return {"workflow_complete": True}
        return {
            "workflow_complete": False,
            "next_step": step.key,
            "instruction": step.instruction,
            "is_tool_action": step.is_tool_action,
        }
