"""Wiring smoke tests using a fake OpenAI-shaped client (no network, no API
key). These confirm the tool-use loop itself -- executing tool calls,
feeding tool result messages back, stopping on a text-only response -- is
correct for every agent architecture, independent of real model behavior.
"""
from __future__ import annotations

from tennis_booking.agents.a2a_fsm_api import create_agent as create_a2a_fsm_api
from tennis_booking.agents.prompt_chain_agent import create_agent as create_prompt_chain_agent
from tennis_booking.agents.prompt_chain_agent_v2 import create_agent as create_prompt_chain_v2_agent
from tennis_booking.agents.workflow_step_agent import create_agent as create_workflow_step_agent
from tests.fakes import FakeOpenAIClient, FakeResponse, FakeToolCall


def test_workflow_step_agent_executes_search_then_replies():
    fake_client = FakeOpenAIClient(
        scripted_responses=[
            FakeResponse(
                tool_calls=[
                    FakeToolCall(
                        id="tu_1",
                        name="search_availability",
                        input={
                            "area": "downtown",
                            "date": "2026-09-05",
                            "surface": "clay",
                            "indoor_outdoor": "outdoor",
                        },
                    )
                ]
            ),
            FakeResponse(content="Here's what's open downtown."),
        ]
    )
    agent = create_workflow_step_agent(client=fake_client)

    reply = agent.send_user_message("Book me a clay court downtown on 2026-09-05, outdoor.")

    assert reply == "Here's what's open downtown."
    assert len(agent.tool_call_log) == 1
    assert agent.tool_call_log[0].name == "search_availability"
    assert "courts" in agent.tool_call_log[0].result
    # Two model calls: one that produced the tool call, one after the tool result.
    assert len(fake_client.chat.completions.calls) == 2


def test_prompt_chain_agent_calls_get_next_step_then_replies():
    fake_client = FakeOpenAIClient(
        scripted_responses=[
            FakeResponse(tool_calls=[FakeToolCall(id="tu_1", name="get_next_step", input={})]),
            FakeResponse(content="Roughly where would you like to play?"),
        ]
    )
    agent = create_prompt_chain_agent(client=fake_client)

    reply = agent.send_user_message("Hi, I'd like to book a tennis court.")

    assert reply == "Roughly where would you like to play?"
    assert len(agent.tool_call_log) == 1
    assert agent.tool_call_log[0].name == "get_next_step"
    assert agent.tool_call_log[0].result["next_step"] == "ask_area"
    assert agent.state.area is None


def test_prompt_chain_v2_agent_calls_get_next_step_with_minimal_payload():
    # create_agent() generates its own conversation_id and embeds it in the
    # system prompt, so build the agent first (with a throwaway client) to
    # learn that id, then swap in a fake client scripted with a tool call
    # that references it -- exactly what the real model would do after
    # reading the id out of its own system prompt.
    agent = create_prompt_chain_v2_agent(client=FakeOpenAIClient(scripted_responses=[]))
    conversation_id = agent.conversation_id
    assert conversation_id in agent.system_prompt

    agent.client = FakeOpenAIClient(
        scripted_responses=[
            FakeResponse(
                tool_calls=[
                    FakeToolCall(id="tu_1", name="get_next_step", input={"conversation_id": conversation_id})
                ]
            ),
            FakeResponse(content="Roughly where would you like to play?"),
        ]
    )

    reply = agent.send_user_message("Hi, I'd like to book a tennis court.")

    assert reply == "Roughly where would you like to play?"
    assert len(agent.tool_call_log) == 1
    record = agent.tool_call_log[0]
    assert record.name == "get_next_step"
    assert record.result["next_step"] == "ask_area"
    assert "state" not in record.result


def test_a2a_fsm_api_uses_the_structured_schema():
    # book_tennis_court takes an `updates` array of {slot, value} deltas --
    # setting `area` directly as a slot should land on FSMAgent's state and
    # advance to ask_date, same as any other single-slot update.
    fake_client = FakeOpenAIClient(
        scripted_responses=[
            FakeResponse(
                tool_calls=[
                    FakeToolCall(
                        id="tu_1",
                        name="book_tennis_court",
                        input={"updates": [{"slot": "area", "value": "downtown"}]},
                    )
                ]
            ),
            FakeResponse(content="What date works for you?"),
        ]
    )
    agent = create_a2a_fsm_api(client=fake_client)

    reply = agent.send_user_message("Hi, I'd like to book a tennis court near downtown.")

    assert reply == "What date works for you?"
    assert len(agent.tool_call_log) == 1
    assert agent.tool_call_log[0].name == "book_tennis_court"
    assert agent.tool_call_log[0].result["current_node"] == "ask_date"
    assert agent.state.area == "downtown"


def test_a2a_fsm_api_accepts_multiple_slots_in_one_call():
    fake_client = FakeOpenAIClient(
        scripted_responses=[
            FakeResponse(
                tool_calls=[
                    FakeToolCall(
                        id="tu_1",
                        name="book_tennis_court",
                        input={
                            "updates": [
                                {"slot": "area", "value": "downtown"},
                                {"slot": "date", "value": "2026-09-19"},
                                {"slot": "surface", "value": "clay"},
                            ]
                        },
                    )
                ]
            ),
            FakeResponse(content="ok"),
        ]
    )
    agent = create_a2a_fsm_api(client=fake_client)

    agent.send_user_message("downtown, Sept 19th, clay")

    result = agent.tool_call_log[0].result
    assert result["applied"] == {"area": "downtown", "date": "2026-09-19", "surface": "clay"}
    assert result["current_node"] == "ask_duration"


def test_a2a_fsm_api_folds_internal_tool_calls_into_the_log():
    # Updates that complete the whole workflow up to search_availability
    # make FSMAgent execute search_availability itself, as a side effect of
    # one book_tennis_court call -- that internal call must show up in the
    # agent's own tool_call_log too, not just FSMAgent's private list.
    fake_client = FakeOpenAIClient(
        scripted_responses=[
            FakeResponse(
                tool_calls=[
                    FakeToolCall(
                        id="tu_1",
                        name="book_tennis_court",
                        input={"updates": [{"slot": "area", "value": "downtown"}]},
                    )
                ]
            ),
            FakeResponse(content="ok"),
        ]
    )
    agent = create_a2a_fsm_api(client=fake_client)
    agent.state.date = "2026-09-05"
    agent.state.surface = "clay"
    agent.state.duration_minutes = 90
    agent.state.num_players = 4
    agent.state.indoor_outdoor = "outdoor"

    agent.send_user_message("downtown")

    names = [r.name for r in agent.tool_call_log]
    assert names == ["search_availability", "book_tennis_court"]


def test_prompt_chain_v2_agent_rejects_missing_conversation_id():
    fake_client = FakeOpenAIClient(
        scripted_responses=[
            FakeResponse(tool_calls=[FakeToolCall(id="tu_1", name="get_next_step", input={})]),
            FakeResponse(content="ok"),
        ]
    )
    agent = create_prompt_chain_v2_agent(client=fake_client)

    agent.send_user_message("Hi, I'd like to book a tennis court.")

    assert agent.tool_call_log[0].result == {
        "error": "conversation_id is required on every get_next_step call"
    }
