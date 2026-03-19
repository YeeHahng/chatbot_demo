import asyncio
from app.models import ConversationState
from app.config import settings

# Module-level storage
_sessions: dict[str, ConversationState] = {}
_locks: dict[str, asyncio.Lock] = {}


def get_lock(phone: str) -> asyncio.Lock:
    """Get or create a per-phone asyncio.Lock."""
    if phone not in _locks:
        _locks[phone] = asyncio.Lock()
    return _locks[phone]


def get_session(phone: str) -> ConversationState:
    """Get existing session or create new UNKNOWN state."""
    if phone not in _sessions:
        _sessions[phone] = ConversationState(phone=phone)
    return _sessions[phone]


def update_session(phone: str, **kwargs) -> ConversationState:
    """
    Update fields on a session. Returns updated session.
    Only updates fields that are provided (skip None values for
    building/unit to avoid overwriting known values with null).
    """
    session = get_session(phone)

    # Build update dict, handling building and unit specially
    update_dict = {}
    for key, value in kwargs.items():
        if key in ("building", "unit"):
            # Only update if value is not None
            if value is not None:
                update_dict[key] = value
        else:
            # Always update for other fields
            update_dict[key] = value

    # Use model_copy with update if there are changes
    if update_dict:
        session = session.model_copy(update=update_dict)
        _sessions[phone] = session

    return session


def add_to_history(phone: str, role: str, content: str) -> None:
    """
    Append {"role": role, "content": content} to session history.
    Trim history to last max_history_turns*2 entries (user+assistant pairs).
    """
    session = get_session(phone)
    session.history.append({"role": role, "content": content})

    # Trim to keep only last max_history_turns * 2 entries
    max_entries = settings.max_history_turns * 2
    if len(session.history) > max_entries:
        session.history = session.history[-max_entries:]
