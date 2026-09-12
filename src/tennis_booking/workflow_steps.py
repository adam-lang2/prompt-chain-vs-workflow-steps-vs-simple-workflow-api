"""Single source of truth for the tennis-booking workflow.

Every agent architecture implements the *same* workflow defined here:

- The workflow agent (`agents/workflow_agent.py`) renders this list into a
  numbered "Step 1 / Step 2 / ..." system prompt and relies entirely on the
  model re-reading the transcript each turn to figure out which step it's
  resuming from. One static prompt, no state tool.
- The prompt-chain agent (`agents/prompt_chain_agent.py`) renders a much
  shorter system prompt and instead exposes a `get_next_step()` tool that
  looks at server-side BookingState (see workflow_engine/state.py) and
  deterministically hands back the next step's instruction each turn -- a
  fresh, dynamically chained prompt fragment per turn, rather than one fixed
  prompt.
- The simple-workflow-api agent (`agents/simple_workflow_api_agent.py`) doesn't
  give the model a `next_step_for`-shaped tool at all: `FSMAgent`
  (`workflow_engine/`) is a separate, non-LLM step machine built from these
  same `STEPS` (see `workflow_engine/step_engine_shared.py`'s
  `step_is_current`/`step_payload`) that the model's one tool call reports
  slot updates to.

Changing the workflow (add/remove/reorder a question) means editing this
file once and every agent picks it up.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tennis_booking.workflow_engine.state import BookingState


@dataclass(frozen=True)
class Step:
    key: str
    # Slots this step is responsible for filling. Empty for pure-action steps.
    slot_names: tuple[str, ...]
    # Human-readable instruction, used verbatim in the prompt-chain numbered
    # list and as the `instruction` field returned by get_next_step().
    instruction: str
    # True if this step is a tool call the agent must make (not a question
    # to the user).
    is_tool_action: bool = False
    # True if this step is a simple, self-contained slot question: no
    # branching on the user's answer, and its extractor needs nothing but
    # the raw value (no dependency on a prior tool-action's result). Used by
    # step_engine_shared.py to hand back a whole run of consecutive such
    # steps' instructions at once (see step_engine_shared.step_payload's
    # "upcoming_instructions"), so agent-1 can ask several questions across
    # several turns before it needs to check
    # back in with the tool. ask_time (needs real search results) and
    # confirm_booking (branches on yes/no, needs the booking summary) are
    # deliberately NOT chainable -- each always needs a fresh tool round
    # trip once reached.
    chainable: bool = False
    # True if this step's slot(s) feed search_availability -- i.e. changing
    # this slot after a search already ran makes that search's results
    # stale. Marks SEARCH_INPUT_SLOTS below; kept as an explicit per-step
    # flag rather than "every step before search_availability" so reordering
    # STEPS can't silently change which slots are search inputs.
    is_search_input: bool = False

# TODO - i can't see mention of the tools here!? The steps should tell the model which tool to call
STEPS: list[Step] = [
    Step(
        key="ask_area",
        slot_names=("area",),
        instruction=(
            "Ask the user roughly where they want to play — a city, "
            "neighborhood, or general area, not a specific court name or "
            "address. If they name a specific court instead of an area, "
            "politely ask which general area that court is in. Keep the "
            "question to one short sentence and do not ask about anything "
            "else in the same message."
        ),
        chainable=True,
        is_search_input=True,
    ),
    Step(
        key="ask_date",
        slot_names=("date",),
        instruction=(
            "Ask the user what date they want to play. Accept any date "
            "format the user gives (e.g. 'next Saturday', 'Sept 5th', "
            "'2026-09-05') without correcting their phrasing back to them, "
            "but whenever you pass the date to a tool, always convert it to "
            "ISO format (YYYY-MM-DD). Ask for the date only — time of day is "
            "asked about later, once real availability is known, so do not "
            "ask about it here."
        ),
        chainable=True,
        is_search_input=True,
    ),
    Step(
        key="ask_surface",
        slot_names=("surface",),
        instruction=(
            "Ask the user which court surface they prefer. The only valid "
            "options are: hard, clay, grass, indoor carpet, or no "
            "preference. Do not suggest or mention surfaces outside this "
            "list, and do not explain the differences between surfaces "
            "unless the user explicitly asks."
        ),
        chainable=True,
        is_search_input=True,
    ),
    Step(
        key="ask_duration",
        slot_names=("duration_minutes",),
        instruction=(
            "Ask the user how long they want to play. The only valid "
            "durations are 60, 90, or 120 minutes. If the user gives a "
            "duration outside this list (e.g. '2 hours' or '45 minutes'), "
            "tell them which of the three options is closest and confirm "
            "that works before moving on."
        ),
        chainable=True,
        is_search_input=True,
    ),
    Step(
        key="ask_num_players",
        slot_names=("num_players",),
        instruction=(
            "Ask the user how many players will be on the court: 2 for "
            "singles or 4 for doubles. If the user gives an ambiguous "
            "answer (e.g. 'just a casual game' or 'a few friends'), ask "
            "directly whether it will be singles or doubles rather than "
            "guessing a player count."
        ),
        chainable=True,
        is_search_input=True,
    ),
    Step(
        key="ask_indoor_outdoor",
        slot_names=("indoor_outdoor",),
        instruction=(
            "Ask the user whether they want an indoor court, an outdoor "
            "court, or have no preference (either is fine). This is the "
            "last preference needed before you can look up availability, "
            "so keep it to a single direct question."
        ),
        chainable=True,
        is_search_input=True,
    ),
    Step(
        key="search_availability",
        slot_names=(),
        instruction=(
            "You now have all six required booking preferences: area, "
            "date, surface, duration, player count, and indoor/outdoor "
            "preference. Call the search_availability tool now, passing "
            "exactly the values the user gave you — do not alter, "
            "normalize, or guess at any of them beyond formatting the date "
            "as ISO. Do not ask the user anything in this step, and do not "
            "skip calling the tool."
        ),
        is_tool_action=True,
    ),
    Step(
        key="ask_time",
        slot_names=("selected_court_id", "selected_time"),
        instruction=(
            "Read the search_availability tool result carefully. Present "
            "the courts and their exact open time slots from that result to "
            "the user — do not summarize, round, reorder, or invent times "
            "or prices. If there are multiple courts, list each one "
            "separately with its own times. Ask the user which specific "
            "court and time they want."
        ),
    ),
    Step(
        key="ask_skill_level",
        slot_names=("skill_level",),
        instruction=(
            "Ask the user's skill level so the facility can pair them "
            "appropriately: beginner, intermediate, or advanced. If the "
            "user is unsure or doesn't want to say, tell them 'intermediate' "
            "is a reasonable default and ask if that's fine, but let them "
            "choose a different level if they'd rather."
        ),
        chainable=True,
    ),
    Step(
        key="ask_equipment_rental",
        slot_names=("equipment_rental",),
        instruction=(
            "Ask the user whether they need to rent a racket at the "
            "facility. This is a single yes/no question — do not ask about "
            "other equipment such as balls, shoes, or ball machines."
        ),
        chainable=True,
    ),
    Step(
        key="ask_contact_name",
        slot_names=("contact_name",),
        instruction="Ask the user's full name for the booking record.",
        chainable=True,
    ),
    Step(
        key="ask_contact_email",
        slot_names=("contact_email",),
        instruction=(
            "Ask the user for an email address to send the booking "
            "confirmation to. If what they give you clearly does not look "
            "like a valid email address (e.g. missing an '@' or a domain), "
            "point that out and ask them to double-check it before moving "
            "on — don't silently accept an obviously malformed address."
        ),
        chainable=True,
    ),
    Step(
        key="confirm_booking",
        slot_names=(),
        instruction=(
            "Recite the complete booking summary back to the user: area/"
            "court name, date, time, surface, duration, player count, "
            "skill level, equipment rental choice, name, and email. Read "
            "back every one of those fields — do not omit any, even ones "
            "that feel minor like skill level or equipment rental. Ask the "
            "user to confirm the summary is correct. Do NOT call book_court "
            "in this step — wait for their next reply."
        ),
    ),
    Step(
        key="call_book_court",
        slot_names=(),
        instruction=(
            "The user confirmed the booking summary in their previous "
            "message. Call the book_court tool now, using exactly the "
            "values already confirmed — do not re-derive, re-ask, or guess "
            "any value. Do not ask the user anything else before calling "
            "the tool."
        ),
        is_tool_action=True,
    ),
    Step(
        key="send_confirmation",
        slot_names=(),
        instruction=(
            "The booking was just confirmed. Call the send_confirmation "
            "tool now, using the contact_email, confirmation_id, court "
            "name, area, date, and time already established — do not "
            "re-derive, re-ask, or guess any value. Do not ask the user "
            "anything else before calling the tool."
        ),
        is_tool_action=True,
    ),
    Step(
        key="close_out",
        slot_names=(),
        instruction=(
            "Give the user their booking confirmation number exactly as "
            "returned by book_court — do not alter it. Briefly mention that "
            "a confirmation email was sent to their address. Briefly restate "
            "the date and time. Ask if there's anything else they need."
        ),
    ),
]

# The ordered slots a booking must have filled before a court can be booked,
# and the subset search_availability is called with -- both derived from
# STEPS above (each step's slot_names, in order) rather than hand-maintained,
# so the workflow definition stays the single source of truth. See
# workflow_engine/state.py's BookingState for how these are used.
REQUIRED_SLOTS: tuple[str, ...] = tuple(
    slot for step in STEPS for slot in step.slot_names
)
SEARCH_INPUT_SLOTS: tuple[str, ...] = tuple(
    slot for step in STEPS if step.is_search_input for slot in step.slot_names
)


def next_step_for(state: BookingState) -> Step | None:
    """Deterministically compute the next incomplete step for `state`.

    This is the logic the getNextStep() tool wraps. It is also used by the
    scripted-scenario test harness to independently verify each agent
    actually asked about the right slot at the right time.
    """
    for step in STEPS:
        if step.key == "search_availability":
            if not state.ready_to_search_availability():
                # Shouldn't happen if steps are followed in order, but guard
                # anyway: fall through to whichever slot step is missing.
                continue
            # Also re-fires if area/date/surface/... changed since the last
            # search -- e.g. the user changed the date after already seeing
            # times. Without this, a stale search would never get invalidated
            # since availability_searched() only checks *whether* a search
            # ran, not whether its inputs are still current.
            if not state.availability_searched() or state.search_params_stale():
                return step
            continue

        if step.key == "confirm_booking":
            if not state.ready_to_book():
                continue
            if not state.summary_confirmed:
                return step
            continue

        if step.key == "call_book_court":
            if not (state.ready_to_book() and state.summary_confirmed):
                continue
            if not state.booking_confirmed:
                return step
            continue

        if step.key == "send_confirmation":
            if not state.booking_confirmed:
                continue
            if not state.email_sent:
                return step
            continue

        if step.key == "close_out":
            if state.email_sent:
                return step
            continue

        # Ordinary slot-filling step.
        if any(getattr(state, slot) in (None, "") for slot in step.slot_names):
            # ask_time's slots only become askable after a current (non-stale)
            # availability search.
            if step.key == "ask_time" and (
                not state.availability_searched() or state.search_params_stale()
            ):
                continue
            return step

    return None  # Workflow fully complete.


def render_numbered_steps() -> str:
    """Render STEPS as the numbered instruction block for the workflow-step agent."""
    lines = []
    for i, step in enumerate(STEPS, start=1):
        lines.append(f"Step {i}: {step.instruction}")
    return "\n".join(lines)


# --- Shared policy text -----------------------------------------------------
#
# Both agent prompts interpolate these verbatim rather than each writing
# their own wording. That matters for the comparison this project runs: a
# quality difference should come from the *architecture* (static prompt vs.
# get_next_step tool), not from one agent happening to get better-written
# instructions than the other.

STALE_SEARCH_GUIDANCE = (
    "If the user changes a preference (area, date, surface, duration, "
    "player count, or indoor/outdoor) after you already looked up "
    "availability, the previous results are stale: look up availability "
    "again with the updated preferences before letting the user pick a "
    "time, even if they had already picked one from the old results."
)

GROUNDING_GUIDANCE = (
    "Grounding -- read this before presenting or booking any time:\n"
    "- The ONLY valid court names, times, and prices are the ones that "
    "literally appear in the most recent search_availability tool result. "
    "Before you state a time to the user, or pass a time to book_court, "
    "re-check that exact value against that tool result.\n"
    "- Never state or book a time that is not present in the tool result, "
    "even if it seems like a typical or reasonable time. If you are not "
    "certain a value came from the tool result, call search_availability "
    "again rather than guess.\n"
    "- If the user asks for a time that is not in the results, say so "
    "plainly and offer only the times that are actually available."
)
