"""Tool schemas + implementations, one tool per module.

Every schema is defined in Anthropic's `{"name", "description",
"input_schema"}` shape -- kept that way for historical/readability reasons,
not because it's tied to Anthropic. `agents/base.py`'s `_to_openai_tool`
converts each one to OpenAI's `{"type": "function", "function": {...}}`
shape at request time, since every agent now talks to DeepSeek through
OpenRouter's OpenAI-compatible Chat Completions endpoint.

`search_availability` and `book_court` are domain tools shared by every
agent. `get_next_step` (two variants) is the extra tool that only the
prompt-chain agents get -- it wraps a server-side BookingState +
workflow_steps.next_step_for() so the model never has to infer its own
progress from the transcript.

- `NextStepTool` / `GET_NEXT_STEP_TOOL` (v1, used by `prompt_chain_agent.py`,
  see `get_next_step.py`): echoes the *entire* BookingState back in every
  tool result. Simple, but wasteful -- the model never actually needs to
  see the state, only the next instruction, and echoing a growing dict
  back on every call means that growing payload gets baked into message
  history and re-billed on every subsequent API call for the rest of the
  conversation (measured live: this is the dominant reason v1 ends up
  costing *more* tokens overall than the numbered-static-prompt agent,
  despite v1's system prompt being far shorter).
- `NextStepToolV2` / `GET_NEXT_STEP_TOOL_V2` (v2, used by
  `prompt_chain_agent_v2.py`, see `get_next_step_v2.py`): assumes
  get_next_step is backed by a real persistent store (`ConversationStore` --
  a stand-in for e.g. Redis or a DB table in production) keyed by a
  `conversation_id` that's fixed for the life of the conversation and given
  to the model once, in the system prompt. The tool call then carries only
  conversation_id plus whatever fields the user just gave; the tool result
  carries only the next instruction. No state ever round-trips through the
  model's context.
- `BOOK_TENNIS_COURT_TOOL_V4` (used by `agents/a2a_fsm_api.py`, see
  `book_tennis_court_v4.py`): agent-1's only tool. Instead of one optional
  property per field, there is a single `updates` array of `{slot, value}`
  deltas -- any combination, in one call: a correction to something
  answered earlier, the current node's answer, one or more not-yet-reached
  nodes the user already answered, or several of these at once, every slot
  always legal regardless of which node is currently active. `value` is
  typed loosely (string | number | boolean) since JSON Schema can't key a
  discriminated union off a sibling `slot` property; each slot's real
  type/enum constraint is checked server-side instead (`fsm_agent.agent.
  SLOT_VALIDATORS`), so an invalid value round-trips through `errors`
  rather than being rejected by the tool-calling layer. The backend
  (`fsm_agent.FSMAgent`) is `LangGraphStepEngine`
  (`langgraph.graph.StateGraph`, `fsm_agent/step_engine_langgraph.py`) --
  see that module's and `fsm_agent/__init__.py`'s docstrings for how it
  computes the current step.
"""
from __future__ import annotations

from tennis_booking.tools.book_court import BOOK_COURT_TOOL, run_book_court
from tennis_booking.tools.book_tennis_court_v4 import BOOK_TENNIS_COURT_TOOL_V4
from tennis_booking.tools.get_next_step import GET_NEXT_STEP_TOOL, NextStepTool
from tennis_booking.tools.get_next_step_v2 import (
    GET_NEXT_STEP_TOOL_V2,
    ConversationStore,
    NextStepToolV2,
)
from tennis_booking.tools.search_availability import SEARCH_AVAILABILITY_TOOL, run_search_availability

__all__ = [
    "SEARCH_AVAILABILITY_TOOL",
    "run_search_availability",
    "BOOK_COURT_TOOL",
    "run_book_court",
    "GET_NEXT_STEP_TOOL",
    "NextStepTool",
    "GET_NEXT_STEP_TOOL_V2",
    "NextStepToolV2",
    "ConversationStore",
    "BOOK_TENNIS_COURT_TOOL_V4",
]
