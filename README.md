# prompt-chain-vs-workflow-steps-vs-simple-workflow-api

An experiment comparing the **operational metrics** — cost, latency, and
reliability — of three structurally different ways to implement the exact
same multi-turn agent workflow (booking a tennis court through a
conversational back-and-forth). Rather than debate which pattern *should*
be better in the abstract, this project implements all three against one
shared workflow definition, drives them through the same scripted
conversations, and scores them with the same deterministic criteria — so
any difference the numbers show comes from the architecture itself, not
from a test drifting between copy-pasted versions or one agent getting
better-written prompts than another. See `evals/compare.py`'s
`tennis-compare` CLI and the [results below](#what-the-comparison-currently-shows)
for how to reproduce and interpret a run.

The three architectures under comparison:

- **Workflow-steps agent** (`src/tennis_booking/agents/workflow_agent.py`) — the
  workflow is a numbered list of steps baked into one static system prompt,
  used unchanged for the whole conversation. The model has no state tool
  and must re-read the whole transcript every turn to figure out which
  numbered step to resume from.
- **Prompt-chain agent** (`src/tennis_booking/agents/prompt_chain_agent.py`)
  — the workflow lives server-side. The system prompt only describes it at a
  high level, and the model calls a `get_next_step()` tool every turn to get
  back a fresh, dynamically generated instruction — a chain of small
  prompts, one per step, rather than one fixed prompt for the whole
  conversation. Progress is tracked in a `ConversationStore` (a stand-in for
  a real persistent store, e.g. Redis) keyed by a `conversation_id` the
  model is given once and must pass on every call — the same pattern a
  real, stateless tool-execution backend would use. `get_next_step()`'s
  wire payload is minimal: no state echo, just the next instruction.
- **Simple-workflow-api agent** (`src/tennis_booking/agents/simple_workflow_api_agent.py`)
  — a structurally different approach, but running through the same shared
  Messages-API tool-use loop (`agents/base.py`) as the others. Agent-1 has
  exactly one tool, `book_tennis_court`, taking a single `updates` array of
  `{slot, value}` deltas -- any combination, in one call: a correction to
  something answered earlier, the current node's answer, one or more
  not-yet-reached nodes the user already answered, or several of these at
  once. That tool's handler delegates to `BookingWorkflowEngine` (`workflow_engine/`) — agent-2,
  not an LLM at all: a deterministic step machine (`LangGraphStepEngine`, a
  `langgraph.graph.StateGraph`) that validates each slot, executes
  `search_availability` / `book_court` itself the instant the workflow
  reaches them (agent-1 has no tools to call those directly), and hands back
  only the single next instruction.

Every agent implements the *identical* workflow, defined once in
`src/tennis_booking/workflow_steps.py`, and is listed together in
`src/tennis_booking/agents/agent_registry.py`. Every eval is written once and
parametrized over that registry, so any difference the evals surface comes
from the architecture, not from the task or from a test drifting between
copy-pasted versions.

## Goals

1. Compare cost, latency, and reliability across implementations, to find
   which architecture performs best with a cheap, low-reasoning LLM.
2. Define clear abstractions and roles for the agent, so it's responsible
   for the things a model is actually good at (conversational tone,
   elicitation) while deterministic code owns workflow state and validation.
3. Support highly natural conversations, where callers might answer two
   questions at once, ask questions themselves, skip ahead, or skip back
   to earlier steps too.
4. Make effective, idiomatic use of AI tool-calling for each pattern.

## The workflow (tennis court booking)

1. Ask roughly where the user wants to play (area)
2. Ask what date
3. Ask what court surface (hard / clay / grass / indoor carpet / any)
4. Ask session duration (60 / 90 / 120 min)
5. Ask number of players (2 singles / 4 doubles)
6. Ask indoor vs. outdoor vs. either
7. **Tool call:** look up nearby court availability
8. Ask which court/time, from the real availability results
9. Ask skill level (beginner / intermediate / advanced)
10. Ask whether a racket rental is needed
11. Ask the user's name
12. Ask the user's email
13. Recite the full booking summary and ask the user to confirm it
14. **Tool call:** book the court (only after the user confirmed)
15. Give the confirmation number, ask if there's anything else

Two policies apply throughout, defined once (`STALE_SEARCH_GUIDANCE`,
`GROUNDING_GUIDANCE` in `workflow_steps.py`) and included verbatim in every
agent's prompt:

- **Staleness**: if the user changes a preference (area, date, surface,
  duration, players, indoor/outdoor) after availability was already looked
  up, the old results are stale — search again before letting the user pick
  a time, even if they'd already picked one. `BookingState.search_params_stale()`
  enforces this deterministically wherever server-side state exists
  (prompt-chain, simple-workflow-api); `workflow_agent.py` relies on
  the same instruction text alone, since it has no state to check against.
- **Grounding**: never state or book a court name, time, or price that isn't
  literally present in the most recent `search_availability` result.

Court data comes from one of three places depending on context:

- **Live** (`tools/live_courts.py`) — the default for `tennis-chat` and any
  direct use of `search_availability`: a real Nominatim geocode of whatever
  free-text area the user gives, followed by a real Overpass API query for
  actual tennis courts/sports centres nearby. This is what makes `area`
  genuinely free text rather than a fixed enum.
- **Recorded cassette** (`evals/fixtures/live_courts_cassette.py`) — every
  pytest eval and `tennis-compare` run replays one fixed, real recording per
  named area instead of hitting the network, since a scripted scenario's
  literal expected values would break if live data drifted underneath it.
- **`mock_courts.py`** — a small fully-synthetic 9-court/4-area directory,
  used only by the offline unit/wiring tests in `tests/`, which need zero
  network dependency at all.

Per-slot open/closed availability has no live-data equivalent in any of the
three, so it's always the same deterministic hash of `(court_id, date,
time)` (`mock_courts.py`'s `_slot_is_open`), which is what keeps scripted
scenarios reproducible even against live court data.

## Project layout

```
src/tennis_booking/
  models.py               domain dataclasses/enums (CourtAvailability, TimeSlot,
                            Surface, IndoorOutdoor, ...) shared by every
                            architecture -- see workflow_engine/state.py for
                            BookingState itself
  mock_courts.py           small synthetic court directory + the deterministic
                            (court_id, date, time) availability hash every
                            court-data source (live, cassette, or mock) uses
  workflow_steps.py        single source of truth for the 15-step workflow,
                            plus the shared staleness/grounding guidance text
  tools/                    one tool (schema + implementation) per module --
                             see __init__.py's docstring for the full
                             rationale of each; every name is re-exported from
                             `tools/__init__.py`, so `from tennis_booking.tools
                             import X` is unchanged regardless of which file X
                             actually lives in
    search_availability.py    SEARCH_AVAILABILITY_TOOL, run_search_availability
    live_courts.py             real Nominatim geocode + Overpass court lookup
                               backing search_availability by default (see
                               "Court data" above for when this is swapped out)
    book_court.py             BOOK_COURT_TOOL, run_book_court
    send_confirmation.py      SEND_CONFIRMATION_TOOL, run_send_confirmation --
                               mocks sending the booking-confirmation email
    prompt_chain_get_next_step.py
                               GET_NEXT_STEP_TOOL, NextStepTool, ConversationStore --
                               used by the prompt-chain agent
    book_tennis_court.py      BOOK_TENNIS_COURT_TOOL (simple-workflow-api) --
                               `updates` array of {slot, value} deltas
  workflow_engine/            package holding the non-LLM, non-native-tool-calling
                             "turn typed fields into workflow progress"
                             engine that backs simple-workflow-api:
    state.py                    BookingState -- the durable, server-side
                               workflow-progress state shared by every
                               step-computation path in this package AND by
                               workflow_steps.next_step_for (prompt-chain)
    step_engine_shared.py            domain logic every step-computation engine
                               needs: field dependents (which corrections
                               cascade into a re-search vs. just a reset
                               confirmation), tool-action execution
                               (search_availability/book_court as a side
                               effect of reaching that step), response
                               shaping, and `step_is_current` (the per-step
                               "is this still unmet" guard)
    step_engine_langgraph.py             LangGraphStepEngine -- step-computation engine backed by a
                               compiled `langgraph.graph.StateGraph` (a
                               `route` node whose conditional edges are
                               guarded by step_is_current, with tool-action
                               nodes that loop back to route)
    agent.py                    BookingWorkflowEngine(LangGraphStepEngine) -- adds
                               `book_tennis_court`'s typed `updates` array of
                               {slot, value} deltas (with server-side
                               per-slot validation) on top of that engine
    __init__.py                  re-exports BookingWorkflowEngine, LangGraphStepEngine so
                               `from tennis_booking.workflow_engine import X`
                               works regardless of which file X lives in
  scoring.py                deterministic pass/fail scoring from tool-call args
  cli.py                     `tennis-chat` interactive terminal harness
  agents/
    base.py                  shared OpenAI-compatible Chat Completions
                             tool-use loop (talking to DeepSeek via
                             OpenRouter), used by every agent. UsageRecord
                             carries input/output tokens AND per-call
                             latency_ms, timed around the API call itself
    prompt_chain_agent.py     get_next_step() agent -- minimal wire payload,
                               state kept in a ConversationStore
    workflow_agent.py         numbered-steps-in-one-prompt agent
    simple_workflow_api_agent.py    agent-1 (book_tennis_court, {slot, value}
                               deltas) + BookingWorkflowEngine (LangGraphStepEngine)
    agent_registry.py         AGENTS_UNDER_TEST -- the single list the CLI
                               and every eval iterate over

