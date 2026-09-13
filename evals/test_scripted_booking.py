"""Deterministic scripted-scenario reliability eval.

One test body, parametrized over every entry in AGENTS_UNDER_TEST and every
scenario in the standard suite (`evals.suite.STANDARD_SUITE`, at least 10
scenarios -- see that module) -- each (agent, scenario) pair runs the
identical fixed user-turn script through `agent.create()` and is scored by
the identical `score_conversation` logic. That symmetry is what makes this
a fair comparison: nothing about the scoring or the input can silently
differ between architectures, because there is only one copy of it.

    uv run pytest evals/test_scripted_booking.py -v

Every (agent, scenario) result is also recorded to `results_tracking.py`
(pass/fail) alongside `token_tracking.py` (usage/latency, recorded per
call inside `record_usage`), so `evals/report.py`'s standard comparison
report -- printed by `conftest.py`'s `pytest_terminal_summary`, or built
directly by `evals/compare.py` -- reflects this same run.
"""
from __future__ import annotations

import pytest

from tennis_booking.agents.agent_registry import AGENTS_UNDER_TEST, AgentUnderTest
from tennis_booking.scoring import score_conversation
from evals.results_tracking import record_result
from evals.scenarios.runner import run_scripted_scenario
from evals.scenarios.scripted import ScriptedScenario
from evals.suite import STANDARD_SUITE
from evals.token_tracking import record_usage


@pytest.mark.eval
@pytest.mark.parametrize("agent", AGENTS_UNDER_TEST, ids=[a.id for a in AGENTS_UNDER_TEST])
@pytest.mark.parametrize("scenario", STANDARD_SUITE, ids=[s.name for s in STANDARD_SUITE])
def test_scripted_booking(agent: AgentUnderTest, scenario: ScriptedScenario):
    conversation_agent = agent.create()
    run_scripted_scenario(conversation_agent, scenario)
    record_usage(agent.id, conversation_agent)

    score = score_conversation(
        tool_call_log=conversation_agent.tool_call_log,
        expected=scenario.expected,
        num_turns=len(scenario.turns),
    )
    record_result(agent.id, conversation_agent.model, scenario.name, score)

    label = f"{agent.id}/{scenario.name}"
    assert not conversation_agent.exceeded_iteration_limit_turns, (
        f"[{label}] hit MAX_TOOL_ITERATIONS_PER_TURN on turn(s) "
        f"{conversation_agent.exceeded_iteration_limit_turns}"
    )
    assert score.searched, f"[{label}] agent never called search_availability"
    assert score.booked, f"[{label}] agent never called book_court"
    assert not score.mismatches, f"[{label}] mismatches: {score.mismatches}"

    # Every declared tool must be called at least once -- e.g. this is what
    # catches the prompt_chain agent degenerating into a plain tool-calling
    # loop that skips get_next_step but still passes the scoring above.
    called_tool_names = {r.name for r in conversation_agent.tool_call_log}
    declared_tool_names = {t["name"] for t in conversation_agent.tools}
    unused = declared_tool_names - called_tool_names
    assert not unused, f"[{label}] agent never called: {sorted(unused)}"

    # No tool result may leak a "state" blob onto the wire -- the specific
    # efficiency claim get_next_step makes.
    leaks = [r for r in conversation_agent.tool_call_log if "state" in r.result]
    assert not leaks, f"[{label}] a tool result leaked a 'state' payload on {len(leaks)} call(s)"
