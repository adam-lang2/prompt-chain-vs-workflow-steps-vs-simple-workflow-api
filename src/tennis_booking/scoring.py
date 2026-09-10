"""Deterministic scoring of a finished conversation against a scenario's
expected booking. Used by the scripted pytest suite, and importable by the
deepeval suite for a fast pre-check before spending an LLM-judge call.

This does NOT use an LLM judge -- it only looks at the tool calls the agent
actually made (search_availability / book_court args), since those are the
observable, verifiable outcome of "did the agent correctly resume and
complete the workflow," independent of exactly how the conversation's
questions were phrased or ordered.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tennis_booking.agents.base import ToolCallRecord
from tennis_booking.mock_courts import find_listing

EXPECTED_SEARCH_FIELDS = ("area", "date", "surface", "indoor_outdoor")
EXPECTED_BOOK_FIELDS = (
    "court_id",
    "date",
    "time",
    "duration_minutes",
    "num_players",
    "skill_level",
    "equipment_rental",
    "contact_name",
    "contact_email",
)


@dataclass
class WorkflowScore:
    booked: bool
    searched: bool
    num_search_calls: int
    num_book_calls: int
    num_turns: int
    mismatches: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.booked and not self.mismatches


def _last_call(log: list[ToolCallRecord], name: str) -> ToolCallRecord | None:
    for record in reversed(log):
        if record.name == name:
            return record
    return None


def score_conversation(
    tool_call_log: list[ToolCallRecord],
    expected: dict,
    num_turns: int,
) -> WorkflowScore:
    """`expected` maps field name -> expected value for the fields in
    EXPECTED_SEARCH_FIELDS and EXPECTED_BOOK_FIELDS that the scenario cares
    about checking (a scenario may omit fields it doesn't want strictly
    checked, e.g. contact_name casing).
    """
    search_calls = [r for r in tool_call_log if r.name == "search_availability"]
    book_calls = [r for r in tool_call_log if r.name == "book_court"]

    last_search = _last_call(tool_call_log, "search_availability")
    last_book = _last_call(tool_call_log, "book_court")

    mismatches: list[str] = []

    for f in EXPECTED_SEARCH_FIELDS:
        if f not in expected:
            continue
        if last_search is None:
            mismatches.append(f"search_availability was never called (expected {f}={expected[f]!r})")
            continue
        actual = last_search.args.get(f)
        if str(actual).lower() != str(expected[f]).lower():
            mismatches.append(f"search_availability.{f} = {actual!r}, expected {expected[f]!r}")

    for f in EXPECTED_BOOK_FIELDS:
        if f not in expected:
            continue
        if last_book is None:
            mismatches.append(f"book_court was never called (expected {f}={expected[f]!r})")
            continue
        actual = last_book.args.get(f)
        if str(actual).lower() != str(expected[f]).lower():
            mismatches.append(f"book_court.{f} = {actual!r}, expected {expected[f]!r}")

    if last_book is not None:
        mismatches.extend(
            _validate_booked_court_consistency(
                court_id=last_book.args.get("court_id"),
                # `booked_*` overrides let a scenario distinguish "any/either"
                # search filters from the specific court the user actually
                # picked once they saw results (see scripted scenario 3).
                expected_area=expected.get("booked_area", expected.get("area")),
                expected_surface=expected.get("booked_surface", expected.get("surface")),
                expected_indoor_outdoor=expected.get(
                    "booked_indoor_outdoor", expected.get("indoor_outdoor")
                ),
            )
        )

    return WorkflowScore(
        booked=last_book is not None,
        searched=last_search is not None,
        num_search_calls=len(search_calls),
        num_book_calls=len(book_calls),
        num_turns=num_turns,
        mismatches=mismatches,
    )


def _validate_booked_court_consistency(
    court_id: str | None,
    expected_area: str | None,
    expected_surface: str | None,
    expected_indoor_outdoor: str | None,
) -> list[str]:
    """The agent picks court_id from whatever search_availability returned, so
    we can't assert an exact id -- instead verify the booked court actually
    satisfies the user's stated constraints (a wrong-court booking is exactly
    the kind of silent failure this comparison is meant to catch).
    """
    if not court_id:
        return ["book_court.court_id was empty"]
    listing = find_listing(court_id)
    if listing is None:
        return [f"book_court.court_id {court_id!r} does not match any known court"]

    problems: list[str] = []
    if expected_area and expected_area.lower() not in listing.area and listing.area not in expected_area.lower():
        problems.append(f"booked court area={listing.area!r}, expected near {expected_area!r}")
    if expected_surface and expected_surface != "any" and listing.surface != expected_surface:
        problems.append(f"booked court surface={listing.surface!r}, expected {expected_surface!r}")
    if (
        expected_indoor_outdoor
        and expected_indoor_outdoor != "either"
        and listing.indoor_outdoor != expected_indoor_outdoor
    ):
        problems.append(
            f"booked court indoor_outdoor={listing.indoor_outdoor!r}, expected {expected_indoor_outdoor!r}"
        )
    return problems
