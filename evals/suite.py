"""The standard scripted comparison suite -- named separately from
`evals.scenarios.scripted.ALL_SCENARIOS` so "the suite used for routine
architecture comparisons" can later diverge from "every scripted scenario
that exists" (e.g. if a slow/expensive scenario is added for depth but
excluded from the routine comparison run) without touching the pytest test
bodies or `evals/compare.py`.

Both `test_scripted_booking.py` (pytest) and `evals/compare.py` (the
standalone comparison script) parametrize over `STANDARD_SUITE`, so the
suite exercised by CI/pytest and the suite exercised by an interactive
`tennis-compare` run can never silently drift apart.
"""
from __future__ import annotations

from evals.scenarios.scripted import ALL_SCENARIOS, ScriptedScenario

STANDARD_SUITE: list[ScriptedScenario] = list(ALL_SCENARIOS)

assert len(STANDARD_SUITE) >= 10, (
    f"STANDARD_SUITE has only {len(STANDARD_SUITE)} scenarios -- the project's "
    "standard suite is meant to hold at least 10 for a meaningful comparison."
)
