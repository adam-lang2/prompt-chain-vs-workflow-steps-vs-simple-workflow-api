"""Unit tests for the step engines' step machine + field extraction -- pure
Python, no LLM calls, no API key needed. This is the piece the
agent-to-agent-prompt-chain architecture depends on most heavily, since it's
the only architecture in the project extracting structured slot values from
free text without Claude's native tool-calling doing it.

Parametrized over HandRolledStepEngine (step_engine_handrolled.py),
TransitionsStepEngine (step_engine_transitions.py, transitions.Machine-backed),
and LangGraphStepEngine (step_engine_langgraph.py, langgraph.graph.StateGraph-backed
-- the engine FSMAgent/book_tennis_court_v4 itself subclasses) via the
`agent_cls` fixture -- same grammar, same responses, same STEPS for all
three, only the step-computation engine differs, so every test body runs
unchanged against all of them, no duplicated assertions.
"""
from __future__ import annotations

import pytest

from tennis_booking.fsm_agent.step_engine_handrolled import HandRolledStepEngine
from tennis_booking.fsm_agent.step_engine_langgraph import LangGraphStepEngine
from tennis_booking.fsm_agent.step_engine_transitions import TransitionsStepEngine
from tennis_booking.workflow_steps import STEPS

_INSTRUCTION_BY_KEY = {s.key: s.instruction for s in STEPS}


@pytest.fixture(params=[HandRolledStepEngine, TransitionsStepEngine, LangGraphStepEngine], ids=["v1", "v2", "v3"])
def agent_cls(request):
    return request.param


def test_bootstrap_call_returns_first_step_without_error(agent_cls):
    agent = agent_cls()
    result = agent.handle("")
    assert result["step"] == "ask_area"
    assert result["instruction"] == _INSTRUCTION_BY_KEY["ask_area"]


def test_empty_payload_after_the_first_call_is_rejected_not_silently_replayed(agent_cls):
    # Regression: live-reproduced -- agent-1 once sent "" instead of a real
    # "confirm" at confirm_booking, got the same booking_summary back
    # unchanged, and then narrated a fabricated confirmation the tool never
    # actually gave it. A later empty call must surface as a clear error
    # instead of looking like a harmless no-op repeat of the current step.
    agent = agent_cls()
    agent.handle("")  # legitimate bootstrap -- must NOT itself error
    result = agent.handle("")
    assert "error" in result
    assert result["step"] == "ask_area"
    assert not agent.state.area


def test_bootstrap_call_includes_upcoming_instructions_through_the_pre_search_run(agent_cls):
    # ask_area..ask_indoor_outdoor are all chainable (no branching, no
    # dependency on a prior tool-action's result) -- the whole run should be
    # handed back at once so agent-1 can ask them one at a time without
    # re-calling the tool just to learn what's next. search_availability
    # itself is a tool-action, not chainable, so the run stops there.
    agent = agent_cls()
    result = agent.handle("")
    assert [s["step"] for s in result["upcoming_instructions"]] == [
        "ask_date",
        "ask_surface",
        "ask_duration",
        "ask_num_players",
        "ask_indoor_outdoor",
    ]
    for entry in result["upcoming_instructions"]:
        assert entry["instruction"] == _INSTRUCTION_BY_KEY[entry["step"]]


def test_upcoming_instructions_omits_already_answered_steps_but_keeps_scanning(agent_cls):
    # A forward-filled field mid-run shouldn't end the run early, just be
    # left out of the list -- it's already known, nothing left to ask.
    agent = agent_cls()
    result = agent.handle("area: eastside; duration: 90")
    assert [s["step"] for s in result["upcoming_instructions"]] == [
        "ask_surface",
        "ask_num_players",
        "ask_indoor_outdoor",
    ]


def test_upcoming_instructions_absent_for_a_non_chainable_step(agent_cls):
    # ask_time depends on real search results and confirm_booking branches
    # on the user's answer -- neither should advertise a further run.
    agent = agent_cls()
    agent.handle(
        "area: downtown; date: 2026-09-05; surface: clay; duration: 90; "
        "players: 4; indoor_outdoor: outdoor"
    )
    result = agent.handle("skill_level: intermediate")  # forward-fill past ask_time
    assert result["step"] == "ask_time"
    assert "upcoming_instructions" not in result


