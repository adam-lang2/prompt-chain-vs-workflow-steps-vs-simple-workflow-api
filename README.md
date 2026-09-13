# prompt-chain-vs-workflow-steps-vs-simple-workflow-api

Reliability comparison of three ways to implement the same multi-turn agent
workflow:

- **Workflow agent** (`src/tennis_booking/agents/workflow_agent.py`) — the
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

1. Compare different agent implementations, to optimise for low cost, low
   latency, high reliability, cheap llm model performance.
2. Better capture the "workflow" abstraction into a solid code component.
3. Better utilise the model's trained knowledge, to minimise cost and
   improve reliability.
4. Better define abstractions and roles for the agent, to improve
   reliability by making it responsible for the things it's good at, e.g.
   conversational experience, and elicitation.
5. Support highly natural conversations, where callers might answer two
   questions at once, ask questions themselves, skip ahead, or skip back
   to earlier steps too.
6. Better conceptual representation of components and roles in code.
7. Effective use of AI tool calling techniques.
8. Fix the issues with the simple workflow steps agent forgetting where
   it's up to, due to its lack of support for having a "current step"
   pointer.

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

Court/availability data is mocked (`src/tennis_booking/mock_courts.py`) —
no network calls, and availability is a deterministic hash of
`(court_id, date)` so scripted scenarios are reproducible.

## Project layout

```
src/tennis_booking/
  models.py               BookingState + related dataclasses. search_has_run
                            distinguishes "never searched" from "searched,
                            zero results" -- shared by every architecture
  mock_courts.py           mock court directory, deterministic availability,
                            KNOWN_AREAS
  workflow_steps.py        single source of truth for the 15-step workflow,
                            plus the shared staleness/grounding guidance text
  tools/                    one tool (schema + implementation) per module --
                             see __init__.py's docstring for the full
                             rationale of each; every name is re-exported from
                             `tools/__init__.py`, so `from tennis_booking.tools
                             import X` is unchanged regardless of which file X
                             actually lives in
    search_availability.py    SEARCH_AVAILABILITY_TOOL, run_search_availability
    book_court.py             BOOK_COURT_TOOL, run_book_court
    prompt_chain_get_next_step.py
                               GET_NEXT_STEP_TOOL, NextStepTool, ConversationStore --
                               used by the prompt-chain agent
    book_tennis_court.py      BOOK_TENNIS_COURT_TOOL (simple-workflow-api) --
                               `updates` array of {slot, value} deltas
  workflow_engine/            package holding the non-LLM, non-native-tool-calling
                             "turn typed fields into workflow progress"
                             engine that backs simple-workflow-api:
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
uv run tennis-compare --format json --out gpt-4o-mini.json
uv run tennis-compare --format markdown --out latest-comparison.md
```

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
  its questions. Because the agent picks a `court_id` from live mock
  results, we don't hardcode an expected id — we instead verify the booked
  court's area/surface/indoor-outdoor are consistent with what the user
  asked for. For `simple_workflow_api`, these two calls happen *inside*
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

### What repeated live runs have found so far

Not a one-time result — re-run the commands above; findings here reflect a
point-in-time sample and should be refreshed periodically, not treated as
settled.

> **Provider migration note**: every finding below was measured under
> Claude (Anthropic), before the project switched to DeepSeek via
> OpenRouter (see Setup). They document real, verified-live failure modes
> and are kept as a record of what to watch for architecturally, but the
> specific reliability numbers and token counts are provider-specific and
> have not been re-measured under DeepSeek -- treat this whole section as a
> pre-migration snapshot until it's refreshed.
>
> **Simulated-eval retirement note**: the LLM-simulated-user eval
> (`evals/test_simulated_conversations.py`) referenced in the findings below
> has since been removed in favor of the scripted suite alone — it never fed
> the report's pass/fail column (only token/cost/latency), and mixed its
> usage samples into the scripted suite's numbers whenever both ran in the
> same session. The findings are kept below as a historical record of real,
> verified-live failure modes it caught.

**Reliability (workflow / prompt-chain, n≈3-6 per cell, Haiku-tier agents
and judge, measured pre-migration under Claude):**

- The scripted eval is a clean sweep across these architectures (18/18
  across 3 reps x 3 scenarios on the original 3-scenario suite) — fixed,
  well-formed, one-topic-per-turn input doesn't differentiate them.
  Reliability gaps only showed up under the simulated eval's
  LLM-improvised, multi-topic, self-correcting pressure — conversational
  *messiness*, not length, is what a useful regression check here needs to
  stress.
- The two failure modes seen there were architecture-relevant, not
  identical: the workflow agent once hallucinated and booked a time
  slot never present in a real `search_availability` result (this motivated
  the grounding guidance above); the prompt-chain agent once skipped
  reciting the booking summary and called `book_court` directly under a busy
  conversation (this motivated splitting the single "confirm, then book"
  step into two atomic ones above).
- The eval's own judge/criteria wording turned out to be as impactful as
  anything in the agents' prompts: a same-tier (Haiku) judge, forced by the
  subscription OAuth rate limit, once flagged an agent for "never asking" a
  question whose answer the user had volunteered unprompted — correct
  behavior, misread as a violation. Tightening the GEval criteria wording
  fixed the whole failure category. Treat eval-criteria text with the same
  scrutiny as the agents' own system prompts.

