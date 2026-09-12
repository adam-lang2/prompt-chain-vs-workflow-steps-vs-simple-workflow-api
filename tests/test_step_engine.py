"""Unit tests for `FSMAgent` -- the non-LLM step machine behind
`agents/simple_workflow_api_agent.py` (`book_tennis_court`'s `{"updates": [...]}`
schema). Pure Python, no LLM calls, no API key needed.

This is the only place `LangGraphStepEngine`'s step computation
(`step_engine_langgraph.py`) and the domain logic in `step_engine_shared.py`
(`step_is_current`, `execute_tool_action`, `step_payload`,
`FIELD_DEPENDENTS`) get exercised directly, rather than through the fake
Chat-Completions wiring in `test_agent_wiring.py` (which only smoke-tests
that a tool call reaches `FSMAgent.handle` at all, not the workflow logic
itself).
"""
from __future__ import annotations

from tennis_booking.workflow_engine import FSMAgent
from tennis_booking.workflow_steps import STEPS

_INSTRUCTION_BY_KEY = {s.key: s.instruction for s in STEPS}


def _update(slot: str, value) -> dict:
    return {"updates": [{"slot": slot, "value": value}]}


def _fill_through_indoor_outdoor(agent: FSMAgent) -> dict:
    agent.handle(_update("area", "downtown"))
    agent.handle(_update("date", "2026-09-05"))
    agent.handle(_update("surface", "clay"))
    agent.handle(_update("duration_minutes", 90))
    agent.handle(_update("num_players", 4))
    return agent.handle(_update("indoor_outdoor", "outdoor"))


def test_bootstrap_call_returns_first_step_without_error():
    agent = FSMAgent()
    result = agent.handle({})
    assert result["current_node"] == "ask_area"
    assert result["instructions"] == _INSTRUCTION_BY_KEY["ask_area"]


def test_empty_call_after_the_first_is_rejected_not_silently_replayed():
    # Regression: live-reproduced -- agent-1 once sent an empty call instead
    # of a real update at confirm_booking, got the same booking_summary back
    # unchanged, and then narrated a fabricated confirmation the tool never
    # actually gave it. A later empty call must surface as a clear error
    # instead of looking like a harmless no-op repeat of the current node.
    agent = FSMAgent()
    agent.handle({})  # legitimate bootstrap -- must NOT itself error
    result = agent.handle({})
    assert "error" in result
    assert result["current_node"] == "ask_area"
    assert not agent.state.area


def test_bootstrap_call_includes_upcoming_instructions_through_the_pre_search_run():
    # ask_area..ask_indoor_outdoor are all chainable (no branching, no
    # dependency on a prior tool-action's result) -- the whole run should be
    # handed back at once so agent-1 can ask them one at a time without
    # re-calling the tool just to learn what's next. search_availability
    # itself is a tool-action, not chainable, so the run stops there.
    agent = FSMAgent()
    result = agent.handle({})
    assert [s["current_node"] for s in result["upcoming_instructions"]] == [
        "ask_date",
        "ask_surface",
        "ask_duration",
        "ask_num_players",
        "ask_indoor_outdoor",
    ]
    for entry in result["upcoming_instructions"]:
        assert entry["instructions"] == _INSTRUCTION_BY_KEY[entry["current_node"]]


def test_upcoming_instructions_omits_already_answered_steps_but_keeps_scanning():
    # A forward-filled field mid-run shouldn't end the run early, just be
    # left out of the list -- it's already known, nothing left to ask.
    agent = FSMAgent()
    result = agent.handle(
        {"updates": [{"slot": "area", "value": "eastside"}, {"slot": "duration_minutes", "value": 90}]}
    )
    assert [s["current_node"] for s in result["upcoming_instructions"]] == [
        "ask_surface",
        "ask_num_players",
        "ask_indoor_outdoor",
    ]