def test_area_extraction_strips_leading_preposition(agent_cls):
    agent = agent_cls()
    result = agent.handle("somewhere in downtown")
    assert result["step"] == "ask_date"
    assert agent.state.area == "downtown"


def test_area_extraction_finds_known_area_inside_a_full_sentence(agent_cls):
    # Regression: agent-1 relays the user's raw opening message verbatim,
    # which often isn't just an area name -- the leading-preposition strip
    # alone doesn't help here since the sentence doesn't start with one, so
    # this needs the known-area gazetteer match to find "downtown" instead
    # of accepting the entire sentence as the area value.
    agent = agent_cls()
    result = agent.handle("Hi, I'd like to book a tennis court somewhere near downtown.")
    assert result["step"] == "ask_date"
    assert agent.state.area == "downtown"


def test_contact_name_extraction_strips_common_lead_ins(agent_cls):
    from tennis_booking.fsm_agent.step_engine_shared import _extract_contact_name

    agent = agent_cls()
    for payload, expected in [
        ("My name is Jordan Lee.", "Jordan Lee"),
        ("it's Priya Shah", "Priya Shah"),
        ("I'm Sam Okafor", "Sam Okafor"),
        ("Alex Rivera", "Alex Rivera"),
    ]:
        ok, fields, error = _extract_contact_name(payload, agent.state)
        assert ok, error
        assert fields["contact_name"] == expected


def test_contact_name_extraction_strips_a_bundled_trailing_email(agent_cls):
    # Regression: a name+email bundled in one message (e.g. "Sam Okafor,
    # sam.okafor@example.com") used to leave the email hanging off the end
    # of the extracted name, since the permissive fallback just accepted
    # whatever text remained after the lead-in phrase was stripped.
    from tennis_booking.fsm_agent.step_engine_shared import _extract_contact_name

    agent = agent_cls()
    for payload, expected in [
        ("Sam Okafor, sam.okafor@example.com.", "Sam Okafor"),
        ("Name's Priya Shah, email priya.shah@example.com.", "Priya Shah"),
        ("It's Jordan Lee and my email is jordan.lee@example.com", "Jordan Lee"),
    ]:
        ok, fields, error = _extract_contact_name(payload, agent.state)
        assert ok, error
        assert fields["contact_name"] == expected


def test_bad_date_returns_error_without_advancing(agent_cls):
    agent = agent_cls()
    agent.handle("downtown")
    result = agent.handle("next Saturday")  # not ISO -- should be rejected
    assert "error" in result
    assert result["step"] == "ask_date"
    assert agent.state.date is None


def test_iso_date_advances(agent_cls):
    agent = agent_cls()
    agent.handle("downtown")
    result = agent.handle("2026-09-05")
    assert result["step"] == "ask_surface"
    assert agent.state.date == "2026-09-05"


def _fill_through_indoor_outdoor(agent: HandRolledStepEngine) -> dict:
    agent.handle("downtown")
    agent.handle("2026-09-05")
    agent.handle("clay please")
    agent.handle("let's do 90 minutes")
    agent.handle("doubles")
    return agent.handle("outdoor")


def test_search_availability_auto_executes_and_returns_ask_time(agent_cls):
    agent = agent_cls()
    result = _fill_through_indoor_outdoor(agent)
    assert result["step"] == "ask_time"
    assert agent.state.availability_searched()
    assert len(agent.internal_tool_calls) == 1
    assert agent.internal_tool_calls[0].name == "search_availability"


def test_ask_time_response_embeds_real_availability_data(agent_cls):
    # Agent-1 never calls search_availability itself (only the regex-agent
    # does, internally) -- so unless the real courts/times are embedded in
    # this response, agent-1 would have nothing to relay to the user except
    # invented options, defeating the grounding guarantee every other
    # architecture gets for free from seeing the raw tool result.
    agent = agent_cls()
    result = _fill_through_indoor_outdoor(agent)
    assert "available_courts" in result
    assert result["available_courts"] == [
        {
            "court_id": c.court_id,
            "name": c.name,
            "surface": c.surface,
            "indoor_outdoor": c.indoor_outdoor,
            "open_times": [{"time": s.time, "price_usd": s.price_usd} for s in c.slots],
        }
        for c in agent.state.available_courts
    ]
    assert result["available_courts"]  # non-empty for this scenario
    assert "note" not in result


