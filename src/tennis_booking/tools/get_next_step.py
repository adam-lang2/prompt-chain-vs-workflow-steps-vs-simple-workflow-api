"""`get_next_step` v1 -- used by `agents/prompt_chain_agent.py`. Echoes the
*entire* BookingState back in every tool result. Simple, but wasteful -- the
model never actually needs to see the state, only the next instruction, and
echoing a growing dict back on every call means that growing payload gets
baked into message history and re-billed on every subsequent API call for
the rest of the conversation (measured live: this is the dominant reason v1
ends up costing *more* tokens overall than the numbered-static-prompt
agent, despite v1's system prompt being far shorter). See
`get_next_step_v2.py` for the minimal-payload variant.
"""
from __future__ import annotations

from typing import Any

from tennis_booking.models import BookingState
from tennis_booking.workflow_steps import next_step_for

GET_NEXT_STEP_TOOL: dict[str, Any] = {
    "name": "get_next_step",
    "description": (
        "Report any new tennis-booking details the user just gave you (only "
        "the fields you just learned -- previously reported fields are "
        "remembered for you), and get back the single next step of the "
        "workflow to execute. Call this at the start of every turn before "
        "deciding what to say or do, instead of guessing your progress from "
        "the conversation history. Pass summary_confirmed=true once you've "
        "recited the booking summary and the user has confirmed it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
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
        "required": [],
    },
}


class NextStepTool:
    """Stateful get_next_step() implementation bound to one BookingState.

    One instance is created per conversation and shared with the tool-loop
    runner so repeated calls accumulate state across turns.
    """

    def __init__(self, state: BookingState):
        self.state = state

    def run(self, args: dict) -> dict:
        for field_name, value in args.items():
            if value not in (None, ""):
                setattr(self.state, field_name, value)

        step = next_step_for(self.state)
        if step is None:
            return {
                "workflow_complete": True,
                "state": self.state.as_dict(),
            }
        return {
            "workflow_complete": False,
            "next_step": step.key,
            "instruction": step.instruction,
            "is_tool_action": step.is_tool_action,
            "state": self.state.as_dict(),
        }