def test_upcoming_instructions_absent_for_a_non_chainable_step():
    # ask_time depends on real search results and confirm_booking branches
    # on the user's answer -- neither should advertise a further run.
    agent = FSMAgent()
    agent.handle(
        {
            "updates": [
                {"slot": "area", "value": "downtown"},
                {"slot": "date", "value": "2026-09-05"},
                {"slot": "surface", "value": "clay"},
                {"slot": "duration_minutes", "value": 90},
                {"slot": "num_players", "value": 4},
                {"slot": "indoor_outdoor", "value": "outdoor"},
                {"slot": "skill_level", "value": "intermediate"},  # forward-fill past ask_time
            ]
        }
    )
    result = agent.handle({})
    assert result["current_node"] == "ask_time"
    assert "upcoming_instructions" not in result


def test_unrecognized_slot_is_rejected():
    agent = FSMAgent()
    result = agent.handle(_update("favorite_color", "blue"))
    assert "favorite_color" in result.get("errors", {})
    assert result["current_node"] == "ask_area"


def test_bad_value_returns_error_without_advancing():
    agent = FSMAgent()
    result = agent.handle(_update("date", "next Saturday"))  # not ISO
    assert "date" in result.get("errors", {})
    assert result["current_node"] == "ask_area"
    assert agent.state.date is None


def test_valid_value_advances():
    agent = FSMAgent()
    result = agent.handle(_update("area", "downtown"))
    assert result["current_node"] == "ask_date"
    assert agent.state.area == "downtown"


def test_search_availability_auto_executes_and_returns_ask_time():
    agent = FSMAgent()
    result = _fill_through_indoor_outdoor(agent)
    assert result["current_node"] == "ask_time"
    assert agent.state.availability_searched()
    assert len(agent.internal_tool_calls) == 1
    assert agent.internal_tool_calls[0].name == "search_availability"


def test_ask_time_response_embeds_real_availability_data():
    # Agent-1 never calls search_availability itself (only FSMAgent does,
    # internally) -- so unless the real courts/times are embedded in this
    # response, agent-1 would have nothing to relay to the user except
    # invented options.
    agent = FSMAgent()
    result = _fill_through_indoor_outdoor(agent)
    assert "available_courts" in result
    assert result["available_courts"] == [
        {
            "court_id": c.court_id,
            "name": c.name,
            "surface": c.surface,
            "indoor_outdoor": c.indoor_outdoor,
            "address": c.address,
            "rating": c.rating,
            "distance_km": c.distance_km,
            "open_times": [{"time": s.time, "price_usd": s.price_usd} for s in c.slots],
        }
        for c in agent.state.available_courts
    ]
    assert result["available_courts"]  # non-empty for this scenario
    assert "note" not in result


def test_ask_time_response_notes_zero_results_instead_of_looping():
    # downtown has no grass courts (see mock_courts.COURT_DIRECTORY) -- a
    # real, known area with a real preference combination that just
    # happens to match nothing.
    agent = FSMAgent()
    agent.handle(_update("area", "downtown"))
    agent.handle(_update("date", "2026-09-05"))
    agent.handle(_update("surface", "grass"))
    agent.handle(_update("duration_minutes", 90))
    agent.handle(_update("num_players", 4))

    result = agent.handle(_update("indoor_outdoor", "outdoor"))  # triggers search_availability -- zero matches

    assert agent.state.availability_searched()
    assert result["current_node"] == "ask_time"
    assert result["available_courts"] == []
    assert "note" in result
    assert len(agent.internal_tool_calls) == 1  # searched exactly once, not looping


def test_selected_time_matches_against_real_search_results():
    agent = FSMAgent()
    _fill_through_indoor_outdoor(agent)
    open_time = agent.state.available_courts[0].slots[0].time

    result = agent.handle(_update("selected_time", open_time))

    assert result["current_node"] == "ask_skill_level"
    assert agent.state.selected_time == open_time
    assert agent.state.selected_court_id == agent.state.available_courts[0].court_id


