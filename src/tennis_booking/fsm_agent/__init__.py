"""FSMAgent -- the backend behind `agents/a2a_fsm_api.py`, and the fourth
variation on the agent-to-agent-prompt-chain architecture (see
`step_engine_handrolled.py` for v1/v2, `step_engine_transitions.py` for v3's engine
swap, `step_engine_langgraph.py` for FSMAgent's own engine swap on top of v3).

HandRolledStepEngine/TransitionsStepEngine/LangGraphStepEngine exist because agent-1's only
tool takes a single free-text `payload` string -- something has to parse
it, since nothing upstream guarantees it's well-formed. FSMAgent's
`book_tennis_court` (`BOOK_TENNIS_COURT_TOOL_V4`, see
tools/book_tennis_court_v4.py) replaces that string with a single
`updates` array of `{slot, value}` deltas, so there is nothing left here
to parse -- only to validate (`SLOT_VALIDATORS` in `agent.py`), since JSON
Schema can't enforce a per-slot type/enum on a value whose shape depends
on a sibling `slot` property the way it could when each field was its own
typed schema property (v3). FSMAgent is deliberately a thin subclass of
`LangGraphStepEngine` -- it reuses that class's `langgraph.graph.StateGraph`
step engine (`_advance_past_tool_actions`, `self._graph`) and
`step_engine_shared.step_payload`'s response shaping (reshaped into this
variant's `current_node`/`instructions`/`current_node_slots` vocabulary by
`agent._node_payload`); the only thing it replaces is
`HandRolledStepEngine.handle()`'s job of turning raw text into field
values, which it no longer needs.

The one slot that still needs real logic is `selected_time`: knowing a
time string is well-formed doesn't tell you *which* court has an open
slot at that time when more than one does, so `court_hint` (a court name
or surface, see tools/book_tennis_court_v4.py) still narrows the
candidates exactly the way step_engine_shared.py's `_extract_time` did -- the
disambiguation problem is domain logic, not a parsing problem, so it
doesn't go away just because the input arrives structured.

This package also holds the three non-LLM step-computation engines FSMAgent
has been built from over time -- `step_engine_handrolled.py` (HandRolledStepEngine,
the hand-rolled scan), `step_engine_transitions.py` (TransitionsStepEngine, the
transitions.Machine engine), `step_engine_langgraph.py` (LangGraphStepEngine, the
`langgraph.graph.StateGraph` engine FSMAgent itself now subclasses), and
`step_engine_shared.py` (the grammar/extractors/response shaping all three
engines share, plus `step_is_current`, the per-step guard
TransitionsStepEngine and LangGraphStepEngine both use -- see that module's own
docstring for why none of the engines inherit from one another). All five
modules are one family: "how does something other than the model's own
native tool-calling turn free text or typed fields into workflow
progress," with FSMAgent/LangGraphStepEngine as the family's most recent,
most structured member. Grouping them here keeps that whole lineage in one
importable place, rather than scattered at the top of the `tennis_booking`
package.
"""
from __future__ import annotations

from tennis_booking.fsm_agent.agent import SLOT_TO_NODE, SLOTS_BY_NODE, FSMAgent
from tennis_booking.fsm_agent.step_engine_handrolled import HandRolledStepEngine
from tennis_booking.fsm_agent.step_engine_langgraph import LangGraphStepEngine
from tennis_booking.fsm_agent.step_engine_transitions import TransitionsStepEngine

__all__ = [
    "FSMAgent",
    "SLOT_TO_NODE",
    "SLOTS_BY_NODE",
    "HandRolledStepEngine",
    "TransitionsStepEngine",
    "LangGraphStepEngine",
]
