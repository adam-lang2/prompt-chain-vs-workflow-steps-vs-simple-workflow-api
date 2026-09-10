"""LLM-simulated-user reliability eval (deepeval ConversationSimulator).

Complements test_scripted_booking.py: that one uses fixed scripted user
turns for fully reproducible pass/fail checks; this one lets an LLM
improvise the user according to a persona (see simulated/personas.py), which
is noisier but closer to how a real player would actually type.

One test body, parametrized over AGENTS_UNDER_TEST -- both architectures are
run through the identical personas/goldens, the identical judge model, and
the identical criteria, so a score difference reflects the architecture.

    uv run pytest evals/test_simulated_conversations.py -v -s

or via the deepeval CLI for its nicer reporting:

    uv run deepeval test run evals/test_simulated_conversations.py
"""
from __future__ import annotations

import os

import pytest
from deepeval import assert_test
from deepeval.metrics import ConversationalGEval
from deepeval.simulator import ConversationSimulator
from deepeval.test_case.conversational_test_case import MultiTurnParams

from tennis_booking.agents.base import DEFAULT_MODEL
from tennis_booking.agents.agent_registry import AGENTS_UNDER_TEST, AgentUnderTest
from evals.simulated.callback_adapter import make_model_callback
from evals.simulated.openrouter_model import OpenRouterModel
from evals.simulated.personas import ALL_GOLDENS
from evals.token_tracking import record_usage

# Ideally a stronger model plays the judge/simulator than the agents being
# evaluated -- a judge no more capable than the thing it's grading
# undermines the eval. Defaults to the same DeepSeek model the agents under
# test use (there's no cheaper/pricier tier split here the way Haiku/Sonnet
# gave the old Anthropic setup), overridable via TENNIS_BOOKING_JUDGE_MODEL
# for anyone who wants to point the judge at a different OpenRouter model.
#
# Uses OpenRouterModel (see simulated/openrouter_model.py), not deepeval's
# own model wrappers: those are tied to each provider's own SDK/auth, none
# of which is OpenRouter -- OpenRouterModel resolves OPENROUTER_API_KEY the
# same way the agents under test do (agents/base.py:new_client()).
DEFAULT_JUDGE_MODEL = DEFAULT_MODEL
# The workflow has 15 steps (12 questions + 3 tool actions) -- an orderly
# persona answering one question per turn needs ~13 turns just to reach
# confirmation, so this needs real headroom above the old 11-step workflow's
# 12-turn budget.
MAX_USER_TURNS = 18


def _judge_model() -> OpenRouterModel:
    model = os.environ.get("TENNIS_BOOKING_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)
    return OpenRouterModel(model=model)


def _workflow_adherence_metric(judge_model: OpenRouterModel) -> ConversationalGEval:
    return ConversationalGEval(
        name="Workflow Adherence",
        model=judge_model,
        evaluation_params=[MultiTurnParams.CONTENT, MultiTurnParams.TOOLS_CALLED, MultiTurnParams.ROLE],
        criteria=(
            "Determine whether the assistant correctly followed a tennis court "
            "booking workflow with two groups of fields. Group A (search "
            "inputs), needed before search_availability: area, date, surface, "
            "duration, player count, indoor/outdoor preference. Group B "
            "(booking details), needed before book_court: a court/time picked "
            "from real search results, skill level, whether they need a "
            "racket rental, name, and email. For EVERY field in either group: "
            "if the user volunteers it unprompted (before the assistant asked), "
            "the assistant must use that value and must NOT ask for it again -- "
            "only fields the user did not volunteer need an explicit question, "
            "in any order within their group. Do NOT penalize the assistant "
            "for skipping a question whose answer the user already "
            "volunteered -- that is correct behavior, not a missing step. "
            "Required sequence: call search_availability only once all of "
            "group A is known; present only real results from that call; let "
            "the user pick a time from those results; collect the rest of "
            "group B; recite the FULL summary (including skill level and "
            "equipment rental, not just the group A fields) and get explicit "
            "confirmation; only then call book_court exactly once with the "
            "values the user actually gave, including any corrections. DO "
            "penalize: skipping a value the assistant never had (neither "
            "asked for nor volunteered), asking a question already answered, "
            "inventing court names/times not present in a search_availability "
            "result, calling book_court before reciting the summary and "
            "getting confirmation, or booking with stale/uncorrected values "
            "after the user changed their mind."
        ),
        threshold=0.7,
    )


@pytest.mark.eval
@pytest.mark.parametrize("agent", AGENTS_UNDER_TEST, ids=[a.id for a in AGENTS_UNDER_TEST])
def test_simulated_conversation_reliability(agent: AgentUnderTest):
    judge_model = _judge_model()
    model_callback = make_model_callback(agent.create)
    simulator = ConversationSimulator(
        model_callback=model_callback,
        simulator_model=judge_model,
        async_mode=True,
        # Keep concurrency low by default -- raise it if your OpenRouter
        # account has more throughput headroom than a fresh/free-tier key.
        max_concurrent=1,
    )
    test_cases = simulator.simulate(
        conversational_goldens=ALL_GOLDENS,
        max_user_simulations=MAX_USER_TURNS,
    )
    for conversation_agent in model_callback.agents_by_thread.values():
        record_usage(agent.id, conversation_agent)

    # Deliberately not using deepeval's built-in ConversationCompletenessMetric
    # here -- verified live: it penalizes the agent for correctly declining
    # the messy persona's out-of-scope tangents (cancellation policy, guest
    # policy, "do you support pickleball") as "unmet user intentions", when
    # deflecting those is exactly the right behavior for a narrowly-scoped
    # booking assistant. The custom criteria below score what this project
    # actually cares about: following the *booking* workflow correctly.
    metrics = [_workflow_adherence_metric(judge_model)]

    failures = []
    for test_case in test_cases:
        try:
            assert_test(test_case, metrics=metrics)
        except AssertionError as e:
            failures.append(f"[{agent.id}/{test_case.name}] {e}")

    assert not failures, "\n\n".join(failures)
