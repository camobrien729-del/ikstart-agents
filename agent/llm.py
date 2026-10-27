"""One small client for the AI model. Returns parsed JSON, with retries.

Providers (set LLM_PROVIDER):
  gemini     Google Gemini API, free tier (default). Needs GEMINI_API_KEY.
  anthropic  Claude API (paid, very cheap per run). Needs ANTHROPIC_API_KEY.
  demo       No AI at all: fills the writing from templates. For testing only.
"""
from __future__ import annotations

import json
import os
import re
import time

import requests

GEMINI_MODELS = [m for m in os.environ.get(
    "GEMINI_MODEL", "gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite").split(",") if m]
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


class LLMError(Exception):
    pass


def provider() -> str:
    return os.environ.get("LLM_PROVIDER", "gemini").lower()


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("Model did not return JSON")
    return json.loads(text[start:end + 1])


def _gemini(system: str, user: str) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise LLMError("GEMINI_API_KEY is not set")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
    }
    last = None
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        r = requests.post(url, json=body, headers={"x-goog-api-key": key}, timeout=120)
        if r.status_code == 404:  # model not available on this key: try the next one
            last = f"{model}: not found"
            continue
        if r.status_code >= 400:
            raise LLMError(f"Gemini error {r.status_code}: {r.text[:300]}")
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    raise LLMError(f"No Gemini model available ({last}). Set GEMINI_MODEL.")


def _anthropic(system: str, user: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise LLMError("ANTHROPIC_API_KEY is not set")
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": ANTHROPIC_MODEL, "max_tokens": 4000, "temperature": 0.4, "system": system,
              "messages": [{"role": "user", "content": user + "\n\nReturn JSON only."}]},
        timeout=120,
    )
    if r.status_code >= 400:
        raise LLMError(f"Claude error {r.status_code}: {r.text[:300]}")
    return "".join(b.get("text", "") for b in r.json()["content"])


def ask_json(system: str, user: str, attempts: int = 3) -> dict:
    """Ask the model and return a parsed JSON object. Retries on bad output or rate limits."""
    call = {"gemini": _gemini, "anthropic": _anthropic}.get(provider())
    if call is None:
        raise LLMError(f"Unknown LLM_PROVIDER {provider()!r}")
    err = None
    for i in range(attempts):
        try:
            return _extract_json(call(system, user))
        except (LLMError, json.JSONDecodeError, KeyError, requests.RequestException) as e:
            err = e
            time.sleep(5 * (i + 1))
    raise LLMError(f"AI call failed after {attempts} tries: {err}")
