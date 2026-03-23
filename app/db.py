"""
PostgreSQL connection pool and DB helper functions.
Uses asyncpg for async access.

Pool is initialized once at FastAPI startup via init_db_pool()
and closed at shutdown via close_db_pool().
"""
import uuid
import json
import asyncpg
from app.config import settings

# Module-level pool singleton
_pool: asyncpg.Pool | None = None


async def init_db_pool() -> None:
    """Create asyncpg connection pool. Called once at FastAPI startup."""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.postgres_dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )


async def close_db_pool() -> None:
    """Gracefully close pool. Called at FastAPI shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the active pool. Raises if not initialized."""
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call init_db_pool() first.")
    return _pool


# ── Guest helpers ─────────────────────────────────────────────────────────────

async def upsert_guest(phone: str, language: str = "en") -> None:
    """Insert guest if not exists, or update language and last_active_at."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO guests (phone, language_pref)
            VALUES ($1, $2)
            ON CONFLICT (phone) DO UPDATE
                SET language_pref  = EXCLUDED.language_pref,
                    last_active_at = NOW()
        """, phone, language)


# ── Booking helpers ───────────────────────────────────────────────────────────

async def create_booking(phone: str, building_id: str, unit_id: str) -> uuid.UUID:
    """
    Upsert guest then create a new booking row.
    Returns the generated booking UUID.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # Ensure guest row exists (FK requirement)
        await conn.execute("""
            INSERT INTO guests (phone)
            VALUES ($1)
            ON CONFLICT (phone) DO UPDATE SET last_active_at = NOW()
        """, phone)

        row = await conn.fetchrow("""
            INSERT INTO bookings (phone, building_id, unit_id)
            VALUES ($1, $2, $3)
            RETURNING booking_id
        """, phone, building_id, unit_id)

    return row["booking_id"]


# ── Session helpers ───────────────────────────────────────────────────────────

async def get_session_db(phone: str) -> dict | None:
    """
    Fetch session row for phone. Returns dict with all session fields,
    or None if no session exists.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM sessions WHERE phone = $1", phone
        )
    if row is None:
        return None
    result = dict(row)
    # asyncpg returns JSONB as a string — parse it
    if isinstance(result.get("history"), str):
        result["history"] = json.loads(result["history"])
    # Convert UUID to string for Pydantic compatibility
    if result.get("booking_id") is not None:
        result["booking_id"] = str(result["booking_id"])
    return result


async def upsert_session_db(
    phone: str,
    state: str | None = None,
    building: str | None = None,
    unit: str | None = None,
    language: str | None = None,
    history: list | None = None,
    booking_id: str | None = None,
    max_history_entries: int = 12,
) -> None:
    """
    Upsert session row. Only non-None kwargs are applied.
    building and unit are never overwritten with None (preserves known values).
    history is trimmed to max_history_entries before saving.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # Ensure guest row exists first
        await conn.execute("""
            INSERT INTO guests (phone)
            VALUES ($1)
            ON CONFLICT (phone) DO UPDATE SET last_active_at = NOW()
        """, phone)

        # Ensure session row exists
        await conn.execute("""
            INSERT INTO sessions (phone)
            VALUES ($1)
            ON CONFLICT (phone) DO NOTHING
        """, phone)

        # Build SET clause dynamically for non-None fields
        # building/unit: never overwrite with None
        sets = ["updated_at = NOW()"]
        args = [phone]
        idx = 2  # $1 is phone

        if state is not None:
            sets.append(f"state = ${idx}")
            args.append(state)
            idx += 1

        if building is not None:
            sets.append(f"building = ${idx}")
            args.append(building)
            idx += 1

        if unit is not None:
            sets.append(f"unit = ${idx}")
            args.append(unit)
            idx += 1

        if language is not None:
            sets.append(f"language = ${idx}")
            args.append(language)
            idx += 1

        if history is not None:
            trimmed = history[-max_history_entries:]
            sets.append(f"history = ${idx}::jsonb")
            args.append(json.dumps(trimmed))
            idx += 1

        if booking_id is not None:
            sets.append(f"booking_id = ${idx}")
            args.append(uuid.UUID(booking_id))
            idx += 1

        if len(sets) > 1:  # more than just updated_at
            sql = f"UPDATE sessions SET {', '.join(sets)} WHERE phone = $1"
            await conn.execute(sql, *args)


async def append_history_db(
    phone: str,
    role: str,
    content: str,
    max_history_entries: int = 12,
) -> None:
    """
    Atomically append a history entry to the session JSONB column and trim.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # Ensure session exists
        await conn.execute("""
            INSERT INTO guests (phone) VALUES ($1)
            ON CONFLICT (phone) DO UPDATE SET last_active_at = NOW()
        """, phone)
        await conn.execute("""
            INSERT INTO sessions (phone) VALUES ($1)
            ON CONFLICT (phone) DO NOTHING
        """, phone)

        # Fetch current history, append, trim, save back
        row = await conn.fetchrow(
            "SELECT history FROM sessions WHERE phone = $1", phone
        )
        current = json.loads(row["history"]) if row and row["history"] else []
        new_entry = {"role": role, "content": content}
        updated = (current + [new_entry])[-max_history_entries:]

        await conn.execute("""
            UPDATE sessions SET history = $2::jsonb, updated_at = NOW()
            WHERE phone = $1
        """, phone, json.dumps(updated))


# ── Interaction log helpers ───────────────────────────────────────────────────

async def log_interaction_db(log_data: dict, booking_id: str | None = None) -> None:
    """Insert one row into interaction_logs."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO interaction_logs (
                phone, question, language_detected, guest_state,
                building, unit, intent, context, model, prompt_version,
                response, latency_ms, input_tokens, output_tokens, booking_id
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10,
                $11, $12, $13, $14, $15
            )
        """,
            log_data["phone"],
            log_data["question"],
            log_data["language_detected"],
            log_data["guest_state"],
            log_data.get("building"),
            log_data.get("unit"),
            log_data["intent"],
            json.dumps(log_data.get("context", {})),
            log_data["model"],
            log_data["prompt_version"],
            log_data["response"],
            log_data["latency_ms"],
            log_data["input_tokens"],
            log_data["output_tokens"],
            uuid.UUID(booking_id) if booking_id else None,
        )
