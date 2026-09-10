"""Shared OpenAI-compatible tool-use loop for every agent architecture in
this project, talking to DeepSeek through OpenRouter.

This is deliberately the *only* place that talks to the model API.
`prompt_chain_agent.py`, `prompt_chain_agent_v2.py`, `workflow_step_agent.py`,
and `a2a_fsm_api.py` are all thin configuration over this class -- same
model, same message-handling loop, same transcript logging -- so any
behavioral difference measured in the evals comes from the system prompt /
tool-set difference, not from different plumbing.

Every tool schema in `tools.py` is defined once, in Anthropic's
`{"name", "description", "input_schema"}` shape (kept as-is so nothing
outside this module needs to change); `_to_openai_tool` converts each one to
OpenAI's `{"type": "function", "function": {...}}` shape at request time,
since OpenRouter's Chat Completions endpoint speaks the OpenAI tool-calling
wire format regardless of which underlying model serves the request.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import openai
from dotenv import load_dotenv

# Picks up OPENROUTER_API_KEY from a local .env if present, without
# overriding any already-exported env var. This is the single import point
# both the CLI and the test suite go through.
load_dotenv()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash-20260731"
MAX_TOOL_ITERATIONS_PER_TURN = 8


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

        for _ in range(MAX_TOOL_ITERATIONS_PER_TURN):
            request_messages = [{"role": "system", "content": self.system_prompt}, *self.messages]
            call_start = time.perf_counter()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=request_messages,
                tools=openai_tools,
            )
            latency_ms = (time.perf_counter() - call_start) * 1000
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
                if executor is None:
                    result: dict = {"error": f"unknown tool {tc.function.name}"}
                else:
                    result = executor(args)
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
    return openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=os.environ.get("OPENROUTER_API_KEY"))


def has_usable_credentials() -> bool:
    """Local, no-network check for whether `new_client()` will be able to
    authenticate at all -- used to skip live-API tests cleanly instead of
    letting them fail with an auth error.
    """
    return bool(os.environ.get("OPENROUTER_API_KEY"))
