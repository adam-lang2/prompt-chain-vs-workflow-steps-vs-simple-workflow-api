"""Tiny, dependency-free descriptive-stats helpers used by the terminal
summary and the standard comparison report (see report.py). Deliberately
not pulling in numpy for three functions.
"""
from __future__ import annotations

import math


def percentile(values: list[float], p: float) -> float:
    """Linear-interpolation percentile, matching numpy's default method.
    `p` is 0-100. Raises on an empty `values` -- callers are expected to
    guard for that themselves (there's no sensible percentile of nothing).
    """
    if not values:
        raise ValueError("percentile() requires at least one value")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("mean() requires at least one value")
    return sum(values) / len(values)
