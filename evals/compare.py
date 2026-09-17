"""`tennis-compare` -- standalone entry point that runs the standard
scripted comparison suite (`evals.suite.STANDARD_SUITE`) against one,
several, or (by default) every registered agent architecture
(`agents.agent_registry.AGENTS_UNDER_TEST`), across one or more models,
outside of pytest, and prints the standard comparison report
(`evals/report.py`).

pytest's existing parametrization (`test_scripted_booking.py`) already
covers the automated-test use case; this script is what you actually reach
for to run "just react vs. simple_workflow_api" interactively, or to
compare several models in one shot, without pytest's node-id `-k`/`::`
syntax, and to get the report in JSON or Markdown instead of pytest's
terminal output.

    uv run tennis-compare
    uv run tennis-compare --agent react --agent prompt_chain
    uv run tennis-compare --model openai/gpt-4o-mini --model openai/gpt-5.6-luna
    uv run tennis-compare --model deepseek/deepseek-v4-flash-20260731 --model openai/gpt-5.6-luna:none
    uv run tennis-compare --format json --out models.json
    uv run tennis-compare --format markdown --out latest-comparison.md

`--model` accepts an optional `:EFFORT` suffix (e.g. `openai/gpt-5.6-luna:none`)
to set that one model's OpenRouter reasoning effort ("none", "low", "high", ...)
for this run, overriding TENNIS_BOOKING_REASONING_EFFORT for that (agent, model)
pair only -- every other model in the same run keeps its own suffix (or the
env var / no override) untouched, so comparing a reasoning-capable model
against a non-reasoning one in one report doesn't require two invocations.

`--model` is repeatable: every agent runs once per model given (default:
just `agents.base.DEFAULT_MODEL`), and every (agent, model) pair lands as
its own row in the SAME report -- comparing models is a `--model` flag on
one run, not separate invocations/files to stitch together by hand.

Every report lands under results/ at the repo root (created automatically) --
that's the one enforced convention for where eval output lives, so results
from different runs are always findable in one place instead of scattered
wherever `--out` happened to point. `--out` takes a bare filename or a path
relative to results/, not an absolute path or one that escapes it via `..`;
omit it and a timestamped filename is used.

STANDARD_SUITE's scripted scenarios have fixed user turns written against
`evals/fixtures/live_courts_cassette.py`'s recorded court data (the same
cassette `evals/conftest.py` patches in for pytest) -- this script patches
the same two functions before running, for the same reason: real live
Nominatim/Overpass results won't match what a scenario's scripted turns
assume, which breaks scoring for reasons that have nothing to do with the
model or architecture under test.

Requires OPENROUTER_API_KEY (see README's Setup section) -- this makes
real, live model calls, same as `uv run pytest evals/ -v`.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from evals.fixtures import live_courts_cassette
from evals.report import build_report
from evals.results_tracking import record_result
from evals.scenarios.runner import run_scripted_scenario
from evals.suite import STANDARD_SUITE
from evals.token_tracking import record_usage
from tennis_booking.agents.base import DEFAULT_MODEL, has_usable_credentials
from tennis_booking.agents.agent_registry import AGENTS_BY_ID, AGENTS_UNDER_TEST
from tennis_booking.scoring import score_conversation
from tennis_booking.tools import live_courts

# The one enforced location for eval output -- see module docstring. Resolved
# from this file's location (not cwd) so it's always the repo-root results/
# regardless of where `tennis-compare` is invoked from.
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
_FORMAT_EXTENSIONS = {"text": "txt", "json": "json", "markdown": "md"}


def _parse_model_spec(spec: str) -> tuple[str, str | None]:
    """Split a `--model` value into (slug, reasoning_effort). The effort is
    an optional `:EFFORT` suffix (e.g. `openai/gpt-5.6-luna:none`) -- absent
    means "use TENNIS_BOOKING_REASONING_EFFORT / no override", not "none".
    Model slugs are plain `provider/name` strings with no ':' of their own,
    so a single rsplit is unambiguous.
    """
    slug, sep, effort = spec.rpartition(":")
    if not sep:
        return spec, None
    return slug, effort


def _resolve_out_path(out_arg: str | None, fmt: str) -> Path:
    """Every tennis-compare report is required to land under RESULTS_DIR.
    `out_arg` is joined onto RESULTS_DIR (never treated as an independent
    path), then checked that it didn't escape via `..` or an absolute
    override -- Path's `/` operator ignores the left side entirely when the
    right side is absolute, which would otherwise let `--out /tmp/x.md`
    silently bypass the whole point of this function.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if out_arg is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_arg = f"{timestamp}-comparison.{_FORMAT_EXTENSIONS[fmt]}"
    if Path(out_arg).is_absolute():
        raise ValueError(f"--out must be a relative path under {RESULTS_DIR}, not absolute: {out_arg}")
    candidate = (RESULTS_DIR / out_arg).resolve()
    if not candidate.is_relative_to(RESULTS_DIR.resolve()):
        raise ValueError(
            f"--out must resolve to a path inside {RESULTS_DIR} (got {candidate}); "
            "pass a bare filename or a path relative to results/, not one that escapes it."
        )
    return candidate


