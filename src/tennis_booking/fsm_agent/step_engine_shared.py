"""Shared vocabulary between `HandRolledStepEngine` (step_engine_handrolled.py, a hand-rolled
scanning engine) and `TransitionsStepEngine` (step_engine_transitions.py, a
`transitions.Machine` engine) -- extracted here, as free functions, so
neither class needs to inherit from the other.

Why this split: the two classes exist specifically to compare two different
step-*computation* engines (see step_engine_transitions.py's own docstring). Nothing
in this module is that engine -- it's the payload grammar, field
extractors, and response shaping that are identical by design across both
architectures (the tool's own schema docstring says as much: "v1 and v2
share the exact same grammar and the exact same backend -- nothing about
parsing changes"). Keeping this here, imported (not inherited) by both
engines, means:

- Each engine class can be read end-to-end on its own, with no inherited
  method to chase into a sibling file, when assessing its complexity --
  the whole point of decoupling them.
- The grammar/extractors/response-shape stay a single copy, exactly like
  `workflow_steps.py` is a single copy both engines already share -- a
  change here can't silently drift between the two compared variants.

This mirrors `workflow_steps.py`'s existing role (shared workflow
definition, used by composition, not inheritance) one level down, for the
regex-specific machinery only HandRolledStepEngine/TransitionsStepEngine need.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from tennis_booking.mock_courts import KNOWN_AREAS
from tennis_booking.models import SEARCH_INPUT_SLOTS, BookingState
from tennis_booking.tools import run_book_court, run_search_availability
from tennis_booking.workflow_steps import STEPS, Step

# (ok, fields_to_set, error_message). `fields_to_set` may set more than one
# BookingState field (e.g. ask_time sets both selected_court_id and
# selected_time from one payload). extractors receive the raw payload text
# plus the current BookingState, since a couple of them (ask_time above all)
# can only be resolved against what's actually in the state right now (the
# real court names / times returned by the last search).
#
# These extractors assume the payload is already a sanitized, single-purpose
# value -- agent-1 is responsible for stripping filler and normalizing
# before it ever reaches here (dates to ISO, etc). That's also why there's
# no permissive "accept whatever's left"
# fallback anywhere below: a value that doesn't match this field's expected
# shape is treated as a real parse failure, not something to guess at. (This
# used to be a real bug: an unconstrained area fallback once swallowed an
# entire date-correction sentence as if it were a new area name.) Corrections
# to an EARLIER field don't run these extractors against the raw payload
# either -- see FIELD_LABELS / _handle_labeled_batch below, which isolates
# just the value agent-1 tagged before handing it to the right extractor.
ExtractResult = tuple[bool, dict, Optional[str]]
Extractor = Callable[[str, BookingState], ExtractResult]


def _ok(fields: dict) -> ExtractResult:
    return True, fields, None


def _err(message: str) -> ExtractResult:
    return False, {}, message


def _extract_area(text: str, state: BookingState) -> ExtractResult:
    # Matches against the known-area gazetteer only -- an area outside it
    # can never return real search results anyway (see mock_courts.py), so
    # rejecting it here and telling agent-1 immediately is strictly better
    # than silently accepting an unserviceable area and only discovering
    # that two steps later as an empty search result. Matched anywhere in
    # the text (not anchored) since a sanitized payload is normally just the
    # area name on its own, but this also correctly pulls "downtown" out of
    # a lightly-sanitized "somewhere near downtown" without needing a
    # separate leading-preposition strip.
    lowered = text.lower()
    for area in KNOWN_AREAS:
        if re.search(rf"\b{re.escape(area)}\b", lowered):
            return _ok({"area": area})
    return _err(
        "No known area name found in that message. Resend the payload naming a city, "
        "neighborhood, or general area (e.g. 'downtown', 'eastside')."
    )


_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _extract_date(text: str, state: BookingState) -> ExtractResult:
    match = _ISO_DATE_RE.search(text)
    if not match:
        return _err(
            "Could not find an ISO date (YYYY-MM-DD) in that message. Convert whatever date the "
            "user gave to ISO format before resending, e.g. '2026-09-05'."
        )
    return _ok({"date": match.group(1)})


_SURFACE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bindoor\s*carpet\b", "indoor_carpet"),
    (r"\bhard\b", "hard"),
    (r"\bclay\b", "clay"),
    (r"\bgrass\b", "grass"),
    (r"\b(?:any|no\s+preference|doesn'?t\s+matter|either)\b", "any"),
)


def _extract_surface(text: str, state: BookingState) -> ExtractResult:
    for pattern, value in _SURFACE_PATTERNS:
        if re.search(pattern, text, re.I):
            return _ok({"surface": value})
    return _err(
        "Could not find a valid surface in that message. Resend the payload naming exactly one "
        "of: hard, clay, grass, indoor carpet, or any/no preference."
    )


def _extract_duration(text: str, state: BookingState) -> ExtractResult:
    match = re.search(r"\b(60|90|120)\b", text)
    if not match:
        return _err(
            "Could not find a valid duration in that message. Resend the payload with exactly "
            "one of: 60, 90, or 120 (minutes)."
        )
    return _ok({"duration_minutes": int(match.group(1))})


def _extract_num_players(text: str, state: BookingState) -> ExtractResult:
    if re.search(r"\bsingles?\b", text, re.I):
        return _ok({"num_players": 2})
    if re.search(r"\bdoubles?\b", text, re.I):
        return _ok({"num_players": 4})
    match = re.search(r"\b(2|4)\b", text)
    if not match:
        return _err(
            "Could not find a valid player count in that message. Resend the payload with "
            "exactly '2' (singles) or '4' (doubles)."
        )
    return _ok({"num_players": int(match.group(1))})


_EITHER_SYNONYM_RE = re.compile(
    # "any" included -- it's the accepted no-preference value for `surface`,
    # so it's a natural (and observed live) mistake to reuse it here too.
    r"\b(either|any|no\s+preference|doesn'?t\s+matter|don'?t\s+care|not\s+picky|whichever)\b",
    re.I,
)


def _extract_indoor_outdoor(text: str, state: BookingState) -> ExtractResult:
    if _EITHER_SYNONYM_RE.search(text):
        return _ok({"indoor_outdoor": "either"})
    has_indoor = re.search(r"\bindoor\b", text, re.I) is not None
    has_outdoor = re.search(r"\boutdoor\b", text, re.I) is not None
    if has_indoor and has_outdoor:
        # Both mentioned with no "either"/"doesn't matter" synonym and no
        # single-preference wording -- e.g. "indoor or outdoor, 4 players"
        # -- is itself a no-preference signal, same as if they'd said
        # "either" outright.
        return _ok({"indoor_outdoor": "either"})
    if has_indoor:
        return _ok({"indoor_outdoor": "indoor"})
    if has_outdoor:
        return _ok({"indoor_outdoor": "outdoor"})
    return _err(
        "Could not find a valid indoor/outdoor preference in that message. Resend the payload "
        "with exactly one of: indoor, outdoor, or either."
    )


_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b|\b(1[0-2]|[1-9])\s*(am|pm)\b", re.I)


def _normalize_time(match: re.Match) -> str:
    if match.group(1) is not None:
        return f"{int(match.group(1)):02d}:{match.group(2)}"
    hour = int(match.group(3))
    meridiem = match.group(4).lower()
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:00"


def _extract_time(text: str, state: BookingState) -> ExtractResult:
    if not state.available_courts:
        return _err("No availability has been searched yet -- this shouldn't happen; please retry.")

    time_match = _TIME_RE.search(text)
    if not time_match:
        return _err(
            "Could not find a valid time in that message. Resend the payload with one of the "
            "times just shown, in HH:MM (e.g. '12:00') or 'H am/pm' (e.g. '2pm') format."
        )
    wanted_time = _normalize_time(time_match)

    # Narrow to a specific court if the payload identifies one -- either by
    # its literal name, or (verified live: a real gap when a scripted user
    # says "the grass court" rather than repeating the court's actual name,
    # e.g. "Northpark Lawn Club" -- the name-substring check alone falls
    # through to "any court with this time slot", silently picking the wrong
    # one whenever two courts share an open slot) by the surface it's on.
    lowered = text.lower()
    named_courts = [c for c in state.available_courts if c.name.lower() in lowered]
    surface_courts = [
        c for c in state.available_courts if re.search(rf"\b{re.escape(c.surface.replace('_', ' '))}\b", lowered)
    ]
    candidates = named_courts or surface_courts or state.available_courts

    for court in candidates:
        if any(slot.time == wanted_time for slot in court.slots):
            return _ok({"selected_court_id": court.court_id, "selected_time": wanted_time})

    return _err(
        f"'{wanted_time}' is not an open time on any matching court from the last search. "
        "Resend the payload with one of the times actually shown."
    )


def _extract_skill_level(text: str, state: BookingState) -> ExtractResult:
    for level in ("beginner", "intermediate", "advanced"):
        if re.search(rf"\b{level}\b", text, re.I):
            return _ok({"skill_level": level})
    return _err(
        "Could not find a valid skill level in that message. Resend the payload with exactly "
        "one of: beginner, intermediate, or advanced."
    )


def _extract_equipment_rental(text: str, state: BookingState) -> ExtractResult:
    if re.search(r"\b(no|don'?t|do\s+not|not\s+need|have\s+(?:my\s+)?own)\b", text, re.I):
        return _ok({"equipment_rental": False})
    # No bare "please" fallback -- too generic a "yes" signal on its own
    # (a sanitized payload should already read as an unambiguous yes/no).
    if re.search(r"\b(yes|need|rent)\b", text, re.I):
        return _ok({"equipment_rental": True})
    return _err(
        "Could not tell whether a racket rental is needed from that message. Resend the payload "
        "clearly saying yes or no."
    )


_NAME_LEAD_IN_ANCHORED_RE = re.compile(
    r"^\s*(?:(?:my\s+name\s+is|i'?m|it'?s|this\s+is|call\s+me|name'?s)\s+)", re.I
)
# Whatever precedes an embedded email address, e.g. "..., email " or "... and
# my email is " -- stripped so a bundled "name, email X@Y" message doesn't
# leave the email hanging off the end of the extracted name.
_TRAILING_EMAIL_CONNECTOR_RE = re.compile(r"[,\s]*(?:and\s+)?(?:my\s+)?email(?:\s+is)?\s*[:\-]?\s*$", re.I)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _strip_embedded_email(text: str) -> str:
    """Cut `text` at the start of any embedded email address, plus whatever
    connector word led into it -- for when a step's answer arrives bundled
    with a later step's answer in one message (e.g. "Sam Okafor,
    sam.okafor@example.com" while only the name is being asked about)."""
    match = _EMAIL_RE.search(text)
    if not match:
        return text
    before = text[: match.start()]
    before = _TRAILING_EMAIL_CONNECTOR_RE.sub("", before)
    return before.rstrip(",. ").strip()