def test_ask_time_response_notes_zero_results_instead_of_looping(agent_cls):
    # downtown has no grass courts (see mock_courts.COURT_DIRECTORY) -- a
    # real, known area with a real preference combination that just
    # happens to match nothing, as opposed to an unserviceable area name.
    agent = agent_cls()
    agent.handle("downtown")
    agent.handle("2026-09-05")
    agent.handle("grass")
    agent.handle("90 minutes")
    agent.handle("4")

    result = agent.handle("outdoor")  # triggers search_availability -- zero matches

    assert agent.state.availability_searched()
    assert result["step"] == "ask_time"
    assert result["available_courts"] == []
    assert "note" in result
    assert len(agent.internal_tool_calls) == 1  # searched exactly once, not looping


def test_ask_time_matches_against_real_search_results(agent_cls):
    agent = agent_cls()
    _fill_through_indoor_outdoor(agent)
    court_name = agent.state.available_courts[0].name
    open_time = agent.state.available_courts[0].slots[0].time

    result = agent.handle(f"{court_name} at {open_time}")

    assert result["step"] == "ask_skill_level"
    assert agent.state.selected_time == open_time
    assert agent.state.selected_court_id == agent.state.available_courts[0].court_id


def test_ask_time_matches_court_by_surface_when_name_not_repeated(agent_cls):
    # Regression: a user describing the court by surface ("the grass court")
    # instead of repeating its actual name used to fall through to "any
    # court with this open time," silently picking the WRONG court whenever
    # two courts share a slot (verified live: booked the hard court when the
    # user explicitly asked for the grass one).
    agent = agent_cls()
    agent.handle("northpark")
    agent.handle("2026-09-19")
    agent.handle("any surface is fine")
    agent.handle("90 minutes")
    agent.handle("4 players")
    agent.handle("indoor or outdoor doesn't matter")
    courts_by_surface = {c.surface: c for c in agent.state.available_courts}
    assert "hard" in courts_by_surface and "grass" in courts_by_surface
    # Both courts are open at 14:00 -- the exact ambiguity that caused the bug.
    assert any(s.time == "14:00" for s in courts_by_surface["hard"].slots)
    assert any(s.time == "14:00" for s in courts_by_surface["grass"].slots)

    result = agent.handle("The grass court at 14:00 looks good.")

    assert result["step"] == "ask_skill_level"
    assert agent.state.selected_court_id == courts_by_surface["grass"].court_id
    assert agent.state.selected_time == "14:00"


def test_ask_time_rejects_a_time_not_actually_open(agent_cls):
    agent = agent_cls()
    _fill_through_indoor_outdoor(agent)

    result = agent.handle("03:17")  # not a real slot time

    assert "error" in result
    assert result["step"] == "ask_time"
    assert agent.state.selected_time is None


def test_full_conversation_reaches_close_out(agent_cls):
    agent = agent_cls()
    _fill_through_indoor_outdoor(agent)
    court_name = agent.state.available_courts[0].name
    open_time = agent.state.available_courts[0].slots[0].time

    agent.handle(f"{court_name} at {open_time}")
    agent.handle("intermediate")
    agent.handle("no thanks, I have my own racket")
    agent.handle("Jordan Lee")
    agent.handle("jordan.lee@example.com")
    result = agent.handle("yes, confirm and book it")

    # close_out is the workflow's terminal step -- like every other agent in
    # this project, the regex-agent hands it back once the booking is made,
    # and it's up to the calling agent to stop calling the tool after
    # delivering that message rather than waiting for a separate sentinel.
    assert result["step"] == "close_out"
    assert agent.state.booking_confirmed
    assert agent.state.confirmation_id is not None
    # Agent-1 never calls book_court itself, so the confirmation id has to
    # be handed back here or it would have nothing real to give the user.
    assert result["confirmation_id"] == agent.state.confirmation_id
    assert result["date"] == "2026-09-05"
    assert result["time"] == open_time

    tool_names = [c.name for c in agent.internal_tool_calls]
    assert tool_names == ["search_availability", "book_court"]
    book_call = agent.internal_tool_calls[-1]
    assert book_call.args["contact_name"] == "Jordan Lee"
    assert book_call.args["contact_email"] == "jordan.lee@example.com"
    assert book_call.args["skill_level"] == "intermediate"
    assert book_call.args["equipment_rental"] is False


