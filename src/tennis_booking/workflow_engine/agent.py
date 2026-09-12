"""FSMAgent itself -- see `tennis_booking.workflow_engine`'s package docstring
(`__init__.py`) for the full architectural rationale.
"""
from __future__ import annotations

import re

from tennis_booking.workflow_engine.step_engine_langgraph import LangGraphStepEngine
from tennis_booking.workflow_engine.step_engine_shared import apply_field_change, step_payload
from tennis_booking.workflow_engine.state import BookingState
from tennis_booking.workflow_steps import STEPS, Step

_STEP_BY_KEY: dict[str, Step] = {s.key: s for s in STEPS}

# Which node owns each settable slot -- used both to sort a multi-slot
# `updates[]` call into WORKFLOW order (not the order the caller listed
# them in) and to dispatch a slot to its handler. Sorting matters because
# a later slot in the same call must see whatever
# an earlier one just produced (e.g. the six search-input slots settling
# before selected_time is validated against fresh results). This is NOT a
# gate on when a slot may be sent -- every slot here is always legal in any
# call regardless of which node is currently active (forward-fill and
# correction both still work exactly as before); it only decides ordering
# and which handler runs. `court_hint` maps to ask_time purely for that
# ordering purpose -- it never reaches `setattr` itself (it isn't a
# BookingState field), see `handle()`.
SLOT_TO_NODE: dict[str, str] = {
    "area": "ask_area",
    "date": "ask_date",
    "surface": "ask_surface",
    "duration_minutes": "ask_duration",
    "num_players": "ask_num_players",
    "indoor_outdoor": "ask_indoor_outdoor",
    "selected_time": "ask_time",
    "court_hint": "ask_time",
    "skill_level": "ask_skill_level",
    "equipment_rental": "ask_equipment_rental",
    "contact_name": "ask_contact_name",
    "contact_email": "ask_contact_email",
    "confirmed": "confirm_booking",
}