def _extract_contact_name(text: str, state: BookingState) -> ExtractResult:
    cleaned = _strip_embedded_email(_NAME_LEAD_IN_ANCHORED_RE.sub("", text).strip()).rstrip(".!")
    if not re.search(r"[a-zA-Z]{2,}.*[a-zA-Z]{1,}", cleaned):
        return _err("Could not find a name in that message. Resend the payload with the user's full name.")
    return _ok({"contact_name": cleaned})


def _extract_contact_email(text: str, state: BookingState) -> ExtractResult:
    match = _EMAIL_RE.search(text)
    if not match:
        return _err(
            "Could not find a valid email address in that message. Resend the payload with an "
            "address in the form name@domain.tld."
        )
    return _ok({"contact_email": match.group(0)})


def _extract_summary_confirmed(text: str, state: BookingState) -> ExtractResult:
    if re.search(r"\b(yes|confirm(?:ed)?|correct|looks?\s+good|that'?s\s+right|book\s+it|go\s+ahead)\b", text, re.I):
        return _ok({"summary_confirmed": True})
    if re.search(r"\b(no|wrong|incorrect|change)\b", text, re.I):
        return _err(
            "The user did not confirm the summary. Ask them what needs to change, then resend "
            "the corrected field(s) as their own payload(s) before confirming again."
        )
    return _err(
        "Could not tell whether the user confirmed the summary from that message. Resend the "
        "payload once they've clearly said yes or no."
    )


