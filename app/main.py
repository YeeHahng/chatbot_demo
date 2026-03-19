from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.config import settings
from app.models import WebhookMessage, EvalLog
from app.session import get_lock, get_session, update_session, add_to_history
from app.search import init_search
from app.responder import generate_response
from app.logger import log_interaction


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: preload embedding model. Shutdown: nothing."""
    # startup
    print(f"Starting SkyView Property Bot...")
    print(f"Model: {settings.model}")
    init_search()  # loads embedding model + connects ChromaDB
    print("Ready!")
    yield
    # shutdown (nothing to clean up)


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
    update_session(req.phone, building=req.building, unit=req.unit, state=req.state)
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
        session = get_session(phone)

        # Run Option C pipeline
        llm_response, input_tokens, output_tokens, latency_ms = await generate_response(
            phone=phone,
            message=message,
            session=session,
        )

        # Update session with extracted building/unit/language from LLM response
        update_session(
            phone,
            building=llm_response.building_extracted,
            unit=llm_response.unit_extracted,
            language=llm_response.language,
            state="BOOKED" if (session.building or llm_response.building_extracted) and (session.unit or llm_response.unit_extracted) else session.state,
        )

        # Add this exchange to history
        add_to_history(phone, "user", message)
        add_to_history(phone, "assistant", llm_response.response)

        # Get updated session for logging
        updated_session = get_session(phone)

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
            context={},  # simplified — full context logging would add overhead
            model=settings.model,
            prompt_version=settings.prompt_version,
            response=llm_response.response,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ))

    return {
        "reply": llm_response.response,
        "intent": llm_response.intent,
        "language": llm_response.language,
    }