# The inverse grouping, one entry per STEPS key -- exposed to the model as
# `current_node_slots` in `_node_payload` so it knows what THIS node is
# actively asking about. Not a whitelist: SLOT_TO_NODE above is what
# actually gates dispatch, and it accepts every slot regardless of the
# current node.
SLOTS_BY_NODE: dict[str, tuple[str, ...]] = {
    "ask_area": ("area",),
    "ask_date": ("date",),
    "ask_surface": ("surface",),
    "ask_duration": ("duration_minutes",),
    "ask_num_players": ("num_players",),
    "ask_indoor_outdoor": ("indoor_outdoor",),
    "search_availability": (),
    "ask_time": ("selected_time", "court_hint"),
    "ask_skill_level": ("skill_level",),
    "ask_equipment_rental": ("equipment_rental",),
    "ask_contact_name": ("contact_name",),
    "ask_contact_email": ("contact_email",),
    "confirm_booking": ("confirmed",),
    "call_book_court": (),
    "send_confirmation": (),
    "close_out": (),
}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _as_int(value) -> int | None:
    """Accepts a real int, or a float with no fractional part (some models
    emit e.g. 90.0 for a JSON Schema `number` property) -- never a bool
    (which is a subclass of int in Python) or a numeral string, since a
    slot's `value` arriving as the wrong JSON type is a real error to
    surface, not something to silently coerce (see confirmed/
    equipment_rental below, where the same principle applies to bools)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _validate_area(value):
    """area is now free text -- geocoded for real by the live court lookup
    (`tools/live_courts.py`) at search time, so there's no fixed allowlist
    to validate against here. A bad/unresolvable location surfaces as a
    tool-result error from search_availability instead (see
    tools/search_availability.py)."""
    if not isinstance(value, str) or not value.strip():
        return False, None, "area must be a non-empty string."
    return True, value.strip(), None


def _validate_date(value):
    if not isinstance(value, str) or not _ISO_DATE_RE.match(value):
        return False, None, "date must be an ISO date string (YYYY-MM-DD), e.g. '2026-09-06'."
    return True, value, None


_SURFACES = frozenset({"hard", "clay", "grass", "indoor_carpet", "any"})


def _validate_surface(value):
    if not isinstance(value, str) or value not in _SURFACES:
        return False, None, f"surface must be one of: {sorted(_SURFACES)}."
    return True, value, None


def _validate_duration_minutes(value):
    n = _as_int(value)
    if n is None or n not in (60, 90, 120):
        return False, None, "duration_minutes must be exactly one of 60, 90, or 120."
    return True, n, None


def _validate_num_players(value):
    n = _as_int(value)
    if n is None or n not in (2, 4):
        return False, None, "num_players must be exactly one of 2 (singles) or 4 (doubles)."
    return True, n, None


_INDOOR_OUTDOOR = frozenset({"indoor", "outdoor", "either"})


def _validate_indoor_outdoor(value):
    if not isinstance(value, str) or value not in _INDOOR_OUTDOOR:
        return False, None, f"indoor_outdoor must be one of: {sorted(_INDOOR_OUTDOOR)}."
    return True, value, None


_SKILL_LEVELS = frozenset({"beginner", "intermediate", "advanced"})


def _validate_skill_level(value):
    if not isinstance(value, str) or value not in _SKILL_LEVELS:
        return False, None, f"skill_level must be one of: {sorted(_SKILL_LEVELS)}."
    return True, value, None


def _validate_equipment_rental(value):
    if not isinstance(value, bool):
        return False, None, "equipment_rental must be true or false (a real boolean), not a string."
    return True, value, None


def _validate_contact_name(value):
    if not isinstance(value, str) or not value.strip():
        return False, None, "contact_name must be a non-empty string."
    return True, value.strip(), None


def _validate_contact_email(value):
    if not isinstance(value, str):
        return False, None, "contact_email must be a string."
    match = _EMAIL_RE.search(value)
    if not match:
        return False, None, "That doesn't look like a valid email address -- resend it in the form name@domain.tld."
    return True, match.group(0), None


# One validator per cross-cutting slot -- each returns (ok, canonical_value,
# error). `selected_time`/`court_hint` and `confirmed` are step-specific and
# handled directly in `handle()` instead (they need access to `self.state`
# beyond a single value, e.g. resolving against `available_courts` or
# gating on `ready_to_book()`).
#
# This validation lives here, server-side, rather than in BOOK_TENNIS_COURT_TOOL's
# JSON Schema, because JSON Schema can't key a discriminated union off a
# sibling property -- `updates[].value`'s real type/enum depends on that same
# entry's `slot`, which the schema has no way to express. An invalid value
# round-trips through `errors` instead of being rejected by the tool-calling
# layer.
SLOT_VALIDATORS = {
    "area": _validate_area,
    "date": _validate_date,
    "surface": _validate_surface,
    "duration_minutes": _validate_duration_minutes,
    "num_players": _validate_num_players,
    "indoor_outdoor": _validate_indoor_outdoor,
    "skill_level": _validate_skill_level,
    "equipment_rental": _validate_equipment_rental,
    "contact_name": _validate_contact_name,
    "contact_email": _validate_contact_email,
}


def _node_payload(state: BookingState, step: Step) -> dict:
    """`step_engine_shared.step_payload`'s response, reshaped for this
    variant's vocabulary: `step`/`instruction` -> `current_node`/
    `instructions` (including inside `upcoming_instructions` entries, which
    are shaped the same way), plus a new `current_node_slots`.
    """
    base = step_payload(state, step)
    node_key = base.pop("step")
    instructions = base.pop("instruction")
    upcoming = base.pop("upcoming_instructions", None)

    payload = {
        "current_node": node_key,
        "instructions": instructions,
        "current_node_slots": list(SLOTS_BY_NODE.get(step.key, ())),
    }
    if upcoming is not None:
        payload["upcoming_instructions"] = [
            {"current_node": entry["step"], "instructions": entry["instruction"]} for entry in upcoming
        ]
    payload.update(base)  # available_courts/note, booking_summary, confirmation_id/date/time
    return payload


def _node_error(step: Step, message: str) -> dict:
    return {
        "error": message,
        "current_node": step.key,
        "instructions": step.instruction,
        "current_node_slots": list(SLOTS_BY_NODE.get(step.key, ())),
    }


class FSMAgent(LangGraphStepEngine):
    """Backend for `book_tennis_court`: reuses `LangGraphStepEngine`'s step
    computation, but `handle()` takes an already-validated
    `{"updates": [{"slot", "value"}, ...]}` dict instead of a free-text
    payload string.
    """

    def _resolve_selected_time(self, selected_time: str, court_hint: str | None) -> tuple[bool, dict, str | None]:
        if not self.state.available_courts:
            return False, {}, "No availability has been searched yet -- this shouldn't happen; please retry."

        candidates = self.state.available_courts
        if court_hint:
            hint = court_hint.strip().lower()
            named = [c for c in candidates if hint in c.name.lower()]
            surface = [c for c in candidates if c.surface.replace("_", " ") in hint or hint in c.surface.replace("_", " ")]
            candidates = named or surface or candidates

        for court in candidates:
            if any(slot.time == selected_time for slot in court.slots):
                return True, {"selected_court_id": court.court_id, "selected_time": selected_time}, None

        return False, {}, (
            f"'{selected_time}' is not an open time on any matching court from the last search. "
            "Resend one of the times actually shown."
        )

    def handle(self, args: dict) -> dict:
        """The single entry point `book_tennis_court`'s handler calls.
        `args` is the tool call's already-validated arguments dict --
        `{}` (or `{"updates": []}`) on the bootstrap call, otherwise
        `{"updates": [{"slot": ..., "value": ...}, ...]}` covering any mix
        of a correction, the current node, or a not-yet-reached node's
        slot(s), in one call (see SLOT_TO_NODE above).
        """
        updates = (args or {}).get("updates") or []
        step = self._advance_past_tool_actions()

        if step is None:
            return {"workflow_complete": True}

        if not updates:
            # Empty is only meaningful as the very first call of the whole
            # conversation -- a later empty call must error instead of
            # silently re-showing the same node, which would look like
            # progress was made when it wasn't.
            if self._called_before:
                return _node_error(
                    step,
                    "Empty call -- this only bootstraps the very first call of a "
                    "conversation. Resend with the update(s) the user just gave you.",
                )
            self._called_before = True
            return _node_payload(self.state, step)
        self._called_before = True

        slots_seen = [u.get("slot") for u in updates]
        duplicate_slots = {s for s in slots_seen if slots_seen.count(s) > 1}

        errors: dict = {
            s: f"'{s}' was set more than once in this call -- resend it once, with just one value."
            for s in duplicate_slots
        }

        values: dict = {}
        for u in updates:
            slot = u.get("slot")
            value = u.get("value")
            if slot in duplicate_slots:
                continue
            if slot not in SLOT_TO_NODE:
                errors[slot] = f"'{slot}' is not a recognized slot."
                continue
            if value == "":
                errors[slot] = (
                    f"'{slot}' was sent with an empty value -- omit it instead of clearing "
                    "it, or resend with a real value."
                )
                continue
            values[slot] = value

        court_hint = values.pop("court_hint", None)
        if court_hint is not None and "selected_time" not in values:
            errors["court_hint"] = (
                "court_hint only makes sense alongside selected_time in the same call -- "
                "resend both together."
            )
            court_hint = None

        ordered = sorted(values.items(), key=lambda item: STEPS.index(_STEP_BY_KEY[SLOT_TO_NODE[item[0]]]))

        applied: dict = {}

        for slot, value in ordered:
            if self.state.booking_confirmed:
                errors[slot] = "This booking is already confirmed and can't be changed through this tool."
                continue

            if slot == "selected_time":
                ok, result_fields, error = self._resolve_selected_time(value, court_hint)
                if not ok:
                    errors[slot] = error
                    continue
                for field_name, field_value in result_fields.items():
                    if getattr(self.state, field_name) != field_value:
                        apply_field_change(self.state, field_name, field_value)
                applied[slot] = value
                self._advance_past_tool_actions()
                continue

            if slot == "confirmed":
                if not isinstance(value, bool):
                    errors[slot] = "confirmed must be true or false (a real boolean), not a string."
                    continue
                if not self.state.ready_to_book():
                    errors[slot] = (
                        "Every other field must be filled in and the booking summary recited "
                        "before confirming -- this shouldn't happen if you followed the "
                        "workflow in order."
                    )
                    continue
                if not value:
                    errors[slot] = (
                        "The user did not confirm the summary. Ask them what needs to change, "
                        "then resend the corrected field(s) before confirming again."
                    )
                    continue
                if not self.state.summary_confirmed:
                    apply_field_change(self.state, "summary_confirmed", True)
                applied[slot] = True
                self._advance_past_tool_actions()
                continue

            ok, canonical, error = SLOT_VALIDATORS[slot](value)
            if not ok:
                errors[slot] = error
                continue
            if getattr(self.state, slot) != canonical:
                apply_field_change(self.state, slot, canonical)
            applied[slot] = canonical
            self._advance_past_tool_actions()

        next_step = self._advance_past_tool_actions()
        response = {"workflow_complete": True} if next_step is None else _node_payload(self.state, next_step)
        if applied:
            response["applied"] = applied
        if errors:
            response["errors"] = errors
        return response
