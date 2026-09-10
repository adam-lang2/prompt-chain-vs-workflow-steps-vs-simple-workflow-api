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
}


def cost_for_call(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimated $ cost of one call, or None if `model` isn't priced here."""
    prices = PRICE_PER_MILLION_TOKENS.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