STEP_EXTRACTORS: dict[str, Extractor] = {
    "ask_area": _extract_area,
    "ask_date": _extract_date,
    "ask_surface": _extract_surface,
    "ask_duration": _extract_duration,
    "ask_num_players": _extract_num_players,
    "ask_indoor_outdoor": _extract_indoor_outdoor,
    "ask_time": _extract_time,
    "ask_skill_level": _extract_skill_level,
    "ask_equipment_rental": _extract_equipment_rental,
    "ask_contact_name": _extract_contact_name,
    "ask_contact_email": _extract_contact_email,
    "confirm_booking": _extract_summary_confirmed,
}


# --- Labeled fields: corrections AND forward-fills ---------------------------
#
# A payload that doesn't match the CURRENTLY active step might still be
# valid input -- either a correction to something answered several steps ago
# (e.g. "actually, let's do 2026-09-12 instead" arriving while duration is
# being asked about), or an answer to a step that hasn't come up yet (e.g.
# the user names their skill level in the same breath as their area, several
# steps before ask_skill_level is reached). Both are the same situation from
# this module's point of view: a value for a NAMED field that isn't the
# current step. Without explicit labels, both would be invisible -- the
# active step's extractor rejects a payload that doesn't match its own
# shape, and the value is silently lost (a correction ships a stale original
# value later; a forward-filled answer gets re-asked once its step comes
# up). See `apply_labeled_batch` below, which handles any number of labeled
# fields -- earlier, current, or later than the active step -- in one call.
#
# FIELD_DEPENDENTS models what depends on what, explicitly:
# - "search": the six search-input fields. Changing one doesn't need any
#   invalidation code here at all -- BookingState.search_params_stale()
#   already detects the mismatch against last_search_params, and
#   next_step_for() already re-triggers search_availability (which clears
#   available_courts/selected_court_id/selected_time via
#   record_search_results()) the next time the step machine runs. Reusing
#   that existing, already-tested cascade instead of duplicating it is the
#   point of routing corrections through the normal handle() flow.
# - "confirmation": every field. If the user already confirmed the summary
#   and then corrects ANYTHING, that confirmation is stale -- reset
#   summary_confirmed so confirm_booking is asked again before book_court
#   can run. This never re-asks any OTHER field: a corrected contact_name,
#   for instance, has zero effect on area/date/surface/etc.
FIELD_DEPENDENTS: dict[str, frozenset[str]] = {
    **{slot: frozenset({"search", "confirmation"}) for slot in SEARCH_INPUT_SLOTS},
    "selected_court_id": frozenset({"confirmation"}),
    "selected_time": frozenset({"confirmation"}),
    "skill_level": frozenset({"confirmation"}),
    "equipment_rental": frozenset({"confirmation"}),
    "contact_name": frozenset({"confirmation"}),
    "contact_email": frozenset({"confirmation"}),
}

