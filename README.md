# prompt-chain-vs-workflow-steps

Reliability comparison of four ways to implement the same multi-turn agent
workflow:

- **Prompt-chain agent** (`src/tennis_booking/agents/prompt_chain_agent.py`)
  — the workflow lives server-side. The system prompt only describes it at a
  high level, and the model calls a `get_next_step()` tool every turn to get
  back a fresh, dynamically generated instruction — a chain of small prompts,
  one per step, rather than one fixed prompt for the whole conversation.
  Progress is tracked in a server-side `BookingState`, but `get_next_step()`
  echoes that *entire* state back to the model on every call.
- **Prompt-chain v2 agent** (`src/tennis_booking/agents/prompt_chain_agent_v2.py`)
  — identical architecture, but `get_next_step()`'s wire payload is minimal:
  no state echo, just the next instruction. State lives in a
  `ConversationStore` (a stand-in for a real persistent store, e.g. Redis)
  keyed by a `conversation_id` the model is given once and must pass on
  every call — the same pattern a real, stateless tool-execution backend
  would use.
- **Workflow-step agent** (`src/tennis_booking/agents/workflow_step_agent.py`)
  — the workflow is a numbered list of steps baked into one static system
  prompt, used unchanged for the whole conversation. The model has no state
  tool and must re-read the whole transcript every turn to figure out which
  numbered step to resume from.
- **a2a-fsm-api** (`src/tennis_booking/agents/a2a_fsm_api.py`) — a
  structurally different approach, but running through the same shared
  Messages-API tool-use loop (`agents/base.py`) as the others. Agent-1 has
  exactly one tool, `book_tennis_court`, taking a single `updates` array of
  `{slot, value}` deltas -- any combination, in one call: a correction to
  something answered earlier, the current node's answer, one or more
  not-yet-reached nodes the user already answered, or several of these at
  once. That tool's handler delegates to `FSMAgent` (`fsm_agent/`) — agent-2,
  not an LLM at all: a deterministic step machine (`LangGraphStepEngine`, a
  `langgraph.graph.StateGraph`) that validates each slot, executes
  `search_availability` / `book_court` itself the instant the workflow
  reaches them (agent-1 has no tools to call those directly), and hands back
  only the single next instruction.

Every agent implements the *identical* workflow, defined once in
`src/tennis_booking/workflow_steps.py`, and is listed together in
`src/tennis_booking/agents/registry.py`. Every eval is written once and
parametrized over that registry, so any difference the evals surface comes
from the architecture, not from the task or from a test drifting between
copy-pasted versions. See `docs/improvements-plan.md` for the design
rationale behind the tooling described below (per-call latency metrics, the
`tools/` package layout, the `fsm_agent` step-engine family, the
standard scripted suite, and the standard comparison report).

