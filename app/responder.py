import asyncio
import json
import time
from pathlib import Path

from app.config import settings
from app.models import ConversationState, LLMResponse, RetrievedContext
from app.lookup import get_general, get_building, get_unit, get_all_units_public, PUBLIC_UNIT_FIELDS
from app.search import query_narrative
from app.llm import call_llm

# Module-level cache for system prompt (loaded once on first call)
_system_prompt: str | None = None


def _load_system_prompt() -> str:
    """Load system prompt from prompts/system_v1.txt (relative to project root)."""
    prompt_path = (
        Path(__file__).parent.parent / "prompts" / f"system_{settings.prompt_version}.txt"
    )
    return prompt_path.read_text(encoding="utf-8")


def _build_context_block(context: RetrievedContext, guest_state: str = "UNKNOWN", booking_id: str | None = None) -> str:
    """Format retrieved context into a readable string block for injection into the prompt."""
    parts = []

    if booking_id and guest_state == "BOOKED":
        short_ref = f"BK-{booking_id.replace('-', '').upper()[:8]}"
        parts.append(f"[BOOKING REFERENCE]\nbooking_id: {short_ref}")

    if context.general:
        lines = ["[GENERAL POLICIES]"]
        for key, value in context.general.items():
            lines.append(f"{key}: {value}")
        parts.append("\n".join(lines))

    if context.building:
        lines = ["[BUILDING INFO]"]
        for key, value in context.building.items():
            lines.append(f"{key}: {value}")
        parts.append("\n".join(lines))

    if context.unit:
        lines = ["[UNIT DETAILS]"]
        unit_fields = context.unit if guest_state == "BOOKED" else {
            k: v for k, v in context.unit.items() if k in PUBLIC_UNIT_FIELDS
        }
        for key, value in unit_fields.items():
            lines.append(f"{key}: {value}")
        parts.append("\n".join(lines))
    else:
        all_units = get_all_units_public()
        if all_units:
            lines = ["[ALL UNITS OVERVIEW]"]
            for u in all_units:
                lines.append(
                    f"- {u['suite_name']} (unit {u['unit_id']}, {u['building_id']}): "
                    f"floor {u['floor']}, {u['room_type']}, up to {u['max_pax']} guests, "
                    f"RM{u['price_per_night']}/night — {u['description']}"
                )
            parts.append("\n".join(lines))

    if context.narrative_chunks:
        lines = ["[RELEVANT DOCUMENTS]"]
        for chunk in context.narrative_chunks:
            lines.append("<chunk>")
            lines.append(chunk)
            lines.append("</chunk>")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)



async def generate_response(
    phone: str,
    message: str,
    session: ConversationState,
) -> tuple[LLMResponse, int, int, int]:
    """
    Full Option C pipeline: parallel retrieval → single LLM call → parse response.

    Returns: (LLMResponse, input_tokens, output_tokens, latency_ms)
    """
    global _system_prompt

    start = time.monotonic()

    # Step 1: Parallel retrieval
    general, building_info, unit_info, narrative = await asyncio.gather(
        asyncio.to_thread(get_general),
        asyncio.to_thread(get_building, session.building or ""),
        asyncio.to_thread(get_unit, session.building or "", session.unit or ""),
        query_narrative(message, session.building, settings.top_k_chunks),
    )

    # Step 2: Build RetrievedContext
    context = RetrievedContext(
        general=general,
        building=building_info,
        unit=unit_info,
        narrative_chunks=narrative,
    )

    # Step 3: Load system prompt (cached after first load)
    if _system_prompt is None:
        _system_prompt = _load_system_prompt()

    # Step 4: Build context block
    context_block = _build_context_block(context, guest_state=session.state, booking_id=session.booking_id)

    # Step 5: Fill prompt template
    # Use .replace() instead of .format() — the system prompt contains JSON
    # examples with {curly braces} that str.format() would misinterpret as
    # template variables, causing KeyError.
    filled_prompt = _system_prompt.replace("{context_block}", context_block)

    # Step 6: Call LLM with history as native messages array
    response_text, input_tokens, output_tokens = await call_llm(
        system_prompt=filled_prompt,
        user_message=message,
        history=session.history or None,
    )

    # Step 7: Parse JSON response into LLMResponse
    try:
        data = json.loads(response_text)
        llm_response = LLMResponse(**data)
    except (json.JSONDecodeError, Exception):
        llm_response = LLMResponse(
            intent="other",
            language=session.language,
            needs_clarification=False,
            response=response_text,
        )

    # Step 8: Calculate latency
    latency_ms = int((time.monotonic() - start) * 1000)

    return llm_response, input_tokens, output_tokens, latency_ms
