"""Per-model $/1M-token pricing, used to turn raw token counts into an
estimated cost for the standard comparison report (see report.py).

This table is a point-in-time snapshot of OpenRouter's published pricing
for the models this project actually calls (`agents/base.py:DEFAULT_MODEL`,
plus any judge/simulator override) -- it WILL go stale silently, since
nothing here re-fetches live pricing. Re-check against
https://openrouter.ai/models before trusting a cost figure this table
produces for anything beyond rough architecture-to-architecture comparison
(which only needs the *ratio* between models/agents to be right, not the
absolute dollar figure).

A model not in this table simply prices as unknown (`None`) rather than
guessing -- see `token_tracking.record_usage`.
"""
from __future__ import annotations

# model slug -> (input $/1M tokens, output $/1M tokens)
PRICE_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "deepseek/deepseek-v4-flash-20260731": (0.20, 0.60),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-5.6-luna": (0.20, 1.20),
    # Measured directly from OpenRouter's own response.usage.cost (via
    # `usage: {"include": true}`), not the /models listing -- see
    # results/jev-gemma-3-12b.md. $0.05/$0.15 per 1M in/out tokens via
    # DeepInfra at the time this was measured.
    "google/gemma-3-12b-it": (0.05, 0.15),
}

# TypeSafe Jev: $0.042/MTok input, output is free.
JEV_PRICE_PER_MILLION_TOKENS: tuple[float, float] = (0.042, 0.0)


def cost_for_call(model: str, input_tokens: int, output_tokens: int, source: str = "llm") -> float | None:
    """Estimated $ cost of one call, or None if `model` isn't priced here.
    `source="jev"` prices a TypeSafe Jev call at the flat Jev rate instead."""
    prices = JEV_PRICE_PER_MILLION_TOKENS if source == "jev" else PRICE_PER_MILLION_TOKENS.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