**Token cost (prompt-chain's minimal payload vs. its full-state-echo
predecessor, measured on the identical scripted scenario, pre-migration):**

- Trimming `get_next_step()`'s wire payload down to just the next
  instruction (no state echo) measurably worked: **~13% lower** total input
  tokens and **~16% lower** average tokens/call than the full-echo version,
  on an otherwise-identical conversation (same message count, same API call
  count).
- It did *not* close the gap with `workflow_agent`, and the reason is
  structural: `prompt_chain` makes roughly 2× the API calls per
  conversation (an extra `get_next_step` round-trip almost every turn), and
  since the Messages API is stateless, every one of those extra
  round-trips' `tool_use`/`tool_result` messages gets resent in full on
  every later call in that conversation. That compounding is the dominant
  cost driver — bigger than any single payload's size. `workflow_agent`
  trades a bigger static prompt for far fewer round-trips and comes out
  cheaper in total, even though its first-call fixed overhead is the larger
  of the two (measured directly via `count_tokens`: `workflow_agent` 2,345
  tokens vs. `prompt_chain` 1,806 tokens on a from-scratch first call).

**Simple-workflow-api — architecture-specific findings:**

- **This architecture originally ran agent-1 as a real Claude Code subprocess
  via the Claude Agent SDK (`claude_agent_sdk`)**, since the "agent-to-agent"
  framing suggested it. Live testing showed that harness carries substantial
  fixed overhead (~80K+ tokens of `cache_read`/`cache_creation` per session)
  even with every built-in tool disabled — and none of the SDK's actual
  differentiating capabilities (built-in tools, permissions, subagents,
  skills, sandboxing) were ever exercised, since `tools=[]` disables all of
  them except the one custom `book_tennis_court` tool. Agent-1's job is
  identical in shape to the raw tool-use loop every other agent in this
  project already runs through, so it was rewritten onto the same shared
  `ConversationAgent` loop (`agents/base.py`) instead. This removed the fixed
  overhead entirely (measured live: avg ~3,700 input tokens/call, in line
  with the other architectures) and made cost directly comparable on
  raw token counts, with no more SDK-side caching caveat.
- **A single design bug caused a total failure the first time this was
  tested live**, and is worth naming precisely because it's the kind of
  thing that's easy to get wrong in this pattern: the system prompt
  originally told agent-1 to bootstrap with an *empty* `book_tennis_court`
  payload "before saying anything," which caused it to discard the user's
  actual opening message whenever that message already contained useful
  information (e.g. "I'd like to book a court near downtown") — the
  workflow never advanced past `ask_area`. Fixed by having agent-1 relay
  the user's first message as the bootstrap payload whenever it contains
  anything answerable, falling back to an empty payload only for a truly
  content-free opener like a bare "hi."
- **The one-field-per-call design (agent-2 "keeps track of the current
  workflow step") originally had a real, structural failure mode on scripted
  messy scenarios in an early free-text-payload version of this
  architecture -- since fixed, in two directions, and superseded by the
  current typed `updates` array (which has no free-text extraction step to
  fail this way in the first place).** When a user bundled multiple answers
  into one message (e.g. "eastside... 2 players"), the free-text handler
  only ever extracted the field for whichever step was *currently* active.
  Two distinct gaps followed from that:
  - **Forward** — an answer for a step several turns *ahead* got silently
    dropped, and (on a fixed script that never repeats itself, unlike an
    adaptive user) the conversation could get stuck re-asking the same
    question forever. Fixed in the system prompt: agent-1 tracks every
    detail the user has given across the *whole* conversation (not just
    their latest message) and proactively resubmits it once the relevant
    step comes up, instead of waiting to be asked -- still true of the
    current `updates`-array design, which is exactly what forward-filling a
    not-yet-reached slot is for.
  - **Backward** — a correction to a field from a step already *passed*
    (e.g. "wait, let's do 2026-09-12 instead" arriving while duration is
    being asked) was invisible to the active step's free-text extractor and
    silently dropped, shipping the stale original value to
    `search_availability` / `book_court`. Fixed with an explicit,
    extensible dependency model, `FIELD_DEPENDENTS`
    (`workflow_engine/step_engine_shared.py`): correcting a slot reuses
    `BookingState.search_params_stale()`'s existing cascade for the six
    search-input fields (no new invalidation code needed -- a re-search and
    cleared selection fall out of the normal step machine automatically)
    and resets `summary_confirmed` for every other field, with no other
    re-asking. The current typed schema makes this simpler still: a
    correction is just any slot named in `updates[]`, current or not --
    there's no "which step is this free text answering" ambiguity left to
    get wrong.
  - Building and verifying the correction path surfaced two more real bugs
    along the way, both fixed at the shared model level so every
    architecture benefits: (1) `BookingState.availability_searched()` used
    `bool(available_courts)` as a proxy for "has search run," so a genuine
    zero-result search looked identical to "never searched" and the step
    machine re-issued the same search forever -- fixed with an explicit
    `search_has_run` flag. (2) selecting a time by court surface alone
    (e.g. "the grass court") instead of the court's actual name used to
    fall through to "any court with this open time," silently picking the
    wrong one whenever two courts shared a slot -- fixed by also matching
    on surface (`court_hint` in the current schema; see
    `BookingWorkflowEngine._resolve_selected_time`).

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
