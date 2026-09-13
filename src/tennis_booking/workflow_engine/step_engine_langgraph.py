"""LangGraphStepEngine -- the non-LLM step-computation engine `BookingWorkflowEngine`
(`agent.py`, backing `BOOK_TENNIS_COURT_TOOL` / `agents/simple_workflow_api_agent.py`)
subclasses, backed by a `langgraph.graph.StateGraph`: a single `route` node
whose conditional edges -- guarded by `step_engine_shared.step_is_current`,
evaluated in STEPS order -- decide which step is current, tool-action steps
(search_availability, call_book_court) are their own graph nodes that run
`step_engine_shared.execute_tool_action` as a side effect and edge straight
back to `route`, and every other step is a terminal node (an edge to END)
that reports which step it is. `BookingWorkflowEngine` reuses `_advance_past_tool_actions`/
`self._graph` from this class and layers its own `handle()` (a typed
`{"updates": [...]}` dict, not free text) on top -- see `agent.py`.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from tennis_booking.workflow_engine.step_engine_shared import InternalToolCall, execute_tool_action, step_is_current
from tennis_booking.workflow_engine.state import BookingState
from tennis_booking.workflow_steps import STEPS, Step

_STEP_BY_KEY: dict[str, Step] = {s.key: s for s in STEPS}


class _GraphState(TypedDict, total=False):
    """The graph's own state -- deliberately just a marker of which node was
    last entered. The real workflow state is `BookingState`, held by
    `LangGraphStepEngine.self.state` and mutated in place by
    `execute_tool_action`; it does not flow through the graph's state
    channel, since `step_is_current`/`execute_tool_action` both already take
    it as an explicit argument (closed over below).
    """

    current_step: str


class LangGraphStepEngine:
    """Independent, non-LLM step machine backed by a compiled
    `langgraph.graph.StateGraph`. Owns only step computation
    (`_advance_past_tool_actions`) -- `BookingWorkflowEngine` (`agent.py`) is what turns
    that into a tool response.
    """

    def __init__(self, state: BookingState | None = None):
        self.state = state or BookingState()
        self.internal_tool_calls: list[InternalToolCall] = []
        self._called_before = False
        # Built once per instance (not per class) -- every node closes over
        # `self.state`/`self.internal_tool_calls`.
        self._graph = self._build_graph()

    def _route(self, _graph_state: _GraphState) -> str:
        """The graph's one conditional-edge decision function: the first
        step in STEPS order whose `step_is_current` guard is still true,
        given `self.state` right now. Re-evaluated from scratch on every
        entry to `route` -- including right after a tool-action node just
        mutated `self.state` -- which is what makes a loop back to `route`
        reproduce next_step_for's priority scan on each call.
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
