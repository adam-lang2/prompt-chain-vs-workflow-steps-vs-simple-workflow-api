"""Simulated-user personas + scenarios for the deepeval suite.

Unlike tests/scenarios/scripted.py (fixed user utterances), these are fed to
deepeval's ConversationSimulator, which uses an LLM to *play* the user
according to `persona.characteristics` and `scenario`/`expected_outcome`.
That makes this suite a realism check on top of the scripted suite's
determinism check: same underlying workflow, but the user's phrasing,
ordering, and digressions vary each run.
"""
from __future__ import annotations

from deepeval.dataset.golden import ConversationalGolden, Persona

ORDERLY_PERSONA = Persona(
    name="Orderly Player",
    characteristics=(
        "Answers exactly the question the assistant just asked, one at a "
        "time, in plain and direct language. Does not volunteer information "
        "before being asked for it."
    ),
)

MESSY_PERSONA = Persona(
    name="Scattered Player",
    characteristics=(
        "Talkative and a little scattered. Often answers two or three "
        "questions at once in a single message, sometimes before being "
        "asked. Occasionally asks an unrelated question (like whether the "
        "app supports other sports, or what the cancellation policy is) "
        "before getting back on topic. At least once mid-conversation, "
        "changes their mind about an earlier answer (e.g. the date, the "
        "surface, or the number of players) and expects the assistant to "
        "use the corrected value. Never abandons the goal of booking a "
        "court by the end of the conversation."
    ),
)

ORDERLY_DOWNTOWN_GOLDEN = ConversationalGolden(
    name="orderly_downtown_clay",
    scenario=(
        "A player wants to book a tennis court somewhere near downtown, "
        "on 2026-09-05, on a clay surface, outdoors, for 90 minutes, "
        "doubles (4 players). They are happy to pick whatever time the "
        "assistant finds available, are an intermediate player who doesn't "
        "need to rent a racket, and will give their name as 'Jordan Lee' "
        "and email as 'jordan.lee@example.com' when asked."
    ),
    expected_outcome=(
        "The assistant collects area, date, surface, duration, player "
        "count, and indoor/outdoor preference one at a time; looks up "
        "availability; lets the player choose a time from real results; "
        "collects skill level, equipment rental need, name, and email; "
        "confirms the full summary; and books the court, ending with a "
        "confirmation number."
    ),
    persona=ORDERLY_PERSONA,
)

MESSY_EASTSIDE_GOLDEN = ConversationalGolden(
    name="messy_eastside_hard",
    scenario=(
        "A player wants to book a tennis court near eastside, on "
        "2026-09-12 (though they'll first mention a different date before "
        "correcting themselves), on a hard surface, outdoors, for 60 "
        "minutes, singles (2 players). They are happy to pick whatever time "
        "the assistant finds available, are an advanced player who does not "
        "need to rent a racket, and will give their name as 'Priya Shah' "
        "and email as 'priya.shah@example.com' when asked."
    ),
    expected_outcome=(
        "Despite answering out of order, bundling multiple answers "
        "together, and correcting an earlier answer, the assistant ends up "
        "with the corrected values (area=eastside, date=2026-09-12, "
        "surface=hard, indoor_outdoor=outdoor, duration=60, players=2), "
        "looks up real availability, lets the player pick a time, collects "
        "skill level, equipment rental need, name, and email, confirms, and "
        "books the court with a confirmation number -- without asking the "
        "player to repeat anything they already said."
    ),
    persona=MESSY_PERSONA,
)

TERSE_PERSONA = Persona(
    name="Terse Player",
    characteristics=(
        "Answers with the fewest possible words -- often a single word or a "
        "short fragment, never a full sentence, never volunteers anything "
        "beyond exactly what was asked. Never bundles more than one answer "
        "into a message. Gets mildly impatient (but stays polite) if asked "
        "to repeat something already said."
    ),
)

OVER_EXPLAINER_PERSONA = Persona(
    name="Over-Explainer Player",
    characteristics=(
        "Answers every question with a lot of unrequested context and "
        "backstory before finally giving the actual answer (e.g. explaining "
        "why they prefer a surface, or a story about a past booking) -- the "
        "real answer is always in there, just buried in extra sentences. "
        "Never actually asks for anything out of scope, just talkative."
    ),
)