def test_confirm_booking_response_embeds_full_summary(agent_cls):
    agent = agent_cls()
    _fill_through_indoor_outdoor(agent)
    court_name = agent.state.available_courts[0].name
    open_time = agent.state.available_courts[0].slots[0].time
    agent.handle(f"{court_name} at {open_time}")
    agent.handle("intermediate")
    agent.handle("no thanks, I have my own racket")
    agent.handle("Jordan Lee")

    result = agent.handle("jordan.lee@example.com")

    assert result["step"] == "confirm_booking"
    summary = result["booking_summary"]
    assert summary["court_name"] == court_name
    assert summary["time"] == open_time
    assert summary["skill_level"] == "intermediate"
    assert summary["equipment_rental"] is False
    assert summary["contact_name"] == "Jordan Lee"
    assert summary["contact_email"] == "jordan.lee@example.com"
    # book_court hasn't been called yet -- only search_availability has run
    # so far, since confirm_booking is reached before the user confirms.
    assert [c.name for c in agent.internal_tool_calls] == ["search_availability"]


def test_confirm_booking_rejects_non_affirmative_reply_without_booking(agent_cls):
    agent = agent_cls()
    _fill_through_indoor_outdoor(agent)
    court_name = agent.state.available_courts[0].name
    open_time = agent.state.available_courts[0].slots[0].time
    agent.handle(f"{court_name} at {open_time}")
    agent.handle("intermediate")
    agent.handle("no")
    agent.handle("Jordan Lee")
    agent.handle("jordan.lee@example.com")

    result = agent.handle("actually that's wrong")

    assert "error" in result
    assert result["step"] == "confirm_booking"
    assert not agent.state.booking_confirmed


def test_indoor_outdoor_doesnt_matter_maps_to_either(agent_cls):
    from tennis_booking.fsm_agent.step_engine_shared import _extract_indoor_outdoor

    state = agent_cls().state
    # Regression: this used to match the literal word "indoor" (checked
    # before "doesn't matter" was recognized as an "either" synonym) instead
    # of correctly reading the phrase as no-preference.
    ok, fields, error = _extract_indoor_outdoor("indoor or outdoor doesn't matter", state)
    assert ok, error
    assert fields == {"indoor_outdoor": "either"}


def test_indoor_outdoor_both_mentioned_without_either_synonym_still_means_either(agent_cls):
    from tennis_booking.fsm_agent.step_engine_shared import _extract_indoor_outdoor

    state = agent_cls().state
    ok, fields, error = _extract_indoor_outdoor("indoor or outdoor is fine", state)
    assert ok, error
    assert fields == {"indoor_outdoor": "either"}


def test_bad_surface_error_message_names_valid_options(agent_cls):
    agent = agent_cls()
    agent.handle("downtown")
    agent.handle("2026-09-05")

    result = agent.handle("something exotic")

    assert "error" in result
    assert "hard" in result["error"] and "clay" in result["error"]


def test_email_extraction_ignores_surrounding_text(agent_cls):
    agent = agent_cls()
    _fill_through_indoor_outdoor(agent)
    court_name = agent.state.available_courts[0].name
    open_time = agent.state.available_courts[0].slots[0].time
    agent.handle(f"{court_name} at {open_time}")
    agent.handle("intermediate")
    agent.handle("no")
    agent.handle("Jordan Lee")

    result = agent.handle("sure thing, it's jordan.lee@example.com, thanks")

    assert result["step"] == "confirm_booking"
    assert agent.state.contact_email == "jordan.lee@example.com"


def test_singles_doubles_keywords_map_to_player_count(agent_cls):
    agent = agent_cls()
    agent.handle("downtown")
    agent.handle("2026-09-05")
    agent.handle("clay")
    agent.handle("90 minutes")

    result = agent.handle("just singles for me")

    assert result["step"] == "ask_indoor_outdoor"


# --- Corrections to already-answered fields ---------------------------------


