"""Registry of agent architectures under comparison.

The CLI chat harness (`cli.py`) and every eval in `evals/` import this
instead of importing `prompt_chain_agent` / `prompt_chain_agent_v2` /
`workflow_step_agent` directly, so there is exactly one place that says
which agents exist and how to build one. An eval parametrized over
`AGENTS_UNDER_TEST` runs the identical test body against every entry --
that symmetry is what makes the comparison fair. Adding another
architecture later means adding one entry here, not editing every eval
file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from tennis_booking.agents.a2a_fsm_api import create_agent as create_a2a_fsm_api
from tennis_booking.agents.base import ConversationAgent
from tennis_booking.agents.prompt_chain_agent import create_agent as create_prompt_chain_agent
from tennis_booking.agents.prompt_chain_agent_v2 import create_agent as create_prompt_chain_v2_agent
from tennis_booking.agents.workflow_step_agent import create_agent as create_workflow_step_agent


@dataclass(frozen=True)
class AgentUnderTest:
    id: str
    label: str
    create: Callable[[], ConversationAgent]
    # Optional architecture-specific invariant (e.g. "this agent must call
    # its state tool"), checked in addition to -- never instead of -- the
    # shared scoring every agent is held to. Keeps eval bodies identical
    # across agents while still letting each architecture assert on its own
    # mechanism.
    extra_invariant: Optional[Callable[[ConversationAgent], None]] = None


def _assert_uses_get_next_step(agent: ConversationAgent) -> None:
    calls = [r for r in agent.tool_call_log if r.name == "get_next_step"]
    assert calls, "prompt_chain agent never called get_next_step at all"


def _assert_uses_get_next_step_with_no_state_payload(agent: ConversationAgent) -> None:
    """v2-specific: locks in the whole point of v2 -- verifies every
    get_next_step tool_result actually stayed minimal (no "state" key ever
    leaked back into the wire payload)."""
    calls = [r for r in agent.tool_call_log if r.name == "get_next_step"]
    assert calls, "prompt_chain_v2 agent never called get_next_step at all"
    leaks = [r for r in calls if "state" in r.result]
    assert not leaks, f"get_next_step result leaked a 'state' payload on {len(leaks)} call(s)"


def _assert_uses_book_tennis_court(agent: ConversationAgent) -> None:
    calls = [r for r in agent.tool_call_log if r.name == "book_tennis_court"]
    assert calls, "a2a_fsm_api agent never called book_tennis_court at all"


AGENTS_UNDER_TEST: tuple[AgentUnderTest, ...] = (
    AgentUnderTest(
        id="prompt_chain",
        label="Prompt-chain (get_next_step() tool chains a fresh instruction each turn)",
        create=create_prompt_chain_agent,
        extra_invariant=_assert_uses_get_next_step,
    ),
    AgentUnderTest(
        id="prompt_chain_v2",
        label="Prompt-chain v2 (get_next_step() with a minimal payload, backed by a persistent store)",
        create=create_prompt_chain_v2_agent,
        extra_invariant=_assert_uses_get_next_step_with_no_state_payload,
    ),
    AgentUnderTest(
        id="workflow_step",
        label="Workflow-step (numbered steps baked into one static system prompt)",
        create=create_workflow_step_agent,
    ),
    AgentUnderTest(
        id="a2a_fsm_api",
        label=(
            "a2a-fsm-api (agent-1 with one tool, book_tennis_court, taking a structured "
            "`updates` array of {slot, value} deltas, backed by FSMAgent -- a "
            "langgraph.graph.StateGraph step machine, LangGraphStepEngine)"
        ),
        create=create_a2a_fsm_api,
        extra_invariant=_assert_uses_book_tennis_court,
    ),
)

AGENTS_BY_ID: dict[str, AgentUnderTest] = {a.id: a for a in AGENTS_UNDER_TEST}
