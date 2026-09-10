"""HandRolledStepEngine: a deterministic, non-LLM engine that drives the same
tennis-booking workflow as every other architecture in this project, but
instead of Claude's native structured tool-calling extracting slot values
for it, it parses whatever free-text payload it's handed with regexes.

This is the "agent-to-agent-prompt-chain" pattern: agent-1 is a real LLM
with exactly one tool, `book_tennis_court`, whose only parameter is an
unstructured string; every call into that tool lands here (agent-2).
Deliberately "dumb" by design -- it has no language understanding, so it
never guesses: a payload has to already be a clean, sanitized value
(agent-1's job, not this module's) or it's rejected with a clear `error`
rather than coerced into something that might be wrong. No agent module in
this project currently wires this engine up standalone (the earlier
`agent_to_agent_prompt_chain*.py` architectures that did have since been
retired in favor of `a2a-fsm-api`/`FSMAgent`) -- it's exercised directly by
`tests/test_step_engine.py` as a comparison point for
`TransitionsStepEngine`/`LangGraphStepEngine`.

This class owns exactly one thing: WHICH step is current, computed by a
hand-rolled priority scan (`_advance_past_tool_actions`, built on
`workflow_steps.next_step_for`). Everything else -- payload parsing,
labeled-batch application, response shaping, running a tool-action step's
side effect -- is genuinely shared, non-differentiating machinery, and
lives in `step_engine_shared.py`, called here as plain functions rather than
inherited from a base class. See `step_engine_transitions.py` (the
`transitions.Machine`-based sibling engine) and `step_engine_shared.py`'s own
docstring for why: both engines compose the same shared functions, and
neither inherits from the other, so either one can be read end-to-end on
its own when assessing its complexity.
"""
from __future__ import annotations

from tennis_booking.fsm_agent.step_engine_shared import (
    FIELD_DEPENDENTS,
    FIELD_LABELS,
    STEP_EXTRACTORS,
    InternalToolCall,
    execute_tool_action,
    handle as _shared_handle,
    parse_labeled_segments,
    step_payload,
)
from tennis_booking.models import BookingState
from tennis_booking.workflow_steps import Step, next_step_for

# Re-exported for tests/tools that want the extractors or field vocabulary
# directly -- the canonical definitions live in step_engine_shared.py, shared
# with step_engine_transitions.py.
__all__ = [
    "HandRolledStepEngine",
    "InternalToolCall",
    "FIELD_DEPENDENTS",
    "FIELD_LABELS",
    "STEP_EXTRACTORS",
]


class HandRolledStepEngine:
    """One instance per conversation. Not an LLM -- a deterministic step
    machine + regex extractor + tool executor, all in one.
    """

    def __init__(self, state: BookingState | None = None):
        self.state = state or BookingState()
        self.internal_tool_calls: list[InternalToolCall] = []
        self._called_before = False

    def _advance_past_tool_actions(self) -> Step | None:
        """The step-computation engine: a hand-rolled priority scan over
        `workflow_steps.STEPS` via `next_step_for`, running any tool-action
        step's side effect (search_availability / book_court) the moment
        it's reached, since agent-1 has no way to call those itself."""
        step = next_step_for(self.state)
        while step is not None and step.is_tool_action:
            call = execute_tool_action(self.state, step)
            self.internal_tool_calls.append(call)
            step = next_step_for(self.state)
        return step

    def handle(self, payload: str) -> dict:
        """The single entry point `book_tennis_court`'s handler calls.
        `payload` is unstructured free text -- either empty (a bootstrap
        call: "just tell me what to ask first"), a single unlabeled value
        answering the current step, or one or more "<label>: <value>"
        fields (see step_engine_shared.FIELD_LABELS) covering any mix of
        earlier, current, or not-yet-reached steps in one call.
        """
        result, self._called_before = _shared_handle(
            self.state, payload, self._called_before, self._advance_past_tool_actions
        )
        return result
