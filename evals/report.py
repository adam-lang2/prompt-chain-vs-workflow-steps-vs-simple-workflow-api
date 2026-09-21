"""The standard comparison report: one row per (agent, model), built from
`token_tracking.py` (tokens/cost/latency) + `results_tracking.py`
(pass/fail), rendered as an aligned text table, JSON, or Markdown.

Used from two places:
- `evals/conftest.py`'s `pytest_terminal_summary`, printing the text
  rendering at the end of `uv run pytest evals/ -v` (one model per process,
  so every row in that report shares the same model).
- `evals/compare.py`, the standalone `tennis-compare` entry point, which can
  run several models in one invocation (`--model`, repeatable) -- rows for
  different models sit in the same report/table rather than one report per
  model, so a blog-post-style model comparison never has to be stitched
  together by hand from separate files.

Keeping report-building here (not duplicated in both callers) is what
guarantees the pytest run and the standalone script report identically
shaped, identically computed numbers for the same underlying samples.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from evals import results_tracking, stats, token_tracking
from tennis_booking.agents.agent_registry import AGENTS_BY_ID


def _usd(value: float | None) -> str:
    return f"${value:.4f}" if value is not None else "—"


@dataclass
class AgentReportRow:
    agent_id: str
    model: str
    label: str
    num_calls: int
    avg_input_tokens: float
    total_input_tokens: int
    avg_output_tokens: float
    total_output_tokens: int
    total_reasoning_tokens: int
    total_cached_tokens: int
    total_cost_usd: float | None
    latency_p50_ms: float
    latency_p90_ms: float
    total_latency_ms: float
    max_tool_calls_per_turn: int
    turn_latency_p50_ms: float
    turn_latency_p90_ms: float
    passed_scenarios: int
    total_scenarios: int
    failures: list[tuple[str, list[str]]] = field(default_factory=list)
    # Jev (TypeSafe) interpretation calls, reported apart from the LLM's
    # (num_calls / *_tokens above are LLM-only). Zero for agents without Jev.
    jev_calls: int = 0
    jev_input_tokens: int = 0
    jev_output_tokens: int = 0
    jev_latency_p50_ms: float = 0.0
    jev_latency_p90_ms: float = 0.0
    jev_total_latency_ms: float = 0.0
    jev_cost_usd: float | None = None

    @property
    def combined_cost_usd(self) -> float | None:
        if self.total_cost_usd is None and self.jev_cost_usd is None:
            return None
        return (self.total_cost_usd or 0.0) + (self.jev_cost_usd or 0.0)

    @property
    def pass_rate(self) -> float | None:
        if self.total_scenarios == 0:
            return None
        return self.passed_scenarios / self.total_scenarios


@dataclass
class ComparisonReport:
    rows: list[AgentReportRow]

    def render_text(self) -> str:
        if not self.rows:
            return "No comparison data collected this run."
        lines = ["Agent comparison (tokens / cost / latency / pass-fail)", ""]
        for row in self.rows:
            cost = f"${row.total_cost_usd:.4f}" if row.total_cost_usd is not None else "—"
            pass_rate = (
                f"{row.passed_scenarios}/{row.total_scenarios}" if row.total_scenarios else "n/a"
            )
            lines.append(
                f"{row.agent_id} [{row.model}]: {row.num_calls} calls | "
                f"avg input={row.avg_input_tokens:,.0f} tok/call | "
                f"avg output={row.avg_output_tokens:,.0f} tok/call | "
                f"total input={row.total_input_tokens:,} | "
                f"total output={row.total_output_tokens:,} (reasoning={row.total_reasoning_tokens:,}) | "
                f"cached input={row.total_cached_tokens:,} | "
                f"jev calls={row.jev_calls} input={row.jev_input_tokens:,} output={row.jev_output_tokens:,} "
                f"latency p50={row.jev_latency_p50_ms:,.0f}ms p90={row.jev_latency_p90_ms:,.0f}ms "
                f"total={row.jev_total_latency_ms:,.0f}ms | "
                f"LLM cost={cost} | jev cost={_usd(row.jev_cost_usd)} | total cost={_usd(row.combined_cost_usd)} | "
                f"LLM latency p50={row.latency_p50_ms:,.0f}ms p90={row.latency_p90_ms:,.0f}ms "
                f"total={row.total_latency_ms:,.0f}ms | "
                f"max tool calls/turn={row.max_tool_calls_per_turn} | "
                f"turn latency p50={row.turn_latency_p50_ms:,.0f}ms p90={row.turn_latency_p90_ms:,.0f}ms | "
                f"scenarios passed={pass_rate}"
            )
            for scenario_name, mismatches in row.failures:
                lines.append(f"    FAIL {scenario_name}: {'; '.join(mismatches) or 'unknown failure'}")
        return "\n".join(lines)

    def render_markdown(self) -> str:
        if not self.rows:
            return "_No comparison data collected this run._"
        header = (
            "| Agent | Model | LLM calls | LLM input tok | LLM cached input tok | LLM output tok | "
            "LLM reasoning tok | "
            "Jev calls | Jev input tok | Jev output tok | LLM cost | Jev cost | Total cost | "
            "LLM latency p50 | LLM latency p90 | Jev latency p50 | Jev latency p90 | "
            "Max tool calls/turn | Turn latency p50 | "
            "Turn latency p90 | Passed |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
        )
        lines = [header]
        for row in self.rows:
            cost = f"${row.total_cost_usd:.4f}" if row.total_cost_usd is not None else "—"
            pass_rate = (
                f"{row.passed_scenarios}/{row.total_scenarios}" if row.total_scenarios else "n/a"
            )
            lines.append(
                f"| {row.agent_id} | {row.model} | {row.num_calls} | {row.total_input_tokens:,} | "
                f"{row.total_cached_tokens:,} | {row.total_output_tokens:,} | "
                f"{row.total_reasoning_tokens:,} | {row.jev_calls or '—'} | "
                f"{row.jev_input_tokens:,} | {row.jev_output_tokens:,} | "
                f"{cost} | {_usd(row.jev_cost_usd) if row.jev_calls else '—'} | {_usd(row.combined_cost_usd)} | "
                f"{row.latency_p50_ms:,.0f}ms | {row.latency_p90_ms:,.0f}ms | "
                f"{f'{row.jev_latency_p50_ms:,.0f}ms' if row.jev_calls else '—'} | "
                f"{f'{row.jev_latency_p90_ms:,.0f}ms' if row.jev_calls else '—'} | "
                f"{row.max_tool_calls_per_turn} | "
                f"{row.turn_latency_p50_ms:,.0f}ms | {row.turn_latency_p90_ms:,.0f}ms | {pass_rate} |"
            )
        if any(row.failures for row in self.rows):
            lines.append("")
            lines.append("Failures:")
            for row in self.rows:
                for scenario_name, mismatches in row.failures:
                    lines.append(f"- **{row.agent_id}** [{row.model}] / `{scenario_name}`: {'; '.join(mismatches)}")
        return "\n".join(lines)

    def render_json(self) -> str:
        return json.dumps(
            [
                {
                    "agent_id": row.agent_id,
                    "model": row.model,
                    "label": row.label,
                    "num_calls": row.num_calls,
                    "avg_input_tokens": row.avg_input_tokens,
                    "total_input_tokens": row.total_input_tokens,
                    "avg_output_tokens": row.avg_output_tokens,
                    "total_output_tokens": row.total_output_tokens,
                    "total_reasoning_tokens": row.total_reasoning_tokens,
                    "total_cached_tokens": row.total_cached_tokens,
                    "total_cost_usd": row.total_cost_usd,
                    "jev_calls": row.jev_calls,
                    "jev_input_tokens": row.jev_input_tokens,
                    "jev_output_tokens": row.jev_output_tokens,
                    "jev_latency_p50_ms": row.jev_latency_p50_ms,
                    "jev_latency_p90_ms": row.jev_latency_p90_ms,
                    "jev_total_latency_ms": row.jev_total_latency_ms,
                    "jev_cost_usd": row.jev_cost_usd,
                    "combined_cost_usd": row.combined_cost_usd,
                    "latency_p50_ms": row.latency_p50_ms,
                    "latency_p90_ms": row.latency_p90_ms,
                    "total_latency_ms": row.total_latency_ms,
                    "max_tool_calls_per_turn": row.max_tool_calls_per_turn,
                    "turn_latency_p50_ms": row.turn_latency_p50_ms,
                    "turn_latency_p90_ms": row.turn_latency_p90_ms,
                    "passed_scenarios": row.passed_scenarios,
                    "total_scenarios": row.total_scenarios,
                    "failures": [
                        {"scenario": name, "mismatches": mismatches} for name, mismatches in row.failures
                    ],
                }
                for row in self.rows
            ],
            indent=2,
        )


def build_report(agent_ids: list[str] | None = None) -> ComparisonReport:
    """Build a ComparisonReport from every usage sample + scenario result
    recorded so far this session (see token_tracking.py / results_tracking.py),
    optionally restricted to `agent_ids`. Rows are keyed by (agent_id, model)
    -- a session that ran several models (e.g. `tennis-compare --model a
    --model b`) gets one row per agent per model, all in the same report,
    rather than a separate report per model."""
    samples = token_tracking.all_samples()
    turn_samples = token_tracking.all_turn_samples()
    results = results_tracking.all_results()

    by_key_samples: dict[tuple[str, str], list] = {}
    for sample in samples:
        by_key_samples.setdefault((sample.agent_id, sample.model), []).append(sample)

    by_key_turn_samples: dict[tuple[str, str], list] = {}
    for turn_sample in turn_samples:
        by_key_turn_samples.setdefault((turn_sample.agent_id, turn_sample.model), []).append(turn_sample)

    by_key_results: dict[tuple[str, str], list] = {}
    for result in results:
        by_key_results.setdefault((result.agent_id, result.model), []).append(result)

    all_keys = set(by_key_samples) | set(by_key_results)
    if agent_ids is not None:
        all_keys = {key for key in all_keys if key[0] in agent_ids}
    keys_to_report = sorted(all_keys)

    rows: list[AgentReportRow] = []
    for agent_id, model in keys_to_report:
        all_key_samples = by_key_samples.get((agent_id, model), [])
        key_samples = [s for s in all_key_samples if s.source == "llm"]
        jev_samples = [s for s in all_key_samples if s.source == "jev"]
        key_turn_samples = by_key_turn_samples.get((agent_id, model), [])
        key_results = by_key_results.get((agent_id, model), [])
        label = AGENTS_BY_ID[agent_id].label if agent_id in AGENTS_BY_ID else agent_id

        if key_turn_samples:
            max_tool_calls_per_turn = max(s.max_tool_calls_in_a_turn for s in key_turn_samples)
            turn_latencies = [ms for s in key_turn_samples for ms in s.turn_latencies_ms]
            turn_p50 = stats.percentile(turn_latencies, 50) if turn_latencies else 0.0
            turn_p90 = stats.percentile(turn_latencies, 90) if turn_latencies else 0.0
        else:
            max_tool_calls_per_turn = 0
            turn_p50 = turn_p90 = 0.0

        if key_samples:
            input_toks = [s.input_tokens for s in key_samples]
            output_toks = [s.output_tokens for s in key_samples]
            latencies = [s.latency_ms for s in key_samples if s.latency_ms]
            costs = [s.cost_usd for s in key_samples if s.cost_usd is not None]
            num_calls = len(key_samples)
            avg_input = stats.mean(input_toks)
            avg_output = stats.mean(output_toks)
            total_input = sum(input_toks)
            total_output = sum(output_toks)
            total_reasoning = sum(s.reasoning_tokens for s in key_samples)
            total_cached = sum(s.cached_tokens for s in key_samples)
            total_cost = sum(costs) if costs else None
            p50 = stats.percentile(latencies, 50) if latencies else 0.0
            p90 = stats.percentile(latencies, 90) if latencies else 0.0
            total_latency = sum(latencies)
        else:
            num_calls = 0
            avg_input = avg_output = 0.0
            total_input = total_output = total_reasoning = total_cached = 0
            total_cost = None
            p50 = p90 = total_latency = 0.0

        failures = [(r.scenario_name, r.mismatches) for r in key_results if not r.success]
        passed = sum(1 for r in key_results if r.success)

        rows.append(
            AgentReportRow(
                agent_id=agent_id,
                model=model,
                label=label,
                num_calls=num_calls,
                avg_input_tokens=avg_input,
                total_input_tokens=total_input,
                avg_output_tokens=avg_output,
                total_output_tokens=total_output,
                total_reasoning_tokens=total_reasoning,
                total_cached_tokens=total_cached,
                total_cost_usd=total_cost,
                latency_p50_ms=p50,
                latency_p90_ms=p90,
                total_latency_ms=total_latency,
                max_tool_calls_per_turn=max_tool_calls_per_turn,
                turn_latency_p50_ms=turn_p50,
                turn_latency_p90_ms=turn_p90,
                passed_scenarios=passed,
                total_scenarios=len(key_results),
                failures=failures,
                jev_calls=len(jev_samples),
                jev_input_tokens=sum(s.input_tokens for s in jev_samples),
                jev_output_tokens=sum(s.output_tokens for s in jev_samples),
                jev_cost_usd=(
                    sum(s.cost_usd for s in jev_samples if s.cost_usd is not None) if jev_samples else None
                ),
                jev_latency_p90_ms=(
                    stats.percentile([s.latency_ms for s in jev_samples], 90) if jev_samples else 0.0
                ),
                jev_total_latency_ms=sum(s.latency_ms for s in jev_samples),
                jev_latency_p50_ms=(
                    stats.percentile([s.latency_ms for s in jev_samples], 50) if jev_samples else 0.0
                ),
            )
        )

    return ComparisonReport(rows=rows)
