"""Shared OpenAI-compatible tool-use loop for every agent architecture in
this project, talking to DeepSeek through OpenRouter.

This is deliberately the *only* place that talks to the model API.
`prompt_chain_agent.py`, `workflow_agent.py`, and `simple_workflow_api_agent.py`
are all thin configuration over this class -- same model, same
message-handling loop, same transcript logging -- so any behavioral
difference measured in the evals comes from the system prompt / tool-set
difference, not from different plumbing.

Every tool schema in `tools/` is defined once, in Anthropic's
`{"name", "description", "input_schema"}` shape (kept as-is so nothing
outside this module needs to change); `_to_openai_tool` converts each one to
OpenAI's `{"type": "function", "function": {...}}` shape at request time,
since OpenRouter's Chat Completions endpoint speaks the OpenAI tool-calling
wire format regardless of which underlying model serves the request.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# The `openai` package is the correct client here even though we talk to
# OpenRouter, not OpenAI: OpenRouter's Chat Completions endpoint is
# OpenAI-wire-compatible, and LangChain's OpenAI-compatible client is itself
# a wrapper over this same package -- pulling it in would add a dependency
# without removing this one.
import openai
from dotenv import load_dotenv

# Picks up OPENROUTER_API_KEY from a local .env if present, without
# overriding any already-exported env var. This is the single import point
# both the CLI and the test suite go through.
load_dotenv()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash-20260731"
MAX_TOOL_ITERATIONS_PER_TURN = 8
# No timeout previously meant a stalled OpenRouter connection could hang
# this loop indefinitely with no error and no log line -- set an explicit
# ceiling so a hang surfaces as a TimeoutError within a bounded time instead.
REQUEST_TIMEOUT_SECONDS = 120

# Set TENNIS_BOOKING_DEBUG_TIMING=1 to log every model call and tool
# execution's wall-clock time to stderr -- added to debug a run that took
# far longer than expected with no visible cause (see UsageRecord.latency_ms,
# which records this but only after the fact, in the final report).
_DEBUG_TIMING = bool(os.environ.get("TENNIS_BOOKING_DEBUG_TIMING"))


def _debug(msg: str) -> None:
    if _DEBUG_TIMING:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


@dataclass
class ToolCallRecord:
    turn: int
    name: str
    args: dict
    result: dict


@dataclass
class UsageRecord:
    """Token usage (+ latency) for one model call. `input_tokens` is the
    *total* input size billed for that call (system prompt + tools + full
    message history so far) -- not incremental -- which is exactly what
    makes it comparable across architectures: a shorter system prompt or a
    smaller tool list shows up directly as a lower number here.

    `latency_ms` times only the `chat.completions.create()` network call
    itself (see `send_user_message`) -- not JSON parsing or tool execution
    -- so it measures model/provider latency specifically, not agent-side
    overhead. It's a per-call metric deliberately: call count itself varies
    by architecture (prompt-chain makes ~2x the round-trips of
    workflow-step per turn), so a per-conversation total would conflate
    "slower model response" with "more round-trips" -- p50/p90 across calls
    isolates the former.

    `cost_usd` is populated from `evals/pricing.py`'s per-model price table
    where the model is known, else left None -- every agent in this project
    runs through this same raw Chat Completions loop now, so cost is
    otherwise comparable across all of them directly from
    `input_tokens`/`output_tokens` without needing a per-call cost figure.
    """

    turn: int
    input_tokens: int
    output_tokens: int
    latency_ms: float = 0.0
    cost_usd: float | None = None


# Deliberately hand-rolled rather than a LangChain AgentExecutor (or similar):
# this loop is what produces tool_call_log/usage_log, and every eval in this
# project depends on that instrumentation being identical and fully
# controlled across all three agent architectures under comparison. A
# library's own agent loop would make that harder to keep uniform, which
# would undermine the comparison this project exists to make.
@dataclass
class ConversationAgent:
    system_prompt: str
    tools: list[dict[str, Any]]
    tool_executors: dict[str, Callable[[dict], dict]]
    model: str = DEFAULT_MODEL
    client: openai.OpenAI | None = None

    messages: list[dict] = field(default_factory=list)
    tool_call_log: list[ToolCallRecord] = field(default_factory=list)
    usage_log: list[UsageRecord] = field(default_factory=list)
    _turn: int = 0

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = new_client()

    @property
    def turn_count(self) -> int:
        return self._turn

    def send_user_message(self, text: str) -> str:
        """Append a user turn, run the tool-use loop, return the agent's reply text."""
        self._turn += 1
        self.messages.append({"role": "user", "content": text})

        openai_tools = [_to_openai_tool(t) for t in self.tools] if self.tools else None

        for iteration in range(MAX_TOOL_ITERATIONS_PER_TURN):
            request_messages = [{"role": "system", "content": self.system_prompt}, *self.messages]
            _debug(f"turn {self._turn} iter {iteration}: chat.completions.create starting ({len(request_messages)} messages)")
            call_start = time.perf_counter()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=request_messages,
                tools=openai_tools,
            )
            latency_ms = (time.perf_counter() - call_start) * 1000
            _debug(f"turn {self._turn} iter {iteration}: chat.completions.create finished in {latency_ms:.0f}ms")
            self.usage_log.append(
                UsageRecord(
                    turn=self._turn,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    latency_ms=latency_ms,
                )
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []

            assistant_message: dict[str, Any] = {"role": "assistant", "content": message.content}
            if tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ]
            self.messages.append(assistant_message)

            if not tool_calls:
                return (message.content or "").strip()

            for tc in tool_calls:
                executor = self.tool_executors.get(tc.function.name)
                args = _parse_tool_arguments(tc.function.arguments)
                _debug(f"turn {self._turn} iter {iteration}: executing tool {tc.function.name}({args})")
                tool_start = time.perf_counter()
                if executor is None:
                    result: dict = {"error": f"unknown tool {tc.function.name}"}
                else:
                    result = executor(args)
                _debug(f"turn {self._turn} iter {iteration}: tool {tc.function.name} finished in {(time.perf_counter() - tool_start) * 1000:.0f}ms")
                self.tool_call_log.append(
                    ToolCallRecord(turn=self._turn, name=tc.function.name, args=args, result=result)
                )
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    }
                )

        return "[agent exceeded max tool iterations for this turn]"

# A pydantic-validating tool-call parser (e.g. LangChain's) would reject
# malformed arguments outright; this one deliberately doesn't -- treating a
# bad call as `{}` instead of raising is what keeps one malformed tool call
# from crashing an eval turn, which matters more here than schema strictness.
def _parse_tool_arguments(raw: str) -> dict:
    """A tool-calling model is expected to emit a valid JSON object for
    `arguments`, but isn't guaranteed to -- treat malformed JSON as an empty
    call rather than raising, so one bad call doesn't crash the whole loop."""
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }


def new_client() -> openai.OpenAI:
    """A zero-arg client resolves OPENROUTER_API_KEY from the environment.
    OpenRouter is designed as a drop-in for the OpenAI SDK: point `base_url`
    at it and every model it hosts (including DeepSeek) speaks the same
    Chat Completions wire format."""
    return openai.OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def has_usable_credentials() -> bool:
    """Local, no-network check for whether `new_client()` will be able to
    authenticate at all -- used to skip live-API tests cleanly instead of
    letting them fail with an auth error.
    """
    return bool(os.environ.get("OPENROUTER_API_KEY"))
