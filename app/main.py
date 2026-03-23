from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.config import settings
from app.models import WebhookMessage, EvalLog
from app.session import get_lock, get_session_async, update_session_async, add_to_history_async
from app.search import init_search
from app.responder import generate_response
from app.logger import log_interaction
from app.db import init_db_pool, close_db_pool, create_booking


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB pool + embedding model. Shutdown: close pool."""
    print(f"Starting SkyView Property Bot...")
    print(f"Model: {settings.model}")
    await init_db_pool()
    init_search()  # loads embedding model + connects ChromaDB
    print("Ready!")
    yield
    await close_db_pool()


app = FastAPI(title="SkyView Property Bot", lifespan=lifespan)


class SeedRequest(BaseModel):
    phone: str
    building: str | None = None
    unit: str | None = None
    state: Literal["UNKNOWN", "PRE_BOOKING", "BOOKED"] = "UNKNOWN"


@app.get("/health")
async def health():
    return {"status": "ok", "model": settings.model}


@app.post("/seed")
async def seed_session(req: SeedRequest):
    """Pre-seed a session with known building/unit/state. Used by benchmark.py."""
    await update_session_async(
        req.phone, building=req.building, unit=req.unit, state=req.state
    )
    return {"seeded": req.phone, "building": req.building, "unit": req.unit, "state": req.state}


@app.post("/webhook")
async def webhook(msg: WebhookMessage):
    """
    Main entry point. Receives a guest message, runs full pipeline, returns reply.
    """
    phone = msg.phone
    message = msg.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Empty message")

    # Acquire per-phone lock to prevent concurrent session corruption
    lock = get_lock(phone)
    async with lock:
        session = await get_session_async(phone)

        # Run Option C pipeline
        llm_response, input_tokens, output_tokens, latency_ms = await generate_response(
            phone=phone,
            message=message,
            session=session,
        )

        # Determine new state and booking ID
        building_final = session.building or llm_response.building_extracted
        unit_final = session.unit or llm_response.unit_extracted
        new_state = "BOOKED" if (building_final and unit_final) else session.state

        booking_id: str | None = None
        final_reply = llm_response.response

        if new_state == "BOOKED" and session.state != "BOOKED":
            # Fresh BOOKED transition — create booking record
            booking_uuid = await create_booking(phone, building_final, unit_final)
            booking_id = str(booking_uuid)
            short_ref = f"BK-{booking_id.replace('-', '').upper()[:8]}"
            final_reply = llm_response.response + f"\n\n📋 Booking reference: **{short_ref}**"

        # Persist session state
        await update_session_async(
            phone,
            building=llm_response.building_extracted,
            unit=llm_response.unit_extracted,
            language=llm_response.language,
            state=new_state,
            booking_id=booking_id or (session.booking_id if session.state == "BOOKED" else None),
        )

        # Persist conversation history
        await add_to_history_async(phone, "user", message)
        await add_to_history_async(phone, "assistant", final_reply)

        # Get updated session for logging
        updated_session = await get_session_async(phone)

        # Log the interaction
        await log_interaction(EvalLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            phone=phone,
            question=message,
            language_detected=llm_response.language,
            guest_state=updated_session.state,
            building=updated_session.building,
            unit=updated_session.unit,
            intent=llm_response.intent,
            context={},
            model=settings.model,
            prompt_version=settings.prompt_version,
            response=final_reply,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            booking_id=booking_id,
        ))

    return {
        "reply": final_reply,
        "intent": llm_response.intent,
        "language": llm_response.language,
        "booking_id": booking_id,
    }
