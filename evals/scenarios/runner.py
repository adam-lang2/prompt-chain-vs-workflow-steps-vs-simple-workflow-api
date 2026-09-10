from __future__ import annotations

from tennis_booking.agents.base import ConversationAgent
from evals.scenarios.scripted import ScriptedScenario


def run_scripted_scenario(agent: ConversationAgent, scenario: ScriptedScenario) -> list[str]:
    """Play every user turn in `scenario` through `agent`. Returns agent replies."""
    replies = []
    for turn in scenario.turns:
        replies.append(agent.send_user_message(turn))
    return replies
