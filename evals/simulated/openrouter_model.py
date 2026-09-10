"""A deepeval judge/simulator model that talks to DeepSeek through
OpenRouter, authenticated the same way `tennis_booking`'s own agents are
(`OPENROUTER_API_KEY` -- see `agents/base.py:new_client()`).

deepeval doesn't ship an OpenRouter model out of the box, so this is a thin
`DeepEvalBaseLLM` wrapper around a zero-arg-constructible OpenAI SDK client
pointed at OpenRouter's base URL -- the same client shape `agents/base.py`
uses for the agents under test.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional, Type, TypeVar, Union

import openai
from deepeval.metrics.utils import trimAndLoadJson
from deepeval.models.base_model import DeepEvalBaseLLM
from pydantic import BaseModel

from tennis_booking.agents.base import OPENROUTER_BASE_URL, new_client

SchemaT = TypeVar("SchemaT", bound=BaseModel)

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_object(text: str) -> dict:
    """Parse the judge's JSON reply robustly against a chatty model.

    deepeval's own `trimAndLoadJson` just does `find("{")` ... `rfind("}")`,
    which breaks when the model second-guesses itself mid-response and
    emits more than one JSON block ("Wait, I need to re-read the
    conversation..." followed by a second ```json block -- the naive
    first-brace/last-brace span then straddles both blocks and isn't valid
    JSON on its own). Prefer the *last* fenced ```json block, on the theory
    that a self-correction's final answer is the intended one; fall back to
    the naive heuristic if there's no fence.
    """
    fenced_blocks = _FENCED_JSON_RE.findall(text)
    for candidate in reversed(fenced_blocks):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return trimAndLoadJson(text)


class OpenRouterModel(DeepEvalBaseLLM):
    def __init__(
        self,
        model: str,
        client: openai.OpenAI | None = None,
        async_client: openai.AsyncOpenAI | None = None,
    ):
        """`client`/`async_client` let tests inject a fake; leave unset to
        use real ones (credentials resolved the same way as agents/base.py)."""
        self._client = client
        self._async_client = async_client
        super().__init__(model)

    def load_model(self) -> openai.OpenAI:
        return self._client or new_client()

    def get_model_name(self) -> str:
        return self.name

    def generate(self, prompt: str, schema: Optional[Type[SchemaT]] = None) -> Union[str, SchemaT]:
        response = self.model.chat.completions.create(
            model=self.name,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        if schema is None:
            return text
        return schema.model_validate(_extract_json_object(text))

    async def a_generate(self, prompt: str, schema: Optional[Type[SchemaT]] = None) -> Union[str, SchemaT]:
        if self._async_client is None:
            self._async_client = openai.AsyncOpenAI(
                base_url=OPENROUTER_BASE_URL, api_key=os.environ.get("OPENROUTER_API_KEY")
            )
        client = self._async_client
        response = await client.chat.completions.create(
            model=self.name,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        if schema is None:
            return text
        return schema.model_validate(_extract_json_object(text))
