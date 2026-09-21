"""Interpretation models and protocol for the Jev agent."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from tennis_booking.workflow_engine.state import BookingState


@dataclass(frozen=True)
class Interpretation:
    """Result of interpreting a user turn with TypeSafe's Jev model.

    `slots` contains only slots the user mentioned (not_mentioned option omitted).
    Each slot value is a (value, confidence) tuple.
    """

    act: str  # answers_current, corrects_earlier, gives_later_info, etc.
    act_confidence: float  # 0.0-1.0
    slots: dict[str, tuple]  # {slot_name: (value, confidence), ...}
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None


class Interpreter(Protocol):
    """Protocol for interpreting user turns via TypeSafe's Jev model."""

    def interpret(self, state: BookingState, last_assistant: str, user_turn: str) -> Interpretation:
        """Interpret a user's turn given the current booking state.

        Returns an Interpretation with the interpreted act and mentioned slots.
        """
        ...
