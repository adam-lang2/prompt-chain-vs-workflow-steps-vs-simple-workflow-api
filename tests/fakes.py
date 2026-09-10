"""A minimal stand-in for the OpenAI client (as used against OpenRouter),
shaped just enough like the real SDK response objects for
ConversationAgent.send_user_message to work. Used to smoke-test the
tool-use loop wiring without spending real API calls.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class FakeFunctionCall:
    name: str
    arguments: str  # JSON-encoded, matching the real SDK's wire shape


class FakeToolCall:
    def __init__(self, id: str, name: str, input: dict[str, Any]):
        # `input` mirrors the old Anthropic-shaped fixture's ergonomics
        # (pass a dict, not a pre-serialized JSON string) -- constructs the
        # OpenAI-shaped `function.arguments` string underneath.
        self.id = id
        self.function = FakeFunctionCall(name=name, arguments=json.dumps(input))


@dataclass
class FakeMessage:
    content: str | None = None
    tool_calls: list[FakeToolCall] | None = None


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


class FakeResponse:
    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[FakeToolCall] | None = None,
        usage: FakeUsage | None = None,
    ):
        self.choices = [FakeChoice(message=FakeMessage(content=content, tool_calls=tool_calls))]
        self.usage = usage or FakeUsage()


class _FakeCompletions:
    def __init__(self, scripted_responses: list[FakeResponse]):
        self._responses = list(scripted_responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeClient ran out of scripted responses")
        return self._responses.pop(0)


class _FakeChat:
    def __init__(self, scripted_responses: list[FakeResponse]):
        self.completions = _FakeCompletions(scripted_responses)


class FakeOpenAIClient:
    """Pass a fixed sequence of FakeResponse objects; each call to
    chat.completions.create() returns the next one, in order."""

    def __init__(self, scripted_responses: list[FakeResponse]):
        self.chat = _FakeChat(scripted_responses)