def test_court_hint_disambiguates_when_two_courts_share_a_time():
    # Regression (free-text-era equivalent): a user describing the court by
    # surface instead of naming it must not silently fall through to "any
    # court with this open time," which can pick the WRONG court whenever
    # two courts share a slot.
    agent = FSMAgent()
    agent.handle(_update("area", "northpark"))
    agent.handle(_update("date", "2026-09-19"))
    agent.handle(_update("surface", "any"))
    agent.handle(_update("duration_minutes", 90))
    agent.handle(_update("num_players", 4))
    agent.handle(_update("indoor_outdoor", "either"))
    courts_by_surface = {c.surface: c for c in agent.state.available_courts}
    assert "hard" in courts_by_surface and "grass" in courts_by_surface
    shared_time = next(
        s.time for s in courts_by_surface["hard"].slots if s.time in {t.time for t in courts_by_surface["grass"].slots}
    )

    result = agent.handle(
        {"updates": [{"slot": "selected_time", "value": shared_time}, {"slot": "court_hint", "value": "grass"}]}
    )

    assert result["current_node"] == "ask_skill_level"
    assert agent.state.selected_court_id == courts_by_surface["grass"].court_id
    assert agent.state.selected_time == shared_time


def test_court_hint_without_selected_time_in_the_same_call_is_rejected():
    agent = FSMAgent()
    _fill_through_indoor_outdoor(agent)

    result = agent.handle(_update("court_hint", "grass"))

    assert "court_hint" in result.get("errors", {})
    assert agent.state.selected_time is None


def test_selected_time_rejects_a_time_not_actually_open():
    agent = FSMAgent()
    _fill_through_indoor_outdoor(agent)

    result = agent.handle(_update("selected_time", "03:17"))  # not a real slot time

    assert "selected_time" in result.get("errors", {})
    assert agent.state.selected_time is None


def _finish_to_confirm_booking(agent: FSMAgent) -> dict:
    _fill_through_indoor_outdoor(agent)
    open_time = agent.state.available_courts[0].slots[0].time
    agent.handle(_update("selected_time", open_time))
    agent.handle(_update("skill_level", "intermediate"))
    agent.handle(_update("equipment_rental", False))
    agent.handle(_update("contact_name", "Jordan Lee"))
    return agent.handle(_update("contact_email", "jordan.lee@example.com"))


def test_confirm_booking_response_embeds_full_summary():
    agent = FSMAgent()
    result = _finish_to_confirm_booking(agent)
    open_time = agent.state.selected_time

    assert result["current_node"] == "confirm_booking"
    summary = result["booking_summary"]
    assert summary["time"] == open_time
    assert summary["skill_level"] == "intermediate"
    assert summary["equipment_rental"] is False
    assert summary["contact_name"] == "Jordan Lee"
    assert summary["contact_email"] == "jordan.lee@example.com"
    # book_court hasn't been called yet -- only search_availability has run
    # so far, since confirm_booking is reached before the user confirms.
    assert [c.name for c in agent.internal_tool_calls] == ["search_availability"]


def test_confirmed_false_rejects_without_booking():
    agent = FSMAgent()
    _finish_to_confirm_booking(agent)

    result = agent.handle(_update("confirmed", False))

    assert "confirmed" in result.get("errors", {})
    assert not agent.state.booking_confirmed
    assert not agent.state.summary_confirmed


def test_confirmed_before_ready_to_book_is_rejected():
    agent = FSMAgent()
    result = agent.handle(_update("confirmed", True))
    assert "confirmed" in result.get("errors", {})


