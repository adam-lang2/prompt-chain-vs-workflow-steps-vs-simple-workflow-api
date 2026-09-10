"""Domain logic shared by every non-LLM step-computation engine in this
package -- currently just `LangGraphStepEngine` (`step_engine_langgraph.py`)
and its subclass `FSMAgent` (`agent.py`), but kept as free functions rather
than methods so a future step-computation engine could reuse the same
domain logic without inheriting from either.

Nothing in this module is "which step is current" logic (that's
`step_engine_langgraph.py`'s job) -- it's what happens once a step's slots
are known (`FIELD_DEPENDENTS`, `apply_field_change`'s cascading-reset rule),
what a tool-action step actually does (`execute_tool_action`), and what a
step's response looks like (`step_payload`).
"""
from __future__ import annotations

from dataclasses import dataclass

from tennis_booking.workflow_engine.state import SEARCH_INPUT_SLOTS, BookingState
from tennis_booking.workflow_steps import STEPS, Step

# run_book_court/run_search_availability are imported inside execute_tool_action,
# not here at module level: tools/__init__.py imports prompt_chain_get_next_step.py, which
# imports BookingState from tennis_booking.workflow_engine.state -- importing
# that submodule runs this package's __init__.py first, which reaches this
# module, which would otherwise import tennis_booking.tools while it's still
# mid-import.

# FIELD_DEPENDENTS models what depends on what, explicitly:
# - "search": the six search-input fields. Changing one doesn't need any
#   invalidation code here at all -- BookingState.search_params_stale()
#   already detects the mismatch against last_search_params, and the step
#   engine already re-triggers search_availability (which clears
#   available_courts/selected_court_id/selected_time via
#   record_search_results()) the next time it runs. Reusing that existing,
#   already-tested cascade instead of duplicating it is the point of routing
#   corrections through the normal step-computation flow.
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
    (`agents/simple_workflow_api_agent.py`) can fold these into `tool_call_log`
    alongside the `book_tennis_court` calls, keeping `scoring.py`'s shared
    scoring logic working unmodified across every architecture.
    """

    name: str
    args: dict
    result: dict


def step_is_current(step: Step, state: BookingState) -> bool:
    """Is `step` still unmet, given `state`? A near-verbatim port of
    `workflow_steps.next_step_for`'s per-step conditions, extracted into a
    standalone predicate so it can be used as a routing condition instead of
    a branch inside a scanning loop (see `step_engine_langgraph.py`'s
    `_route`).
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
    """Run search_availability / book_court as a side effect of the engine
    settling into one of those steps, mutating `state` in place. This is
    domain logic (what a tool-action step DOES), not step-computation logic
    (WHICH step is current), so it belongs here rather than in the engine
    itself."""
    from tennis_booking.tools import run_book_court, run_search_availability

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
    relay to the user (or would have to invent it).
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
            # something that changes a search input.
            payload["note"] = (
                "No courts matched those preferences. Tell the user plainly, and ask if "
                "they'd like to try a different area, surface, or indoor/outdoor preference."
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
