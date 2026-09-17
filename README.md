# prompt-chain-vs-workflow-steps-vs-simple-workflow-api

An experiment comparing the **operational metrics** — cost, latency, and
reliability — of three structurally different ways to implement the same
multi-turn agent workflow (booking a tennis court through a conversational
back-and-forth).

Rather than argue about which pattern *should* win, this project implements all
three against one shared workflow definition, drives them through the same
scripted conversations, and scores them with the same deterministic criteria —
so any difference in the numbers comes from the architecture itself, not from
one agent getting better-written prompts or a test drifting between
copy-pasted versions.

## The three architectures

The difference between them is **how much of the job stays inside the LLM**.
Each step moves one more responsibility out of the model and into
deterministic server-side code:

| Agent | Conversation | Workflow state | Tool execution |
|---|---|---|---|
| **`react`** | LLM | **LLM** — re-derived from the raw transcript every turn | **LLM** — calls all 3 tools itself |
| **`prompt_chain`** | LLM | **Server-side** — `BookingState` in a `ConversationStore` | **LLM** — calls all 3 tools itself |
| **`simple_workflow_api`** | LLM | **Server-side** — `BookingState` in a LangGraph step machine | **Server-side** — `BookingWorkflowEngine` runs them |

- **ReAct** (`agents/react_agent.py`) — the workflow is a numbered list of steps
  baked into one static system prompt. The model has no state tool and must
  re-read the whole transcript every turn to work out which step it's on.
- **Prompt-chain** (`agents/prompt_chain_agent.py`) — the workflow lives
  server-side. The system prompt describes it only at a high level, and the
  model calls `get_next_step()` every turn to receive one freshly generated
  instruction. Progress is keyed by a `conversation_id` the model must pass on
  every call — the pattern a real stateless tool backend would use. The wire
  payload is minimal: no state echo, just the next instruction.
- **Simple-workflow-api** (`agents/simple_workflow_api_agent.py`) — agent-1 has
  exactly one tool, `book_tennis_court_with_grammar`, taking an `updates` array
  of `{slot, value}` deltas: a correction, the current answer, or several
  not-yet-reached answers, in any combination, in one call. Its handler
  delegates to `BookingWorkflowEngine` (`workflow_engine/`) — agent-2, not an
  LLM at all, but a deterministic `langgraph.graph.StateGraph` that validates
  each slot, runs `search_availability` / `book_court` / `send_confirmation`
  itself the instant the workflow reaches them, and hands back only the next
  instruction.

Every agent implements the *identical* workflow, defined once in
`workflow_steps.py`, and is listed in `agents/agent_registry.py`. Every eval is
written once and parametrized over that registry. All three share the same
OpenAI-SDK Chat Completions tool-use loop (`agents/base.py`, talking to
OpenRouter), so token, latency, and cost numbers are directly comparable.

## The workflow

Sixteen steps (`STEPS` in `workflow_steps.py`), three of which are tool
actions: ask area → date → surface → duration → players → indoor/outdoor →
**search availability** → pick court/time → skill level → racket rental → name
→ email → confirm summary → **book court** → **send confirmation** → close out.

Two policies are defined once (`STALE_SEARCH_GUIDANCE`, `GROUNDING_GUIDANCE`)
and included verbatim in every agent's prompt:

- **Staleness** — if the user changes a search input (area, date, surface,
  duration, players, indoor/outdoor) after availability was looked up, the old
  results are stale; search again before letting them pick a time.
  `BookingState.search_params_stale()` enforces this wherever server-side state
  exists; `react` relies on the instruction text alone.
- **Grounding** — never state or book a court, time, or price that isn't
  literally in the most recent `search_availability` result.

Court data has three sources: **live** (`tools/live_courts.py`, a real
Nominatim geocode + Overpass query — what makes `area` genuinely free text),
a **recorded cassette** (`evals/fixtures/`, replayed by every eval so scripted
expectations can't break when live data drifts), and **`mock_courts.py`** (a
synthetic directory used only by the offline tests). Per-slot availability is
always the same deterministic hash of `(court_id, date, time)`, which keeps
scenarios reproducible even against live data.

## Setup

```bash
uv sync --group dev
echo "OPENROUTER_API_KEY=sk-or-..." > .env
```