def test_full_conversation_reaches_close_out():
    agent = FSMAgent()
    _finish_to_confirm_booking(agent)
    open_time = agent.state.selected_time

    result = agent.handle(_update("confirmed", True))

    assert result["current_node"] == "close_out"
    assert agent.state.booking_confirmed
    assert agent.state.confirmation_id is not None
    assert result["confirmation_id"] == agent.state.confirmation_id
    assert result["date"] == "2026-09-05"
    assert result["time"] == open_time

    tool_names = [c.name for c in agent.internal_tool_calls]
    assert tool_names == ["search_availability", "book_court", "send_confirmation"]
    book_call = agent.internal_tool_calls[-2]
    assert book_call.args["contact_name"] == "Jordan Lee"
    assert book_call.args["contact_email"] == "jordan.lee@example.com"
    assert book_call.args["skill_level"] == "intermediate"
    assert book_call.args["equipment_rental"] is False


# --- Corrections to already-answered fields ---------------------------------


def test_correction_before_first_search_is_applied_and_used_by_search():
    # Regression: a date correction arriving before the very first
    # search_availability call must not be silently dropped or shipped
    # stale.
    agent = FSMAgent()
    agent.handle(_update("area", "eastside"))
    agent.handle(_update("date", "2026-09-11"))
    agent.handle(_update("surface", "hard"))

    result = agent.handle(_update("date", "2026-09-12"))

    assert agent.state.date == "2026-09-12"
    assert result.get("applied") == {"date": "2026-09-12"}
    # No re-search has happened yet (num_players/indoor_outdoor still missing).
    assert result["current_node"] == "ask_duration"

    agent.handle(_update("duration_minutes", 60))
    agent.handle(_update("num_players", 2))
    agent.handle(_update("indoor_outdoor", "outdoor"))
    assert agent.state.availability_searched()
    search_call = agent.internal_tool_calls[0]
    assert search_call.name == "search_availability"
    assert search_call.args["date"] == "2026-09-12"


def test_correction_after_search_triggers_a_fresh_search():
    agent = FSMAgent()
    _fill_through_indoor_outdoor(agent)
    assert len(agent.internal_tool_calls) == 1  # first search has run
    open_time = agent.state.available_courts[0].slots[0].time
    agent.handle(_update("selected_time", open_time))
    assert agent.state.selected_time == open_time

    result = agent.handle(_update("date", "2026-09-06"))

    assert agent.state.date == "2026-09-06"
    # The stale selection must not survive a search-input correction.
    assert agent.state.selected_court_id is None
    assert agent.state.selected_time is None
    # step_is_current sees search_params_stale() and re-routes through
    # search_availability again automatically.
    assert result["current_node"] == "ask_time"
    assert len(agent.internal_tool_calls) == 2
    assert agent.internal_tool_calls[1].args["date"] == "2026-09-06"


def test_correction_to_leaf_field_does_not_reask_unrelated_fields():
    agent = FSMAgent()
    _finish_to_confirm_booking(agent)
    assert agent.state.area == "downtown"  # unaffected reference point

    result = agent.handle(_update("contact_name", "Jordan Smith"))

    assert agent.state.contact_name == "Jordan Smith"
    assert result.get("applied") == {"contact_name": "Jordan Smith"}
    # Nothing else was touched or needs re-asking -- straight to confirm_booking.
    assert result["current_node"] == "confirm_booking"
    assert agent.state.area == "downtown"
    assert agent.state.skill_level == "intermediate"


def test_multi_slot_update_applies_all_of_them_in_workflow_order():
    # A single call naming several different fields must apply ALL of them,
    # not just the first -- this is what lets agent-1 report a bulk-dumped
    # user message in one round trip instead of one call per field.
    agent = FSMAgent()
    agent.handle(_update("area", "northpark"))

    result = agent.handle(
        {
            "updates": [
                {"slot": "date", "value": "2026-09-19"},
                {"slot": "surface", "value": "any"},
                {"slot": "duration_minutes", "value": 90},
                {"slot": "num_players", "value": 4},
                {"slot": "indoor_outdoor", "value": "either"},
            ]
        }
    )

    assert agent.state.date == "2026-09-19"
    assert agent.state.surface == "any"
    assert agent.state.duration_minutes == 90
    assert agent.state.num_players == 4
    assert agent.state.indoor_outdoor == "either"
    assert result.get("applied") == {
        "date": "2026-09-19",
        "surface": "any",
        "duration_minutes": 90,
        "num_players": 4,
        "indoor_outdoor": "either",
    }
    # All six search inputs became known mid-batch -- search_availability
    # must have auto-fired already, landing straight on ask_time.
    assert result["current_node"] == "ask_time"
    assert "errors" not in result
    assert len(agent.internal_tool_calls) == 1
    assert agent.internal_tool_calls[0].name == "search_availability"