# The fixed label vocabulary agent-1 is told about UP FRONT (in its own
# system prompt or tool schema, not just under a "corrections" heading) to
# name exactly which field a value belongs to -- e.g. "date: 2026-09-12".
# Agent-1, not this regex layer, decides which field(s) a payload is naming;
# a label is matched literally, so there's never any guessing across every
# field's extractor pattern. No cue word (e.g. "actually") is required or
# checked -- the label alone is unambiguous, whether the value corrects an
# earlier answer, answers the current step, or forward-fills a step nobody
# has reached yet.
FIELD_LABELS: dict[str, str] = {
    "area": "ask_area",
    "date": "ask_date",
    "surface": "ask_surface",
    "duration": "ask_duration",
    "players": "ask_num_players",
    "indoor_outdoor": "ask_indoor_outdoor",
    "time": "ask_time",
    "skill_level": "ask_skill_level",
    "equipment": "ask_equipment_rental",
    "name": "ask_contact_name",
    "email": "ask_contact_email",
}

_STEP_BY_KEY: dict[str, Step] = {s.key: s for s in STEPS}

# Matches each "<label>:" tag in a payload (not the value) -- used to split a
# payload into one or more (label, value) segments, so a single call can
# carry several fields at once (e.g. "date: 2026-09-19; surface: any;
# duration: 90"), in any mix of earlier, current, or not-yet-reached steps.
_LABEL_TAG_RE = re.compile(rf"\b({'|'.join(FIELD_LABELS)})\s*:\s*", re.I)