tests/                  fast, deterministic, no credentials needed -- always
                         safe to run, never talks to the real API
  test_workflow_steps.py     pure unit tests of the step machine + get_next_step
  test_step_engine.py         pure unit tests of BookingWorkflowEngine's step machine (every
                               slot validator, correction/staleness/forward-fill
                               behavior, multi-slot updates) -- the most
                               heavily tested module in the project, since
                               it's exercised only through a fake client
                               elsewhere
  test_agent_wiring.py       tool-loop smoke tests via a fake OpenAI-shaped
                             client, covering every agent
  test_scoring.py             unit tests for score_conversation's field-matching
                               rules (area's substring leniency vs. every other
                               field's exact match)
  fakes.py                    minimal fake client used by test_agent_wiring.py

evals/                  live-API agent reliability evals -- every test here
                         is marked @pytest.mark.eval (registered in
                         pyproject.toml) and skipped cleanly without
                         OpenRouter credentials (see conftest.py)
  conftest.py                  pytest_collection_modifyitems: skips every
                               `eval`-marked test when has_usable_credentials()
                               is false; pytest_terminal_summary: prints the
                               standard comparison report (report.py) at the
                               end of a run
  suite.py                    STANDARD_SUITE -- the named, ≥10-scenario
                               scripted suite used for comparisons; both
                               test_scripted_booking.py and compare.py
                               parametrize over this same list
  compare.py                   `tennis-compare` standalone CLI: runs
                               STANDARD_SUITE against one/several/all agents
                               outside pytest, in text/json/markdown
  token_tracking.py            session-wide token/latency/cost accounting, by
                               agent id (see stats.py for the percentile helper
                               and pricing.py for the $/1M-token table)
  results_tracking.py          session-wide pass/fail accounting, by
                               (agent, scenario) -- the report's other input
  report.py                    ComparisonReport: builds the standard
                               tokens/cost/latency/pass-fail table from
                               token_tracking.py + results_tracking.py,
                               rendered as text, JSON, or Markdown
  stats.py                     dependency-free percentile()/mean() helpers
  pricing.py                    per-model $/1M-token price table (point-in-time
                               snapshot -- see its own docstring on staleness)
  fixtures/
    live_courts_cassette.py       replays one fixed, real Nominatim/Overpass
                               recording per named area instead of hitting
                               the network -- every eval and tennis-compare
                               run patches tools/live_courts.py to use this
    live_courts/*.json          the recorded {lat, lon, elements} data itself,
                               one file per named area
  test_scripted_booking.py    STANDARD_SUITE x AGENTS_UNDER_TEST
  scenarios/
    scripted.py                ScriptedScenario definitions (in-order + messy;
                                11 scenarios as of this writing, including
                                zero-result relaxation, a post-selection
                                staleness re-search, a malformed-email retry,
                                an all-fields-at-once opener, a multi-field
                                "redo", a double correction to the same field,
                                naming a specific court instead of an area,
                                and an out-of-range duration)
    runner.py
```

## Setup

```bash
uv sync --group dev
```

**Auth**: every agent authenticates via a zero-arg OpenAI-SDK client pointed
at [OpenRouter](https://openrouter.ai) (`agents/base.py:new_client()`),
talking to DeepSeek (`deepseek/deepseek-v4-flash-20260731` by default). Get
a key from [openrouter.ai/keys](https://openrouter.ai/keys):

```bash
echo "OPENROUTER_API_KEY=sk-or-..." > .env
```

`.env` is gitignored and auto-loaded (`agents/base.py` calls
`load_dotenv()`), so this is a one-time setup step. Override the model for
every agent via the `TENNIS_BOOKING_MODEL` env var, or by editing
`DEFAULT_MODEL` in `agents/base.py` directly (any model slug OpenRouter
serves).

## Try it yourself first: the CLI chat harness

Before trusting any automated eval, talk to any agent directly in your
terminal:

```bash
uv run tennis-chat --agent prompt_chain              # get_next_step, minimal payload
uv run tennis-chat --agent workflow_steps --quiet    # numbered steps, one static prompt
uv run tennis-chat --agent simple_workflow_api       # one tool, book_tennis_court, + BookingWorkflowEngine backend
```

Type messages, watch which tool gets called each turn, and see a full
call-log summary when you exit (`exit` or Ctrl-D). For `simple_workflow_api`
you'll only ever see one tool name (`book_tennis_court`) in the trace —
`search_availability` / `book_court` still show up in the log too, but as
calls `BookingWorkflowEngine` made on its own, folded in alongside it for consistency
with the other two agents.

## Running the tests

Fast, free, no credentials needed (pure logic + fake-client wiring checks):

```bash
uv run pytest tests/ -v
```

Every live-API eval, parametrized across every agent (needs OpenRouter
credentials — see Setup):

```bash
uv run pytest evals/ -v
```

Select by marker instead of directory (equivalent to the two commands
above):

```bash
uv run pytest -m "not eval" -v      # fast tests only
uv run pytest -m eval -v            # evals only
```

One eval file at a time, or scoped to one agent:

```bash
uv run pytest evals/test_scripted_booking.py -v
uv run pytest evals/test_scripted_booking.py -k simple_workflow_api -v
```

Repeat each case to get a real reliability signal instead of one noisy run
(uses `pytest-repeat`; select with `-k` since `--count` changes node ids):

```bash
uv run pytest evals/test_scripted_booking.py --count=5 -v
```

Everything at once:

```bash
uv run pytest -v
```

Evals without usable credentials are automatically **skipped** (see
`evals/conftest.py`), never failed, so `uv run pytest`
is always safe to run regardless of whether `.env` is set up yet.

### The standard comparison report

Every `uv run pytest evals/ -v` run ends with a comparison table (tokens,
cost where priced, per-call latency p50/p90, and scenario pass/fail) built
by `evals/report.py` from that run's samples.

For an interactive comparison outside pytest -- no node-id syntax, and
JSON/Markdown output instead of pytest's terminal text -- use the
standalone `tennis-compare` entry point, which runs the same named
`evals.suite.STANDARD_SUITE` (≥10 scripted scenarios):

```bash
uv run tennis-compare                                   # every registered agent
uv run tennis-compare --agent workflow_steps --agent prompt_chain
uv run tennis-compare --model openai/gpt-5.6-luna:none  # reasoning effort off for this model
uv run tennis-compare --format markdown --out latest-comparison.md
```

`--model` is repeatable — every agent runs once per model given, and every
(agent, model) pair lands as its own row in the same report, so comparing
several models is one invocation, not several files stitched together by
hand. Append `:EFFORT` to a model slug (e.g. `openai/gpt-5.6-luna:none`) to
set that model's OpenRouter reasoning effort ("none", "low", "high", ...)
for this run only — useful for comparing a model with and without reasoning
in the same report, without a process-wide env var forcing every model in
the run to the same setting.

Every report is written under `results/` at the repo root (created
automatically) as well as printed -- `--out` is a filename (or path relative
to `results/`), not an independent path, so eval output always lands in one
enforced place instead of scattered wherever you happened to point it.
Omit `--out` for a timestamped filename.

Also requires `OPENROUTER_API_KEY` (same as the pytest evals above) -- it
makes real, live model calls.

## How scoring works

- **Scripted eval** (`evals/test_scripted_booking.py` + `scoring.py`): after
  playing a fixed scenario through an agent, we look at the *actual
  arguments* the agent passed to `search_availability` and `book_court` —
  not the chat text — and compare them against the scenario's expected
  final values. This is what actually catches "reverted to a stale answer"
  or "skipped a required question" bugs regardless of how any agent phrases
  its questions. Because the agent picks a `court_id` from whatever
  `search_availability` actually returned, we don't hardcode an expected id
  — we instead verify the booked
  court's area/surface/indoor-outdoor are consistent with what the user
  asked for. `area` specifically is matched as a substring either way
  (`"near Golden Gate Park"` vs. `"Golden Gate Park"` both pass), not exact
  string equality, since it's free text the agent is expected to paraphrase
  from however the user phrased their location — every other field (date,
  surface, indoor/outdoor, ...) is a fixed value from a schema enum or the
  user's exact wording, so those stay exact-match (`scoring.py`). For
  `simple_workflow_api`, these two calls happen *inside*
  `BookingWorkflowEngine` rather than as literal tool calls from agent-1 — the adapter
  (`simple_workflow_api_agent.py`) folds them into the same `tool_call_log` shape
  every other agent produces, so this scoring code runs completely
  unmodified across all three architectures.
- **Fairness**: the eval is a single parametrized test function over
  `AGENTS_UNDER_TEST` (`agents/agent_registry.py`) — the scenario data, the
  scoring/criteria, and the assertions are one copy shared by every agent,
  with no per-architecture branch inside the eval body. That includes the
  mechanism check: `test_scripted_booking.py` asserts every tool an agent
  was given actually got called at least once (so `simple_workflow_api`
  really used `book_tennis_court`, `prompt_chain` really used
  `get_next_step`, rather than any agent silently degenerating into a
  plainer tool-calling loop that happens to still pass scoring) and that no
  tool result ever leaks a `"state"` payload — one generic check applied
  identically to all three, not a per-agent invariant.
- **Token/latency/cost accounting** (`evals/token_tracking.py`): every agent
  records a `UsageRecord` per model call — input/output tokens straight from
  the same `response.usage` the Chat Completions API returns, plus
  `latency_ms` timed around that same API call (`agents/base.py`). Cost is
  estimated from `evals/pricing.py`'s per-model $/1M-token table where the
  model is priced. `evals/report.py`'s `ComparisonReport` (printed by
  `evals/conftest.py`'s `pytest_terminal_summary`, or built directly by
  `evals/compare.py`) shows avg/total tokens, total cost, and per-call
  latency p50/p90 per agent. Since every agent now goes through the
  identical raw API loop, this is directly comparable across all of them —
  no per-architecture caveat.

### What the comparison currently shows

Not a one-time result — re-run `tennis-compare` yourself; results are
live-model-dependent and vary run to run (see the two full runs referenced
below, which used identical code and settings but produced different exact
numbers). Treat what follows as a description of *how* to read a run and
the failure patterns to watch for, not settled numbers.

**Reliability**: across full 3-agent × 2-model runs (`deepseek-v4-flash`
and `gpt-5.6-luna` with reasoning off) against the 11-scenario
`STANDARD_SUITE`, `prompt_chain` and `simple_workflow_api` are consistently
the more reliable architectures (typically 10-11/11 per cell), while
`workflow_steps` is the weakest (typically 7-10/11). `workflow_steps`'
failures cluster almost entirely around one pattern: **dense, multi-field
messages** (an opener or reply that answers several steps at once, e.g.
"...Discovery Park, any surface, indoor or outdoor is fine, 120 minutes, 4
players..."). Because this architecture has no state tool — every turn it
must re-derive "which of the 15 steps am I on" purely by re-reading the raw
transcript against its static numbered-list prompt — it can correctly
extract clearly-labeled fields (a name, an email) while silently dropping a
qualifier buried mid-sentence (`surface="any"`, `indoor_outdoor="either"`).
Once dropped, there's no external state to catch or correct it: the model
just keeps marching through its numbered steps, treating each new user
reply as answering whatever step it currently thinks it's on, and can get
permanently stuck re-asking an already-answered question — `search_availability`
and `book_court` then never get called at all. `prompt_chain` (server-side
`BookingState`, tracked in code) and `simple_workflow_api` (a `LangGraph`
step machine validating each `{slot, value}` update) don't share this
failure mode, since neither relies on the model re-inferring state from
prose alone.

**Cost and call volume**: `prompt_chain` makes roughly 2× the tool/API
calls per conversation of `workflow_steps` (an extra `get_next_step` round
trip almost every turn), and since the underlying Chat Completions API is
stateless, every one of those extra round-trips' messages gets resent in
full on every later call in the same conversation — that compounding is the
dominant cost driver, bigger than any single payload's size. `workflow_steps`
trades a larger static system prompt for far fewer round trips and comes
out cheapest in total on both models; `simple_workflow_api` sits in
between. Reasoning-off (`:none`) on `gpt-5.6-luna` doesn't reliably improve
either cost or latency relative to `deepseek-v4-flash` — it's consistently
the more expensive, higher-latency model of the two in this comparison
despite reasoning being disabled.

See `results/` for full per-run reports (columns: calls, avg input/output
tokens, total cost, latency p50/p90, max tool calls/turn, turn latency
p50/p90, pass rate, plus a per-scenario failure breakdown).

## Extending

- **Add a workflow step**: edit `STEPS` in `workflow_steps.py` once — every
  agent's prompt/tool logic regenerates from it.
- **Add another agent architecture to compare**: add an `AgentUnderTest`
  entry to `agents/agent_registry.py`; every eval and the CLI pick it up
  automatically. Every agent in this project shares
  `agents.base.ConversationAgent`'s raw Messages API loop — a new
  architecture is expected to as well (system prompt + tool set + tool
  executors is normally all that differs). If a future architecture
  genuinely can't (e.g. it owns a real subprocess), duck-type
  `ConversationAgent`'s public surface instead: `send_user_message(text) ->
  str`, `tool_call_log: list[ToolCallRecord]`, `usage_log:
  list[UsageRecord]`, `turn_count`, `model`.
- **Add a scripted scenario**: add a `ScriptedScenario` to
  `evals/scenarios/scripted.py`'s `ALL_SCENARIOS`.