def _patch_live_courts() -> None:
    """Replace the two real-network calls with the recorded cassette, same
    as `evals/conftest.py`'s autouse `_recorded_court_lookups` fixture does
    for pytest. Unlike that fixture, this has no teardown -- fine here since
    the whole point of this script is a single eval run per process, not a
    long-lived session other code might expect unpatched.
    """
    live_courts._geocode = live_courts_cassette.geocode
    live_courts._query_overpass = live_courts_cassette.query_overpass


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--agent",
        action="append",
        dest="agent_ids",
        metavar="AGENT_ID",
        help=(
            "Agent id to include (repeatable), e.g. --agent react. "
            "Defaults to every entry in AGENTS_UNDER_TEST. "
            f"Valid ids: {', '.join(a.id for a in AGENTS_UNDER_TEST)}."
        ),
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        metavar="MODEL_SLUG",
        help=(
            "OpenRouter model slug to run every agent against (repeatable), "
            "e.g. --model openai/gpt-4o-mini. Repeat to compare several models "
            f"in one report. Defaults to just {DEFAULT_MODEL!r}. Append "
            "':EFFORT' to set that model's reasoning effort for this run, "
            "e.g. --model openai/gpt-5.6-luna:none."
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
        metavar="FILENAME",
        help=(
            f"Filename (or path relative to {RESULTS_DIR}/) to write the report to, "
            "in addition to printing it. Defaults to a timestamped name. Must not be "
            "absolute or escape results/ via '..'."
        ),
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

    try:
        out_path = _resolve_out_path(args.out, args.format)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    models = args.models or [DEFAULT_MODEL]
    _patch_live_courts()

    for model_spec in models:
        model, reasoning_effort = _parse_model_spec(model_spec)
        for agent_id in agent_ids:
            agent = AGENTS_BY_ID[agent_id]
            print(f"Running {agent.id} [{model_spec}] against {len(STANDARD_SUITE)} scenarios...", file=sys.stderr)
            for i, scenario in enumerate(STANDARD_SUITE):
                scenario_start = time.perf_counter()
                print(f"  [{i + 1}/{len(STANDARD_SUITE)}] {scenario.name} ...", file=sys.stderr, flush=True)
                conversation_agent = agent.create()
                conversation_agent.model = model
                if reasoning_effort is not None:
                    conversation_agent.reasoning_effort = reasoning_effort
                run_scripted_scenario(conversation_agent, scenario)
                print(f"  [{i + 1}/{len(STANDARD_SUITE)}] {scenario.name} done in {time.perf_counter() - scenario_start:.1f}s", file=sys.stderr, flush=True)
                record_usage(agent.id, conversation_agent, model=model_spec)
                score = score_conversation(
                    tool_call_log=conversation_agent.tool_call_log,
                    expected=scenario.expected,
                    num_turns=len(scenario.turns),
                )
                record_result(agent.id, model_spec, scenario.name, score)

    report = build_report(agent_ids=agent_ids)
    rendered = {
        "text": report.render_text,
        "json": report.render_json,
        "markdown": report.render_markdown,
    }[args.format]()

    with open(out_path, "w") as f:
        f.write(rendered + "\n")
    print(f"Report written to {out_path}", file=sys.stderr)
    print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