def parse_labeled_segments(payload: str) -> list[tuple[str, str]] | None:
    """Split `payload` at each "<label>: " tag into (label, value) pairs, in
    the order they appear. Returns None if the payload contains no
    recognized tag at all -- the caller should fall back to treating the
    whole payload as a single unlabeled answer to the current step.

    Any text before the first tag is discarded, never guessed at as an
    answer to some field -- consistent with this module never guessing at
    unlabeled text once a label is in play. Agent-1 is told to either send a
    single bare unlabeled value (no tags anywhere) or label every field it's
    reporting; a stray leading filler word (e.g. "wait, date: ...") should
    not be silently misread as a failed answer to the current step.
    """
    tags = list(_LABEL_TAG_RE.finditer(payload))
    if not tags:
        return None

    segments: list[tuple[str, str]] = []

    for i, tag in enumerate(tags):
        end = tags[i + 1].start() if i + 1 < len(tags) else len(payload)
        value = payload[tag.end() : end].strip(" ;,.\n\t")
        segments.append((tag.group(1).lower(), value))

    return segments


def apply_field_change(state: BookingState, field_name: str, value) -> None:
    setattr(state, field_name, value)
    dependents = FIELD_DEPENDENTS.get(field_name, frozenset())
    if "confirmation" in dependents and state.summary_confirmed:
        state.summary_confirmed = False
    # "search" dependents need no action here -- see FIELD_DEPENDENTS above.


@dataclass
class InternalToolCall:
    """Records a search_availability / book_court call an engine made on
    its own, internally, while auto-advancing past a tool-action step --
    agent-1 never calls these itself. Exposed so the calling agent module
    (e.g. `agents/a2a_fsm_api.py`) can fold these into `tool_call_log`
    alongside the `book_tennis_court` calls, keeping `scoring.py`'s shared
    scoring logic working unmodified across every architecture.
    """

    name: str
    args: dict
    result: dict


def step_is_current(step: Step, state: BookingState) -> bool:
    """Is `step` still unmet, given `state`? A near-verbatim port of
    workflow_steps.next_step_for's per-step conditions, extracted into a
    standalone predicate so it can be used as a transition guard (or a
    routing condition) instead of a branch inside a scanning loop. Shared by
    every non-regex step-computation engine (step_engine_transitions.py's
    transitions.Machine, step_engine_langgraph.py's StateGraph) -- kept here
    rather than in either engine module so a change to "what does 'unmet'
    mean per step" can't drift between them. Not used by HandRolledStepEngine,
    which still has its own scan (workflow_steps.next_step_for) predating
    this extraction.
    """
    if step.key == "search_availability":
        if not state.ready_to_search_availability():
            return False
        return not state.availability_searched() or state.search_params_stale()

    if step.key == "confirm_booking":
        return state.ready_to_book() and not state.summary_confirmed

    if step.key == "call_book_court":
        return state.ready_to_book() and state.summary_confirmed and not state.booking_confirmed

    if step.key == "close_out":
        return state.booking_confirmed

    # Ordinary slot-filling step.
    unmet = any(getattr(state, slot) in (None, "") for slot in step.slot_names)
    if not unmet:
        return False
    # ask_time's slots only become askable after a current (non-stale)
    # availability search -- same carve-out next_step_for has.
    if step.key == "ask_time" and (not state.availability_searched() or state.search_params_stale()):
        return False
    return True


def execute_tool_action(state: BookingState, step: Step) -> InternalToolCall:
    """Run search_availability / book_court as a side effect of an engine
    settling into one of those steps, mutating `state` in place. Shared by
    both engines -- this is domain logic (what a tool-action step DOES),
    not step-computation logic (WHICH step is current), so it belongs here
    rather than being reimplemented per engine."""
    if step.key == "search_availability":
        args = {
            "area": state.area,
            "date": state.date,
            "surface": state.surface,
            "indoor_outdoor": state.indoor_outdoor,
        }
        result, courts = run_search_availability(args)
        state.record_search_results(courts)
        return InternalToolCall("search_availability", args, result)
    if step.key == "call_book_court":
        args = {
            "court_id": state.selected_court_id,
            "date": state.date,
            "time": state.selected_time,
            "duration_minutes": state.duration_minutes,
            "num_players": state.num_players,
            "skill_level": state.skill_level,
            "equipment_rental": state.equipment_rental,
            "contact_name": state.contact_name,
            "contact_email": state.contact_email,
        }
        result = run_book_court(args)
        state.booking_confirmed = True
        state.confirmation_id = result["confirmation_id"]
        return InternalToolCall("book_court", args, result)
    raise AssertionError(f"unhandled tool-action step: {step.key}")


