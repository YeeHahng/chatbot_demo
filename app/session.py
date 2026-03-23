import asyncio
from app.models import ConversationState
from app.config import settings

# Per-phone asyncio locks for in-process concurrency safety
_locks: dict[str, asyncio.Lock] = {}


def get_lock(phone: str) -> asyncio.Lock:
    """Get or create a per-phone asyncio.Lock."""
    if phone not in _locks:
        _locks[phone] = asyncio.Lock()
    return _locks[phone]


def get_session(phone: str) -> ConversationState:
    """
    Fetch session from DB synchronously (via asyncio.run).
    Falls back to a fresh UNKNOWN state if no session exists.
    Used by sync callers (e.g. Streamlit).
    """
    import asyncio as _asyncio
    try:
        loop = _asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an async context — caller should use get_session_async
            from app.db import get_session_db
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(_asyncio.run, get_session_db(phone))
                row = future.result()
        else:
            from app.db import get_session_db
            row = loop.run_until_complete(get_session_db(phone))
    except Exception:
        row = None

    if row is None:
        return ConversationState(phone=phone)
    return ConversationState(
        phone=row["phone"],
        state=row["state"],
        building=row.get("building"),
        unit=row.get("unit"),
        language=row.get("language", "en"),
        history=row.get("history", []),
        booking_id=row.get("booking_id"),
    )


async def get_session_async(phone: str) -> ConversationState:
    """Async version — preferred inside FastAPI request handlers."""
    from app.db import get_session_db
    row = await get_session_db(phone)
    if row is None:
        return ConversationState(phone=phone)
    return ConversationState(
        phone=row["phone"],
        state=row["state"],
        building=row.get("building"),
        unit=row.get("unit"),
        language=row.get("language", "en"),
        history=row.get("history", []),
        booking_id=row.get("booking_id"),
    )


async def update_session_async(phone: str, **kwargs) -> ConversationState:
    """
    Persist session fields to DB. Skips None values for building/unit.
    Returns the refreshed ConversationState.
    """
    from app.db import upsert_session_db
    max_entries = settings.max_history_turns * 2
    await upsert_session_db(phone, max_history_entries=max_entries, **kwargs)
    return await get_session_async(phone)


def update_session(phone: str, **kwargs) -> ConversationState:
    """
    Sync wrapper around update_session_async.
    Used by Streamlit / non-async callers.
    """
    import asyncio as _asyncio
    try:
        loop = _asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(_asyncio.run, update_session_async(phone, **kwargs))
                return future.result()
        else:
            return loop.run_until_complete(update_session_async(phone, **kwargs))
    except Exception:
        return ConversationState(phone=phone)


async def add_to_history_async(phone: str, role: str, content: str) -> None:
    """Async: append one history entry to the DB session."""
    from app.db import append_history_db
    max_entries = settings.max_history_turns * 2
    await append_history_db(phone, role, content, max_history_entries=max_entries)


def add_to_history(phone: str, role: str, content: str) -> None:
    """Sync wrapper around add_to_history_async."""
    import asyncio as _asyncio
    try:
        loop = _asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(_asyncio.run, add_to_history_async(phone, role, content))
                future.result()
        else:
            loop.run_until_complete(add_to_history_async(phone, role, content))
    except Exception:
        pass
