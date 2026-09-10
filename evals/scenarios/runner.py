from __future__ import annotations

import os
import sys
import time

from tennis_booking.agents.base import ConversationAgent
from evals.scenarios.scripted import ScriptedScenario

# Same opt-in flag agents/base.py's per-call timing log uses -- see there.
_DEBUG_TIMING = bool(os.environ.get("TENNIS_BOOKING_DEBUG_TIMING"))


def run_scripted_scenario(agent: ConversationAgent, scenario: ScriptedScenario) -> list[str]:
    """Play every user turn in `scenario` through `agent`. Returns agent replies."""
    replies = []
    for i, turn in enumerate(scenario.turns):
        if _DEBUG_TIMING:
            print(f"[{time.strftime('%H:%M:%S')}]   scenario {scenario.name!r} turn {i}/{len(scenario.turns)} starting", file=sys.stderr, flush=True)
        turn_start = time.perf_counter()
        replies.append(agent.send_user_message(turn))
        if _DEBUG_TIMING:
            print(f"[{time.strftime('%H:%M:%S')}]   scenario {scenario.name!r} turn {i} finished in {(time.perf_counter() - turn_start) * 1000:.0f}ms", file=sys.stderr, flush=True)
    return replies
