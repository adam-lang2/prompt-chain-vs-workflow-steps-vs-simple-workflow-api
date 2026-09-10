"""The prompt-chain-v2 agent: same architecture as `prompt_chain_agent.py`
(a `get_next_step()` tool hands back a fresh instruction each turn, driven
by server-side progress tracking) but with a minimal wire payload.

v1's `get_next_step` result echoes the *entire* BookingState back to the
model on every call -- unnecessary, since the model never needs to see the
state, only the single instruction it's handed next; `next_step_for` already
does the right thing with whatever's been filled in, out of order or not.
Echoing a dict that grows every turn means that growing payload gets baked
into message history and re-billed on every subsequent API call for the
rest of the conversation.

v2 instead assumes `get_next_step` is backed by a real persistent store
(`ConversationStore` in `tools.py` -- a stand-in for e.g. Redis or a DB
table in production) keyed by a `conversation_id` that's fixed for the life
of the conversation and given to the model exactly once, in the system
prompt. The tool call then carries only `conversation_id` plus whatever
fields the user just gave; the tool result carries only the next
instruction. No state ever round-trips through the model's context.
"""
from __future__ import annotations

from tennis_booking.agents.base import ConversationAgent
from tennis_booking.tools import (
    BOOK_COURT_TOOL,
    GET_NEXT_STEP_TOOL_V2,
    SEARCH_AVAILABILITY_TOOL,
    ConversationStore,
    NextStepToolV2,
    run_book_court,
    run_search_availability,
)
from tennis_booking.workflow_steps import GROUNDING_GUIDANCE, STALE_SEARCH_GUIDANCE

SYSTEM_PROMPT_TEMPLATE = """\
You are a helpful tennis court booking assistant. You help the user book a \
tennis court through a multi-step workflow: collect where/when/what-surface \
they want to play plus duration, player count, and indoor/outdoor \
preference; look up nearby court availability; have the user pick a court \
and time; collect their skill level and whether they need a racket rented; \
get their name and email; confirm; and book the court.

Your conversation_id is: {conversation_id}
This id is fixed for the whole conversation. Always pass it, exactly as \
given, as the conversation_id argument every time you call get_next_step -- \
it's how the server finds your booking-in-progress. Never omit it and \
never invent or reuse a different one.

You do NOT need to track your own progress through this workflow, and \
get_next_step will NOT hand the state back to you -- your progress is \
tracked for you server-side, keyed by conversation_id. Instead:
- At the start of every turn, call get_next_step with your conversation_id \
and any new booking details the user just gave you in their latest message \
(pass only what's new or changed -- everything else is already remembered \
for you server-side).
- get_next_step tells you exactly what to do next: either a question to ask \
the user, or a tool to call (search_availability or book_court).
- Follow its instruction exactly. If it tells you to call search_availability \
or book_court, call that tool, then call get_next_step again (with your \
conversation_id) before replying to the user.
- Ask about ONE thing at a time. Keep questions short and conversational.

{stale_search_guidance}

{grounding_guidance}
"""


def create_agent(client=None) -> ConversationAgent:
    """`client` lets tests inject a fake OpenAI-shaped client; leave it unset to
    use a real one (requires ANTHROPIC_API_KEY)."""
    store = ConversationStore()
    conversation_id, state = store.create()
    next_step_tool = NextStepToolV2(store)

    def _search(args: dict) -> dict:
        result, courts = run_search_availability(args)
        state.record_search_results(courts)
        return result

    def _book(args: dict) -> dict:
        result = run_book_court(args)
        state.booking_confirmed = True
        state.confirmation_id = result["confirmation_id"]
        return result

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        conversation_id=conversation_id,
        stale_search_guidance=STALE_SEARCH_GUIDANCE,
        grounding_guidance=GROUNDING_GUIDANCE,
    )

    agent = ConversationAgent(
        system_prompt=system_prompt,
        tools=[GET_NEXT_STEP_TOOL_V2, SEARCH_AVAILABILITY_TOOL, BOOK_COURT_TOOL],
        tool_executors={
            "get_next_step": next_step_tool.run,
            "search_availability": _search,
            "book_court": _book,
        },
        client=client,
    )
    agent.state = state  # type: ignore[attr-defined]  # convenience handle for tests
    agent.conversation_id = conversation_id  # type: ignore[attr-defined]
    return agent
