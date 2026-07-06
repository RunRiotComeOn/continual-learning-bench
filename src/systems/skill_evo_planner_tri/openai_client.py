"""OpenAI-backed client exposing the same surface as BedrockClient.

Lets the skill_evo_planner_skeleton system run its working agent + optimizer on
OpenAI models (e.g. gpt-5.4) via litellm, instead of Bedrock/kimi. Implements the
three methods the pipeline and base_system call — ``chat``, ``chat_json``,
``chat_structured`` — and exposes ``model_id``. The OpenAI key is read from the
environment by litellm (OPENAI_API_KEY); no key is stored here.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import litellm
from pydantic import BaseModel


logger = logging.getLogger(__name__)

# Reasoning models reject some chat params (e.g. temperature != 1); let litellm
# silently drop anything the target model does not accept.
litellm.drop_params = True


def _usage_dict(response: Any) -> dict[str, int]:
    u = getattr(response, "usage", None)
    if u is None:
        return {"input_tokens": 0, "output_tokens": 0}
    return {
        "input_tokens": getattr(u, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(u, "completion_tokens", 0) or 0,
    }


def _content(response: Any) -> str:
    try:
        return response.choices[0].message.content or ""
    except Exception:
        return ""


class OpenAIChatClient:
    """litellm-backed client matching BedrockClient's method surface."""

    def __init__(
        self,
        api_key: str = "",
        model_id: str = "gpt-5.4",
        region: str = "",
        max_tokens: int = 8192,
        temperature: float = 1.0,
    ):
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        retries: int = 15,
        json_mode: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        kwargs: dict[str, Any] = dict(
            model=self.model_id,
            messages=messages,
            max_tokens=max_tokens or self.max_tokens,
        )
        if temperature is not None or self.temperature is not None:
            kwargs["temperature"] = (
                temperature if temperature is not None else self.temperature
            )
        if json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response_schema", "schema": json_schema},
            }
        elif json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last: Exception | None = None
        for attempt in range(retries):
            try:
                resp = litellm.completion(**kwargs)
                content = _content(resp)
                # The proxy intermittently returns empty content; treat as
                # retryable rather than letting an empty string propagate.
                if not content or not content.strip():
                    raise ValueError("empty content from provider")
                return content, _usage_dict(resp)
            except Exception as e:  # noqa: BLE001
                last = e
                logger.warning("[OpenAIChatClient] chat attempt %d/%d: %s",
                               attempt + 1, retries, e)
                time.sleep(min(2.0 + 1.5 * attempt, 10.0))  # capped backoff
        raise RuntimeError(f"OpenAI chat failed after {retries} retries: {last}")

    def chat_json(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        retries: int = 6,
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        text, usage = self.chat(
            messages,
            max_tokens=max_tokens,
            retries=retries,
            json_schema=json_schema,
            json_mode=json_schema is None,
        )
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # rescue: grab the outermost JSON object
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(text[start : end + 1])
            else:
                raise ValueError(f"Failed to parse JSON from response: {text[:300]}")
        return parsed, usage

    def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_schema: type[BaseModel],
        max_tokens: int | None = None,
        retries: int = 15,
    ) -> tuple[BaseModel, dict[str, Any]]:
        from ..skill_evo_planner.structured_output import validate_with_coercion

        schema = response_schema.model_json_schema()
        last: Exception | None = None
        for attempt in range(retries):
            try:
                # chat() already retries empty/network errors internally; here we
                # additionally retry malformed-but-nonempty JSON (parse failures).
                text, usage = self.chat(
                    messages, max_tokens=max_tokens, retries=4, json_schema=schema
                )
                return validate_with_coercion(text, response_schema), usage
            except Exception as e:  # noqa: BLE001
                last = e
                logger.warning("[OpenAIChatClient] structured attempt %d/%d: %s",
                               attempt + 1, retries, e)
                time.sleep(min(2.0 + 1.5 * attempt, 10.0))
        raise RuntimeError(f"OpenAI structured failed after {retries} retries: {last}")


__all__ = ["OpenAIChatClient"]
