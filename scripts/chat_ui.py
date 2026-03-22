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
from app.session import get_session, update_session, add_to_history, _sessions
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
    return True  # sentinel so cache_resource has something to store


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


init_session_state()


# ── Apply pre-seed on fresh session ──────────────────────────────────────────
def apply_preseed():
    building = st.session_state.building_seed or None
    unit = st.session_state.unit_seed or None
    if (building or unit) and not st.session_state.messages:
        state = "BOOKED" if (building and unit) else "PRE_BOOKING"
        update_session(st.session_state.phone, building=building, unit=unit, state=state)


apply_preseed()


# ── Pipeline helper ──────────────────────────────────────────────────────────
def send_message(user_text: str) -> dict:
    """Run the full pipeline. Returns response dict with stats."""
    phone = st.session_state.phone
    session = get_session(phone)

    # asyncio.run() is safe here — Streamlit runs in a sync thread context
    # Do NOT use get_lock() — asyncio.Lock is bound to a specific event loop
    llm_response, input_tokens, output_tokens, latency_ms = asyncio.run(
        generate_response(phone=phone, message=user_text, session=session)
    )

    # Update session (mirrors chat.py lines 122-130)
    update_session(
        phone,
        building=llm_response.building_extracted,
        unit=llm_response.unit_extracted,
        language=llm_response.language,
        state=(
            "BOOKED"
            if (session.building or llm_response.building_extracted)
            and (session.unit or llm_response.unit_extracted)
            else session.state
        ),
    )
    add_to_history(phone, "user", user_text)
    add_to_history(phone, "assistant", llm_response.response)

    return {
        "response": llm_response.response,
        "intent": llm_response.intent,
        "language": llm_response.language,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


# ── Reset helper ─────────────────────────────────────────────────────────────
def reset_session():
    """Clear backend session store and UI state, optionally re-seed."""
    phone = st.session_state.phone
    # Clear backend session (mirrors chat.py /reset pattern)
    if phone in _sessions:
        del _sessions[phone]
    # Re-seed if building/unit configured
    building = st.session_state.building_seed or None
    unit = st.session_state.unit_seed or None
    if building or unit:
        state = "BOOKED" if (building and unit) else "PRE_BOOKING"
        update_session(phone, building=building, unit=unit, state=state)
    # Clear UI state
    st.session_state.messages = []
    st.session_state.total_input_tokens = 0
    st.session_state.total_output_tokens = 0


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

    # Live session state from backend
    st.subheader("Current Session State")
    current_session = get_session(st.session_state.phone)
    st.markdown(f"**Phone:** `{current_session.phone}`")
    st.markdown(f"**State:** `{current_session.state}`")
    st.markdown(f"**Building:** `{current_session.building or '—'}`")
    st.markdown(f"**Unit:** `{current_session.unit or '—'}`")
    st.markdown(f"**Language:** `{current_session.language}`")
    st.markdown(f"**History turns:** {len(current_session.history) // 2}")

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
