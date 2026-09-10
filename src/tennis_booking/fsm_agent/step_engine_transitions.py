"""TransitionsStepEngine -- identical grammar, identical responses, identical STEPS
as HandRolledStepEngine (step_engine_handrolled.py). Only HOW "what's the current step" gets
computed changes, and this class does NOT extend HandRolledStepEngine -- the two are
independent, sibling implementations of the step-computation engine,
composing the same shared, non-differentiating machinery from
`step_engine_shared.py` (payload parsing, labeled-batch application, response
shaping, tool-action side effects) rather than one inheriting it from the
other. See `step_engine_shared.py`'s module docstring for why: reading this file
end to end (plus its one import line into that shared module) is enough to
assess this engine's complexity, with no inherited method to chase through
HandRolledStepEngine.

HandRolledStepEngine's original engine -- workflow_steps.next_step_for plus
HandRolledStepEngine._advance_past_tool_actions -- is a scan: for each step in order,
check a step-specific condition, return the first one that's still unmet.
Three different concerns are tangled into that one function plus its
while-loop: what "done" means per step, the priority-ordered scanning to
find the first undone one, and (in the while-loop) running the
side-effecting tool actions encountered along the way.

This module pulls those apart:
- `step_engine_shared.step_is_current` is the first concern alone: a plain
  per-step guard, a near-verbatim port of next_step_for's per-step
  conditions, as a standalone predicate instead of a branch in a scanning
  loop -- shared with step_engine_langgraph.py's StateGraph engine, since
  both need the identical "is this step unmet" answer and only differ in
  how they scan/route with it.
- A `transitions.Machine` owns the second concern generically: one
  wildcard ("*") transition per step, guarded by that step's condition,
  declared in STEPS order. `transitions` evaluates same-trigger candidates
  in the order they were added (verified live), so this reproduces
  next_step_for's priority scan exactly -- but now as a table you can
  print or diagram, not nested if/continue.
- `step_engine_shared.execute_tool_action` still owns the third concern: running
  search_availability/book_court as a side effect of settling into one of
  those steps.

Everything else -- payload parsing, labeled-batch application, response
shaping -- comes from `step_engine_shared.py`, identically to how HandRolledStepEngine uses
it. None of that is "workflow" logic, so none of it needed a different
conceptual mapping; only the step-computation engine did.
"""
from __future__ import annotations

from transitions import Machine

from tennis_booking.fsm_agent.step_engine_shared import (
    InternalToolCall,
    execute_tool_action,
    handle as _shared_handle,
    step_is_current,
)
from tennis_booking.models import BookingState
from tennis_booking.workflow_steps import STEPS, Step

_STEP_BY_KEY: dict[str, Step] = {s.key: s for s in STEPS}


class TransitionsStepEngine:
    """Independent, non-LLM step machine -- same `handle()` contract and
    responses as HandRolledStepEngine (see step_engine_handrolled.py's own docstring for the
    payload grammar and response shape), backed by a declared
    `transitions.Machine` instead of a hand-rolled scan for step
    computation. Deliberately has no base class -- see this module's
    docstring.
    """

    def __init__(self, state: BookingState | None = None):
        self.state = state or BookingState()
        self.internal_tool_calls: list[InternalToolCall] = []
        self._called_before = False
        # No `model=` -- attaches to the Machine object itself, so
        # `self.machine.state` / `self.machine.advance()` are used
        # directly. Keeps this fully separate from `self.state`, which
        # already means "the BookingState" -- attaching the machine to
        # `self` instead would collide on that same name.
        self.machine = Machine(
            states=[s.key for s in STEPS],
            initial=STEPS[0].key,
            auto_transitions=False,
            ignore_invalid_triggers=True,
        )
        for step in STEPS:
            self.machine.add_transition(
                "advance", "*", step.key, conditions=lambda s=step: step_is_current(s, self.state)
            )

    def _advance_past_tool_actions(self) -> Step | None:
        for _ in range(len(STEPS) + 1):
            self.machine.advance()
            step = _STEP_BY_KEY[self.machine.state]
            if step.is_tool_action:
                call = execute_tool_action(self.state, step)
                self.internal_tool_calls.append(call)
                continue
            return step
        return None  # defensive; unreachable given STEPS' terminal close_out

    def handle(self, payload: str) -> dict:
        """The single entry point `book_tennis_court`'s handler calls --
        identical contract to HandRolledStepEngine.handle (see its docstring)."""
        result, self._called_before = _shared_handle(
            self.state, payload, self._called_before, self._advance_past_tool_actions
        )
        return result
