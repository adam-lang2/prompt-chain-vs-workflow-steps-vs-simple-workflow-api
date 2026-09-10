"""Bridges a stateful ConversationAgent into the `model_callback` shape
deepeval's ConversationSimulator expects: a function of (input, turns,
thread_id) -> Turn.

deepeval runs multiple simulated conversations concurrently (bounded by
`max_concurrent` on ConversationSimulator), each identified by a unique
`thread_id` for the life of that conversation -- so we lazily create one
ConversationAgent per thread_id and keep it around across turns, which is
exactly the "each turn resumes from wherever the agent left off" behavior
this whole project is built to compare.
"""
from __future__ import annotations

from typing import Callable

from deepeval.test_case import ToolCall, Turn

from tennis_booking.agents.base import ConversationAgent


def make_model_callback(agent_factory: Callable[[], ConversationAgent]) -> Callable:
    agents_by_thread: dict[str, ConversationAgent] = {}

    def model_callback(input: str, turns: list, thread_id: str) -> Turn:
        agent = agents_by_thread.get(thread_id)
        if agent is None:
            agent = agent_factory()
            agents_by_thread[thread_id] = agent

        calls_before = len(agent.tool_call_log)
        reply_text = agent.send_user_message(input)
        new_calls = agent.tool_call_log[calls_before:]

        return Turn(
            role="assistant",
            content=reply_text,
            tools_called=[
                ToolCall(name=record.name, input_parameters=record.args, output=record.result)
                for record in new_calls
            ],
        )

    # Exposed so callers can fold each created agent's usage_log into the
    # session-wide token accounting after the simulation finishes (see
    # evals/token_tracking.py) -- the simulator itself never sees the
    # ConversationAgent objects, only this callback.
    model_callback.agents_by_thread = agents_by_thread
    return model_callback
