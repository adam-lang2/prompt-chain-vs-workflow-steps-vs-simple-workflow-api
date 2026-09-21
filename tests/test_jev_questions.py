"""Tests for jev question building."""
from __future__ import annotations

from datetime import datetime, timedelta

from tennis_booking.jev.questions import build_questions
from tennis_booking.models import CourtAvailability, TimeSlot
from tennis_booking.workflow_engine.agent import (
    _INDOOR_OUTDOOR,
    _SKILL_LEVELS,
    _SURFACES,
)
from tennis_booking.workflow_engine.state import BookingState


def test_build_questions_vocabulary_matches_surfaces():
    """Surface vocabulary in questions should match engine's _SURFACES."""
    state = BookingState()
    questions = build_questions(state)

    surface_q = questions.get("surface")
    assert surface_q is not None
    surface_options = set(surface_q.criteria.keys()) - {"not_mentioned"}
    assert surface_options == _SURFACES


def test_build_questions_vocabulary_matches_indoor_outdoor():
    """Indoor/outdoor vocabulary should match engine's _INDOOR_OUTDOOR."""
    state = BookingState()
    questions = build_questions(state)

    io_q = questions.get("indoor_outdoor")
    assert io_q is not None
    io_options = set(io_q.criteria.keys()) - {"not_mentioned"}
    assert io_options == _INDOOR_OUTDOOR


def test_build_questions_vocabulary_matches_skill_levels():
    """Skill level vocabulary should match engine's _SKILL_LEVELS."""
    state = BookingState()
    questions = build_questions(state)

    skill_q = questions.get("skill_level")
    assert skill_q is not None
    skill_options = set(skill_q.criteria.keys()) - {"not_mentioned"}
    assert skill_options == _SKILL_LEVELS


def test_build_questions_duration_options():
    """Duration should offer 60, 90, 120 + not_mentioned."""
    state = BookingState()
    questions = build_questions(state)

    duration_q = questions.get("duration_minutes")
    assert duration_q is not None
    assert set(duration_q.criteria.keys()) == {"60", "90", "120", "not_mentioned"}


def test_build_questions_num_players_options():
    """Num players should offer 2, 4 + not_mentioned."""
    state = BookingState()
    questions = build_questions(state)

    players_q = questions.get("num_players")
    assert players_q is not None
    assert set(players_q.criteria.keys()) == {"2", "4", "not_mentioned"}


def test_build_questions_equipment_rental_options():
    """Equipment rental should offer yes, no + not_mentioned."""
    state = BookingState()
    questions = build_questions(state)

    equip_q = questions.get("equipment_rental")
    assert equip_q is not None
    assert set(equip_q.criteria.keys()) == {"yes", "no", "not_mentioned"}


def test_build_questions_date_covers_14_days():
    """Date options should cover next 14 days + not_mentioned."""
    state = BookingState()
    questions = build_questions(state)

    date_q = questions.get("date")
    assert date_q is not None
    options = set(date_q.criteria.keys())
    assert "not_mentioned" in options
    assert len(options) == 15  # 14 days + not_mentioned


def test_build_questions_time_from_available_courts():
    """Time options should come from available_courts when populated."""
    state = BookingState()
    state.available_courts = [
        CourtAvailability(
            court_id="c1",
            name="Downtown Court",
            area="downtown",
            surface="hard",
            indoor_outdoor="outdoor",
            slots=[
                TimeSlot(time="09:00", price_usd=30.0),
                TimeSlot(time="10:00", price_usd=30.0),
            ],
        ),
        CourtAvailability(
            court_id="c2",
            name="Park Court",
            area="park",
            surface="clay",
            indoor_outdoor="outdoor",
            slots=[TimeSlot(time="14:00", price_usd=25.0)],
        ),
    ]

    questions = build_questions(state)

    time_q = questions.get("selected_time")
    assert time_q is not None
    options = set(time_q.criteria.keys())
    assert "09:00" in options
    assert "10:00" in options
    assert "14:00" in options
    assert "not_mentioned" in options


def test_build_questions_court_hint_from_names():
    """Court hint should offer court names from available_courts."""
    state = BookingState()
    state.available_courts = [
        CourtAvailability(
            court_id="c1",
            name="Downtown Court",
            area="downtown",
            surface="hard",
            indoor_outdoor="outdoor",
            slots=[TimeSlot(time="09:00", price_usd=30.0)],
        ),
        CourtAvailability(
            court_id="c2",
            name="Park Court",
            area="park",
            surface="clay",
            indoor_outdoor="outdoor",
            slots=[TimeSlot(time="14:00", price_usd=25.0)],
        ),
    ]

    questions = build_questions(state)

    court_q = questions.get("court_hint")
    assert court_q is not None
    options = set(court_q.criteria.keys())
    assert "Downtown Court" in options
    assert "Park Court" in options
    assert "not_mentioned" in options


def test_build_questions_asks_filled_slots_so_corrections_work():
    state = BookingState(surface="hard", duration_minutes=90, num_players=4)
    questions = build_questions(state)
    assert {"surface", "duration_minutes", "num_players"} <= set(questions)


def test_build_questions_span_questions_index_the_user_tokens():
    tokens = ["near", "Golden", "Gate", "Park"]
    questions = build_questions(BookingState(), tokens)
    for name in ("area_start", "area_end", "contact_name_start", "contact_name_end"):
        assert set(questions[name].criteria) == {"0", "1", "2", "3", "not_mentioned"}


def test_interpreter_slices_span_and_regexes_email():
    from types import SimpleNamespace as NS
    from tennis_booking.jev.interpreter import JevInterpreter

    def ans(choice, conf=0.9):
        return NS(choice=choice, confidence=conf)

    class FakeClient:
        def system_one(self, state, questions):
            return NS(
                choices={"act": ans("answers_current"), "area_start": ans("1"), "area_end": ans("3", 0.8)},
                usage=None,
            )

    interp = JevInterpreter(client=FakeClient()).interpret(
        BookingState(), "Where?", "near Golden Gate Park. mail me at a.b@example.com"
    )
    assert interp.slots["area"] == ("Golden Gate Park", 0.8)
    assert interp.slots["contact_email"] == ("a.b@example.com", 1.0)



def test_interpreter_extracts_explicit_iso_date_beyond_offered_window():
    from types import SimpleNamespace as NS
    from tennis_booking.jev.interpreter import JevInterpreter

    class FakeClient:
        def system_one(self, state, questions):
            return NS(choices={"act": NS(choice="answers_current", confidence=0.9)}, usage=None)

    interp = JevInterpreter(client=FakeClient()).interpret(BookingState(), "When?", "I want to play on 2026-09-05.")
    assert interp.slots["date"] == ("2026-09-05", 1.0)