def test_correction_before_first_search_is_applied_and_used_by_search(agent_cls):
    # Regression: this is the exact live-reproduced bug -- a date correction
    # arriving while "ask_duration" is active (i.e. before the very first
    # search_availability call) used to be silently dropped, and the stale
    # original date shipped to search_availability instead.
    agent = agent_cls()
    agent.handle("eastside")
    agent.handle("2026-09-11")
    agent.handle("hard")

    result = agent.handle("date: 2026-09-12")

    assert agent.state.date == "2026-09-12"
    assert result.get("applied") == {"date": "2026-09-12"}
    # No re-search has happened yet (num_players/indoor_outdoor still missing),
    # so this shouldn't have jumped ahead -- just applied the correction.
    assert result["step"] == "ask_duration"

    # Finish the remaining pre-search questions and confirm the corrected
    # date -- not the stale original -- is what actually gets searched.
    agent.handle("60 minutes")
    agent.handle("2 players")
    agent.handle("outdoor")
    assert agent.state.availability_searched()
    search_call = agent.internal_tool_calls[0]
    assert search_call.name == "search_availability"
    assert search_call.args["date"] == "2026-09-12"


def test_correction_after_search_triggers_a_fresh_search(agent_cls):
    agent = agent_cls()
    agent.handle("downtown")
    agent.handle("2026-09-05")
    agent.handle("clay")
    agent.handle("90 minutes")
    agent.handle("4")
    agent.handle("outdoor")
    assert len(agent.internal_tool_calls) == 1  # first search has run
    court_name = agent.state.available_courts[0].name
    open_time = agent.state.available_courts[0].slots[0].time
    agent.handle(f"{court_name} at {open_time}")
    assert agent.state.selected_time == open_time

    result = agent.handle("actually, date: 2026-09-06")

    assert agent.state.date == "2026-09-06"
    # The stale selection must not survive a search-input correction.
    assert agent.state.selected_court_id is None
    assert agent.state.selected_time is None
    # next_step_for sees search_params_stale() and re-routes through
    # search_availability again automatically -- no special-case code needed
    # for this in the correction path itself.
    assert result["step"] == "ask_time"
    assert len(agent.internal_tool_calls) == 2
    assert agent.internal_tool_calls[1].args["date"] == "2026-09-06"


def test_correction_to_leaf_field_does_not_reask_unrelated_fields(agent_cls):
    agent = agent_cls()
    _fill_through_indoor_outdoor(agent)
    court_name = agent.state.available_courts[0].name
    open_time = agent.state.available_courts[0].slots[0].time
    agent.handle(f"{court_name} at {open_time}")
    agent.handle("intermediate")
    agent.handle("no")
    agent.handle("Jordan Lee")
    agent.handle("jordan.lee@example.com")
    assert agent.state.area == "downtown"  # unaffected reference point

    result = agent.handle("name: Jordan Smith")

    assert agent.state.contact_name == "Jordan Smith"
    assert result.get("applied") == {"contact_name": "Jordan Smith"}
    # Nothing else was touched or needs re-asking -- straight to confirm_booking.
    assert result["step"] == "confirm_booking"
    assert agent.state.area == "downtown"
    assert agent.state.skill_level == "intermediate"


def test_bare_value_resembling_an_earlier_field_is_not_treated_as_a_correction(agent_cls):
    agent = agent_cls()
    agent.handle("eastside")
    agent.handle("2026-09-11")
    agent.handle("hard")

    # No "<label>: <value>" tag at all -- a bare value that happens to look
    # like a date for an earlier field must NOT be guessed at; it should
    # fail as a bad duration, same as any other unrecognized current-step
    # answer. Only an explicit label routes a value to a non-current field.
    result = agent.handle("2026-09-12")

    assert agent.state.date == "2026-09-11"
    assert "error" in result
    assert result["step"] == "ask_duration"


def test_correction_phrasing_without_a_label_is_not_treated_as_a_correction(agent_cls):
    agent = agent_cls()
    agent.handle("eastside")
    agent.handle("2026-09-11")
    agent.handle("hard")

    # Correction-sounding phrasing ("wait, actually... instead of...") is
    # irrelevant on its own -- no explicit "<label>: <value>" tag is present,
    # so this must NOT be guessed at; it should fail as a bad duration, same
    # as any other unrecognized current-step answer.
    result = agent.handle("wait, actually let's do 2026-09-12 instead of the 11th")

    assert agent.state.date == "2026-09-11"
    assert "error" in result
    assert result["step"] == "ask_duration"


def test_correction_with_unrecognized_label_falls_through_to_current_step(agent_cls):
    agent = agent_cls()
    agent.handle("eastside")
    agent.handle("2026-09-11")
    agent.handle("hard")

    # "when" isn't in the fixed label vocabulary, so this isn't routed as a
    # correction at all -- falls through and fails as a bad duration.
    result = agent.handle("actually, when: 2026-09-12")

    assert agent.state.date == "2026-09-11"
    assert "error" in result
    assert result["step"] == "ask_duration"