def step_payload(state: BookingState, step: Step) -> dict:
    """The instruction text alone isn't enough for some steps -- agent-1
    never sees search_availability's or book_court's raw results (only the
    engine calls those), so whatever data its instruction refers to has to
    be embedded here explicitly, or agent-1 would have nothing real to
    relay to the user (or would have to invent it). Shared by both engines
    -- this is response shaping, not step computation.
    """
    payload = {"step": step.key, "instruction": step.instruction}

    if step.chainable:
        upcoming = []
        for later in STEPS[STEPS.index(step) + 1 :]:
            if not later.chainable:
                break  # next branching/data-dependent step -- run ends here
            if any(getattr(state, slot) in (None, "") for slot in later.slot_names):
                upcoming.append({"step": later.key, "instruction": later.instruction})
            # else: already answered (e.g. via forward-fill) -- omit but
            # keep scanning, this doesn't end the chainable run.
        if upcoming:
            payload["upcoming_instructions"] = upcoming

    if step.key == "ask_time":
        payload["available_courts"] = [
            {
                "court_id": c.court_id,
                "name": c.name,
                "surface": c.surface,
                "indoor_outdoor": c.indoor_outdoor,
                "open_times": [{"time": s.time, "price_usd": s.price_usd} for s in c.slots],
            }
            for c in state.available_courts
        ]
        if not payload["available_courts"]:
            # A legitimate zero-result search (see search_has_run) --
            # without this note agent-1 has no way to tell a genuine
            # "nothing matched" from an empty response it should treat as
            # an error, and no path out except waiting for the user to say
            # something with a correction cue that changes a search input.
            payload["note"] = (
                "No courts matched those preferences. Tell the user plainly, and ask if "
                "they'd like to try a different area, surface, or indoor/outdoor preference "
                "-- relay whichever they choose as a labeled field (e.g. \"surface: clay\")."
            )
    elif step.key == "confirm_booking":
        court_name = next(
            (c.name for c in state.available_courts if c.court_id == state.selected_court_id),
            state.selected_court_id,
        )
        payload["booking_summary"] = {
            "court_name": court_name,
            "area": state.area,
            "date": state.date,
            "time": state.selected_time,
            "surface": state.surface,
            "duration_minutes": state.duration_minutes,
            "num_players": state.num_players,
            "skill_level": state.skill_level,
            "equipment_rental": state.equipment_rental,
            "contact_name": state.contact_name,
            "contact_email": state.contact_email,
        }
    elif step.key == "close_out":
        payload["confirmation_id"] = state.confirmation_id
        payload["date"] = state.date
        payload["time"] = state.selected_time

    return payload


