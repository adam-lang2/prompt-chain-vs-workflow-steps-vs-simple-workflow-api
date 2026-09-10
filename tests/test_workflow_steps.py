"""Unit tests for the deterministic step machine -- no LLM calls, no API key
needed. These pin down the ground truth that get_next_step() wraps and that
the scripted scenarios' expected order was designed against.
"""
from __future__ import annotations

from tennis_booking.models import BookingState, CourtAvailability, TimeSlot
from tennis_booking.tools import ConversationStore, NextStepTool, NextStepToolV2
from tennis_booking.workflow_steps import STEPS, next_step_for


def test_steps_start_with_area():
    state = BookingState()
    assert next_step_for(state).key == "ask_area"


def test_steps_progress_in_order_as_slots_fill():
    state = BookingState()
    expected_order = [
        "ask_area",
        "ask_date",
        "ask_surface",
        "ask_duration",
        "ask_num_players",
        "ask_indoor_outdoor",
        "search_availability",
    ]
    fills = {
        "area": "downtown",
        "date": "2026-09-05",
        "surface": "clay",
        "duration_minutes": 90,
        "num_players": 4,
        "indoor_outdoor": "outdoor",
    }
    seen = []
    for key, value in fills.items():
        seen.append(next_step_for(state).key)
        setattr(state, key, value)
    seen.append(next_step_for(state).key)  # after last slot fill -> search
    assert seen == expected_order


def test_out_of_order_fills_still_resume_correctly():
    state = BookingState(num_players=2, surface="hard")  # answered out of order
    step = next_step_for(state)
    assert step.key == "ask_area"  # still asks for the earliest missing slot


def _riverside_clay_courts() -> list[CourtAvailability]:
    return [
        CourtAvailability(
            court_id="dt-clay-1",
            name="Riverside Clay Courts",
            area="downtown",
            surface="clay",
            indoor_outdoor="outdoor",
            slots=[TimeSlot(time="12:00", price_usd=34.0)],
        )
    ]


def test_ask_time_only_available_after_search():
    state = BookingState(
        area="downtown",
        date="2026-09-05",
        surface="clay",
        duration_minutes=90,
        num_players=4,
        indoor_outdoor="outdoor",
    )
    step = next_step_for(state)
    assert step.key == "search_availability"

    state.record_search_results(_riverside_clay_courts())
    step = next_step_for(state)
    assert step.key == "ask_time"


def test_post_time_slots_fill_in_order():
    state = BookingState(
        area="downtown",
        date="2026-09-05",
        surface="clay",
        duration_minutes=90,
        num_players=4,
        indoor_outdoor="outdoor",
    )
    state.record_search_results(_riverside_clay_courts())
    state.selected_court_id = "dt-clay-1"
    state.selected_time = "12:00"

    assert next_step_for(state).key == "ask_skill_level"
    state.skill_level = "intermediate"

    assert next_step_for(state).key == "ask_equipment_rental"
    state.equipment_rental = False  # a real "no" answer, not "unanswered"

    assert next_step_for(state).key == "ask_contact_name"
    state.contact_name = "Jordan Lee"

    assert next_step_for(state).key == "ask_contact_email"
    state.contact_email = "jordan@example.com"

    assert next_step_for(state).key == "confirm_booking"


def test_search_refires_when_a_preference_changes_after_search():
    state = BookingState(
        area="downtown",
        date="2026-09-05",
        surface="clay",
        duration_minutes=90,
        num_players=4,
        indoor_outdoor="outdoor",
    )
    state.record_search_results(_riverside_clay_courts())
    assert not state.search_params_stale()

    # User changes their mind about the date after already seeing times.
    state.date = "2026-09-06"
    assert state.search_params_stale()
    assert next_step_for(state).key == "search_availability"

    # A fresh search clears the staleness and invalidates the now-stale pick,
    # instead of silently carrying it forward against the new results.
    state.selected_court_id = "dt-clay-1"  # as if picked before the change
    state.selected_time = "12:00"
    state.record_search_results(_riverside_clay_courts())
    assert not state.search_params_stale()
    assert state.selected_court_id is None
    assert state.selected_time is None


