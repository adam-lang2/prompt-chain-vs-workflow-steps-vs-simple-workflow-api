"""Tests for jev apply logic."""
from __future__ import annotations

from tennis_booking.jev.apply import to_updates
from tennis_booking.jev.interpret import Interpretation
from tennis_booking.workflow_engine.state import BookingState


def test_to_updates_applies_high_confidence_slots():
    """Slots with confidence >= threshold should be applied."""
    interp = Interpretation(
        act="answers_current",
        act_confidence=0.9,
        slots={"area": ("downtown", 0.8), "date": ("2026-09-05", 0.7)},
        latency_ms=100.0,
    )
    state = BookingState()
    result = to_updates(interp, state, threshold=0.6)

    assert len(result.updates) == 2
    assert {"slot": "area", "value": "downtown"} in result.updates
    assert {"slot": "date", "value": "2026-09-05"} in result.updates
    assert result.restart is False


def test_to_updates_low_confidence_creates_ambiguity():
    """Slots with confidence < threshold should create ambiguities."""
    interp = Interpretation(
        act="answers_current",
        act_confidence=0.9,
        slots={"area": ("downtown", 0.5)},
        latency_ms=100.0,
    )
    state = BookingState()
    result = to_updates(interp, state, threshold=0.6)

    assert len(result.updates) == 0
    assert len(result.ambiguities) == 1
    assert "area" in result.ambiguities[0]


def test_to_updates_restart():
    """restart_or_cancel act should set restart=True."""
    interp = Interpretation(
        act="restart_or_cancel",
        act_confidence=0.9,
        slots={},
        latency_ms=100.0,
    )
    state = BookingState()
    result = to_updates(interp, state)

    assert result.restart is True
    assert len(result.updates) == 0


def test_to_updates_declines():
    """declines act should not create updates."""
    interp = Interpretation(
        act="declines",
        act_confidence=0.9,
        slots={},
        latency_ms=100.0,
    )
    state = BookingState()
    result = to_updates(interp, state)

    assert len(result.updates) == 0
    assert result.restart is False


def test_to_updates_coerces_equipment_rental():
    """equipment_rental yes/no should be coerced to bool."""
    interp = Interpretation(
        act="answers_current",
        act_confidence=0.9,
        slots={"equipment_rental": ("yes", 0.8)},
        latency_ms=100.0,
    )
    state = BookingState()
    result = to_updates(interp, state)

    assert len(result.updates) == 1
    assert result.updates[0]["slot"] == "equipment_rental"
    assert result.updates[0]["value"] is True


def test_to_updates_coerces_duration_minutes():
    """duration_minutes string should be coerced to int."""
    interp = Interpretation(
        act="answers_current",
        act_confidence=0.9,
        slots={"duration_minutes": ("90", 0.8)},
        latency_ms=100.0,
    )
    state = BookingState()
    result = to_updates(interp, state)

    assert len(result.updates) == 1
    assert result.updates[0]["slot"] == "duration_minutes"
    assert result.updates[0]["value"] == 90
    assert isinstance(result.updates[0]["value"], int)


def test_to_updates_coerces_num_players():
    """num_players string should be coerced to int."""
    interp = Interpretation(
        act="answers_current",
        act_confidence=0.9,
        slots={"num_players": ("4", 0.8)},
        latency_ms=100.0,
    )
    state = BookingState()
    result = to_updates(interp, state)

    assert len(result.updates) == 1
    assert result.updates[0]["slot"] == "num_players"
    assert result.updates[0]["value"] == 4
    assert isinstance(result.updates[0]["value"], int)


def test_confirm_only_at_confirm_booking_node():
    interp = Interpretation(act="confirms", act_confidence=0.9, slots={}, latency_ms=0.0)
    assert to_updates(interp, BookingState(), current_node="ask_area").updates == []
    assert {"slot": "confirmed", "value": True} in to_updates(
        interp, BookingState(), current_node="confirm_booking"
    ).updates