Every agent authenticates via an OpenAI-SDK client pointed at
[OpenRouter](https://openrouter.ai), defaulting to
`deepseek/deepseek-v4-flash-20260731`. Get a key at
[openrouter.ai/keys](https://openrouter.ai/keys). `.env` is gitignored and
auto-loaded. Override the model with the `TENNIS_BOOKING_MODEL` env var.

## Talk to an agent

```bash
uv run tennis-chat --agent prompt_chain
uv run tennis-chat --agent react --quiet
uv run tennis-chat --agent simple_workflow_api
```

Type messages, watch which tool fires each turn, and get a call-log summary on
exit. For `simple_workflow_api` you'll only ever see agent-1 call
`book_tennis_court_with_grammar` — `search_availability` / `book_court` appear
in the log too, but as calls `BookingWorkflowEngine` made on its own.

## Tests

```bash
uv run pytest tests/ -v      # fast, free, no credentials
uv run pytest evals/ -v      # live-API evals across every agent
uv run pytest -m "not eval"  # same split, by marker
```

Evals without credentials are **skipped**, never failed, so `uv run pytest` is
always safe. Repeat cases for a real reliability signal with
`--count=5` (via `pytest-repeat`; select with `-k`, since `--count` changes
node ids).

## The comparison report

Every `pytest evals/` run ends with a comparison table. For the same suite
outside pytest, with JSON/Markdown output:

```bash
uv run tennis-compare                                   # every agent
uv run tennis-compare --agent react --agent prompt_chain
uv run tennis-compare --model openai/gpt-5.6-luna:none  # reasoning off
uv run tennis-compare --format markdown --out latest.md
```

`--agent` and `--model` are both repeatable — every (agent, model) pair becomes
its own row in one report. Append `:EFFORT` to a model slug to set its
OpenRouter reasoning effort for that run only. Reports are always written under
`results/` (`--out` is a filename, not an arbitrary path) as well as printed.

## How scoring works

After playing a fixed scenario, scoring looks at the *actual arguments* the
agent passed to `search_availability` and `book_court` — not the chat text —
and compares them to the scenario's expected final values. That's what catches
"reverted to a stale answer" or "skipped a required question" regardless of how
an agent phrases things. Since the agent picks a `court_id` from whatever the
search actually returned, no expected id is hardcoded; the booked court's
area/surface/indoor-outdoor are checked for consistency instead. `area` is
matched as a substring (it's free text the agent paraphrases); every other
field is exact-match (`scoring.py`).

**Fairness** is structural: one parametrized test function over
`AGENTS_UNDER_TEST`, with no per-architecture branch in the test body. That
includes a mechanism check — every tool an agent was given must actually get
called, so no agent can quietly degenerate into a plainer tool-calling loop and
still pass. For `simple_workflow_api`, the two calls happen *inside*
`BookingWorkflowEngine`, and the adapter folds them into the same
`tool_call_log` shape, so the scoring code runs unmodified across all three.

## What the comparison shows

Not settled numbers — results are live-model-dependent and vary run to run.
Re-run `tennis-compare` yourself; see `results/` for full per-run reports.

**Reliability.** Across 3-agent × 2-model runs against the 11-scenario
`STANDARD_SUITE`, `prompt_chain` and `simple_workflow_api` are consistently
stronger (typically 10-11/11), while `react` is weakest (typically 7-10/11).
`react`'s failures cluster on one pattern: **dense, multi-field messages**. With
no state tool, it must re-derive "which step am I on" by re-reading the
transcript, so it can extract clearly-labeled fields (a name, an email) while
silently dropping a qualifier buried mid-sentence (`surface="any"`). Once
dropped there's nothing external to catch it, and the agent can get permanently
stuck re-asking an answered question — `search_availability` and `book_court`
then never fire at all. The other two don't share this failure mode, since
neither relies on the model re-inferring state from prose.

**Cost.** `prompt_chain` makes roughly 2× the calls per conversation (an extra
`get_next_step` round trip most turns), and because the API is stateless, every
extra round trip's messages get resent in full on every later call — that
compounding dominates cost, more than any single payload's size. `react` trades
a bigger static prompt for far fewer round trips and comes out cheapest;
`simple_workflow_api` sits in between.

## Extending

- **Add a workflow step**: edit `STEPS` in `workflow_steps.py` — every agent
  regenerates from it.
- **Add an architecture**: add an `AgentUnderTest` to `agents/agent_registry.py`;
  the CLI and every eval pick it up automatically. New agents are expected to
  share `agents.base.ConversationAgent`'s loop (prompt + tools + executors is
  normally all that differs); if one genuinely can't, duck-type its public
  surface: `send_user_message(text) -> str`, `tool_call_log`, `usage_log`,
  `turn_count`, `model`.
- **Add a scenario**: add a `ScriptedScenario` to
  `evals/scenarios/scripted.py`'s `ALL_SCENARIOS`.
