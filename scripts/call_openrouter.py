"""Thin OpenRouter chat completion wrapper with retry."""
from __future__ import annotations
import json
import os
import time
import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

class OpenRouterError(Exception):
    pass

def call_chat(*, model: str, system: str, user: str,
               max_tokens: int = 4000,
               temperature: float = 0.4,
               max_retries: int = 3,
               api_key: str | None = None,
               timeout: int = 180) -> dict:
    """Call OpenRouter with exponential retry on 429/5xx.

    Returns {"content": str, "usage": dict}.
    Raises OpenRouterError on terminal failure.
    """
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise OpenRouterError("OPENROUTER_API_KEY not set")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ckonyaole/daily-armor-readings",
        "X-Title": "Daily Armor Readings",
    }
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            r = requests.post(OPENROUTER_URL, headers=headers,
                                data=json.dumps(body), timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = OpenRouterError(
                    f"HTTP {r.status_code}: {r.text[:200]}")
                if attempt < max_retries - 1:
                    time.sleep(30 * (2 ** attempt))
                continue
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            return {"content": content, "usage": data.get("usage", {})}
        except requests.RequestException as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(30 * (2 ** attempt))
    raise OpenRouterError(f"all retries exhausted: {last_err}")
