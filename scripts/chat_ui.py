#!/usr/bin/env python3
"""
SkyView Property Bot — Streamlit Web Chat UI

Run from project root:
    streamlit run scripts/chat_ui.py

No server needed — runs the full pipeline directly.
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from app.config import settings
from app.search import init_search
from app.models import ConversationState
from app.responder import generate_response

# ── Page config (must be first Streamlit call) ──────────────────────────────
st.set_page_config(
    page_title="SkyView Property Bot",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEFAULT_PHONE = "+60100000999"


# ── One-time init: load embedding model + ChromaDB ───────────────────────────
@st.cache_resource
def load_search():
    """Load embedding model and ChromaDB once for the lifetime of the process."""
    init_search()
    return True


load_search()


# ── Session state init ────────────────────────────────────────────────────────
def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "total_input_tokens" not in st.session_state:
        st.session_state.total_input_tokens = 0
    if "total_output_tokens" not in st.session_state:
        st.session_state.total_output_tokens = 0
    if "phone" not in st.session_state:
        st.session_state.phone = DEFAULT_PHONE
    if "building_seed" not in st.session_state:
        st.session_state.building_seed = ""
    if "unit_seed" not in st.session_state:
        st.session_state.unit_seed = ""
    # Session fields tracked in UI state (no DB reads needed)
    if "guest_state" not in st.session_state:
        st.session_state.guest_state = "UNKNOWN"
    if "building" not in st.session_state:
        st.session_state.building = None
    if "unit" not in st.session_state:
        st.session_state.unit = None
    if "language" not in st.session_state:
        st.session_state.language = "en"
    if "booking_id" not in st.session_state:
        st.session_state.booking_id = None


init_session_state()


def _build_session() -> ConversationState:
    """Build ConversationState from UI state — no DB round-trip needed."""
    history = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in st.session_state.messages
        if msg["role"] in ("user", "assistant")
    ]
    return ConversationState(
        phone=st.session_state.phone,
        state=st.session_state.guest_state,
        building=st.session_state.building,
        unit=st.session_state.unit,
        language=st.session_state.language,
        history=history,
        booking_id=st.session_state.booking_id,
    )


# ── Pipeline helper ──────────────────────────────────────────────────────────
def send_message(user_text: str) -> dict:
    """Run the full pipeline. All async work in one asyncio.run() call."""
    phone = st.session_state.phone
    session = _build_session()

    async def _run():
        llm_response, input_tokens, output_tokens, latency_ms = await generate_response(
            phone=phone, message=user_text, session=session
        )

        building_final = session.building or llm_response.building_extracted
        unit_final = session.unit or llm_response.unit_extracted
        new_state = "BOOKED" if (building_final and unit_final) else session.state

        booking_id = session.booking_id
        final_reply = llm_response.response

        if new_state == "BOOKED" and session.state != "BOOKED":
            # Create booking with its own fresh DB pool inside this same event loop
            from app.db import init_db_pool, close_db_pool, create_booking
            await init_db_pool()
            try:
                booking_uuid = await create_booking(phone, building_final, unit_final)
                booking_id = str(booking_uuid)
                short_ref = f"BK-{booking_id.replace('-', '').upper()[:8]}"
                final_reply = llm_response.response + f"\n\n📋 Booking reference: **{short_ref}**"
            finally:
                await close_db_pool()

        return llm_response, input_tokens, output_tokens, latency_ms, new_state, booking_id, final_reply, building_final, unit_final

    llm_response, input_tokens, output_tokens, latency_ms, new_state, booking_id, final_reply, building_final, unit_final = asyncio.run(_run())

    # Update UI session state
    if llm_response.building_extracted:
        st.session_state.building = llm_response.building_extracted
    if llm_response.unit_extracted:
        st.session_state.unit = llm_response.unit_extracted
    st.session_state.guest_state = new_state
    st.session_state.language = llm_response.language
    if booking_id:
        st.session_state.booking_id = booking_id

    return {
        "response": final_reply,
        "intent": llm_response.intent,
        "language": llm_response.language,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


# ── Reset helper ─────────────────────────────────────────────────────────────
def reset_session():
    """Clear UI session state and optionally apply pre-seed."""
    st.session_state.messages = []
    st.session_state.total_input_tokens = 0
    st.session_state.total_output_tokens = 0
    st.session_state.booking_id = None

    building = st.session_state.building_seed or None
    unit = st.session_state.unit_seed or None
    st.session_state.building = building
    st.session_state.unit = unit
    st.session_state.guest_state = "BOOKED" if (building and unit) else ("PRE_BOOKING" if (building or unit) else "UNKNOWN")
    st.session_state.language = "en"


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Session Config")

    phone_val = st.text_input("Phone", value=st.session_state.phone)
    st.session_state.phone = phone_val

    building_val = st.text_input("Building (pre-seed)", value=st.session_state.building_seed,
                                  placeholder="e.g. tower_a")
    st.session_state.building_seed = building_val

    unit_val = st.text_input("Unit (pre-seed)", value=st.session_state.unit_seed,
                              placeholder="e.g. 3-05")
    st.session_state.unit_seed = unit_val

    if st.button("Reset Session", type="secondary", use_container_width=True):
        reset_session()
        st.rerun()

    st.divider()

    # Live session state from UI state
    st.subheader("Current Session State")
    st.markdown(f"**Phone:** `{st.session_state.phone}`")
    st.markdown(f"**State:** `{st.session_state.guest_state}`")
    st.markdown(f"**Building:** `{st.session_state.building or '—'}`")
    st.markdown(f"**Unit:** `{st.session_state.unit or '—'}`")
    st.markdown(f"**Language:** `{st.session_state.language}`")
    st.markdown(f"**History turns:** {len(st.session_state.messages) // 2}")

    st.divider()

    # Cumulative token totals
    st.subheader("Cumulative Token Usage")
    grand_total = st.session_state.total_input_tokens + st.session_state.total_output_tokens
    col1, col2 = st.columns(2)
    col1.metric("Input", st.session_state.total_input_tokens)
    col2.metric("Output", st.session_state.total_output_tokens)
    st.metric("Grand Total", grand_total)

    st.divider()

    # Last message stats
    st.subheader("Last Message Stats")
    last_assistant = next(
        (m for m in reversed(st.session_state.messages) if m["role"] == "assistant"), None
    )
    if last_assistant:
        st.markdown(f"**Intent:** `{last_assistant.get('intent', '—')}`")
        st.markdown(f"**Language:** `{last_assistant.get('language', '—')}`")
        st.markdown(f"**Latency:** {last_assistant.get('latency_ms', 0)} ms")
        st.markdown(
            f"**Tokens:** in={last_assistant.get('input_tokens', 0)}  "
            f"out={last_assistant.get('output_tokens', 0)}"
        )
    else:
        st.caption("No messages yet.")

    st.divider()
    st.caption(f"Model: `{settings.model}`")


# ── Main chat area ────────────────────────────────────────────────────────────
st.title("SkyView Property Bot")
st.caption(f"Testing interface  |  Model: `{settings.model}`  |  Phone: `{st.session_state.phone}`")

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            st.caption(
                f"intent: `{msg.get('intent', '—')}`  |  "
                f"lang: `{msg.get('language', '—')}`  |  "
                f"{msg.get('latency_ms', 0)} ms  |  "
                f"in={msg.get('input_tokens', 0)} out={msg.get('output_tokens', 0)} tokens"
            )

# Chat input
if prompt := st.chat_input("Type your message..."):
    # Show user message immediately
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Run pipeline
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                result = send_message(prompt)
                error_msg = None
            except Exception as e:
                result = None
                error_msg = str(e)

    if result is None:
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"Error: {error_msg}",
            "intent": "error",
            "language": "—",
            "latency_ms": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        })
    else:
        st.session_state.total_input_tokens += result["input_tokens"]
        st.session_state.total_output_tokens += result["output_tokens"]
        st.session_state.messages.append({
            "role": "assistant",
            "content": result["response"],
            "intent": result["intent"],
            "language": result["language"],
            "latency_ms": result["latency_ms"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
        })

    # Rerun to refresh sidebar metrics
    st.rerun()
