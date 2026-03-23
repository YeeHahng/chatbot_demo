import asyncio
import json
from datetime import datetime
from pathlib import Path
from app.models import EvalLog
from app.config import settings


async def log_interaction(log: EvalLog) -> None:
    """
    Log interaction to PostgreSQL interaction_logs table.
    Optionally also writes to JSONL file if settings.log_to_file is True.
    """
    # Primary: DB log
    try:
        from app.db import log_interaction_db
        await log_interaction_db(log.model_dump(), booking_id=log.booking_id)
    except Exception as e:
        # Don't let logging failure break the request — fallback to file
        print(f"[logger] DB log failed: {e} — falling back to file")
        await _write_jsonl(log)
        return

    # Optional secondary: JSONL file (for local dev / debugging)
    if settings.log_to_file:
        await _write_jsonl(log)


async def _write_jsonl(log: EvalLog) -> None:
    """Append one JSON line to eval/logs/<model_safe_name>.jsonl."""
    safe_model_name = log.model.replace("/", "_").replace(":", "_")
    log_dir = Path(__file__).parent.parent / "eval" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_path = log_dir / f"{safe_model_name}.jsonl"

    def write_log():
        with open(file_path, "a") as f:
            f.write(json.dumps(log.model_dump()) + "\n")

    await asyncio.to_thread(write_log)
