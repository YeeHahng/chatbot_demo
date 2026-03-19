from typing import Literal
from pydantic import BaseModel

class ConversationState(BaseModel):
    phone: str
    state: Literal["UNKNOWN", "PRE_BOOKING", "BOOKED"] = "UNKNOWN"
    building: str | None = None
    unit: str | None = None
    language: str = "en"
    history: list[dict] = []

class LLMResponse(BaseModel):
    intent: str
    building_extracted: str | None = None
    unit_extracted: str | None = None
    language: str = "en"
    needs_clarification: bool = False
    clarification_question: str | None = None
    response: str

class RetrievedContext(BaseModel):
    general: dict = {}
    building: dict = {}
    unit: dict = {}
    narrative_chunks: list[str] = []

class EvalLog(BaseModel):
    timestamp: str
    phone: str
    question: str
    language_detected: str
    guest_state: str
    building: str | None
    unit: str | None
    intent: str
    context: dict
    model: str
    prompt_version: str
    response: str
    latency_ms: int
    input_tokens: int
    output_tokens: int

class WebhookMessage(BaseModel):
    phone: str
    message: str
