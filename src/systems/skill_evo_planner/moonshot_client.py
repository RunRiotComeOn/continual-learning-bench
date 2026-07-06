"""OpenAI-compatible client for the official Moonshot API (api.moonshot.cn).

Exposes the SAME surface the planner family calls on ``BedrockClient``
(``model_id``, ``chat``, ``chat_json``, ``chat_structured``) so it is a drop-in
replacement. Moonshot speaks the OpenAI chat-completions schema, so this wraps the
``openai`` SDK pointed at the Moonshot base URL.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from openai import OpenAI
from pydantic import BaseModel

from .structured_output import validate_with_coercion

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"


def _extract_json(text: str) -> str:
    """Pull the outermost JSON object out of a possibly fenced/prosey reply."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t).strip()
    start = t.find("{")
    if start == -1:
        return t
    depth = 0
    for i in range(start, len(t)):
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                return t[start : i + 1]
    return t[start:]


class MoonshotClient:
    def __init__(
        self,
        api_key: str,
        model_id: str = "kimi-k2.5",
        base_url: str = _DEFAULT_BASE_URL,
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ):
        self.api_key = api_key
        self.model_id = model_id
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def _create(self, messages, max_tokens, temperature, response_format=None):
        # Moonshot's kimi-k2.* models reject any temperature other than 1
        # ("invalid temperature: only 1 is allowed for this model"). kimi is not
        # bitwise-deterministic even at temp 0 anyway, so we force 1 here and lean
        # on N-seed CIs for variance rather than greedy decoding.
        kwargs: dict[str, Any] = dict(
            model=self.model_id,
            messages=messages,
            max_tokens=max_tokens or self.max_tokens,
            temperature=1.0,
        )
        if response_format:
            kwargs["response_format"] = response_format
        return self._client.chat.completions.create(**kwargs)

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        retries: int = 6,
        json_mode: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        msgs = list(messages)
        response_format = None
        if json_mode or json_schema:
            # Moonshot's json_object mode requires the literal word "json" to
            # appear in the conversation; the schema guides the shape.
            response_format = {"type": "json_object"}
            instr = "Respond ONLY with a single valid JSON object, no prose, no code fences."
            if json_schema:
                instr += " It MUST conform to this JSON schema:\n" + json.dumps(
                    json_schema, ensure_ascii=False
                )
            msgs = msgs + [{"role": "system", "content": instr}]

        last_err: Exception | None = None
        for attempt in range(retries):
            t = (
                (self.temperature if temperature is None else temperature)
                if attempt == 0
                else min(0.3 + 0.3 * attempt, 1.0)
            )
            try:
                resp = self._create(msgs, max_tokens, t, response_format)
                text = resp.choices[0].message.content or ""
                u = resp.usage
                usage = {
                    "input_tokens": getattr(u, "prompt_tokens", 0) if u else 0,
                    "output_tokens": getattr(u, "completion_tokens", 0) if u else 0,
                    "model": self.model_id,
                }
                return text, usage
            except Exception as e:  # noqa: BLE001
                last_err = e
                logger.warning("[Moonshot] attempt %d/%d failed: %s", attempt + 1, retries, e)
                time.sleep(min(2 ** attempt, 16))
        raise RuntimeError(f"Moonshot API error after {retries} attempts: {last_err}")

    def chat_json(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        retries: int = 6,
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # Resample on a malformed-but-200 reply: Moonshot occasionally returns
        # truncated/empty JSON, and at temp=1 a fresh draw usually parses. chat()
        # only retries transient API errors, so drive the parse-retry here.
        last_err: Exception | None = None
        for _ in range(retries):
            text, usage = self.chat(
                messages, max_tokens=max_tokens, retries=retries,
                json_schema=json_schema, json_mode=True,
            )
            try:
                return json.loads(_extract_json(text)), usage
            except json.JSONDecodeError as e:
                last_err = e
                continue
        raise RuntimeError(f"Moonshot chat_json could not parse after {retries} tries: {last_err}")

    def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_schema: type[BaseModel],
        max_tokens: int | None = None,
        retries: int = 6,
    ) -> tuple[BaseModel, dict[str, Any]]:
        schema = response_schema.model_json_schema()
        last_err: Exception | None = None
        for attempt in range(retries):
            t = None if attempt == 0 else min(0.3 + 0.3 * attempt, 1.0)
            try:
                text, usage = self.chat(
                    messages, max_tokens=max_tokens, temperature=t,
                    retries=6, json_schema=schema,
                )
                return validate_with_coercion(text, response_schema), usage
            except Exception as e:  # noqa: BLE001
                last_err = e
        raise RuntimeError(f"Moonshot structured call failed: {last_err}")
