"""The workflow-step agent: the workflow is encoded as a numbered list of
steps baked into one static system prompt, used unchanged for the whole
conversation. The model has no state tool -- on every turn it must re-read
the whole transcript and infer for itself which numbered step to resume from
(contrast `prompt_chain_agent.py`, which instead calls a `get_next_step()`
tool each turn to get back a fresh, dynamically chained instruction).
"""
from __future__ import annotations

from tennis_booking.agents.base import ConversationAgent
from tennis_booking.tools import (
    BOOK_COURT_TOOL,
    SEARCH_AVAILABILITY_TOOL,
    run_book_court,
    run_search_availability,
)
from tennis_booking.workflow_steps import GROUNDING_GUIDANCE, STALE_SEARCH_GUIDANCE, render_numbered_steps

SYSTEM_PROMPT_TEMPLATE = """\
You are a helpful tennis court booking assistant. You help the user book a \
tennis court by following this workflow, IN ORDER, one step at a time:

{numbered_steps}

Rules:
- Do not skip a step, and do not ask about something the user has already \
told you (re-read the whole conversation so far before deciding what to ask \
next -- the user may have answered multiple questions in one message, or \
answered out of order, or changed their mind about an earlier answer; if \
they changed their mind, use their latest answer).
- Ask about ONE step at a time. Keep questions short and conversational.
- Only call search_availability once you have area, date, surface, duration, \
player count, and indoor/outdoor preference.

{stale_search_guidance}

{grounding_guidance}
"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        numbered_steps=render_numbered_steps(),
        stale_search_guidance=STALE_SEARCH_GUIDANCE,
        grounding_guidance=GROUNDING_GUIDANCE,
    )


def create_agent(client=None) -> ConversationAgent:
    """`client` lets tests inject a fake OpenAI-shaped client; leave it unset to
    use a real one (requires ANTHROPIC_API_KEY)."""

    def _search(args: dict) -> dict:
        result, _courts = run_search_availability(args)
        return result

    return ConversationAgent(
        system_prompt=build_system_prompt(),
        tools=[SEARCH_AVAILABILITY_TOOL, BOOK_COURT_TOOL],
        tool_executors={
            "search_availability": _search,
            "book_court": run_book_court,
        },
        client=client,
    )
