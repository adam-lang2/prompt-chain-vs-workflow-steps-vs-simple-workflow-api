"""Session-wide pass/fail accounting, by (agent, model, scenario), across
every scripted-suite run this session -- the counterpart to `token_tracking.py`
(which tracks usage/latency, not outcomes). Populated right after
`scoring.score_conversation` runs, so both the pytest eval run and the
standalone `evals/compare.py` script produce identically-shaped data for
`report.py` to render.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tennis_booking.scoring import WorkflowScore

_RESULTS: list["ScenarioResult"] = []


@dataclass(frozen=True)
class ScenarioResult:
    agent_id: str
    model: str
    scenario_name: str
    success: bool
    mismatches: list[str] = field(default_factory=list)


def record_result(agent_id: str, model: str, scenario_name: str, score: WorkflowScore) -> None:
    _RESULTS.append(
        ScenarioResult(
            agent_id=agent_id,
            model=model,
            scenario_name=scenario_name,
            success=score.success,
            mismatches=list(score.mismatches),
        )
    )


def all_results() -> list[ScenarioResult]:
    return list(_RESULTS)


def clear() -> None:
    _RESULTS.clear()
