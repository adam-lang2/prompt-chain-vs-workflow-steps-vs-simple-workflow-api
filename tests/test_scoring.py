"""Unit tests for `scoring.score_conversation`'s field-matching rules -- no
LLM calls, no API key needed. Pins down the leniency `area` gets (it's free
text paraphrased from the user's own wording) versus the exact match every
other field still requires.
"""
from __future__ import annotations

from tennis_booking.agents.base import ToolCallRecord
from tennis_booking.scoring import score_conversation


def _search_call(**args) -> ToolCallRecord:
    return ToolCallRecord(turn=1, name="search_availability", args=args, result={"courts": []})


def _search_mismatches(score) -> list[str]:
    # `date` is a field name shared by EXPECTED_SEARCH_FIELDS and
    # EXPECTED_BOOK_FIELDS -- these tests never call book_court, so filter
    # out the resulting "book_court was never called" noise to isolate what
    # each test actually cares about: search_availability field matching.
    return [m for m in score.mismatches if m.startswith("search_availability")]


def test_area_matches_when_actual_is_a_superset_of_expected():
    # e.g. user says "somewhere near Golden Gate Park" -> agent passes
    # area="near Golden Gate Park", a faithful paraphrase, not a mistake.
    log = [_search_call(area="near Golden Gate Park", date="2026-09-05", surface="hard", indoor_outdoor="outdoor")]
    score = score_conversation(
        tool_call_log=log,
        expected={"area": "Golden Gate Park", "date": "2026-09-05", "surface": "hard", "indoor_outdoor": "outdoor"},
        num_turns=1,
    )
    assert _search_mismatches(score) == []


def test_area_matches_when_expected_is_a_superset_of_actual():
    log = [_search_call(area="Golden Gate", date="2026-09-05", surface="hard", indoor_outdoor="outdoor")]
    score = score_conversation(
        tool_call_log=log,
        expected={
            "area": "near Golden Gate Park",
            "date": "2026-09-05",
            "surface": "hard",
            "indoor_outdoor": "outdoor",
        },
        num_turns=1,
    )
    assert _search_mismatches(score) == []


def test_area_mismatch_still_flagged_when_unrelated():
    log = [_search_call(area="Prospect Park", date="2026-09-05", surface="hard", indoor_outdoor="outdoor")]
    score = score_conversation(
        tool_call_log=log,
        expected={"area": "Golden Gate Park", "date": "2026-09-05", "surface": "hard", "indoor_outdoor": "outdoor"},
        num_turns=1,
    )
    mismatches = _search_mismatches(score)
    assert len(mismatches) == 1
    assert "search_availability.area" in mismatches[0]


def test_non_area_fields_still_require_exact_match():
    # "outdoor" contains no substring relationship to "indoor" -- but even a
    # field that did (e.g. "hard" vs "hardcourt") must stay exact, since
    # date/surface/indoor_outdoor are schema enums/user-stated values, not
    # paraphrased free text.
    log = [_search_call(area="Golden Gate Park", date="2026-09-05", surface="hard", indoor_outdoor="indoor")]
    score = score_conversation(
        tool_call_log=log,
        expected={"area": "Golden Gate Park", "date": "2026-09-05", "surface": "hard", "indoor_outdoor": "outdoor"},
        num_turns=1,
    )
    mismatches = _search_mismatches(score)
    assert len(mismatches) == 1
    assert "search_availability.indoor_outdoor" in mismatches[0]