def handle_labeled_batch(
    state: BookingState,
    segments: list[tuple[str, str]],
    advance: Callable[[], Step | None],
) -> dict:
    """Apply one or more labeled (label, value) pairs in a single call --
    any mix of a correction to an earlier already-answered field, an answer
    to the currently active step, and a forward-fill of a step nobody has
    reached yet. This is what lets agent-1 report an entire bulk-dumped
    user message (e.g. "any surface is fine, indoor or outdoor doesn't
    matter, we're 4 players for 90 minutes") in ONE round trip instead of
    one round trip per field.

    `advance` is the caller's step-computation engine (HandRolledStepEngine's
    hand-rolled scan, or TransitionsStepEngine's transitions.Machine) -- passed in
    as a callback rather than this function calling a method on either
    class, which is what lets this logic be shared without either engine
    inheriting from the other.

    Fields are applied in WORKFLOW order (not the order they appeared in
    the payload), so e.g. a time bundled together with the search-input
    fields in the same call lands only after search_availability has
    actually auto-executed for those inputs -- `advance` runs after every
    field, so a later field in the batch always sees the state a prior one
    just produced.

    One field failing to extract (a bad value, a duplicate label, or any
    label at all once the booking is already confirmed) doesn't abort the
    others -- each is applied or rejected independently, and both outcomes
    are reported back (`applied` / `errors`) so agent-1 knows exactly what
    landed.
    """
    labels_seen = [label for label, _ in segments]
    duplicate_labels = {label for label in labels_seen if labels_seen.count(label) > 1}

    errors: dict = {
        label: f"'{label}' was named more than once in that message -- resend it once, with just one value."
        for label in duplicate_labels
    }

    # A duplicate label is fully ambiguous -- which of its values did the
    # user actually mean? -- so neither is applied, not just the second.
    resolved: list[tuple[Step, str, str]] = [
        (_STEP_BY_KEY[FIELD_LABELS[label]], label, value)
        for label, value in segments
        if label not in duplicate_labels
    ]

    # Process in workflow order so tool-action steps (search_availability,
    # eventually call_book_court) fire at exactly the right point relative
    # to the other fields in this same batch.
    resolved.sort(key=lambda item: STEPS.index(item[0]))

    applied: dict = {}

    for target_step, label, value in resolved:
        if state.booking_confirmed:
            errors[label] = "This booking is already confirmed and can't be changed through this tool."
            continue
        extractor = STEP_EXTRACTORS.get(target_step.key)
        if extractor is None:
            errors[label] = f"'{target_step.key}' cannot be set this way."
            continue
        ok, fields, error = extractor(value, state)
        if not ok:
            errors[label] = error
            continue
        changed = {name: val for name, val in fields.items() if getattr(state, name) != val}
        for field_name, val in changed.items():
            apply_field_change(state, field_name, val)
        applied.update(changed)
        advance()

    next_step = advance()
    response = {"workflow_complete": True} if next_step is None else step_payload(state, next_step)
    if applied:
        response["applied"] = applied
    if errors:
        response["errors"] = errors
    return response


def handle(
    state: BookingState,
    payload: str,
    called_before: bool,
    advance: Callable[[], Step | None],
) -> tuple[dict, bool]:
    """The shared body of `HandRolledStepEngine.handle` / `TransitionsStepEngine.handle`:
    `payload` is unstructured free text -- either empty (a bootstrap call:
    "just tell me what to ask first"), a single unlabeled value answering
    the current step, or one or more "<label>: <value>" fields covering any
    mix of earlier, current, or not-yet-reached steps in one call.

    `advance` is the caller's step-computation engine, threaded through the
    same way as `handle_labeled_batch` -- see its docstring. `called_before`
    is the caller's own `_called_before` flag; returned (possibly flipped)
    as the second element of the result tuple so the caller can persist it
    without this function needing to mutate caller state directly.
    """
    payload = (payload or "").strip()
    step = advance()

    if step is None:
        return {"workflow_complete": True}, called_before

    if not payload:
        # Empty is only meaningful as the very first call of the whole
        # conversation ("just tell me what to ask first"). A later empty
        # call reports nothing -- silently re-showing the same step would
        # look like progress was made when it wasn't (live-reproduced:
        # agent-1 sent "" instead of a real "confirm" at confirm_booking,
        # got the same booking_summary back, and then narrated a fabricated
        # confirmation the tool never gave it). An explicit error forces a
        # real retry instead.
        if called_before:
            return (
                {
                    "error": (
                        "Empty payload -- this only bootstraps the very first call of a "
                        "conversation. Resend the user's actual answer to the current step."
                    ),
                    "step": step.key,
                    "instruction": step.instruction,
                },
                called_before,
            )
        return step_payload(state, step), True

    segments = parse_labeled_segments(payload)
    if segments is not None:
        return handle_labeled_batch(state, segments, advance), True

    extractor = STEP_EXTRACTORS.get(step.key)
    if extractor is not None:
        ok, fields, error = extractor(payload, state)
        if not ok:
            return {"error": error, "step": step.key, "instruction": step.instruction}, True
        for field_name, value in fields.items():
            setattr(state, field_name, value)
        step = advance()
        if step is None:
            return {"workflow_complete": True}, True

    return step_payload(state, step), True
