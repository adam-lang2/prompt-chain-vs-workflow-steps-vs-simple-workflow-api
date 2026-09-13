"""workflow_engine -- BookingWorkflowEngine, the backend behind `agents/simple_workflow_api_agent.py`.

Agent-1's only tool takes a single `updates` array of `{slot, value}`
deltas (`BOOK_TENNIS_COURT_TOOL`, see tools/book_tennis_court.py), so there
is nothing here to parse from free text -- only to validate
(`SLOT_VALIDATORS` in `agent.py`), since JSON Schema can't enforce a
per-slot type/enum on a value whose shape depends on a sibling `slot`
property.

BookingWorkflowEngine is a thin subclass of `LangGraphStepEngine` (`step_engine_langgraph.py`)
-- it reuses that class's `langgraph.graph.StateGraph` step engine
(`_advance_past_tool_actions`, `self._graph`) and
`step_engine_shared.step_payload`'s response shaping (reshaped into this
variant's `current_node`/`instructions`/`current_node_slots` vocabulary by
`agent._node_payload`); the only thing it replaces is turning raw input into
field values, which it no longer needs since `updates[]` already arrives
typed and slot-addressed.

The one slot that still needs real logic is `selected_time`: knowing a time
string is well-formed doesn't tell you *which* court has an open slot at
that time when more than one does, so `court_hint` (a court name or
surface, see tools/book_tennis_court.py) narrows the candidates -- that
disambiguation is domain logic, not a parsing problem, so it doesn't go away
just because the input arrives structured.

This package holds the whole non-LLM step-computation family:
`step_engine_langgraph.py` (`LangGraphStepEngine`, the
`langgraph.graph.StateGraph` engine BookingWorkflowEngine subclasses),
`step_engine_shared.py` (the domain logic every step-computation engine
needs regardless of how it decides "which step is current": `step_is_current`
the per-step "is this still unmet" guard, `execute_tool_action` for running
search_availability/book_court as a side effect of reaching a tool-action
step, `step_payload` for response shaping, and `FIELD_DEPENDENTS` for which
corrections cascade into a re-search vs. just a reset confirmation), and
`state.py` (`BookingState`, the durable per-conversation workflow-progress
state every step-computation engine here reads and mutates -- also reused
by `workflow_steps.next_step_for`, backing `agents/prompt_chain_agent.py`).
Grouping them here keeps this whole family in one importable place, rather
than scattered at the top of the `tennis_booking` package.
"""
from __future__ import annotations

from tennis_booking.workflow_engine.agent import SLOT_TO_NODE, SLOTS_BY_NODE, BookingWorkflowEngine
from tennis_booking.workflow_engine.state import (
    REQUIRED_SLOTS,
    SEARCH_INPUT_SLOTS,
    BookingState,
)
from tennis_booking.workflow_engine.step_engine_langgraph import LangGraphStepEngine

__all__ = [
    "BookingWorkflowEngine",
    "SLOT_TO_NODE",
    "SLOTS_BY_NODE",
    "LangGraphStepEngine",
    "BookingState",
    "REQUIRED_SLOTS",
    "SEARCH_INPUT_SLOTS",
]