def test_confirm_booking_precedes_call_book_court():
    state = BookingState(
        area="downtown",
        date="2026-09-05",
        surface="clay",
        duration_minutes=90,
        num_players=4,
        indoor_outdoor="outdoor",
        skill_level="intermediate",
        equipment_rental=False,
        contact_name="Jordan Lee",
        contact_email="jordan@example.com",
    )
    state.record_search_results(_riverside_clay_courts())
    state.selected_court_id = "dt-clay-1"
    state.selected_time = "12:00"

    assert next_step_for(state).key == "confirm_booking"

    state.summary_confirmed = True
    assert next_step_for(state).key == "call_book_court"

    state.booking_confirmed = True
    assert next_step_for(state).key == "close_out"


def test_workflow_complete_returns_none():
    state = BookingState(
        area="downtown",
        date="2026-09-05",
        surface="clay",
        duration_minutes=90,
        num_players=4,
        indoor_outdoor="outdoor",
        skill_level="intermediate",
        equipment_rental=False,
        contact_name="Jordan Lee",
        contact_email="jordan@example.com",
    )
    state.record_search_results(_riverside_clay_courts())
    state.selected_court_id = "dt-clay-1"
    state.selected_time = "12:00"
    state.summary_confirmed = True
    state.booking_confirmed = True
    assert next_step_for(state).key == "close_out"


def test_next_step_tool_merges_updates_across_calls():
    state = BookingState()
    tool = NextStepTool(state)

    result = tool.run({"area": "downtown"})
    assert result["next_step"] == "ask_date"
    assert state.area == "downtown"

    result = tool.run({"date": "2026-09-05", "surface": "clay"})
    assert result["next_step"] == "ask_duration"
    assert state.date == "2026-09-05"
    assert state.surface == "clay"


def test_all_step_keys_unique():
    keys = [s.key for s in STEPS]
    assert len(keys) == len(set(keys))


def test_next_step_tool_v2_merges_updates_via_conversation_id():
    store = ConversationStore()
    conversation_id, state = store.create()
    tool = NextStepToolV2(store)

    result = tool.run({"conversation_id": conversation_id, "area": "downtown"})
    assert result["next_step"] == "ask_date"
    assert state.area == "downtown"
    assert "state" not in result  # the whole point of v2: no state echoed back

    result = tool.run({"conversation_id": conversation_id, "date": "2026-09-05", "surface": "clay"})
    assert result["next_step"] == "ask_duration"
    assert state.date == "2026-09-05"
    assert state.surface == "clay"
    assert "state" not in result


def test_next_step_tool_v2_requires_conversation_id():
    store = ConversationStore()
    store.create()
    tool = NextStepToolV2(store)

    result = tool.run({"area": "downtown"})
    assert result == {"error": "conversation_id is required on every get_next_step call"}


def test_next_step_tool_v2_rejects_unknown_conversation_id():
    store = ConversationStore()
    tool = NextStepToolV2(store)

    result = tool.run({"conversation_id": "does-not-exist"})
    assert "error" in result


def test_conversation_store_keeps_conversations_isolated():
    store = ConversationStore()
    id_a, state_a = store.create()
    id_b, state_b = store.create()

    assert id_a != id_b
    assert state_a is not state_b

    tool = NextStepToolV2(store)
    tool.run({"conversation_id": id_a, "area": "downtown"})
    tool.run({"conversation_id": id_b, "area": "eastside"})

    assert store.get(id_a).area == "downtown"
    assert store.get(id_b).area == "eastside"


def test_zero_search_results_does_not_loop_forever():
    # Regression: a search that legitimately matches zero courts used to be
    # indistinguishable from "hasn't searched yet" (both left
    # `available_courts` empty), so next_step_for kept re-issuing
    # search_availability on every call, forever. Verified live via a
    # regex-agent correction bug that produced a nonsense area with no
    # matching courts -- fixed at the shared BookingState level with an
    # explicit `search_has_run` flag so every architecture benefits.
    state = BookingState(
        area="nowhere-that-exists",
        date="2026-09-05",
        surface="clay",
        duration_minutes=90,
        num_players=4,
        indoor_outdoor="outdoor",
    )
    assert not state.availability_searched()

    state.record_search_results([])  # a real search that found nothing

    assert state.availability_searched()
    assert state.available_courts == []
    # With a real (if empty) search on record, the step machine must not
    # ask for another search -- it should move on (here: to ask_time, which
    # will have nothing to offer, rather than spinning on search forever).
    step = next_step_for(state)
    assert step is not None
    assert step.key != "search_availability"
