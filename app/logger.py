import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from app.models import EvalLog


async def log_interaction(log: EvalLog) -> None:
    """
    Append one JSON line to eval/logs/<model_safe_name>.jsonl

    Model name sanitization: replace "/" and ":" with "_"
    Example: "deepseek/deepseek-chat" -> "deepseek_deepseek-chat.jsonl"
    """
    # Sanitize model name: replace "/" and ":" with "_"
    safe_model_name = log.model.replace("/", "_").replace(":", "_")

    # Create log directory path
    log_dir = Path(__file__).parent.parent / "eval" / "logs"

    # Create directory if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)

    # Construct file path
    file_path = log_dir / f"{safe_model_name}.jsonl"

    # Write the log as JSON line using asyncio.to_thread
    def write_log():
        with open(file_path, "a") as f:
            f.write(json.dumps(log.model_dump()) + "\n")

    await asyncio.to_thread(write_log)