> Earlier revisions of this project also compared three more architectures
> under the `agent-to-agent-prompt-chain` name (v1/v2/v3) -- a free-text
> `payload` string parsed by a regex-based step engine
> (`HandRolledStepEngine`), then the same protocol re-backed by a
> `transitions.Machine` engine (`TransitionsStepEngine`). Both engines still
> live in `fsm_agent/` and are still unit-tested directly (see
> `tests/test_step_engine.py`), but the agent modules that wired them up as
> standalone architectures have been retired now that `a2a-fsm-api` (backed
> by `LangGraphStepEngine`) is the project's one structured-tool
> architecture. The "What repeated live runs have found so far" section
> below still describes findings from when those architectures existed.

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
  (prompt-chain, v2, a2a-fsm-api); `workflow_step_agent.py` relies on
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
                            KNOWN_AREAS (used by the regex-agent's extractor)
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
    get_next_step.py          GET_NEXT_STEP_TOOL, NextStepTool (v1, full-state echo)
    get_next_step_v2.py       GET_NEXT_STEP_TOOL_V2, NextStepToolV2,
                               ConversationStore (v2, minimal payload)
    book_tennis_court_v4.py   BOOK_TENNIS_COURT_TOOL_V4 (a2a-fsm-api) --
                               `updates` array of {slot, value} deltas
  fsm_agent/                  package holding every non-LLM, non-native-tool-calling
                             "turn text/typed fields into workflow progress"
                             engine -- one family, grouped together rather
                             than scattered at the top of tennis_booking/:
    step_engine_shared.py            shared, non-differentiating machinery behind
                               all three step-computation engines below -- field
                               extractors, the "<label>: <value>" grammar
                               (FIELD_LABELS), FIELD_DEPENDENTS (which
                               corrections cascade into a re-search vs. just
                               a reset confirmation), labeled-batch
                               application, response shaping, and
                               `step_is_current` (the per-step "is this
                               still unmet" guard TransitionsStepEngine and
                               LangGraphStepEngine both use). Composed
                               (never inherited) by every engine so each can
                               be read end-to-end on its own.
    step_engine_handrolled.py              HandRolledStepEngine -- step-computation engine #1: a
                               hand-rolled priority scan (workflow_steps.next_step_for)
    step_engine_transitions.py           TransitionsStepEngine -- step-computation engine #2: a
                               declared transitions.Machine. Does NOT extend
                               HandRolledStepEngine -- both compose step_engine_shared.py as
                               independent siblings (see step_engine_shared.py's docstring)
    step_engine_langgraph.py             LangGraphStepEngine -- step-computation engine #3: a
                               compiled langgraph.graph.StateGraph (route
                               node + conditional edges guarded by
                               step_is_current, tool-action nodes that loop
                               back to route). FSMAgent's current engine --
                               composes step_engine_shared.py the same way
                               as its two siblings, inherits from neither.
    agent.py                    FSMAgent(LangGraphStepEngine) -- same
                               StateGraph engine, but book_tennis_court
                               takes an `updates` array of {slot, value}
                               deltas instead of a payload string to parse
    __init__.py                  re-exports FSMAgent, HandRolledStepEngine,
                               TransitionsStepEngine, LangGraphStepEngine so
                               `from tennis_booking.fsm_agent import X`
                               works regardless of which file X lives in
  scoring.py                deterministic pass/fail scoring from tool-call args
  cli.py                     `tennis-chat` interactive terminal harness
  agents/
    base.py                  shared OpenAI-compatible Chat Completions
                             tool-use loop (talking to DeepSeek via
                             OpenRouter), used by every agent. UsageRecord
                             carries input/output tokens AND per-call
                             latency_ms, timed around the API call itself
    prompt_chain_agent.py     get_next_step() v1 (full state echo)
    prompt_chain_agent_v2.py  get_next_step() v2 (minimal payload, ConversationStore)
    workflow_step_agent.py    numbered-steps-in-one-prompt agent
    a2a_fsm_api.py            agent-1 (book_tennis_court v4, {slot, value}
                               deltas) + FSMAgent (LangGraphStepEngine)
    registry.py               AGENTS_UNDER_TEST -- the single list the CLI
                               and every eval iterate over

tests/                  fast, deterministic, no credentials needed -- always
                         safe to run, never talks to the real API
  test_workflow_steps.py     pure unit tests of the step machine + get_next_step v1/v2
  test_step_engine.py         pure unit tests of HandRolledStepEngine's, TransitionsStepEngine's,
                               AND LangGraphStepEngine's step machine + every field
                               extractor (parametrized over all three engines via
                               the `agent_cls` fixture) -- the most heavily tested
                               module in the project, since it's the only one
                               without the model's own native tool-calling doing
                               slot extraction for it
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
  test_simulated_conversations.py  LLM-simulated-user personas x AGENTS_UNDER_TEST
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
  simulated/
    personas.py                 LLM-simulated-user personas + goldens --
                                 orderly, messy/self-correcting, terse,
                                 over-explaining, and off-topic-detouring
    callback_adapter.py         bridges ConversationAgent -> deepeval's model_callback
    oauth_model.py               deepeval judge model that authenticates the
                                 same way the agents do (see Auth below)
```

## Setup

```bash
uv sync --group dev
```

**Auth**: every agent, plus the eval judge/simulator, authenticates via a
zero-arg OpenAI-SDK client pointed at [OpenRouter](https://openrouter.ai)
(`agents/base.py:new_client()`), talking to DeepSeek
(`deepseek/deepseek-v4-flash-20260731` by default). Get a key from
[openrouter.ai/keys](https://openrouter.ai/keys):

```bash
echo "OPENROUTER_API_KEY=sk-or-..." > .env
```

`.env` is gitignored and auto-loaded (`agents/base.py` calls
`load_dotenv()`), so this is a one-time setup step. Override the model for
every agent by editing `DEFAULT_MODEL` in `agents/base.py`, or just the eval
judge/simulator via the `TENNIS_BOOKING_JUDGE_MODEL` env var (any model slug
OpenRouter serves).

## Try it yourself first: the CLI chat harness

Before trusting any automated eval, talk to any agent directly in your
terminal:

```bash
uv run tennis-chat --agent prompt_chain              # get_next_step, full state echo
uv run tennis-chat --agent prompt_chain_v2            # get_next_step, minimal payload
uv run tennis-chat --agent workflow_step --quiet       # numbered steps, one static prompt
uv run tennis-chat --agent a2a_fsm_api                # one tool, book_tennis_court, + FSMAgent backend
```

Type messages, watch which tool gets called each turn, and see a full
call-log summary when you exit (`exit` or Ctrl-D). For `a2a_fsm_api` you'll
only ever see one tool name (`book_tennis_court`) in the trace —
`search_availability` / `book_court` still show up in the log too, but as
calls `FSMAgent` made on its own, folded in alongside it for consistency
with the other three agents.

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
uv run pytest evals/test_scripted_booking.py -k a2a_fsm -v
uv run pytest evals/test_simulated_conversations.py -v -s
# or via the deepeval CLI for its nicer reporting:
uv run deepeval test run evals/test_simulated_conversations.py
```

Repeat each case to get a real reliability signal instead of one noisy run
(uses `pytest-repeat`; select with `-k` since `--count` changes node ids):

```bash
uv run pytest evals/test_scripted_booking.py --count=5 -v
uv run pytest evals/test_simulated_conversations.py -k prompt_chain --count=5 -v
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
uv run tennis-compare --agent workflow_step --agent prompt_chain
uv run tennis-compare --format json --out report.json
uv run tennis-compare --format markdown --out docs/latest-comparison.md
```

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
  asked for. For `a2a_fsm_api`, these two calls happen *inside* `FSMAgent`
  rather than as literal tool calls from agent-1 — the adapter
  (`a2a_fsm_api.py`) folds them into the same `tool_call_log` shape every
  other agent produces, so this scoring code runs completely unmodified
  across all four architectures.
- **Simulated eval** (`evals/test_simulated_conversations.py`): a custom
  `ConversationalGEval` (did it ask everything once and only once — without
  re-asking for something the user already volunteered — in a sensible
  order, use real tool results, and book with corrected values). Deliberately
  *not* using deepeval's built-in `ConversationCompletenessMetric` — verified
  live that it penalizes the agent for correctly declining a messy persona's
  out-of-scope tangents (cancellation policy, "do you support pickleball") as
  "unmet user intentions," which is the wrong standard for a narrowly-scoped
  booking assistant.
- **Fairness**: both evals are a single parametrized test function over
  `AGENTS_UNDER_TEST` (`agents/registry.py`) — the scenario data, the
  scoring/criteria, and the assertions are one copy shared by every agent.
  An architecture-specific extra check (e.g. `a2a_fsm_api` must actually
  call `book_tennis_court`; `prompt_chain_v2` must never leak a `"state"`
  payload) is expressed as that agent's `extra_invariant` in the registry,
  not as a branch inside the eval body.
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

**Reliability (prompt_chain / prompt_chain_v2 / workflow_step, n≈3-6 per
cell, Haiku-tier agents and judge, measured pre-migration under Claude):**

- The scripted eval is a clean sweep across these three (18/18 across 3 reps
  x 3 scenarios) — fixed, well-formed, one-topic-per-turn input doesn't
  differentiate them. Reliability gaps only showed up under the simulated
  eval's LLM-improvised, multi-topic, self-correcting pressure —
  conversational *messiness*, not length, is what a useful regression check
  here needs to stress.
- The two failure modes seen there were architecture-relevant, not
  identical: the workflow-step agent once hallucinated and booked a time
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

**Token cost (v1 vs. v2, measured on the identical scripted scenario):**

- v2's minimal `get_next_step()` payload measurably worked: **~13% lower**
  total input tokens and **~16% lower** average tokens/call than v1, on an
  otherwise-identical conversation (same message count, same API call
  count). Eliminating the `"state": {...}` echo removed real weight.
- It did *not* close the gap with `workflow_step_agent`, and the reason is
  structural, not a v2 shortcoming: `prompt_chain`/`v2` both make roughly
  2× the API calls per conversation (an extra `get_next_step` round-trip
  almost every turn), and since the Messages API is stateless, every one of
  those extra round-trips' `tool_use`/`tool_result` messages gets resent in
  full on every later call in that conversation. That compounding was
  always the dominant cost driver — bigger than any single payload's size —
  and neither v1 nor v2 touches it, since both still call the tool once a
  turn either way. `workflow_step_agent` trades a bigger static prompt for
  far fewer round-trips and comes out cheaper in total, even though its
  first-call fixed overhead is the larger of the two (measured directly via
  `count_tokens`: `workflow_step` 2,345 tokens vs. `prompt_chain` 1,806
  tokens on a from-scratch first call).

**Agent-to-agent-prompt-chain — architecture-specific findings:**

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
  with the other three architectures) and made cost directly comparable on
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
- **Pure-regex extraction needs a bit of real engineering to be usable, not
  just "write a regex."** The first live test also revealed the naive
  area/name extractors accepting an entire relayed sentence verbatim (e.g.
  `area = "Hi, I'd like to book a tennis court somewhere near downtown."`)
  instead of pulling out just the relevant word. Fixed with two standard
  regex-NLU techniques: gazetteer matching against `mock_courts.KNOWN_AREAS`
  for area, and common lead-in-phrase stripping ("my name is", "it's", "I'm
  ...") for the name. Both are reasonable, expected parts of a competent
  regex extractor — not scope creep into "give the regex-agent semantic
  understanding."
- **The one-field-per-call design (agent-2 "keeps track of the current
  workflow step") originally had a real, structural failure mode on scripted
  messy scenarios — since fixed, in two directions.** When a user bundles
  multiple answers into one message (e.g. "eastside... 2 players"),
  `HandRolledStepEngine.handle()` only ever extracts the field for whichever step is
  *currently* active. Two distinct gaps followed from that:
  - **Forward** — an answer for a step several turns *ahead* got silently
    dropped, and (on a fixed script that never repeats itself, unlike an
    adaptive user) the conversation could get stuck re-asking the same
    question forever. Fixed in the system prompt, not the extractor: agent-1
    now tracks every detail the user has given across the *whole*
    conversation (not just their latest message) and proactively resubmits
    it once the relevant step comes up, instead of waiting to be asked.
  - **Backward** — a correction to a field from a step already *passed*
    (e.g. "wait, let's do 2026-09-12 instead" arriving while duration is
    being asked) was invisible to the active step's extractor and silently
    dropped, shipping the stale original value to `search_availability` /
    `book_court`. Fixed with an explicit, extensible dependency model,
    `FIELD_DEPENDENTS` in `step_engine_handrolled.py`: a correction cue word ("actually",
    "wait", "instead", ...) triggers a scan of earlier, already-answered
    fields; applying a match reuses `BookingState.search_params_stale()`'s
    existing cascade for the six search-input fields (no new invalidation
    code needed — a re-search + cleared selection falls out of the normal
    step machine automatically) and resets `summary_confirmed` for every
    other field, with no other re-asking. Live-verified end to end: a date
    correction now visibly shows up in the eventual `search_availability`
    call, and agent-1 confirms it from the tool's own `"corrected"` field
    rather than assuming it worked.
  - Building and verifying the correction path surfaced four more real bugs
    along the way, all fixed: (1) the first version of correction-scanning
    used each field's normal (permissive) extractor, so `_extract_area`'s
    catch-all fallback intercepted an unrelated date correction and
    misattributed it to `area` — fixed by giving every extractor an explicit
    `strict` mode used only during correction-scanning, with no
    accept-anything fallback. (2) That bug's corrupted `area` value
    legitimately matched zero courts, which exposed a **separate,
    pre-existing latent bug** shared by every architecture:
    `BookingState.availability_searched()` used `bool(available_courts)` as
    a proxy for "has search run," so a genuine zero-result search looked
    identical to "never searched" and `next_step_for` re-issued the same
    search forever — fixed at the shared model level with an explicit
    `search_has_run` flag (benefits all four agents, not just this one).
    (3) `_extract_indoor_outdoor` didn't treat "doesn't matter" (or both
    "indoor" and "outdoor" mentioned together) as "either," matching the
    literal word "indoor" first — fixed with an explicit either-synonym
    list, mirroring the pattern the surface extractor already used for
    "any." (4) `_extract_time` matched a chosen court only by literal name;
    a user describing it by surface instead ("the grass court") fell through
    to "any court with this time slot" and silently booked the wrong one
    whenever two courts shared a slot — fixed by also matching on the
    court's surface. All three scripted scenarios (including both messy
    ones) now pass live end to end after these fixes.

## Extending

- **Add a workflow step**: edit `STEPS` in `workflow_steps.py` once — every
  agent's prompt/tool logic regenerates from it.
- **Add another agent architecture to compare**: add an `AgentUnderTest`
  entry to `agents/registry.py`; every eval and the CLI pick it up
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
- **Add a simulated persona/scenario**: add a `ConversationalGolden` to
  `evals/simulated/personas.py`'s `ALL_GOLDENS`.
