"""Registry of agent architectures under comparison.

The CLI chat harness (`cli.py`) and every eval in `evals/` import this
instead of importing `prompt_chain_agent` / `workflow_agent` /
`simple_workflow_api` directly, so there is exactly one place that says
which agents exist and how to build one. An eval parametrized over
`AGENTS_UNDER_TEST` runs the identical test body against every entry --
that symmetry is what makes the comparison fair. Adding another
architecture later means adding one entry here, not editing every eval
file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from tennis_booking.agents.base import ConversationAgent
from tennis_booking.agents.prompt_chain_agent import create_agent as create_prompt_chain_agent
from tennis_booking.agents.simple_workflow_api_agent import create_agent as create_simple_workflow_api_agent
from tennis_booking.agents.workflow_agent import create_agent as create_workflow_agent


@dataclass(frozen=True)
class AgentUnderTest:
    id: str
    label: str
    create: Callable[[], ConversationAgent]


AGENTS_UNDER_TEST: tuple[AgentUnderTest, ...] = (
    AgentUnderTest(
        id="prompt_chain",
        label="Prompt-chain (get_next_step() chains a fresh instruction each turn, minimal wire payload)",
        create=create_prompt_chain_agent,
    ),
    AgentUnderTest(
        id="workflow",
        label="Workflow (numbered steps baked into one static system prompt)",
        create=create_workflow_agent,
    ),
    AgentUnderTest(
        id="simple_workflow_api",
        label=(
            "Simple-workflow-api (agent-1 with one tool, book_tennis_court, taking a structured "
            "`updates` array of {slot, value} deltas, backed by FSMAgent -- a "
            "langgraph.graph.StateGraph step machine, LangGraphStepEngine)"
        ),
        create=create_simple_workflow_api_agent,
    ),
)

AGENTS_BY_ID: dict[str, AgentUnderTest] = {a.id: a for a in AGENTS_UNDER_TEST}
