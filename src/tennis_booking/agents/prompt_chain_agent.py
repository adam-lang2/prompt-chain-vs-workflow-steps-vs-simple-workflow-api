"""The prompt-chain agent: the workflow lives server-side. The system prompt
only describes the workflow at a high level, and instead of one static
prompt used for the whole conversation, the model calls a `get_next_step()`
tool every turn to get back a fresh instruction -- effectively a chain of
small, dynamically generated prompts, one per step, rather than a single
monolithic one (contrast `workflow_step_agent.py`, which bakes the entire
numbered workflow into one static prompt). Progress is tracked
deterministically in a BookingState object, not inferred from the transcript.
"""
from __future__ import annotations

from tennis_booking.agents.base import ConversationAgent
from tennis_booking.models import BookingState
from tennis_booking.tools import (
    BOOK_COURT_TOOL,
    GET_NEXT_STEP_TOOL,
    SEARCH_AVAILABILITY_TOOL,
    NextStepTool,
    run_book_court,
    run_search_availability,
)
from tennis_booking.workflow_steps import GROUNDING_GUIDANCE, STALE_SEARCH_GUIDANCE

SYSTEM_PROMPT = f"""\
You are a helpful tennis court booking assistant. You help the user book a \
tennis court through a multi-step workflow: collect where/when/what-surface \
they want to play plus duration, player count, and indoor/outdoor \
preference; look up nearby court availability; have the user pick a court \
and time; collect their skill level and whether they need a racket rented; \
get their name and email; confirm; and book the court.

You do NOT need to track your own progress through this workflow. Instead:
- At the start of every turn, call get_next_step with any new booking \
details the user just gave you in their latest message (pass only what's \
new or changed -- everything else is already remembered for you).
- get_next_step tells you exactly what to do next: either a question to ask \
the user, or a tool to call (search_availability or book_court).
- Follow its instruction exactly. If it tells you to call search_availability \
or book_court, call that tool, then call get_next_step again before replying \
to the user.
- Ask about ONE thing at a time. Keep questions short and conversational.

{STALE_SEARCH_GUIDANCE}

{GROUNDING_GUIDANCE}
"""


def create_agent(state: BookingState | None = None, client=None) -> ConversationAgent:
    """`client` lets tests inject a fake OpenAI-shaped client; leave it unset to
    use a real one (requires ANTHROPIC_API_KEY)."""
    state = state or BookingState()
    next_step_tool = NextStepTool(state)

    def _search(args: dict) -> dict:
        result, courts = run_search_availability(args)
        state.record_search_results(courts)
        return result

    def _book(args: dict) -> dict:
        result = run_book_court(args)
        state.booking_confirmed = True
        state.confirmation_id = result["confirmation_id"]
        return result

    agent = ConversationAgent(
        system_prompt=SYSTEM_PROMPT,
        tools=[GET_NEXT_STEP_TOOL, SEARCH_AVAILABILITY_TOOL, BOOK_COURT_TOOL],
        tool_executors={
            "get_next_step": next_step_tool.run,
            "search_availability": _search,
            "book_court": _book,
        },
        client=client,
    )
    agent.state = state  # type: ignore[attr-defined]  # convenience handle for tests
    return agent