def test_labeled_batch_applies_multiple_distinct_fields_in_one_call(agent_cls):
    # This is the core fix for the live-reproduced bulk-dump failure: a
    # single call naming several different fields must apply ALL of them,
    # not be rejected as "ambiguous" -- that's the whole point of letting
    # agent-1 report a bulk-dumped user message in one round trip instead of
    # one call per field.
    agent = agent_cls()
    agent.handle("northpark")

    result = agent.handle(
        "date: 2026-09-19; surface: any; duration: 90; players: 4; indoor_outdoor: either"
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
    assert result["step"] == "ask_time"
    assert "errors" not in result
    assert len(agent.internal_tool_calls) == 1
    assert agent.internal_tool_calls[0].name == "search_availability"


def test_labeled_batch_can_forward_fill_a_step_not_yet_reached(agent_cls):
    # The user answers skill_level before the workflow has even asked about
    # duration -- agent-1 should be able to tag and send it right away
    # rather than waiting for ask_skill_level to become active.
    agent = agent_cls()
    agent.handle("eastside")
    agent.handle("2026-09-11")

    result = agent.handle("surface: hard; skill_level: advanced")

    assert agent.state.surface == "hard"
    assert agent.state.skill_level == "advanced"
    assert result.get("applied") == {"surface": "hard", "skill_level": "advanced"}
    # duration is still missing -- the forward-filled skill_level doesn't
    # skip ahead of it.
    assert result["step"] == "ask_duration"

    # ...and once the workflow actually reaches ask_skill_level, it isn't
    # re-asked -- the already-applied value is used untouched.
    agent.handle("90 minutes")
    agent.handle("4 players")
    step = agent.handle("outdoor")
    assert step["step"] == "ask_time"
    open_time = agent.state.available_courts[0].slots[0].time
    court_name = agent.state.available_courts[0].name
    step = agent.handle(f"{court_name} at {open_time}")
    assert step["step"] == "ask_equipment_rental"  # skill_level already known
    assert agent.state.skill_level == "advanced"


def test_labeled_batch_reports_partial_failure_without_dropping_successes(agent_cls):
    agent = agent_cls()
    agent.handle("eastside")
    agent.handle("2026-09-11")

    result = agent.handle("surface: clay; duration: 45")  # 45 isn't a valid duration

    assert agent.state.surface == "clay"  # the valid field still applied
    assert agent.state.duration_minutes is None  # the invalid one did not
    assert result.get("applied") == {"surface": "clay"}
    assert "duration" in result.get("errors", {})
    assert result["step"] == "ask_duration"  # still the first unmet step


def test_labeled_batch_rejects_duplicate_label_in_one_call(agent_cls):
    agent = agent_cls()
    agent.handle("eastside")

    result = agent.handle("date: 2026-09-11; date: 2026-09-12")

    assert agent.state.date is None
    assert "date" in result.get("errors", {})
    assert result["step"] == "ask_date"


def test_correction_rejected_after_booking_confirmed(agent_cls):
    agent = agent_cls()
    _fill_through_indoor_outdoor(agent)
    court_name = agent.state.available_courts[0].name
    open_time = agent.state.available_courts[0].slots[0].time
    agent.handle(f"{court_name} at {open_time}")
    agent.handle("intermediate")
    agent.handle("no")
    agent.handle("Jordan Lee")
    agent.handle("jordan.lee@example.com")
    agent.handle("yes, confirm and book it")
    assert agent.state.booking_confirmed

    result = agent.handle("date: 2026-09-06")

    assert "date" in result.get("errors", {})
    assert agent.state.date == "2026-09-05"


def test_correction_matching_the_current_stored_value_is_a_no_op(agent_cls):
    agent = agent_cls()
    agent.handle("eastside")
    agent.handle("2026-09-11")
    agent.handle("hard")

    # Same date as already stored -- not a real change, applies cleanly to
    # nothing and falls through to the still-unmet current step (duration).
    result = agent.handle("date: 2026-09-11")

    assert agent.state.date == "2026-09-11"
    assert "errors" not in result
    assert result.get("applied") is None
    assert result["step"] == "ask_duration"
