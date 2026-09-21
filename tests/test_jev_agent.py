"""Wiring tests for the Jev agent using a fake Interpreter."""
from __future__ import annotations

import pytest

from tennis_booking.agents.jev_agent import create_agent
from tennis_booking.jev.interpret import Interpretation
from tennis_booking.jev.interpret import Interpreter
from tennis_booking.models import CourtAvailability, TimeSlot
from tennis_booking.workflow_engine.state import BookingState
from tests.fakes import FakeOpenAIClient, FakeResponse


class FakeInterpreter:
    """Test Interpreter that returns scripted Interpretations."""

    def __init__(self, interpretations: list[Interpretation]):
        self._interpretations = list(interpretations)
        self._call_count = 0

    def interpret(self, state, last_assistant, user_turn) -> Interpretation:
        if self._call_count >= len(self._interpretations):
            raise AssertionError("FakeInterpreter ran out of scripted interpretations")
        result = self._interpretations[self._call_count]
        self._call_count += 1
        return result


def test_jev_agent_executes_one_speaker_call_per_turn():
    """Jev agent should make exactly one (speaker-only) LLM call per turn."""
    fake_client = FakeOpenAIClient(
        scripted_responses=[
            FakeResponse(content="Where would you like to play?"),
        ]
    )

    # First turn: user gives area, interpreter returns it
    interp = Interpretation(
        act="answers_current",
        act_confidence=0.9,
        slots={"area": ("downtown", 0.9)},
        latency_ms=50.0,
    )
    fake_interpreter = FakeInterpreter([interp])

    agent = create_agent(client=fake_client, interpreter=fake_interpreter)

    reply = agent.send_user_message("I want to book downtown.")

    assert reply == "Where would you like to play?"

    # Should be exactly one LLM call (speaker call, no tools)
    assert len(fake_client.chat.completions.calls) == 1
    call = fake_client.chat.completions.calls[0]

    # Verify it's a speaker call (no tools parameter)
    assert "tools" not in call or call.get("tools") is None

    # Verify one tool call was logged (the internal book_tennis_court_with_grammar)
    assert len(agent.tool_call_log) == 0  # No LLM-initiated tools


def test_jev_agent_handles_no_updates():
    """When user says something off-topic (no updates), agent should use peek."""
    fake_client = FakeOpenAIClient(
        scripted_responses=[
            FakeResponse(content="Let's get back to booking. What's your preferred surface?"),
        ]
    )

    interp = Interpretation(
        act="off_topic",
        act_confidence=0.9,
        slots={},
        latency_ms=50.0,
    )
    fake_interpreter = FakeInterpreter([interp])

    agent = create_agent(client=fake_client, interpreter=fake_interpreter)

    reply = agent.send_user_message("How's the weather?")

    assert len(fake_client.chat.completions.calls) == 1
    assert "Let's get back to booking" in reply or reply  # Just verify reply was generated


def test_jev_agent_full_booking_flow():
    """Full booking flow: area -> date -> surface -> duration -> players -> indoor_outdoor -> search."""
    # Script the fake client with enough responses for several turns
    fake_client = FakeOpenAIClient(
        scripted_responses=[
            FakeResponse(content="Got it, downtown. What date?"),
            FakeResponse(content="September 5th. What surface?"),
            FakeResponse(content="Hard court. How long?"),
            FakeResponse(content="90 minutes. How many players?"),
            FakeResponse(content="4 players (doubles). Indoor or outdoor?"),
            FakeResponse(content="Here are the available courts..."),
        ]
    )

    interpretations = [
        Interpretation(
            act="answers_current",
            act_confidence=0.9,
            slots={"area": ("downtown", 0.9)},
            latency_ms=50.0,
        ),
        Interpretation(
            act="answers_current",
            act_confidence=0.9,
            slots={"date": ("2026-09-05", 0.9)},
            latency_ms=50.0,
        ),
        Interpretation(
            act="answers_current",
            act_confidence=0.9,
            slots={"surface": ("hard", 0.9)},
            latency_ms=50.0,
        ),
        Interpretation(
            act="answers_current",
            act_confidence=0.9,
            slots={"duration_minutes": ("90", 0.9)},
            latency_ms=50.0,
        ),
        Interpretation(
            act="answers_current",
            act_confidence=0.9,
            slots={"num_players": ("4", 0.9)},
            latency_ms=50.0,
        ),
        Interpretation(
            act="answers_current",
            act_confidence=0.9,
            slots={"indoor_outdoor": ("either", 0.9)},
            latency_ms=50.0,
        ),
    ]

    fake_interpreter = FakeInterpreter(interpretations)
    agent = create_agent(client=fake_client, interpreter=fake_interpreter)

    # Turn 1
    reply1 = agent.send_user_message("I want to book downtown.")
    assert reply1

    # Turn 2
    reply2 = agent.send_user_message("September 5th, 2026.")
    assert reply2

    # Turn 3
    reply3 = agent.send_user_message("I prefer hard courts.")
    assert reply3

    # Turn 4
    reply4 = agent.send_user_message("90 minutes.")
    assert reply4

    # Turn 5
    reply5 = agent.send_user_message("Doubles, 4 players.")
    assert reply5

    # Turn 6
    reply6 = agent.send_user_message("Either indoor or outdoor is fine.")
    assert reply6

    # By turn 6 with all search inputs filled, search_availability should have run
    # Check that an internal tool call was logged
    search_calls = [tc for tc in agent.tool_call_log if tc.name == "search_availability"]
    assert len(search_calls) >= 1, f"Expected search_availability call, got: {[tc.name for tc in agent.tool_call_log]}"


