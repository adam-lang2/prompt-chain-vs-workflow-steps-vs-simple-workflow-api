"""Apply Interpretation to BookingState via deterministic rules."""
from __future__ import annotations

from dataclasses import dataclass

from tennis_booking.jev.interpret import Interpretation
from tennis_booking.workflow_engine.state import BookingState


@dataclass(frozen=True)
class ApplyResult:
    """Result of applying an interpretation to BookingState."""

    updates: list[dict]  # [{slot, value}, ...]
    ambiguities: list[str]  # Confidence issues to ask about
    act: str  # The act that was interpreted
    restart: bool  # True if user asked to restart/cancel


def to_updates(
    interp: Interpretation,
    state: BookingState,
    threshold: float = 0.6,
    current_node: str | None = None,
    user_turn: str | None = None,
) -> ApplyResult:
    """Convert an Interpretation into state updates and ambiguities.

    Rules:
    - Apply any mentioned slot with confidence >= threshold, else add to ambiguities
    - confirmed: True only if act=="confirms" and at confirm_booking node
    - confirmed: False if act=="declines" (no update, but passed through)
    - restart_or_cancel sets restart=True
    - equipment_rental yes/no -> bool
    - duration_minutes, num_players -> int

    `user_turn` (the raw text of the user's message this turn, if given) is
    folded into any ambiguity string below -- a bare slot name like "surface"
    forces the speaker to replay the whole conversation to guess what's
    actually unclear; the guessed value + the user's own words let it resolve
    the ambiguity directly instead.
    """
    updates_list: list[dict] = []
    ambiguities_list: list[str] = []
    restart = False

    # Handle restart/cancel
    if interp.act == "restart_or_cancel":
        restart = True
        return ApplyResult(updates=[], ambiguities=[], act=interp.act, restart=restart)

    # Process mentioned slots
    for slot_name, (value, confidence) in interp.slots.items():
        if confidence < threshold:
            # A shaky guess at a slot that is already set, on a turn that isn't
            # a correction, is noise: the user didn't re-state it. Asking about
            # it only makes the speaker second-guess settled answers.
            already_set = getattr(state, slot_name, None) not in (None, "")
            if already_set and interp.act != "corrects_earlier":
                continue
            guess = f"best guess {value!r} at {confidence:.0%} confidence"
            if user_turn:
                ambiguities_list.append(f"Unclear what the user meant for {slot_name} ({guess}) in: {user_turn!r}")
            else:
                ambiguities_list.append(f"Unclear what the user meant for {slot_name} ({guess})")
            continue

        # Type coercion
        coerced_value = value
        if slot_name == "equipment_rental":
            if isinstance(value, str):
                coerced_value = value.lower() in ("yes", "true")
            else:
                coerced_value = bool(value)

        elif slot_name in ("duration_minutes", "num_players"):
            if isinstance(value, str):
                coerced_value = int(value)
            else:
                coerced_value = int(value)

        updates_list.append({"slot": slot_name, "value": coerced_value})

    # A court hint only matters when several courts share the chosen time. If
    # exactly one court has it, the time already picks the court, so an unsure
    # hint is not worth asking the user about.
    chosen_time = next((u["value"] for u in updates_list if u["slot"] == "selected_time"), None)
    if chosen_time is not None:
        matching = [c for c in state.available_courts if any(s.time == chosen_time for s in c.slots)]
        if len(matching) == 1:
            ambiguities_list = [a for a in ambiguities_list if "court_hint" not in a]

    # `confirmed` is only ever set by a confirming act at the confirm_booking node.
    if interp.act == "confirms":
        at_confirm = current_node == "confirm_booking" if current_node else state.ready_to_book()
        if at_confirm:
            updates_list.append({"slot": "confirmed", "value": True})

    return ApplyResult(
        updates=updates_list,
        ambiguities=ambiguities_list,
        act=interp.act,
        restart=restart,
    )
