"""Keeps `tests/` fully offline and deterministic.

`tools/search_availability.py` now calls `tools/live_courts.find_nearby_courts`,
which makes real Nominatim/Overpass network calls -- appropriate for the
evals (see evals/ for how those are handled separately), but wrong for this
package's unit/wiring tests, which are meant to run with no network and no
credentials and to keep asserting against the same fixed court data
(`mock_courts.COURT_DIRECTORY`) they always have.

Autouse + session-scoped monkeypatch: every test in this package gets
`run_search_availability` backed by the deterministic mock directory instead
of a live lookup, without each test file needing to know that's happening.
"""
from __future__ import annotations

import pytest

from tennis_booking.mock_courts import search_availability as _mock_search_availability
from tennis_booking.tools import search_availability as _search_availability_module


@pytest.fixture(autouse=True)
def _offline_court_search(monkeypatch):
    monkeypatch.setattr(_search_availability_module, "find_nearby_courts", _mock_search_availability)
