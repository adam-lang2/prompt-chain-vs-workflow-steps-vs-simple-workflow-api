"""Session-wide token-usage accounting, by agent id, across every eval that
ran this session. `usage.prompt_tokens` on each response is the *total*
size of that request (system prompt + tools + full message history so far),
so comparing average input tokens per call directly answers "does a shorter
system prompt / smaller tool list actually cost less" -- which is exactly
the structural difference between the four architectures: the workflow-step
agent's system prompt embeds all 15 steps' full instruction text for the
whole conversation, while the prompt-chain agents' system prompts stay short
and only ever hold one step's instruction text at a time (delivered as a
tool result), at the cost of an extra tool round-trip. Every architecture
now runs through the same uncached OpenRouter/DeepSeek Chat Completions
loop, so raw token counts are directly comparable across all of them with
no per-architecture caveat.

`evals/conftest.py`'s `pytest_terminal_summary` hook prints the aggregated
comparison at the end of the run.
"""
from __future__ import annotations

from dataclasses import dataclass

from evals.pricing import cost_for_call
from tennis_booking.agents.base import ConversationAgent

_SAMPLES: list["UsageSample"] = []


@dataclass(frozen=True)
class UsageSample:
    agent_id: str
    input_tokens: int
    output_tokens: int
    latency_ms: float = 0.0
    cost_usd: float | None = None


def record_usage(agent_id: str, agent: ConversationAgent) -> None:
    """Call once after finishing a conversation with `agent`, to fold its
    per-call usage log into the session-wide accounting. Cost is computed
    here (not carried on UsageRecord itself) from `pricing.py`'s per-model
    table, since it depends on which model the agent actually ran -- left
    None when that model isn't priced."""
    for record in agent.usage_log:
        cost_usd = getattr(record, "cost_usd", None)
        if cost_usd is None:
            cost_usd = cost_for_call(agent.model, record.input_tokens, record.output_tokens)
        _SAMPLES.append(
            UsageSample(
                agent_id=agent_id,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                latency_ms=getattr(record, "latency_ms", 0.0),
                cost_usd=cost_usd,
            )
        )


def all_samples() -> list[UsageSample]:
    return list(_SAMPLES)


def clear() -> None:
    _SAMPLES.clear()
