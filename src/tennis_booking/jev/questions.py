"""Question building for the Jev agent's TypeSafe calls."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping

from typesafe_sdk import Choice

from tennis_booking.workflow_engine.agent import (
    _INDOOR_OUTDOOR,
    _SKILL_LEVELS,
    _SURFACES,
)
from tennis_booking.workflow_engine.state import BookingState
from tennis_booking.workflow_steps import STEPS


def tokenize_user_turn(user_turn: str, max_tokens: int = 250) -> list[str]:
    """Split user turn into words (simple tokenization), capped at max_tokens."""
    return user_turn.split()[:max_tokens]


def build_state(state: BookingState, last_assistant: str, user_turn: str) -> str:
    """Build the state dict/JSON to pass to TypeSafe.

    Includes current booking state, last assistant message, and user turn.
    """
    from datetime import datetime

    return f"""Booking context:
Current state: {state.as_dict()}
Last assistant message: "{last_assistant}"
User's latest message: "{user_turn}"
Current time: {datetime.now().isoformat()}
"""


def build_questions(
    state: BookingState, tokens: list[str] | None = None
) -> Mapping[str, Choice]:
    """Build all TypeSafe Choice questions to interpret the user's turn.

    Returns a mapping of question name -> Choice object.
    `tokens` is the tokenized user turn, used for the free-text span questions.
    """

    questions: dict[str, Choice] = {}

    # Action interpretation
    questions["act"] = Choice(
        instructions=(
            "What best describes what the user just did? "
            "- answers_current: answering the question just asked "
            "- corrects_earlier: correcting an earlier answer "
            "- gives_later_info: providing info for a step not yet asked "
            "- asks_question: asking the assistant a clarifying question "
            "- confirms: saying yes to confirm the booking summary "
            "- declines: saying no, rejecting the booking "
            "- restart_or_cancel: asking to restart or cancel the booking "
            "- off_topic: saying something unrelated to the booking"
        ),
        criteria={
            "answers_current": "answering the question just asked",
            "corrects_earlier": "correcting an earlier answer",
            "gives_later_info": "providing info for a step not yet asked",
            "asks_question": "asking the assistant a clarifying question",
            "confirms": "confirming the booking summary (yes)",
            "declines": "declining the booking (no)",
            "restart_or_cancel": "asking to restart or cancel",
            "off_topic": "off-topic message",
            "not_mentioned": "unclear or ambiguous",
        },
    )

    # Vocabulary choices
    if True:
        questions["surface"] = Choice(
            instructions="Which court surface does the user prefer? (or not_mentioned if not stated)",
            criteria={s: s for s in sorted(_SURFACES)} | {"not_mentioned": "surface not mentioned"},
        )

    if True:
        questions["indoor_outdoor"] = Choice(
            instructions="Does the user prefer indoor, outdoor, or either? (or not_mentioned)",
            criteria={s: s for s in sorted(_INDOOR_OUTDOOR)} | {"not_mentioned": "preference not mentioned"},
        )

    if True:
        questions["skill_level"] = Choice(
            instructions="What skill level does the user mention? (beginner/intermediate/advanced, or not_mentioned)",
            criteria={s: s for s in sorted(_SKILL_LEVELS)} | {"not_mentioned": "skill level not mentioned"},
        )

    if True:
        questions["duration_minutes"] = Choice(
            instructions="How many minutes does the user want to play? (60/90/120 only, or not_mentioned)",
            criteria={
                "60": "60 minutes",
                "90": "90 minutes",
                "120": "120 minutes",
                "not_mentioned": "duration not mentioned",
            },
        )

    if True:
        questions["num_players"] = Choice(
            instructions="How many players: singles (2) or doubles (4)? (or not_mentioned)",
            criteria={
                "2": "singles (2 players)",
                "4": "doubles (4 players)",
                "not_mentioned": "player count not mentioned",
            },
        )

    if True:
        questions["equipment_rental"] = Choice(
            instructions="Does the user need to rent equipment? (yes/no, or not_mentioned)",
            criteria={
                "yes": "yes, needs rental",
                "no": "no, does not need rental",
                "not_mentioned": "equipment rental not mentioned",
            },
        )

    # Date choice
    if True:
        today = datetime.now().date()
        date_options = {
            (today + timedelta(days=i)).isoformat(): (today + timedelta(days=i)).strftime("%A, %b %d")
            for i in range(14)
        }
        date_options["not_mentioned"] = "date not mentioned"
        questions["date"] = Choice(
            instructions="What date does the user want? (ISO date YYYY-MM-DD or not_mentioned)",
            criteria=date_options,
        )

    # Time options (only if availability has been searched)
    if state.available_courts:
        time_options = {}
        for court in state.available_courts:
            for slot in court.slots:
                time_options[slot.time] = f"{slot.time} on {court.name}"
        time_options["not_mentioned"] = "time not mentioned"
        questions["selected_time"] = Choice(
            instructions="Which time does the user want to book? (HH:MM format, from available_courts, or not_mentioned)",
            criteria=time_options,
        )

        court_names = {court.name: court.name for court in state.available_courts}
        court_names["not_mentioned"] = "court not mentioned"
        questions["court_hint"] = Choice(
            instructions="Which court does the user mention by name or hint? (or not_mentioned)",
            criteria=court_names,
        )

    # Free-text slots: Jev selects the start/end token of the span; code slices it verbatim.
    if tokens:
        token_options = {str(i): tok for i, tok in enumerate(tokens)}
        for slot, what in (("area", "the location/place the user wants to play near"), ("contact_name", "the user's own name")):
            for edge in ("start", "end"):
                questions[f"{slot}_{edge}"] = Choice(
                    instructions=(
                        f"The user's message is split into numbered words. Which word is the {edge} of {what}? "
                        "Answer not_mentioned if the message does not state it."
                    ),
                    criteria=token_options | {"not_mentioned": f"{what} not stated"},
                )

    return questions
