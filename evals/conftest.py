"""Every test under evals/ is marked `@pytest.mark.eval` (registered in
pyproject.toml) so it can be selected/excluded independent of directory
(`pytest -m eval`, `pytest -m "not eval"`). This hook is the standard pytest
pattern for conditionally skipping marked tests: when no OpenRouter
credentials are configured, skip (never fail) every `eval`-marked test
instead of letting it hit an auth error, so `pytest` is always safe to run.
"""
from __future__ import annotations

import pytest

from tennis_booking.agents.base import has_usable_credentials
from tennis_booking.tools import live_courts
from evals.fixtures import live_courts_cassette

NO_CREDENTIALS_REASON = (
    "No OPENROUTER_API_KEY found. Get a key from https://openrouter.ai/keys "
    "and put it in .env as OPENROUTER_API_KEY."
)


def pytest_collection_modifyitems(config, items):
    if has_usable_credentials():
        return
    skip_marker = pytest.mark.skip(reason=NO_CREDENTIALS_REASON)
    for item in items:
        if "eval" in item.keywords:
            item.add_marker(skip_marker)


@pytest.fixture(autouse=True)
def _recorded_court_lookups(monkeypatch):
    """Every eval still exercises the real `find_nearby_courts` parsing/
    filtering/normalization logic in `tools/live_courts.py` -- only the two
    actual network calls it makes (`_geocode`, `_query_overpass`) are
    replaced with recorded real responses (see `fixtures/live_courts_cassette.py`),
    so a scripted scenario's expected court/surface/time data stays stable
    run to run instead of depending on live OSM/Nominatim state.
    """
    monkeypatch.setattr(live_courts, "_geocode", live_courts_cassette.geocode)
    monkeypatch.setattr(live_courts, "_query_overpass", live_courts_cassette.query_overpass)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print the standard comparison report -- tokens, cost (where priced),
    per-call latency p50/p90, and scenario pass/fail -- aggregated across
    every eval test that ran this session. See evals/report.py, which is
    also what evals/compare.py (the standalone `tennis-compare` script)
    renders, so both entry points show identically-computed numbers.
    """
    from evals.report import build_report

    report = build_report()
    if not report.rows:
        return

    terminalreporter.section("Agent comparison report")
    terminalreporter.write_line(report.render_text())
