"""BookingState -- the durable, server-side workflow-progress state shared
by every step-computation path in this package (`step_engine_shared.py`,
`step_engine_langgraph.py`, `agent.py`) and by `workflow_steps.next_step_for`
(used by `tools/prompt_chain_get_next_step.py`, backing `agents/prompt_chain_agent.py`).

Every agent drives the user through the exact same slot-filling workflow and
lands on the exact same BookingState shape. Keeping this in one place is
what makes the architectures comparable: any behavioral difference in the
evals comes from *how* the agent tracks progress through the workflow, not
from a different workflow.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Optional

from tennis_booking.models import CourtAvailability
from tennis_booking.workflow_steps import REQUIRED_SLOTS, SEARCH_INPUT_SLOTS

__all__ = [
    "REQUIRED_SLOTS",
    "SEARCH_INPUT_SLOTS",
    "BookingState",
]


@dataclass
class BookingState:
    """Mutable slot-filling state for one in-progress booking conversation."""

    area: Optional[str] = None
    date: Optional[str] = None  # ISO date string, e.g. "2026-09-06"
    surface: Optional[str] = None  # Surface value
    duration_minutes: Optional[int] = None  # 60 / 90 / 120
    num_players: Optional[int] = None  # 2 (singles) or 4 (doubles)
    indoor_outdoor: Optional[str] = None  # IndoorOutdoor value

    # Populated once availability has been looked up.
    available_courts: list[CourtAvailability] = field(default_factory=list)

    selected_court_id: Optional[str] = None
    selected_time: Optional[str] = None  # "HH:MM"

    skill_level: Optional[str] = None  # "beginner" / "intermediate" / "advanced"
    equipment_rental: Optional[bool] = None  # needs a racket rented, y/n

    contact_name: Optional[str] = None
    contact_email: Optional[str] = None

    # Snapshot of SEARCH_INPUT_SLOTS values as of the last search_availability
    # call, so a later preference change can be detected as staleness.
    last_search_params: Optional[dict] = None

    # True once search_availability has run at least once, *regardless* of
    # whether it found any courts. Distinct from `bool(available_courts)`:
    # a search that legitimately matches zero courts must still count as
    # "searched" -- otherwise next_step_for keeps re-issuing the same search
    # forever (verified live: this was a real infinite loop, triggered once
    # a bad extraction produced a nonsense area with no matching courts).
    search_has_run: bool = False

    # True once the user has confirmed the recited booking summary -- distinct
    # from booking_confirmed, which means book_court has actually been called.
    summary_confirmed: bool = False

    booking_confirmed: bool = False
    confirmation_id: Optional[str] = None

    def availability_searched(self) -> bool:
        return self.search_has_run

    def search_params_stale(self) -> bool:
        """True if area/date/surface/duration/players/indoor-outdoor changed
        since the results in `available_courts` were fetched -- e.g. the user
        changed their mind about the date after already seeing times."""
        if not self.availability_searched():
            return False
        current = {slot: getattr(self, slot) for slot in SEARCH_INPUT_SLOTS}
        return current != self.last_search_params

    def record_search_results(self, courts: list[CourtAvailability]) -> None:
        """Store fresh search results and invalidate whatever depended on the
        previous search. Safe to call on a first search too -- the fields
        being reset are already empty/False then. `courts` may legitimately
        be empty (no matches) -- `search_has_run` still flips to True so
        that case is never confused with "hasn't searched yet"."""
        self.available_courts = courts
        self.search_has_run = True
        self.last_search_params = {slot: getattr(self, slot) for slot in SEARCH_INPUT_SLOTS}
        self.selected_court_id = None
        self.selected_time = None
        self.summary_confirmed = False

    def ready_to_search_availability(self) -> bool:
        return all(getattr(self, s) not in (None, "") for s in SEARCH_INPUT_SLOTS)

    def ready_to_book(self) -> bool:
        return (
            self.availability_searched()
            and all(
                getattr(self, s) not in (None, "")
                for s in REQUIRED_SLOTS
            )
        )

    def as_dict(self) -> dict:
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name != "available_courts"
        }
