"""Scripted user turns for the deterministic pytest suite.

Each scenario is a fixed list of user messages (no LLM plays the user) plus
the expected final booking. Areas are real, geocodable places
(`evals/fixtures/live_courts_cassette.py` records their real Nominatim/
Overpass responses, replayed by `evals/conftest.py` so every run sees the
same court data); court/time data below was computed by running the actual
`tools/live_courts.find_nearby_courts` against those recorded fixtures for
each scenario's exact (area, date, surface, indoor_outdoor) -- see the
comment on each scenario for which recorded venue it uses.

Real OSM data has two gaps versus the old synthetic mock directory: it has
no `grass`-tagged courts and no `amenity=sports_centre` (indoor) tagged
courts anywhere findable, so no scenario here exercises a grass or an
indoor pick -- every scenario now works with real hard/clay outdoor courts.

Two scenario styles, per the project's design goal of stress-testing where
each agent architecture resumes a long conversation from:

- IN_ORDER: user answers exactly one question at a time, in the order the
  workflow asks it. This is the "easy mode" baseline.
- MESSY: user answers out of order, bundles several answers into one
  message, corrects an earlier answer mid-conversation, and asks unrelated
  questions that don't fill any slot. Every agent has to resume from the
  right place despite this.

The workflow has 16 steps (12 questions + 4 tool-action steps), so each
scenario now touches more slots than a shorter workflow would -- more
surface area for any architecture to drop or mix up a value.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScriptedScenario:
    name: str
    style: str  # "in_order" | "messy"
    turns: list[str]
    expected: dict = field(default_factory=dict)


IN_ORDER_GOLDEN_GATE_HARD = ScriptedScenario(
    name="in_order_golden_gate_hard",
    style="in_order",
    turns=[
        "Hi, I'd like to book a tennis court somewhere near Golden Gate Park.",
        "I want to play on 2026-09-05.",
        "I prefer hard courts.",
        "Let's do 90 minutes.",
        "It'll be doubles, so 4 players.",
        "Outdoor please.",
        "Let's do the 12:00 slot -- whichever court is closest is fine.",
        "I'd say intermediate level.",
        "No thanks, I have my own racket.",
        "My name is Jordan Lee.",
        "jordan.lee@example.com",
        "Yes, please confirm and book it.",
        "No that's everything, thanks!",
    ],
    expected={
        "area": "Golden Gate Park",
        "date": "2026-09-05",
        "surface": "hard",
        "indoor_outdoor": "outdoor",
        "duration_minutes": 90,
        "num_players": 4,
        "time": "12:00",
        "skill_level": "intermediate",
        "equipment_rental": False,
        "contact_name": "Jordan Lee",
        "contact_email": "jordan.lee@example.com",
    },
)


MESSY_PROSPECT_PARK_CLAY_CORRECTION = ScriptedScenario(
    name="messy_prospect_park_clay_correction",
    style="messy",
    turns=[
        # No slot filled -- a tangential question the agent must answer
        # without losing its place in the workflow.
        "Before we start, what areas can you check courts in?",
        # Answers area AND player count together, out of the workflow's order.
        "Ok let's go with Prospect Park then. Also it'll just be me and a "
        "friend so 2 players.",
        # Bundles date + surface + indoor/outdoor into one message.
        "I want to play on 2026-09-11, clay court, outdoor.",
        # Corrects the date before duration (the last remaining slot) is
        # even given, so availability hasn't been searched yet.
        "Wait, actually let's do 2026-09-12 instead of the 11th.",
        # Final slot -> should trigger exactly one search_availability call,
        # using the corrected date.
        "60 minutes please.",
        # Bundles time + skill level + equipment rental into one message.
        "17:30 works great. I'm advanced level, and I don't need a racket "
        "rental.",
        # Bundles name + email into one message.
        "Name's Priya Shah, email priya.shah@example.com.",
        "Yes go ahead and book that.",
        # Post-booking recall check -- workflow is "done" but the agent
        # should still track the committed state.
        "Can you remind me the confirmation number?",
        "Perfect, that's all I needed, thank you!",
    ],
    expected={
        "area": "Prospect Park",
        "date": "2026-09-12",
        "surface": "clay",
        "indoor_outdoor": "outdoor",
        "duration_minutes": 60,
        "num_players": 2,
        "time": "17:30",
        "skill_level": "advanced",
        "equipment_rental": False,
        "contact_name": "Priya Shah",
        "contact_email": "priya.shah@example.com",
    },
)


MESSY_PROSPECT_PARK_BULK_DUMP = ScriptedScenario(
    name="messy_prospect_park_bulk_dump",
    style="messy",
    turns=[
        "Hi! Can you help me book a tennis court?",
        # Answers area, then asks an unrelated question in the same breath.
        "Sure -- somewhere in Prospect Park, and by the way how many courts "
        "do you usually find nearby?",
        # Dumps four more slots into one message at once.
        "Let's play 2026-09-19. Actually, let me just give you "
        "everything: any surface is fine, indoor or outdoor doesn't "
        "matter, we're 4 players for 90 minutes.",
        # Bundles time + skill level + equipment rental (this time a "yes").
        "16:00 looks good, closest court is fine. I'm a beginner, and yes "
        "I'll need to rent a racket please.",
        # Bundles name + email.
        "It's Sam Okafor, sam.okafor@example.com.",
        "Yes, please book it now.",
        # Post-booking correctness check on a detail given several turns ago.
        "Actually wait, can you double check that's 90 minutes, not 60?",
        "Great, that's all, thank you!",
    ],
    expected={
        "area": "Prospect Park",
        "date": "2026-09-19",
        "surface": "any",
        "indoor_outdoor": "either",
        "duration_minutes": 90,
        "num_players": 4,
        "time": "16:00",
        "skill_level": "beginner",
        "equipment_rental": True,
        "contact_name": "Sam Okafor",
        "contact_email": "sam.okafor@example.com",
    },
)


ZERO_RESULT_RELAX = ScriptedScenario(
    name="zero_result_relax",
    style="messy",
    turns=[
        # Newport has no grass-tagged courts in the recorded data (see
        # evals/fixtures/live_courts/newport_hof.json) -- a legitimate
        # zero-result search, not a bad area name. The agent must tell the
        # user plainly and let them relax a preference instead of getting
        # stuck or inventing a court.
        "Hi, I'd like to book a court in Newport.",
        "2026-09-20",
        "grass, please",
        "90 minutes",
        "2 players, just singles",
        "outdoor",
        "Hmm, no grass courts? Let's try hard instead.",
        "17:30 works, whichever court is closest",
        "intermediate",
        "no need, I have my own racket",
        "My name is Alex Rivera",
        "alex.rivera@example.com",
        "Yes, confirm and book it",
        "No that's all, thanks!",
    ],
    expected={
        "area": "Newport",
        "date": "2026-09-20",
        "surface": "hard",
        "indoor_outdoor": "outdoor",
        "duration_minutes": 90,
        "num_players": 2,
        "time": "17:30",
        "skill_level": "intermediate",
        "equipment_rental": False,
        "contact_name": "Alex Rivera",
        "contact_email": "alex.rivera@example.com",
    },
)


MESSY_DURATION_CHANGE_AFTER_SELECTION = ScriptedScenario(
    name="messy_duration_change_after_selection",
    style="messy",
    turns=[
        "I'd like a court in Prospect Park.",
        "2026-09-21",
        "hard surface",
        "60 minutes",
        "4 players, doubles",
        "outdoor",
        "12:00 works for me, closest court is fine",
        # Changes a search-input field (duration) *after* already picking a
        # time -- must invalidate the stale selection and re-search, per
        # STALE_SEARCH_GUIDANCE, even though this scenario picks a
        # *different* time the second time around (not the same one, so a
        # lazy "keep the old selection" bug can't accidentally pass).
        "Wait, actually let's make it 90 minutes instead of 60.",
        "Let's do 17:30 instead, closest court is fine",
        "advanced level",
        "yes I'll need to rent a racket",
        "Name's Taylor Brooks",
        "taylor.brooks@example.com",
        "Yes, please book it",
        "Great, thanks!",
    ],
    expected={
        "area": "Prospect Park",
        "date": "2026-09-21",
        "surface": "hard",
        "indoor_outdoor": "outdoor",
        "duration_minutes": 90,
        "num_players": 4,
        "time": "17:30",
        "skill_level": "advanced",
        "equipment_rental": True,
        "contact_name": "Taylor Brooks",
        "contact_email": "taylor.brooks@example.com",
    },
)


MESSY_MALFORMED_EMAIL_RETRY = ScriptedScenario(
    name="messy_malformed_email_retry",
    style="messy",
    turns=[
        "Hey, can I book a tennis court in Golden Gate Park?",
        "2026-09-23",
        "any surface, don't mind",
        "60 minutes",
        "just me and a friend, singles",
        "indoor or outdoor doesn't matter",
        "Let's do 12:00, closest court is fine.",
        "beginner",
        "no thanks, got my own racket",
        "Morgan Diaz",
        # Malformed -- no "@" -- the agent must catch this and ask again
        # rather than passing it through to book_court.
        "morgan at example dot com",
        "Sorry, that's morgan.diaz@example.com",
        "Yes, go ahead and book it",
        "Perfect, thank you!",
    ],
    expected={
        "area": "Golden Gate Park",
        "date": "2026-09-23",
        "surface": "any",
        "indoor_outdoor": "either",
        "duration_minutes": 60,
        "num_players": 2,
        "time": "12:00",
        "skill_level": "beginner",
        "equipment_rental": False,
        "contact_name": "Morgan Diaz",
        "contact_email": "morgan.diaz@example.com",
    },
)


MESSY_ALL_AT_ONCE_OPENER = ScriptedScenario(
    name="messy_all_at_once_opener",
    style="messy",
    turns=[
        # Every search-input slot, plus name and email, all in the very
        # first message -- a harder version of the bulk-dump scenarios
        # above, which never bundle more than 4-5 fields at a time and never
        # do it on the opening turn.
        "Hi! I want to book a tennis court in Discovery Park on 2026-09-23, "
        "any surface, indoor or outdoor is fine, 120 minutes, 4 players "
        "(doubles). My name is Jamie Chen and my email is "
        "jamie.chen@example.com.",
        "16:00 please, closest court is fine.",
        "intermediate",
        "No need for a racket rental",
        "Yes, please confirm and book it.",
        "That's everything, thanks!",
    ],
    expected={
        "area": "Discovery Park",
        "date": "2026-09-23",
        "surface": "any",
        "indoor_outdoor": "either",
        "duration_minutes": 120,
        "num_players": 4,
        "time": "16:00",
        "skill_level": "intermediate",
        "equipment_rental": False,
        "contact_name": "Jamie Chen",
        "contact_email": "jamie.chen@example.com",
    },
)


MESSY_MULTI_FIELD_REDO = ScriptedScenario(
    name="messy_multi_field_redo",
    style="messy",
    turns=[
        "I want to book a court in Prospect Park.",
        "2026-09-25",
        "clay surface",
        # Redoes two already-answered fields at once, not just one -- a
        # harder version of the single-field correction scenarios above.
        "Wait, actually, let's redo this: I'd rather play in Golden Gate "
        "Park, still on 2026-09-25, hard surface if possible.",
        "90 minutes",
        "4 players, doubles",
        "outdoor",
        "16:00 sounds great, closest court is fine",
        "advanced",
        "no need, have my own",
        "Name is Riley Kim",
        "riley.kim@example.com",
        "Yes, book it please",
        "Thanks, that's all!",
    ],
    expected={
        "area": "Golden Gate Park",
        "date": "2026-09-25",
        "surface": "hard",
        "indoor_outdoor": "outdoor",
        "duration_minutes": 90,
        "num_players": 4,
        "time": "16:00",
        "skill_level": "advanced",
        "equipment_rental": False,
        "contact_name": "Riley Kim",
        "contact_email": "riley.kim@example.com",
    },
)


MESSY_DOUBLE_DATE_CORRECTION = ScriptedScenario(
    name="messy_double_date_correction",
    style="messy",
    turns=[
        "Book me a court in Prospect Park please.",
        "2026-09-20",
        # First correction...
        "Hmm wait, actually make that 2026-09-21.",
        "hard court",
        # ...then a SECOND correction to the same field before the first
        # search ever runs -- the second one must win, not the first.
        "Sorry, one more change -- let's actually do 2026-09-22, not the 21st.",
        "60 minutes",
        "2 players, singles",
        "outdoor",
        "07:00 works, closest court is fine",
        "beginner",
        "yes, I'd like to rent a racket",
        "Casey Nguyen",
        "casey.nguyen@example.com",
        "Yes, confirm and book",
        "Great, thank you!",
    ],
    expected={
        "area": "Prospect Park",
        "date": "2026-09-22",
        "surface": "hard",
        "indoor_outdoor": "outdoor",
        "duration_minutes": 60,
        "num_players": 2,
        "time": "07:00",
        "skill_level": "beginner",
        "equipment_rental": True,
        "contact_name": "Casey Nguyen",
        "contact_email": "casey.nguyen@example.com",
    },
)


MESSY_NAMED_COURT_INSTEAD_OF_AREA = ScriptedScenario(
    name="messy_named_court_instead_of_area",
    style="messy",
    turns=[
        # Names a specific court instead of a general area -- ask_area's own
        # instruction (workflow_steps.py) explicitly covers this: the agent
        # should ask which general area that court is in, not accept the
        # court name as the area value outright.
        "I'd like to book at Discovery Park Tennis Court #1.",
        "Oh sorry, that's in Discovery Park.",
        "2026-09-23",
        "hard, obviously since that's the court",
        "90 minutes",
        "2 players",
        "outdoor",
        "17:30 please",
        "intermediate",
        "no racket needed",
        "Drew Patel",
        "drew.patel@example.com",
        "Yes book it",
        "Perfect, thanks!",
    ],
    expected={
        "area": "Discovery Park",
        "date": "2026-09-23",
        "surface": "hard",
        "indoor_outdoor": "outdoor",
        "duration_minutes": 90,
        "num_players": 2,
        "time": "17:30",
        "skill_level": "intermediate",
        "equipment_rental": False,
        "contact_name": "Drew Patel",
        "contact_email": "drew.patel@example.com",
    },
)


MESSY_OUT_OF_RANGE_DURATION = ScriptedScenario(
    name="messy_out_of_range_duration",
    style="messy",
    turns=[
        "Looking to book a court in Golden Gate Park.",
        "2026-09-24",
        "hard court please",
        # Not one of 60/90/120 -- ask_duration's instruction says to suggest
        # the closest valid option and confirm, not silently round it.
        "45 minutes",
        "Sure, 60 minutes is fine.",
        "4 players, doubles",
        "outdoor",
        "10:00 works, closest court is fine",
        "advanced",
        "no, I have my own equipment",
        "Jordan Ellis",
        "jordan.ellis@example.com",
        "Yes, please book",
        "Thank you, that's everything!",
    ],
    expected={
        "area": "Golden Gate Park",
        "date": "2026-09-24",
        "surface": "hard",
        "indoor_outdoor": "outdoor",
        "duration_minutes": 60,
        "num_players": 4,
        "time": "10:00",
        "skill_level": "advanced",
        "equipment_rental": False,
        "contact_name": "Jordan Ellis",
        "contact_email": "jordan.ellis@example.com",
    },
)


ALL_SCENARIOS: list[ScriptedScenario] = [
    IN_ORDER_GOLDEN_GATE_HARD,
    MESSY_PROSPECT_PARK_CLAY_CORRECTION,
    MESSY_PROSPECT_PARK_BULK_DUMP,
    ZERO_RESULT_RELAX,
    MESSY_DURATION_CHANGE_AFTER_SELECTION,
    MESSY_MALFORMED_EMAIL_RETRY,
    MESSY_ALL_AT_ONCE_OPENER,
    MESSY_MULTI_FIELD_REDO,
    MESSY_DOUBLE_DATE_CORRECTION,
    MESSY_NAMED_COURT_INSTEAD_OF_AREA,
    MESSY_OUT_OF_RANGE_DURATION,
]
