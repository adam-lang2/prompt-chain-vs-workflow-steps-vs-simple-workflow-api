"""LangGraphStepEngine -- identical grammar, identical responses, identical
STEPS as HandRolledStepEngine/TransitionsStepEngine (step_engine_handrolled.py /
step_engine_transitions.py). Only HOW "what's the current step" gets computed
changes, again: this class is a third, independent step-computation engine,
backed by a `langgraph.graph.StateGraph` instead of a hand-rolled scan or a
`transitions.Machine`. It does NOT extend either sibling engine -- same
reasoning as step_engine_transitions.py's module docstring: reading this file
end to end (plus its one import line into step_engine_shared.py) is enough to
assess this engine's complexity, with no inherited method to chase.

This is `FSMAgent`'s (`agent.py`, backing `BOOK_TENNIS_COURT_TOOL_V4` /
`agents/a2a_fsm_api.py`) current engine, replacing TransitionsStepEngine's
`transitions.Machine` there. Reaching for a graph library instead of another
bespoke state machine is the point: `transitions.Machine` still required this
project to declare its own wildcard-transition table and write its own
"advance past any tool-action steps" loop (`_advance_past_tool_actions`)
around it. LangGraph's `StateGraph` already models exactly this shape --
nodes or conditional edges, with the *graph itself* doing the looping -- so
there is less custom control flow to own here than in either of the other
two engines:

- `step_engine_shared.step_is_current` is still the one per-step guard, used
  identically to how TransitionsStepEngine uses it -- unchanged by this
  swap, since it isn't "workflow" logic, it's slot logic.
- A single `route` node's conditional edges -- guarded by `step_is_current`,
  evaluated in STEPS order, exactly like TransitionsStepEngine's wildcard
  transitions -- decide which step is current. Reproduces next_step_for's
  priority scan exactly, but now as a graph you can visualize
  (`compiled.get_graph().draw_mermaid()`), not a table this project declares
  itself.
- Each tool-action step (search_availability, call_book_court) is its own
  graph node that runs `step_engine_shared.execute_tool_action` as a side
  effect and then edges straight back to `route` -- LangGraph's own
  invoke loop is what repeatedly re-enters `route` until it lands on a
  non-tool-action step, so there is no separate `_advance_past_tool_actions`
  method here the way the other two engines each need one. Every other
  step is a terminal node (an edge straight to END) that just reports which
  step it is.

Everything else -- payload parsing, labeled-batch application, response
shaping -- comes from `step_engine_shared.py`, identically to how
HandRolledStepEngine/TransitionsStepEngine use it. None of that is
"workflow" logic, so none of it needed a different conceptual mapping; only
the step-computation engine did.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from tennis_booking.fsm_agent.step_engine_shared import (
    InternalToolCall,
    execute_tool_action,
    handle as _shared_handle,
    step_is_current,
)
from tennis_booking.models import BookingState
from tennis_booking.workflow_steps import STEPS, Step

_STEP_BY_KEY: dict[str, Step] = {s.key: s for s in STEPS}


class _GraphState(TypedDict, total=False):
    """The graph's own state -- deliberately just a marker of which node was
    last entered. The real workflow state is `BookingState`, held by
    `LangGraphStepEngine.self.state` and mutated in place by
    `execute_tool_action`; it does not flow through the graph's state
    channel, since `step_is_current`/`execute_tool_action` both already take
    it as an explicit argument (closed over below), the same way
    TransitionsStepEngine's guards close over `self.state` rather than
    threading it through `transitions.Machine`'s own state.
    """

    current_step: str


class LangGraphStepEngine:
    """Independent, non-LLM step machine -- same `handle()` contract and
    responses as HandRolledStepEngine/TransitionsStepEngine (see
    step_engine_handrolled.py's own docstring for the payload grammar and
    response shape), backed by a compiled `langgraph.graph.StateGraph`
    instead of a hand-rolled scan or a `transitions.Machine`. Deliberately
    has no base class -- see this module's docstring.
    """

    def __init__(self, state: BookingState | None = None):
        self.state = state or BookingState()
        self.internal_tool_calls: list[InternalToolCall] = []
        self._called_before = False
        # Built once per instance (not per class) -- every node closes over
        # `self.state`/`self.internal_tool_calls`, the same way
        # TransitionsStepEngine's transition guards close over `self.state`.
        self._graph = self._build_graph()

    def _route(self, _graph_state: _GraphState) -> str:
        """The graph's one conditional-edge decision function: the first
        step in STEPS order whose `step_is_current` guard is still true,
        given `self.state` right now. Re-evaluated from scratch on every
        entry to `route` -- including right after a tool-action node just
        mutated `self.state` -- which is what makes a loop back to `route`
        equivalent to TransitionsStepEngine's `self.machine.advance()`
        reproducing next_step_for's priority scan on each call.
        """
        for step in STEPS:
            if step_is_current(step, self.state):
                return step.key
        return END

    def _build_graph(self):
        builder = StateGraph(_GraphState)
        builder.add_node("route", lambda graph_state: graph_state)
        builder.add_edge(START, "route")

        for step in STEPS:
            if step.is_tool_action:

                def _tool_node(_graph_state: _GraphState, step: Step = step) -> _GraphState:
                    call = execute_tool_action(self.state, step)
                    self.internal_tool_calls.append(call)
                    return {"current_step": step.key}

                builder.add_node(step.key, _tool_node)
                builder.add_edge(step.key, "route")
            else:

                def _ask_node(_graph_state: _GraphState, step: Step = step) -> _GraphState:
                    return {"current_step": step.key}

                builder.add_node(step.key, _ask_node)
                builder.add_edge(step.key, END)

        builder.add_conditional_edges("route", self._route, {s.key: s.key for s in STEPS} | {END: END})
        return builder.compile()

    def _advance_past_tool_actions(self) -> Step | None:
        result = self._graph.invoke({"current_step": ""})
        key = result.get("current_step")
        if not key:
            return None
        return _STEP_BY_KEY[key]

    def handle(self, payload: str) -> dict:
        """The single entry point `book_tennis_court`'s handler calls --
        identical contract to HandRolledStepEngine.handle / TransitionsStepEngine.handle
        (see either's docstring)."""
        result, self._called_before = _shared_handle(
            self.state, payload, self._called_before, self._advance_past_tool_actions
        )
        return result
