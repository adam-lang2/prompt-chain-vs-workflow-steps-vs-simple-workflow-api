"""jev agent -- interprets user turns with TypeSafe's Jev model, applies
deterministic code updates to BookingState via BookingWorkflowEngine, and uses
the LLM only as a "speaker" (tool-less chat call) to respond naturally.
"""
from __future__ import annotations

import json
import time
from dataclasses import field

from tennis_booking.agents.base import PROVIDER_ROUTING, ConversationAgent, ToolCallRecord, UsageRecord, reasoning_text, usage_details
from tennis_booking.jev.apply import to_updates
from tennis_booking.jev.interpret import Interpretation, Interpreter
from tennis_booking.jev.interpreter import JevInterpreter
from tennis_booking.workflow_engine import BookingWorkflowEngine

SYSTEM_PROMPT = f"""\
You are the speaking voice for a tennis court booking workflow. Every \
decision -- what's been settled so far, what to ask next, what's true -- was \
already made by the workflow engine before this call, and its output arrives \
below as a tool result. You don't call tools, verify anything, or decide \
anything yourself: your only job is turning that payload into a short, \
natural reply.

- Acknowledge what the user said based on structured information extracted \
from their message.
- Present exactly what you see in the payload: available courts, booking \
summary, confirmation, etc.
- Never invent information.
- Ask the next question, only from what the payload says to ask. If the \
payload lists an ambiguity to clarify, that IS the next question -- fold it \
into your message instead of also asking the current step's question, and \
don't deliberate over which one takes priority.
- Keep messages short and conversational.

Grounding:
- The only court names, times and prices you may state are the ones in the \
payload (`available_courts` or `booking_so_far`). Never state or imply a \
time, court or price that is not there.
- If the user asks for a time that is not in `available_courts`, say so \
plainly and offer only the times that are.
- A price like `31.3` may be shown as `$31.30` -- that's formatting, not \
rounding or inventing. Never change the numeric value itself.
- The workflow engine re-runs any search itself when a preference changes. \
If the payload shows a changed preference, just acknowledge it and ask the \
payload's next question.
- A booking is only real once the payload contains a confirmation_id.
"""


def _booking_so_far(state) -> dict:
    """Everything the user has settled so far, for the speaker's payload."""
    so_far = {
        slot: getattr(state, slot)
        for slot in (
            "area", "date", "surface", "indoor_outdoor", "duration_minutes", "num_players",
            "selected_time", "skill_level", "equipment_rental", "contact_name", "contact_email",
        )
        if getattr(state, slot) not in (None, "")
    }
    court = next((c for c in state.available_courts if c.court_id == state.selected_court_id), None)
    if court is not None:
        slot = next((s for s in court.slots if s.time == state.selected_time), None)
        so_far["selected_court"] = {
            "name": court.name,
            "address": court.address,
            **({"price_usd": slot.price_usd} if slot else {}),
        }
    return so_far


