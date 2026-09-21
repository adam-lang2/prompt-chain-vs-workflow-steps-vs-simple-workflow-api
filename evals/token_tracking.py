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
_TURN_SAMPLES: list["TurnSample"] = []


@dataclass(frozen=True)
class UsageSample:
    agent_id: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float = 0.0
    cost_usd: float | None = None
    source: str = "llm"  # "llm" or "jev" -- see UsageRecord.source
    reasoning_tokens: int = 0
    cached_tokens: int = 0


@dataclass(frozen=True)
class TurnSample:
    """One per finished conversation. `max_tool_calls_in_a_turn` is that
    conversation's worst-case round-trip count for a single turn (see
    ConversationAgent.max_tool_calls_in_a_turn); `turn_latency_ms` is the
    per-turn wall-clock list (ConversationAgent.turn_latencies_ms) -- kept
    together so report.py can both take the max across conversations and
    flatten every turn's latency into one percentile."""

    agent_id: str
    model: str
    max_tool_calls_in_a_turn: int
    turn_latencies_ms: list[float]


def record_usage(agent_id: str, agent: ConversationAgent, model: str | None = None) -> None:
    """Call once after finishing a conversation with `agent`, to fold its
    per-call usage log into the session-wide accounting. Cost is computed
    here (not carried on UsageRecord itself) from `pricing.py`'s per-model
    table, keyed off `agent.model` (the actual OpenRouter slug the calls
    were billed under) regardless of `model` -- left None when that model
    isn't priced. `model` is the report grouping key and defaults to
    `agent.model`; pass it explicitly when the two need to differ, e.g.
    `evals/compare.py`'s `model:effort` syntax reports
    "openai/gpt-5.6-luna:none" as its own row (distinct from a run of the
    same model at a different effort) while still billing/pricing as plain
    "openai/gpt-5.6-luna". report.py groups by (agent_id, model), not agent_id
    alone, since one process can point different conversations at different
    models."""
    model = model if model is not None else agent.model
    for record in agent.usage_log:
        source = getattr(record, "source", "llm")
        cost_usd = getattr(record, "cost_usd", None)
        if cost_usd is None:
            cost_usd = cost_for_call(agent.model, record.input_tokens, record.output_tokens, source)
        _SAMPLES.append(
            UsageSample(
                agent_id=agent_id,
                model=model,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                latency_ms=getattr(record, "latency_ms", 0.0),
                cost_usd=cost_usd,
                source=source,
                reasoning_tokens=getattr(record, "reasoning_tokens", 0),
                cached_tokens=getattr(record, "cached_tokens", 0),
            )
        )
    _TURN_SAMPLES.append(
        TurnSample(
            agent_id=agent_id,
            model=model,
            max_tool_calls_in_a_turn=agent.max_tool_calls_in_a_turn,
            turn_latencies_ms=list(agent.turn_latencies_ms),
        )
    )


def all_samples() -> list[UsageSample]:
    return list(_SAMPLES)


def all_turn_samples() -> list[TurnSample]:
    return list(_TURN_SAMPLES)


def clear() -> None:
    _SAMPLES.clear()
    _TURN_SAMPLES.clear()
