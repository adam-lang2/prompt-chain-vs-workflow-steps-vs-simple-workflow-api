"""Interactive terminal chat with any registered agent, for manually
eyeballing behavior before trusting the automated evals.

    uv run tennis-chat --agent prompt_chain
    uv run tennis-chat --agent workflow --quiet
"""
from __future__ import annotations

import argparse
import json
import sys

from tennis_booking.agents.base import ConversationAgent, has_usable_credentials
from tennis_booking.agents.agent_registry import AGENTS_BY_ID


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=sorted(AGENTS_BY_ID), default="prompt_chain")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Don't print tool calls (search_availability / book_court / get_next_step) as they happen.",
    )
    args = parser.parse_args()

    if not has_usable_credentials():
        print(
            "No OPENROUTER_API_KEY found. Get a key from https://openrouter.ai/keys "
            "and put it in .env as OPENROUTER_API_KEY.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    agent = AGENTS_BY_ID[args.agent].create()

    print(f"--- tennis-chat: {args.agent} agent (model={agent.model}) ---")
    print("Type your message and press enter. Ctrl-D or 'exit' to quit.\n")

    while True:
        try:
            user_text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            continue
        if user_text.lower() in ("exit", "quit"):
            break

        calls_before = len(agent.tool_call_log)
        reply = agent.send_user_message(user_text)

        if not args.quiet:
            for record in agent.tool_call_log[calls_before:]:
                print(f"  [tool] {record.name}({_short_json(record.args)}) -> {_short_json(record.result)}")

        print(f"agent> {reply}\n")

    _print_summary(agent)


def _short_json(value: dict, limit: int = 300) -> str:
    text = json.dumps(value, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _print_summary(agent: ConversationAgent) -> None:
    print("\n--- session summary ---")
    print(f"turns: {agent.turn_count}")
    print(f"tool calls: {len(agent.tool_call_log)}")
    for record in agent.tool_call_log:
        print(f"  turn {record.turn}: {record.name}({_short_json(record.args)})")


if __name__ == "__main__":
    main()
