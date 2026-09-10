"""`tennis-compare` -- standalone entry point that runs the standard
scripted comparison suite (`evals.suite.STANDARD_SUITE`) against one,
several, or (by default) every registered agent architecture
(`agents.agent_registry.AGENTS_UNDER_TEST`), outside of pytest, and prints the
standard comparison report (`evals/report.py`).

pytest's existing parametrization (`test_scripted_booking.py`) already
covers the automated-test use case; this script is what you actually reach
for to run "just workflow vs. simple_workflow_api" interactively, without
pytest's node-id `-k`/`::` syntax, and to get the report in JSON or
Markdown instead of pytest's terminal output.

    uv run tennis-compare
    uv run tennis-compare --agent workflow --agent prompt_chain
    uv run tennis-compare --format json --out report.json
    uv run tennis-compare --format markdown --out docs/latest-comparison.md

Requires OPENROUTER_API_KEY (see README's Setup section) -- this makes
real, live model calls, same as `uv run pytest evals/ -v`.
"""
from __future__ import annotations

import argparse
import sys
import time

from evals.report import build_report
from evals.results_tracking import record_result
from evals.scenarios.runner import run_scripted_scenario
from evals.suite import STANDARD_SUITE
from evals.token_tracking import record_usage
from tennis_booking.agents.base import has_usable_credentials
from tennis_booking.agents.agent_registry import AGENTS_BY_ID, AGENTS_UNDER_TEST
from tennis_booking.scoring import score_conversation


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--agent",
        action="append",
        dest="agent_ids",
        metavar="AGENT_ID",
        help=(
            "Agent id to include (repeatable), e.g. --agent workflow. "
            "Defaults to every entry in AGENTS_UNDER_TEST. "
            f"Valid ids: {', '.join(a.id for a in AGENTS_UNDER_TEST)}."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Report rendering (default: text).",
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        help="Write the report to this file instead of stdout.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if not has_usable_credentials():
        print(
            "No OPENROUTER_API_KEY found. Get a key from https://openrouter.ai/keys "
            "and put it in .env as OPENROUTER_API_KEY.",
            file=sys.stderr,
        )
        return 1

    agent_ids = args.agent_ids or [a.id for a in AGENTS_UNDER_TEST]
    unknown = [a for a in agent_ids if a not in AGENTS_BY_ID]
    if unknown:
        print(f"Unknown agent id(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Valid ids: {', '.join(a.id for a in AGENTS_UNDER_TEST)}", file=sys.stderr)
        return 1

    for agent_id in agent_ids:
        agent = AGENTS_BY_ID[agent_id]
        print(f"Running {agent.id} against {len(STANDARD_SUITE)} scenarios...", file=sys.stderr)
        for i, scenario in enumerate(STANDARD_SUITE):
            scenario_start = time.perf_counter()
            print(f"  [{i + 1}/{len(STANDARD_SUITE)}] {scenario.name} ...", file=sys.stderr, flush=True)
            conversation_agent = agent.create()
            run_scripted_scenario(conversation_agent, scenario)
            print(f"  [{i + 1}/{len(STANDARD_SUITE)}] {scenario.name} done in {time.perf_counter() - scenario_start:.1f}s", file=sys.stderr, flush=True)
            record_usage(agent.id, conversation_agent)
            score = score_conversation(
                tool_call_log=conversation_agent.tool_call_log,
                expected=scenario.expected,
                num_turns=len(scenario.turns),
            )
            record_result(agent.id, scenario.name, score)

    report = build_report(agent_ids=agent_ids)
    rendered = {
        "text": report.render_text,
        "json": report.render_json,
        "markdown": report.render_markdown,
    }[args.format]()

    if args.out:
        with open(args.out, "w") as f:
            f.write(rendered + "\n")
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
