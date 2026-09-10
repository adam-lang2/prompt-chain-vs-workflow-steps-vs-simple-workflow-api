"""Domain models shared by every agent architecture.

For BookingState -- the durable, per-conversation workflow-progress state --
see `tennis_booking.workflow_engine.state`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Surface(str, Enum):
    HARD = "hard"
    CLAY = "clay"
    GRASS = "grass"
    INDOOR_CARPET = "indoor_carpet"
    ANY = "any"


class IndoorOutdoor(str, Enum):
    INDOOR = "indoor"
    OUTDOOR = "outdoor"
    EITHER = "either"


@dataclass
class TimeSlot:
    time: str  # "HH:MM"
    price_usd: float


@dataclass
class CourtAvailability:
    court_id: str
    name: str
    area: str
    surface: str
    indoor_outdoor: str
    slots: list[TimeSlot]