OFF_TOPIC_DETOUR_PERSONA = Persona(
    name="Off-Topic Detour Player",
    characteristics=(
        "Cooperative and answers each question eventually, but at least "
        "twice during the conversation asks a clearly out-of-scope question "
        "first (e.g. membership pricing, whether the facility has a pro "
        "shop, or asking to also book a squash court) before giving the "
        "actual answer in the same or a following message. Accepts a polite "
        "decline or redirect on the out-of-scope questions without pushing "
        "further, and never abandons the goal of booking a tennis court."
    ),
)

TERSE_WESTSIDE_GOLDEN = ConversationalGolden(
    name="terse_westside_indoor",
    scenario=(
        "A player wants to book a tennis court in westside, on "
        "2026-09-24, indoor_carpet surface, indoors, for 60 minutes, "
        "singles (2 players). They'll take whatever time is available, are "
        "a beginner who needs to rent a racket, and will give their name as "
        "'Sam Wu' and email as 'sam.wu@example.com' when asked -- but only "
        "ever in short, single-word-or-fragment answers."
    ),
    expected_outcome=(
        "Despite the player's terse, single-fact-at-a-time answers, the "
        "assistant still collects every required field exactly once each "
        "(area=westside, date=2026-09-24, surface=indoor_carpet, "
        "indoor_outdoor=indoor, duration=60, players=2, skill=beginner, "
        "equipment_rental=true, name='Sam Wu', "
        "email='sam.wu@example.com'), looks up real availability, confirms "
        "the full summary, and books the court with a confirmation number."
    ),
    persona=TERSE_PERSONA,
)

OVER_EXPLAINER_NORTHPARK_GOLDEN = ConversationalGolden(
    name="over_explainer_northpark_grass",
    scenario=(
        "A player wants to book a tennis court in northpark, on "
        "2026-09-25, grass surface, outdoors, for 90 minutes, doubles (4 "
        "players). They'll pick whatever time is available, are an "
        "intermediate player who doesn't need to rent a racket, and will "
        "give their name as 'Nadia Kowalski' and email as "
        "'nadia.kowalski@example.com' when asked -- but always wraps the "
        "actual answer in a paragraph of unrelated backstory or "
        "explanation first."
    ),
    expected_outcome=(
        "Despite each answer arriving buried in extra, unrequested detail, "
        "the assistant correctly extracts just the real answer for every "
        "field (area=northpark, date=2026-09-25, surface=grass, "
        "indoor_outdoor=outdoor, duration=90, players=4, "
        "skill=intermediate, equipment_rental=false, name='Nadia "
        "Kowalski', email='nadia.kowalski@example.com'), looks up real "
        "availability, confirms the full summary, and books the court with "
        "a confirmation number -- without mistaking any of the backstory "
        "for a real answer to a different field."
    ),
    persona=OVER_EXPLAINER_PERSONA,
)

OFF_TOPIC_DETOUR_EASTSIDE_GOLDEN = ConversationalGolden(
    name="off_topic_detour_eastside_clay",
    scenario=(
        "A player wants to book a tennis court in eastside, on "
        "2026-09-26, clay surface, outdoors, for 90 minutes, doubles (4 "
        "players). They'll pick whatever time is available, are an "
        "advanced player who does not need to rent a racket, and will give "
        "their name as 'Owen Baptiste' and email as "
        "'owen.baptiste@example.com' when asked -- but twice during the "
        "conversation asks an out-of-scope question (membership pricing, "
        "whether there's a pro shop) before answering."
    ),
    expected_outcome=(
        "The assistant politely declines or redirects each out-of-scope "
        "question without pretending to answer it, then still collects "
        "every required field (area=eastside, date=2026-09-26, "
        "surface=clay, indoor_outdoor=outdoor, duration=90, players=4, "
        "skill=advanced, equipment_rental=false, name='Owen Baptiste', "
        "email='owen.baptiste@example.com'), looks up real availability, "
        "confirms the full summary, and books the court with a "
        "confirmation number -- never treating the off-topic detours as "
        "unmet workflow steps."
    ),
    persona=OFF_TOPIC_DETOUR_PERSONA,
)

ALL_GOLDENS: list[ConversationalGolden] = [
    ORDERLY_DOWNTOWN_GOLDEN,
    MESSY_EASTSIDE_GOLDEN,
    TERSE_WESTSIDE_GOLDEN,
    OVER_EXPLAINER_NORTHPARK_GOLDEN,
    OFF_TOPIC_DETOUR_EASTSIDE_GOLDEN,
]
