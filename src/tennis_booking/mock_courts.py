"""Mock tennis court directory + a deterministic availability generator.

No network calls: availability is derived from a hash of
(court_id, date) so the same scenario always produces the same slots,
which keeps scripted pytest assertions stable across runs.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from tennis_booking.models import CourtAvailability, TimeSlot

CANDIDATE_TIMES = ["07:00", "08:30", "10:00", "12:00", "14:00", "16:00", "17:30", "19:00"]


@dataclass(frozen=True)
class CourtListing:
    court_id: str
    name: str
    area: str
    surface: str  # Surface value
    indoor_outdoor: str  # IndoorOutdoor value
    base_price_usd: float


# A small directory of courts across a few named areas. Areas are matched
# loosely (case-insensitive substring) against whatever the user says, so
# "downtown", "Downtown Seattle", and "near downtown" all resolve.
COURT_DIRECTORY: list[CourtListing] = [
    CourtListing("dt-hard-1", "Downtown Racquet Club", "downtown", "hard", "outdoor", 28.0),
    CourtListing("dt-clay-1", "Riverside Clay Courts", "downtown", "clay", "outdoor", 34.0),
    CourtListing("dt-indoor-1", "Metro Indoor Tennis Center", "downtown", "hard", "indoor", 45.0),
    CourtListing("np-hard-1", "Northpark Community Courts", "northpark", "hard", "outdoor", 18.0),
    CourtListing("np-grass-1", "Northpark Lawn Club", "northpark", "grass", "outdoor", 40.0),
    CourtListing("ws-hard-1", "Westside Public Courts", "westside", "hard", "outdoor", 15.0),
    CourtListing("ws-indoor-1", "Westside Fieldhouse", "westside", "indoor_carpet", "indoor", 38.0),
    CourtListing("es-clay-1", "Eastside Clay & Country Club", "eastside", "clay", "outdoor", 30.0),
    CourtListing("es-hard-1", "Eastside Rec Center", "eastside", "hard", "outdoor", 20.0),
]


KNOWN_AREAS: tuple[str, ...] = tuple(sorted({listing.area for listing in COURT_DIRECTORY}))


def _matches_area(listing: CourtListing, area_query: str) -> bool:
    q = area_query.strip().lower()
    return listing.area in q or q in listing.area


def _matches_surface(listing: CourtListing, surface: str) -> bool:
    return surface in ("any", None) or listing.surface == surface


def _matches_indoor_outdoor(listing: CourtListing, indoor_outdoor: str) -> bool:
    return indoor_outdoor in ("either", None) or listing.indoor_outdoor == indoor_outdoor


def _slot_is_open(court_id: str, date: str, time: str) -> bool:
    """Deterministic pseudo-availability: ~60% of slots are open."""
    digest = hashlib.sha256(f"{court_id}|{date}|{time}".encode()).hexdigest()
    return int(digest, 16) % 5 < 3  # 3/5 = 60% open


def search_availability(
    area: str,
    date: str,
    surface: str = "any",
    indoor_outdoor: str = "either",
) -> list[CourtAvailability]:
    """Return courts near `area` matching filters, each with open time slots."""
    results: list[CourtAvailability] = []
    for listing in COURT_DIRECTORY:
        if not _matches_area(listing, area):
            continue
        if not _matches_surface(listing, surface):
            continue
        if not _matches_indoor_outdoor(listing, indoor_outdoor):
            continue

        open_slots = [
            TimeSlot(time=t, price_usd=listing.base_price_usd)
            for t in CANDIDATE_TIMES
            if _slot_is_open(listing.court_id, date, t)
        ]
        if open_slots:
            results.append(
                CourtAvailability(
                    court_id=listing.court_id,
                    name=listing.name,
                    area=listing.area,
                    surface=listing.surface,
                    indoor_outdoor=listing.indoor_outdoor,
                    slots=open_slots,
                )
            )
    return results


def find_listing(court_id: str) -> CourtListing | None:
    for listing in COURT_DIRECTORY:
        if listing.court_id == court_id:
            return listing
    return None