def create_agent(state=None, client=None, interpreter: Interpreter | None = None) -> ConversationAgent:
    """`client` lets tests inject a fake OpenAI-shaped client.
    `interpreter` lets tests inject a fake Interpreter.
    `state` is passed to BookingWorkflowEngine for symmetry with other agents."""

    # Use a mutable container to allow updates in the nested function
    engine_holder = {"current": BookingWorkflowEngine(state)}
    if interpreter is None:
        interpreter = JevInterpreter()

    # Track Jev calls and interpretations for debugging
    agent_interpretations: list[Interpretation] = []

    def send_user_message_override(text: str) -> str:
        """Override ConversationAgent.send_user_message to implement Jev logic."""
        nonlocal agent_interpretations

        agent._turn += 1
        turn_start = time.perf_counter()
        agent.messages.append({"role": "user", "content": text})

        # Get the last assistant message if any
        last_assistant_msg = ""
        for msg in reversed(agent.messages[:-1]):  # Exclude the just-added user message
            if msg.get("role") == "assistant":
                last_assistant_msg = msg.get("content", "")
                break

        # Interpret the user turn
        interp = interpreter.interpret(engine_holder["current"].state, last_assistant_msg, text)
        agent_interpretations.append(interp)

        # Record Jev call as a usage record (latency, tokens)
        if interp.input_tokens is not None and interp.output_tokens is not None:
            agent.usage_log.append(
                UsageRecord(
                    turn=agent._turn,
                    input_tokens=interp.input_tokens,
                    output_tokens=interp.output_tokens,
                    latency_ms=interp.latency_ms,
                    source="jev",
                )
            )

        # Convert interpretation to updates
        result = to_updates(
            interp,
            engine_holder["current"].state,
            current_node=engine_holder["current"].peek().get("current_node"),
            user_turn=text,
        )

        before = len(engine_holder["current"].internal_tool_calls)

        # Handle restart
        if result.restart:
            before = 0
            engine_holder["current"] = BookingWorkflowEngine(None)
            payload = engine_holder["current"].peek()
        else:
            # Apply updates via engine
            if result.updates:
                payload = engine_holder["current"].handle({"updates": result.updates})
            else:
                # No updates on this turn - use peek
                if agent._turn == 1:
                    # First turn with no updates - use bootstrap call to handle()
                    payload = engine_holder["current"].handle({})
                else:
                    # Later turn with no updates - peek
                    payload = engine_holder["current"].peek()

        # Copy any internal tool calls to the agent's tool_call_log
        for internal in engine_holder["current"].internal_tool_calls[before:]:
            agent.tool_call_log.append(
                ToolCallRecord(turn=agent._turn, name=internal.name, args=internal.args, result=internal.result, agentic=False)
            )

        # Build speaker prompt with payload and interpretation context. The
        # speaker only needs the current step, so drop the lookahead and slot
        # names, and add the whole booking so far (the payload's `applied`
        # only lists this turn's changes).
        speaker_payload = payload
        if isinstance(payload, dict):
            speaker_payload = {k: v for k, v in payload.items() if k not in ("upcoming_instructions", "current_node_slots")}
            speaker_payload["booking_so_far"] = _booking_so_far(engine_holder["current"].state)

        if result.ambiguities:
            speaker_payload["ambiguities_to_clarify"] = result.ambiguities

        if result.act == "asks_question":
            speaker_payload["note"] = "User is asking a question. Answer only from this payload, then ask the current step's question again."
        elif result.act == "off_topic":
            speaker_payload["note"] = "User said something off-topic. Politely redirect to the booking."
        elif result.act == "restart_or_cancel":
            speaker_payload["note"] = "User asked to restart or cancel. Acknowledge and show the first question."

        # Deliver the payload as a tool result, not spliced into a user
        # message: a `tool`-role message is the channel the model was
        # actually fine-tuned to treat as ground truth to quote, the same
        # channel simple_workflow_api's real tool calls use. Handed to it
        # as user-authored text instead, the model tends to treat it as
        # prose to compose rather than data to cite, second-guessing
        # verbatim values (a price's decimal formatting, a court's exact
        # name) that a real tool result would just be trusted as-is. The
        # `tool_calls`/`tool` pair below is synthetic -- the speaker never
        # actually calls a tool -- but it's the same message shape.
        tool_call_id = f"workflow_payload_turn_{agent._turn}"
        request_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *agent.messages,
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {"name": "get_workflow_payload", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(speaker_payload, separators=(",", ":")),
            },
        ]

        extra_body: dict = {"provider": PROVIDER_ROUTING}
        if agent.reasoning_effort:
            extra_body["reasoning"] = {"effort": agent.reasoning_effort}

        call_start = time.perf_counter()
        response = agent.client.chat.completions.create(
            model=agent.model,
            messages=request_messages,
            # Note: no `tools` parameter - this is a speaker-only call
            extra_body=extra_body,
        )
        latency_ms = (time.perf_counter() - call_start) * 1000

        agent.usage_log.append(
            UsageRecord(
                turn=agent._turn,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                latency_ms=latency_ms,
                reasoning_tokens=usage_details(response.usage)[0],
                cached_tokens=usage_details(response.usage)[1],
                reasoning_text=reasoning_text(response),
            )
        )

        message_content = response.choices[0].message.content or ""
        agent.messages.append({"role": "assistant", "content": message_content})

        agent.turn_latencies_ms.append((time.perf_counter() - turn_start) * 1000)
        return message_content.strip()

    # Create the base agent with no tools
    agent = ConversationAgent(
        system_prompt=SYSTEM_PROMPT,
        tools=[],
        tool_executors={},
        client=client,
    )

    # Attach state and interpreter for tests, then override send_user_message
    # Note: state property will be updated as engine restarts, use lambda to access current
    agent.fsm_agent = engine_holder["current"]  # type: ignore[attr-defined]
    agent.interpretations = agent_interpretations  # type: ignore[attr-defined]
    agent.send_user_message = send_user_message_override  # type: ignore[method-assign]

    return agent
