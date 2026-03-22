# SkyView Property Bot — Testing Guide

## Overview

**SkyView Property Bot** is an AI concierge assistant for a short-term rental company in Kuala Lumpur. Guests message it via WhatsApp to ask about their stay — WiFi passwords, door codes, parking, check-out times, local restaurants, house rules, and more.

This guide covers how to run the **web chat UI** for testing and evaluating LLM performance: response quality, intent classification, multilingual support, token usage, and latency.

### Architecture

```
Guest message
    │
    ├─► Parallel retrieval
    │       ├─ General policies        (data/properties.json)
    │       ├─ Building info           (data/properties.json)
    │       ├─ Unit info               (data/properties.json)
    │       └─ Narrative chunks        (ChromaDB vector search)
    │
    └─► LLM call (OpenRouter)
            └─ Structured JSON response
                    ├─ intent
                    ├─ language
                    ├─ building_extracted / unit_extracted
                    ├─ needs_clarification
                    └─ response (the reply text)
```

---

## Prerequisites

- Python 3.10+
- An [OpenRouter](https://openrouter.ai) API key
- A `.env` file in the project root

**Set up `.env`:**
```bash
cp .env.example .env
# Then open .env and fill in your OPENROUTER_API_KEY
```

`.env` fields:

| Field | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | *(required)* | Your OpenRouter API key |
| `MODEL` | `deepseek/deepseek-chat` | LLM model to use |
| `CHROMA_PATH` | `./data/chroma` | ChromaDB storage path |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-mpnet-base-v2` | Sentence transformer model |
| `TOP_K_CHUNKS` | `3` | Number of narrative chunks retrieved per message |
| `MAX_HISTORY_TURNS` | `6` | Conversation turns kept in memory |
| `PROMPT_VERSION` | `v1` | System prompt version (loads `prompts/system_v1.txt`) |

---

## Installation

```bash
pip install -r requirements.txt
```

> **Note:** The first run downloads the embedding model (`paraphrase-multilingual-mpnet-base-v2`, ~280MB). This is cached locally by `sentence-transformers` and won't re-download on subsequent runs.

---

## Ingesting Documents

Before using the bot, embed the narrative documents into ChromaDB:

```bash
python scripts/ingest.py
```

This reads all `.txt` files from `data/documents/` (area guide, FAQ, house rules), chunks them by paragraph, embeds them, and stores them in `data/chroma/`.

Run this once, or again whenever you update the documents.

---

## Running the Web UI

```bash
streamlit run scripts/chat_ui.py
```

Opens at **http://localhost:8501** in your browser.

### Sidebar controls

| Control | Description |
|---|---|
| **Phone** | Session identifier. Change to simulate a different guest. |
| **Building (pre-seed)** | Pre-set building before the conversation starts (e.g. `tower_a`). Takes effect on Reset. |
| **Unit (pre-seed)** | Pre-set unit (e.g. `3-05`). Takes effect on Reset. |
| **Reset Session** | Clears chat history, token totals, and backend session. Re-applies pre-seed if set. |
| **Current Session State** | Live view of what the bot knows: state, building, unit, language, history depth. |
| **Cumulative Token Usage** | Running total of input/output/grand total tokens for this conversation. |
| **Last Message Stats** | Intent, language, latency, and per-message token counts for the most recent reply. |

---

## Running the CLI Chat (alternative)

If you prefer the terminal:

```bash
python scripts/chat.py
python scripts/chat.py --building tower_a --unit 3-05
python scripts/chat.py --phone +60123456789 --building tower_b --unit 5-01
```

Commands inside the CLI:
- `/reset` — clear session
- `/session` — show session state
- `/model` — show current model
- `quit` / `Ctrl+C` — exit

---

## Understanding the Metrics

### Intent
What the LLM classified the guest's message as. Possible values:

| Intent | Meaning |
|---|---|
| `wifi` | WiFi password question |
| `parking` | Parking bay question |
| `checkin` | Door code / check-in process |
| `checkout` | Check-out time / process |
| `unit_info` | Unit-specific questions (capacity, price, amenities) |
| `building_info` | Building-level questions (facilities, amenities) |
| `narrative` | Questions answered from documents (house rules, area guide, FAQ) |
| `greeting` | Initial greeting / booking enquiry |
| `other` | Anything outside scope |

A correct intent classification means the bot is routing questions properly.

### Language
Detected language of the guest's message:
- `en` — English
- `ms` — Malay (Bahasa Malaysia)
- `zh` — Chinese (Mandarin)

The bot should respond in the same language as the guest.

### Latency (ms)
End-to-end wall time from sending the message to receiving the reply. Includes:
- Parallel retrieval (ChromaDB query + JSON lookup)
- LLM API round-trip (network + model inference)

Typical range: **2,000–8,000 ms** depending on model and network. The embedding model runs locally after the first load, so retrieval is fast. Most latency comes from the LLM API.

### Input Tokens
Tokens sent to the LLM in one call:
- System prompt (with injected context)
- Conversation history
- User message

Higher input token counts mean more context was retrieved or the conversation history is longer. This directly affects cost.

### Output Tokens
Tokens in the LLM's response. This is usually much smaller than input tokens. Also affects cost.

### Grand Total Tokens
Running sum of all input + output tokens for the entire conversation session. Use this to estimate API cost for a full conversation flow.

---

## Interpreting Results

### Signs the retrieval is working
- Bot references specific unit details (WiFi SSID, door code, parking bay number) without being told them in the chat
- Bot uses building-specific information (amenities list matches the right tower)

### Signs the retrieval is NOT working
- Bot says it doesn't have the information when the data is clearly in `data/properties.json` or the documents
- Check: Did you run `python scripts/ingest.py`? Is the building/unit pre-seeded correctly?

### Multilingual testing
Send messages in Malay or Chinese — the bot should detect the language and reply in kind. Mixed-language messages (e.g. English + Malay) should default to the dominant language.

### Token budget guidance
| Scenario | Expected input tokens |
|---|---|
| Fresh session, simple question | ~800–1,200 |
| BOOKED session with full context | ~1,200–1,800 |
| Long conversation (6 turns) | ~2,000–3,000 |

If input tokens are unexpectedly high, check `TOP_K_CHUNKS` (more chunks = more tokens) and `MAX_HISTORY_TURNS`.

### What good responses look like
- Specific and grounded in property data (not generic)
- Correct language match
- Warm and concise tone (this is WhatsApp, not formal email)
- If `needs_clarification: true` in the raw response, the bot asks a follow-up rather than guessing

---

## Session States

| State | Meaning |
|---|---|
| `UNKNOWN` | No building or unit known yet |
| `PRE_BOOKING` | Building known OR unit known (but not both) |
| `BOOKED` | Both building and unit are confirmed |

The bot retrieves unit-specific data (WiFi, door code, parking) only when in `BOOKED` state. Pre-seed building + unit via the sidebar and reset to simulate a booked guest.

**Available buildings and units** (from `data/properties.json`):
- `tower_a` — units: `3-05`, `18-02`
- `tower_b` — units: `5-01`, `22-08`

---

## Running the Benchmark (optional)

The benchmark runs all 20 test cases from `eval/test_cases.json` against a live server and reports pass/fail + latency.

Requires the server to be running first:
```bash
uvicorn app.main:app --reload
```

Then in another terminal:
```bash
python scripts/benchmark.py
python scripts/benchmark.py --url http://localhost:8000
```

Results are logged to `eval/logs/<model_name>.jsonl` for later analysis.

---

## System Prompt

The system prompt lives at `prompts/system_v1.txt`. It instructs the LLM to:
- Answer only from provided context (no hallucination)
- Detect and match the guest's language
- Return structured JSON (intent, language, building/unit extraction, clarification flag, response)
- Keep replies warm and concise (WhatsApp style)

To test a different prompt, create `prompts/system_v2.txt` and set `PROMPT_VERSION=v2` in `.env`.
