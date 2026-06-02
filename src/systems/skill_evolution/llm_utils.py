"""LLM call utilities for the Skill Evolution pipeline.

Wraps litellm calls with structured JSON extraction, retries, and logging.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import litellm

from .prompts import load_prompt

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from LLM output, handling markdown fences."""
    text = text.strip()
    m = _JSON_BLOCK_RE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    return None


def chat_llm(
    *,
    system: str,
    user: str,
    model: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    retries: int = 3,
) -> str:
    """Call LLM via litellm with retries. Returns raw response text."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            response = litellm.completion(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            last_err = e
            wait = 2 ** attempt
            logger.warning(
                "[llm_utils] attempt %d/%d failed: %s — retrying in %ds",
                attempt + 1,
                retries,
                e,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"LLM call failed after {retries} retries: {last_err}")


def chat_llm_json(
    *,
    system: str,
    user: str,
    model: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    retries: int = 3,
) -> dict[str, Any]:
    """Call LLM and parse JSON from the response."""
    raw = chat_llm(
        system=system,
        user=user,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        retries=retries,
    )
    result = extract_json(raw)
    if result is None:
        raise ValueError(f"Failed to parse JSON from LLM response: {raw[:500]}")
    return result