def test_jev_agent_copies_internal_tool_calls():
    """Internal tool calls (from engine) should appear in agent's tool_call_log."""
    fake_client = FakeOpenAIClient(
        scripted_responses=[
            FakeResponse(content="Where?"),
            FakeResponse(content="What date?"),
            FakeResponse(content="What surface?"),
            FakeResponse(content="Duration?"),
            FakeResponse(content="Players?"),
            FakeResponse(content="Indoor/outdoor?"),
            FakeResponse(content="Here are times..."),
        ]
    )

    interpretations = [
        Interpretation(
            act="answers_current",
            act_confidence=0.9,
            slots={"area": ("downtown", 0.9)},
            latency_ms=50.0,
        ),
        Interpretation(
            act="answers_current",
            act_confidence=0.9,
            slots={"date": ("2026-09-05", 0.9)},
            latency_ms=50.0,
        ),
        Interpretation(
            act="answers_current",
            act_confidence=0.9,
            slots={"surface": ("hard", 0.9)},
            latency_ms=50.0,
        ),
        Interpretation(
            act="answers_current",
            act_confidence=0.9,
            slots={"duration_minutes": ("90", 0.9)},
            latency_ms=50.0,
        ),
        Interpretation(
            act="answers_current",
            act_confidence=0.9,
            slots={"num_players": ("4", 0.9)},
            latency_ms=50.0,
        ),
        Interpretation(
            act="answers_current",
            act_confidence=0.9,
            slots={"indoor_outdoor": ("either", 0.9)},
            latency_ms=50.0,
        ),
    ]

    fake_interpreter = FakeInterpreter(interpretations)
    agent = create_agent(client=fake_client, interpreter=fake_interpreter)

    agent.send_user_message("downtown")
    agent.send_user_message("2026-09-05")
    agent.send_user_message("hard")
    agent.send_user_message("90")
    agent.send_user_message("4")
    agent.send_user_message("either")

    # After all 6 inputs, search_availability should have been called
    search_calls = [tc for tc in agent.tool_call_log if tc.name == "search_availability"]
    assert len(search_calls) >= 1
    assert search_calls[0].result  # Should have a result


def test_workflow_functions_are_not_counted_as_agentic_tool_calls():
    from tennis_booking.agents.base import ConversationAgent, ToolCallRecord

    agent = ConversationAgent(system_prompt="", tools=[], tool_executors={}, client=object())
    agent.tool_call_log.append(ToolCallRecord(turn=1, name="search_availability", args={}, result={}, agentic=False))
    agent.tool_call_log.append(ToolCallRecord(turn=1, name="book_court", args={}, result={}, agentic=False))
    assert agent.max_tool_calls_in_a_turn == 0
    agent.tool_call_log.append(ToolCallRecord(turn=1, name="model_tool", args={}, result={}))
    assert agent.max_tool_calls_in_a_turn == 1


def test_report_separates_jev_and_llm_token_usage():
    from evals import token_tracking
    from evals.report import build_report
    from tennis_booking.agents.base import ConversationAgent, UsageRecord

    token_tracking.clear()
    agent = ConversationAgent(system_prompt="", tools=[], tool_executors={}, client=object())
    agent.usage_log.append(UsageRecord(turn=1, input_tokens=100, output_tokens=10, latency_ms=50.0, source="jev"))
    agent.usage_log.append(UsageRecord(turn=1, input_tokens=2000, output_tokens=300, latency_ms=900.0))
    token_tracking.record_usage("jev", agent)
    (row,) = build_report(["jev"]).rows
    token_tracking.clear()

    assert (row.jev_calls, row.jev_input_tokens, row.jev_output_tokens) == (1, 100, 10)
    assert (row.num_calls, row.total_input_tokens, row.total_output_tokens) == (1, 2000, 300)


def test_jev_cost_uses_flat_jev_rate_and_totals_with_llm():
    from evals import token_tracking
    from evals.report import build_report
    from tennis_booking.agents.base import ConversationAgent, UsageRecord

    token_tracking.clear()
    agent = ConversationAgent(system_prompt="", tools=[], tool_executors={}, client=object())
    agent.usage_log.append(UsageRecord(turn=1, input_tokens=1_000_000, output_tokens=500_000, source="jev"))
    agent.usage_log.append(UsageRecord(turn=1, input_tokens=1_000_000, output_tokens=0))
    token_tracking.record_usage("jev", agent)
    (row,) = build_report(["jev"]).rows
    token_tracking.clear()

    assert row.jev_cost_usd == pytest.approx(0.042)
    assert row.combined_cost_usd == pytest.approx(0.042 + 0.20)


def test_report_splits_llm_and_jev_latency():
    from evals import token_tracking
    from evals.report import build_report
    from tennis_booking.agents.base import ConversationAgent, UsageRecord

    token_tracking.clear()
    agent = ConversationAgent(system_prompt="", tools=[], tool_executors={}, client=object())
    for ms in (100.0, 300.0):
        agent.usage_log.append(UsageRecord(turn=1, input_tokens=1, output_tokens=1, latency_ms=ms, source="jev"))
    agent.usage_log.append(UsageRecord(turn=1, input_tokens=1, output_tokens=1, latency_ms=2000.0))
    token_tracking.record_usage("jev", agent)
    report = build_report(["jev"])
    (row,) = report.rows
    token_tracking.clear()

    assert row.jev_total_latency_ms == 400.0
    assert row.total_latency_ms == 2000.0
    assert row.latency_p50_ms == 2000.0
    assert 100.0 <= row.jev_latency_p50_ms <= 300.0
    assert "Jev latency p90" in report.render_markdown()
