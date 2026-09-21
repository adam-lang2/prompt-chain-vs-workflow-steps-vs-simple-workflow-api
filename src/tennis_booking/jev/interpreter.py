"""JevInterpreter implementation using TypeSafe's Jev model."""
from __future__ import annotations

import os
import re
import time
from typing import Mapping

from typesafe_sdk import Choice, TypeSafeClient

from tennis_booking.jev.interpret import Interpretation
from tennis_booking.jev.questions import build_questions, build_state, tokenize_user_turn
from tennis_booking.workflow_engine.agent import _EMAIL_RE

_ISO_DATE_IN_TEXT = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_PUNCT = ".,!?;:\"'"
from tennis_booking.workflow_engine.state import BookingState


class JevInterpreter:
    """Interprets user turns via TypeSafe's Jev model."""

    def __init__(self, client: TypeSafeClient | None = None):
        self.client = client or TypeSafeClient(api_key=os.environ.get("TYPESAFE_API_KEY"))

    def interpret(self, state: BookingState, last_assistant: str, user_turn: str) -> Interpretation:
        """Interpret a user's turn using TypeSafe's Jev model."""
        state_text = build_state(state, last_assistant, user_turn)
        tokens = tokenize_user_turn(user_turn)
        questions = build_questions(state, tokens)

        call_start = time.perf_counter()
        response = self.client.system_one(state=state_text, questions=questions)
        latency_ms = (time.perf_counter() - call_start) * 1000

        # Extract the act (required)
        act_answer = response.choices.get("act")
        act = act_answer.choice if act_answer else "not_mentioned"
        act_confidence = act_answer.confidence if act_answer else 0.0

        # Extract mentioned slots (exclude "not_mentioned" answers)
        slots: dict[str, tuple] = {}
        spans: dict[str, dict[str, tuple[int, float]]] = {}
        for question_name, answer in response.choices.items():
            if question_name == "act":
                continue
            if question_name.endswith(("_start", "_end")):
                slot, edge = question_name.rsplit("_", 1)
                if answer and answer.choice.isdigit():
                    spans.setdefault(slot, {})[edge] = (int(answer.choice), answer.confidence)
                continue
            if answer and answer.choice != "not_mentioned":
                slots[question_name] = (answer.choice, answer.confidence)

        for slot, edges in spans.items():
            if "start" in edges and "end" in edges and edges["start"][0] <= edges["end"][0] < len(tokens):
                text = " ".join(tokens[edges["start"][0] : edges["end"][0] + 1]).strip(_PUNCT)
                if text:
                    slots[slot] = (text, min(edges["start"][1], edges["end"][1]))

        iso_date = _ISO_DATE_IN_TEXT.search(user_turn)
        if iso_date:
            slots["date"] = (iso_date.group(0), 1.0)

        email = _EMAIL_RE.search(user_turn)
        if email:
            slots["contact_email"] = (email.group(0), 1.0)

        input_tokens = response.usage.input_tokens if response.usage else None
        output_tokens = response.usage.output_tokens if response.usage else None

        return Interpretation(
            act=act,
            act_confidence=act_confidence,
            slots=slots,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
