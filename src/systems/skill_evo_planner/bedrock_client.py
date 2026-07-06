"""Direct Amazon Bedrock Converse API client for Skill Evolution.

Calls the Bedrock Converse endpoint with a Bearer API key.
Handles structured output via prompt-based schema injection + JSON parsing.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_json_with_truncation_rescue(text: str) -> Any:
    """Parse JSON, rescuing a top-level array cut off mid-item.

    Batch optimizer calls commonly return objects like ``{"points": [...]}``.
    If max_tokens truncates the response halfway through an array item, preserve
    all complete objects already emitted instead of dropping the whole batch.
    """
    candidates = [_strip_json_fence(text)]

    stripped = candidates[0]
    start = stripped.find("{")
    end = stripped.rfind("}")
    first_arr = stripped.find("[")
    if start != -1 and (first_arr == -1 or start < first_arr) and end > start:
        candidates.append(stripped[start : end + 1])

    first_obj = stripped.find("{")
    starts = [i for i in (first_obj, first_arr) if i != -1]
    if starts:
        candidates.append(stripped[min(starts) :])

    last_err: json.JSONDecodeError | None = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_err = exc

    rescued = _rescue_truncated_json_array(candidates[-1] if candidates else text)
    if rescued is not None:
        logger.warning(
            "[BedrockClient] rescued truncated JSON response with %d complete items",
            _count_rescued_items(rescued),
        )
        return json.loads(rescued)

    if last_err is not None:
        raise last_err
    raise ValueError(f"Failed to parse JSON from response: {text[:300]}")


def _rescue_truncated_json_array(text: str) -> str | None:
    text = _strip_json_fence(text)
    if not text:
        return None

    root_start = min(
        (i for i in (text.find("{"), text.find("[")) if i != -1), default=-1
    )
    if root_start == -1:
        return None
    text = text[root_start:]

    stack: list[str] = []
    in_string = False
    escape = False
    last_complete_item_end: int | None = None
    top_level_array = text.startswith("[")

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if not stack or stack[-1] != "{":
                return None
            stack.pop()
            if top_level_array:
                if stack == ["["]:
                    last_complete_item_end = i
            elif stack == ["{", "["]:
                last_complete_item_end = i
        elif ch == "]":
            if not stack or stack[-1] != "[":
                return None
            stack.pop()

    if last_complete_item_end is None:
        return None

    repaired = text[: last_complete_item_end + 1]
    if top_level_array:
        return repaired + "]"
    return repaired + "]}"


def _count_rescued_items(text: str) -> int:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return 0
    if isinstance(parsed, list):
        return len(parsed)
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                return len(value)
    return 0


class BedrockClient:
    """Lightweight Bedrock Converse API client using Bearer token auth."""

    def __init__(
        self,
        api_key: str,
        model_id: str = "moonshotai.kimi-k2.5",
        region: str = "us-east-1",
        max_tokens: int = 8192,
        temperature: float = 1.0,
    ):
        self.api_key = api_key
        self.model_id = model_id
        self.region = region
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._endpoint = (
            f"https://bedrock-runtime.{region}.amazonaws.com/model/{model_id}/converse"
        )

    def _build_messages(
        self,
        messages: list[dict[str, str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Convert chat messages to Bedrock Converse format.

        Returns (system_parts, converse_messages).
        """
        system_parts: list[dict[str, Any]] = []
        converse_messages: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append({"text": content})
            else:
                bedrock_role = "user" if role == "user" else "assistant"
                converse_messages.append(
                    {
                        "role": bedrock_role,
                        "content": [{"text": content}],
                    }
                )

        # Bedrock requires alternating user/assistant turns
        converse_messages = self._fix_turn_order(converse_messages)
        return system_parts, converse_messages

    @staticmethod
    def _fix_turn_order(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge consecutive same-role messages to satisfy Bedrock's alternation rule."""
        if not messages:
            return [{"role": "user", "content": [{"text": "(empty)"}]}]

        fixed: list[dict[str, Any]] = []
        for msg in messages:
            if fixed and fixed[-1]["role"] == msg["role"]:
                fixed[-1]["content"].extend(msg["content"])
            else:
                fixed.append(
                    {
                        "role": msg["role"],
                        "content": list(msg["content"]),
                    }
                )

        if fixed[0]["role"] != "user":
            fixed.insert(0, {"role": "user", "content": [{"text": "(start)"}]})

        return fixed

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        retries: int = 6,
        json_mode: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Call Bedrock Converse API.

        Args:
            json_mode: When True, sets response_format to json_object via
                additionalModelRequestFields (valid JSON, no schema enforcement).
            json_schema: When provided, uses outputConfig.textFormat.json_schema
                to enforce the exact schema on the response. Stronger than
                json_mode — guarantees field names, types, and enum values.
                Pass a JSON Schema dict (not a string).

        Returns (response_text, usage_dict).
        """
        system_parts, converse_messages = self._build_messages(messages)

        payload: dict[str, Any] = {
            "messages": converse_messages,
            "inferenceConfig": {
                "maxTokens": max_tokens or self.max_tokens,
                "temperature": temperature
                if temperature is not None
                else self.temperature,
            },
        }
        if system_parts:
            payload["system"] = system_parts
        if json_schema is not None:
            payload["outputConfig"] = {
                "textFormat": {
                    "type": "json_schema",
                    "structure": {
                        "jsonSchema": {
                            "schema": json.dumps(json_schema),
                            "name": "response_schema",
                        }
                    },
                }
            }
        elif json_mode:
            payload["additionalModelRequestFields"] = {
                "response_format": {"type": "json_object"}
            }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                resp = requests.post(
                    self._endpoint,
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    output_text = result["output"]["message"]["content"][0]["text"]
                    usage = result.get("usage", {})
                    return output_text, {
                        "input_tokens": usage.get("inputTokens", 0),
                        "output_tokens": usage.get("outputTokens", 0),
                        "model": self.model_id,
                    }
                elif resp.status_code in (429, 500, 502, 503, 529):
                    last_err = RuntimeError(
                        f"Bedrock {resp.status_code}: {resp.text[:500]}"
                    )
                    wait = 2**attempt
                    logger.warning(
                        "[BedrockClient] %d on attempt %d/%d — retrying in %ds",
                        resp.status_code,
                        attempt + 1,
                        retries,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"Bedrock API error {resp.status_code}: {resp.text[:500]}"
                    )
            except requests.exceptions.Timeout:
                last_err = RuntimeError("Bedrock request timed out")
                wait = 2**attempt
                logger.warning(
                    "[BedrockClient] timeout on attempt %d/%d — retrying in %ds",
                    attempt + 1,
                    retries,
                    wait,
                )
                time.sleep(wait)
            except RuntimeError:
                raise
            except Exception as e:
                last_err = e
                wait = 2**attempt
                logger.warning(
                    "[BedrockClient] error on attempt %d/%d: %s — retrying in %ds",
                    attempt + 1,
                    retries,
                    e,
                    wait,
                )
                time.sleep(wait)

        raise RuntimeError(f"Bedrock call failed after {retries} retries: {last_err}")

    def chat_json(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        retries: int = 6,
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Call Bedrock and parse the JSON response.

        Args:
            json_schema: When provided, uses outputConfig.textFormat.json_schema
                for server-side schema enforcement. Otherwise falls back to
                json_mode (additionalModelRequestFields).

        Returns (parsed_dict, usage_dict).
        """
        text, usage = self.chat(
            messages,
            max_tokens=max_tokens,
            retries=retries,
            json_schema=json_schema,
            json_mode=json_schema is None,
        )
        try:
            parsed = _parse_json_with_truncation_rescue(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Failed to parse JSON from response: {text[:300]}"
            ) from exc
        return parsed, usage

    def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_schema: type[BaseModel],
        max_tokens: int | None = None,
        retries: int = 6,
    ) -> tuple[BaseModel, dict[str, Any]]:
        """Call Bedrock and parse response into a Pydantic model.

        Uses outputConfig.textFormat.json_schema for server-side schema
        enforcement. Falls back to validate_with_coercion for robustness.
        """
        from .structured_output import validate_with_coercion

        pydantic_schema = response_schema.model_json_schema()

        last_err: Exception | None = None
        for attempt in range(retries):
            # Escalate temperature on retry so a deterministic (temp=0) run can
            # escape an unparseable-output dead-end: greedy decoding returns the
            # same bad text every retry, so without jitter the call never
            # recovers. attempt 0 keeps the configured temperature; only the
            # rare failing call is perturbed, leaving variance isolation intact.
            retry_temp = None if attempt == 0 else min(0.3 + 0.3 * attempt, 1.0)
            try:
                text, usage = self.chat(
                    messages,
                    max_tokens=max_tokens,
                    temperature=retry_temp,
                    retries=6,
                    json_schema=pydantic_schema,
                )
                parsed = validate_with_coercion(text, response_schema)
                return parsed, usage
            except RuntimeError:
                raise
            except Exception as e:
                last_err = e
                logger.warning(
                    "[BedrockClient] structured parse attempt %d/%d failed: %s",
                    attempt + 1,
                    retries,
                    e,
                )
                if attempt < retries - 1:
                    time.sleep(1)

        raise RuntimeError(
            f"Bedrock structured output failed after {retries} retries: {last_err}"
        )
