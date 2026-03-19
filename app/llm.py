import httpx
import json
from app.config import settings


async def call_llm(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
) -> tuple[str, int, int]:
    """
    Call OpenRouter chat completions API.

    Returns: (response_text, input_tokens, output_tokens)
    Raises: httpx.HTTPStatusError on non-2xx responses
    """
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://skyview-suites.com",
        "X-Title": "SkyView Property Bot",
    }

    body = {
        "model": model or settings.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=body)
        response.raise_for_status()

        response_json = response.json()

        # Extract response text
        response_text = response_json["choices"][0]["message"]["content"]

        # Extract tokens (default to 0 if usage key is missing)
        usage = response_json.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        return response_text, input_tokens, output_tokens