def test_multi_slot_update_can_forward_fill_a_step_not_yet_reached():
    agent = FSMAgent()
    agent.handle(_update("area", "eastside"))
    agent.handle(_update("date", "2026-09-11"))

    result = agent.handle(
        {"updates": [{"slot": "surface", "value": "hard"}, {"slot": "skill_level", "value": "advanced"}]}
    )

    assert agent.state.surface == "hard"
    assert agent.state.skill_level == "advanced"
    assert result.get("applied") == {"surface": "hard", "skill_level": "advanced"}
    # duration is still missing -- the forward-filled skill_level doesn't
    # skip ahead of it.
    assert result["current_node"] == "ask_duration"

    agent.handle(_update("duration_minutes", 90))
    agent.handle(_update("num_players", 4))
    step = agent.handle(_update("indoor_outdoor", "outdoor"))
    assert step["current_node"] == "ask_time"
    open_time = agent.state.available_courts[0].slots[0].time
    step = agent.handle(_update("selected_time", open_time))
    assert step["current_node"] == "ask_equipment_rental"  # skill_level already known
    assert agent.state.skill_level == "advanced"


def test_multi_slot_update_reports_partial_failure_without_dropping_successes():
    agent = FSMAgent()
    agent.handle(_update("area", "eastside"))
    agent.handle(_update("date", "2026-09-11"))

    result = agent.handle(
        {"updates": [{"slot": "surface", "value": "clay"}, {"slot": "duration_minutes", "value": 45}]}
    )  # 45 isn't a valid duration

    assert agent.state.surface == "clay"  # the valid field still applied
    assert agent.state.duration_minutes is None  # the invalid one did not
    assert result.get("applied") == {"surface": "clay"}
    assert "duration_minutes" in result.get("errors", {})
    assert result["current_node"] == "ask_duration"  # still the first unmet step


def test_duplicate_slot_in_one_call_is_rejected():
    agent = FSMAgent()
    agent.handle(_update("area", "eastside"))

    result = agent.handle({"updates": [{"slot": "date", "value": "2026-09-11"}, {"slot": "date", "value": "2026-09-12"}]})

    assert agent.state.date is None
    assert "date" in result.get("errors", {})
    assert result["current_node"] == "ask_date"


def test_empty_string_value_is_rejected_instead_of_clearing_the_slot():
    agent = FSMAgent()
    agent.handle(_update("area", "eastside"))

    result = agent.handle(_update("date", ""))

    assert agent.state.date is None
    assert "date" in result.get("errors", {})


def test_correction_rejected_after_booking_confirmed():
    agent = FSMAgent()
    _finish_to_confirm_booking(agent)
    agent.handle(_update("confirmed", True))
    assert agent.state.booking_confirmed

    result = agent.handle(_update("date", "2026-09-06"))

    assert "date" in result.get("errors", {})
    assert agent.state.date == "2026-09-05"


def test_correction_matching_the_current_stored_value_is_a_no_op():
    agent = FSMAgent()
    agent.handle(_update("area", "eastside"))
    agent.handle(_update("date", "2026-09-11"))
    agent.handle(_update("surface", "hard"))

    # Same date as already stored -- not a real change, applies cleanly and
    # falls through to the still-unmet current step (duration).
    result = agent.handle(_update("date", "2026-09-11"))

    assert agent.state.date == "2026-09-11"
    assert "errors" not in result
    assert result.get("applied") == {"date": "2026-09-11"}
    assert result["current_node"] == "ask_duration"
