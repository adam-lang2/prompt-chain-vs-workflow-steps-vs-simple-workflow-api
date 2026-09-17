"""simple-workflow-api -- agent-1 (a plain tool-calling loop, no workflow
knowledge of its own) talks to a deterministic workflow API instead of
tracking the conversation itself: agent-2, `BookingWorkflowEngine` (`workflow_engine/`), is not
an LLM at all, but a non-LLM step machine that owns the workflow. Agent-1's
only tool, `book_tennis_court_with_grammar` (`BOOK_TENNIS_COURT_TOOL`,
see tools/book_tennis_court.py), takes a single `updates` array of
`{slot, value}` deltas -- any combination, in one call: a correction to
something answered earlier, the current node's answer, one or more
not-yet-reached nodes the user already answered, or several of these at
once, every slot always legal regardless of which node is currently active.
See tools/__init__.py's and workflow_engine/__init__.py's docstrings for the full
rationale behind that schema shape.

`BookingWorkflowEngine`'s own step-computation engine is `LangGraphStepEngine`
(`langgraph.graph.StateGraph`, see `workflow_engine/step_engine_langgraph.py`): a
`route` node whose conditional edges are guarded by `step_is_current`
(evaluated over `STEPS` in order), with `search_availability`/
`call_book_court` as tool-action nodes that mutate `BookingState` and loop
back to `route`. That engine choice is internal to `BookingWorkflowEngine` -- nothing
here, or in `BOOK_TENNIS_COURT_TOOL`'s schema, depends on which engine
backs it.
"""
from __future__ import annotations

from tennis_booking.agents.base import ConversationAgent, ToolCallRecord
from tennis_booking.workflow_engine import BookingWorkflowEngine
from tennis_booking.tools import BOOK_TENNIS_COURT_TOOL
from tennis_booking.workflow_steps import GROUNDING_GUIDANCE, STALE_SEARCH_GUIDANCE

BOOK_TOOL_NAME = "book_tennis_court_with_grammar"

SYSTEM_PROMPT = f"""\
You are a tennis court booking assistant, talking directly to the user. \
The other end of {BOOK_TOOL_NAME} is a deterministic parser, not an LLM -- \
no language understanding, no way to ask you a clarifying question. It owns \
the workflow; you never guess at it, skip ahead, or reorder it. See the \
tool's own description for exactly how to call it.

Your job:
- Read what the user says, and ask exactly what {BOOK_TOOL_NAME} tells you \
to ask, one thing at a time, in your own natural words.
- Never invent information the user didn't give you.
- Report everything you learn the moment you learn it -- including on the \
very first turn: if the user's opening message already answers something \
(e.g. "I'd like to book a court near downtown"), report that, don't \
bootstrap with nothing and re-ask for it. This applies for the rest of the \
conversation too -- a correction to something answered earlier, or an \
answer to a step you haven't been asked about yet -- report it as soon as \
you have it, don't wait to be asked.
- Treat every tool response as the only source of truth: present only \
court/time data, a booking summary, or a confirmation number that a \
response actually contained -- never state or imply anything else. A \
booking is only real once you're holding a confirmation_id from the tool; \
never say or imply otherwise, even right after the user confirms.
- Keep messages short and conversational.

{STALE_SEARCH_GUIDANCE}

{GROUNDING_GUIDANCE}
"""

def create_agent(state=None, client=None) -> ConversationAgent:
    """`client` lets tests inject a fake OpenAI-shaped client; leave it unset
    to use a real one (requires OPENROUTER_API_KEY). `state` is accepted
    (and passed straight through to BookingWorkflowEngine) only for symmetry with the
    other `create_agent()` factories -- BookingWorkflowEngine constructs its own
    BookingState when none is given."""
    fsm_agent = BookingWorkflowEngine(state)

    def _book_tennis_court_with_grammar(args: dict) -> dict:
        before = len(fsm_agent.internal_tool_calls)
        result = fsm_agent.handle(args)

        for internal in fsm_agent.internal_tool_calls[before:]:
            agent.tool_call_log.append(
                ToolCallRecord(turn=agent.turn_count, name=internal.name, args=internal.args, result=internal.result)
            )
        return result

    agent = ConversationAgent(
        system_prompt=SYSTEM_PROMPT,
        tools=[BOOK_TENNIS_COURT_TOOL],
        tool_executors={BOOK_TOOL_NAME: _book_tennis_court_with_grammar},
        client=client,
    )
    agent.state = fsm_agent.state  # type: ignore[attr-defined]  # convenience handle for tests
    agent.fsm_agent = fsm_agent  # type: ignore[attr-defined]
    return agent
