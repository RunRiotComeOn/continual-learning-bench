"""OpenAI-compatible client for OpenRouter (openrouter.ai).

Exposes the SAME surface the planner family / tri_track call on ``BedrockClient``
(``model_id``, ``chat``, ``chat_json``, ``chat_structured``) so it is a drop-in
replacement. OpenRouter speaks the OpenAI chat-completions schema, so this wraps
the ``openai`` SDK pointed at the OpenRouter base URL.

Unlike ``MoonshotClient`` (which must force temperature=1 because the direct
Moonshot API rejects any other value for kimi-k2.*), OpenRouter's kimi routing
accepts arbitrary temperatures, so this client RESPECTS the configured
temperature. kimi is still not bitwise-deterministic even at temp 0 (MoE), so
lean on N-seed CIs for variance rather than trusting greedy decoding.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import time
from typing import Any

from openai import OpenAI
from pydantic import BaseModel

from .structured_output import validate_with_coercion

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def _extract_json(text: str) -> str:
    """Pull the outermost JSON object out of a possibly fenced/prosey reply."""
    # Strip inline reasoning blocks first — reasoning models (MiniMax, some kimi
    # routes) emit <think>…</think> that itself contains braces, which would
    # derail the outermost-object scan below. Remove closed blocks, and any
    # leading unclosed <think> up to the point real content starts.
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    t = re.sub(r"^.*?</think>", "", t, flags=re.S)  # dangling close, if any
    t = t.strip()
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


# ─────────────────────────── XML structured output ───────────────────────────
# JSON forces global validity (one bad quote/brace breaks everything) and needs
# escaping — which weak models (deepseek/kimi) fail on, especially SQL content.
# XML tags are per-field independent, need no escaping, and don't require a
# response_format constraint (which itself triggers empty replies on some
# providers). Enable with OPENROUTER_STRUCTURED_FORMAT=xml.

def _xml_render_object(props: dict, indent: str = "") -> str:
    parts = []
    for name, spec in props.items():
        t = spec.get("type")
        if t == "array":
            items = spec.get("items", {})
            if items.get("type") == "object":
                inner = _xml_render_object(items.get("properties", {}))
                parts.append(
                    f"{indent}<{name}>\n{indent}  <item>{inner}</item>\n"
                    f"{indent}  <!-- repeat <item>…</item> for each element -->\n{indent}</{name}>"
                )
            else:
                parts.append(f"{indent}<{name}>comma,separated,values</{name}>")
        else:
            enum = spec.get("enum")
            hint = f" (one of: {'|'.join(map(str, enum))})" if enum else ""
            desc = (spec.get("description", "") or "")[:80]
            parts.append(f"{indent}<{name}>{desc}{hint}</{name}>")
    return "\n".join(parts)


def _schema_to_xml_instruction(schema: dict) -> str:
    tmpl = _xml_render_object(schema.get("properties", {}))
    return (
        "Respond ONLY with these XML tags, exactly as shown. NO JSON, NO markdown, "
        "NO <think>, NO text outside the tags. Put raw values directly inside tags "
        "— do NOT escape quotes, newlines, or special characters.\n" + tmpl
    )


def _xml_coerce(text: str, spec: dict):
    t = spec.get("type")
    s = text.strip()
    if t == "integer":
        m = re.search(r"-?\d+", s)
        return int(m.group()) if m else None
    if t == "number":
        m = re.search(r"-?\d+\.?\d*", s)
        return float(m.group()) if m else None
    if t == "boolean":
        return s.lower() in ("true", "1", "yes")
    return s


def _xml_parse_object(text: str, props: dict) -> dict:
    obj: dict[str, Any] = {}
    for name, spec in props.items():
        m = re.search(rf"<{re.escape(name)}>(.*?)</{re.escape(name)}>", text, flags=re.S)
        if not m:
            continue
        block = m.group(1)
        t = spec.get("type")
        if t == "array":
            items = spec.get("items", {})
            if items.get("type") == "object":
                iprops = items.get("properties", {})
                obj[name] = [
                    _xml_parse_object(im, iprops)
                    for im in re.findall(r"<item>(.*?)</item>", block, flags=re.S)
                ]
            else:
                vals = [v.strip() for v in re.split(r"[,\n]", block) if v.strip()]
                obj[name] = [_xml_coerce(v, items) for v in vals]
        else:
            obj[name] = _xml_coerce(block, spec)
    return obj


def _xml_parse_to_dict(text: str, schema: dict) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"^.*?</think>", "", text, flags=re.S)
    return _xml_parse_object(text, schema.get("properties", {}))


def _map_model_id(model_id: str) -> str:
    """Map a Bedrock-style id ("moonshotai.kimi-k2.5") to OpenRouter's
    "vendor/model" form ("moonshotai/kimi-k2.5"). Ids that already contain a
    "/" (native OpenRouter ids) are passed through unchanged."""
    if "/" in model_id:
        return model_id
    if "." in model_id:
        vendor, rest = model_id.split(".", 1)
        return f"{vendor}/{rest}"
    return model_id


# JSON-schema validation keywords that OpenAI's *strict* structured-output subset
# rejects (it supports only a small subset). Pydantic emits several of these
# (float ge/le → minimum/maximum, defaults, etc.), which makes a strict request
# 400 on OpenAI/Azure providers even though laxer providers accept it. We strip
# them before sending.
_OPENAI_STRICT_UNSUPPORTED = frozenset(
    {
        "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
        "minLength", "maxLength", "pattern", "format",
        "minItems", "maxItems", "uniqueItems",
        "minProperties", "maxProperties", "default", "$comment",
    }
)


def _strictify_schema(node: Any) -> Any:
    """Recursively rewrite a JSON schema to satisfy OpenAI strict structured output:
    every object gets ``additionalProperties: false`` and a ``required`` list of ALL
    its properties, and unsupported validation keywords are stripped. Idempotent;
    operates on a deep copy supplied by the caller."""
    if isinstance(node, dict):
        for k in list(node.keys()):
            if k in _OPENAI_STRICT_UNSUPPORTED:
                node.pop(k, None)
        if node.get("type") == "object" or "properties" in node:
            node["additionalProperties"] = False
            props = node.get("properties")
            if isinstance(props, dict):
                node["required"] = list(props.keys())
        for container in ("properties", "$defs", "definitions", "patternProperties"):
            sub = node.get(container)
            if isinstance(sub, dict):
                for v in sub.values():
                    _strictify_schema(v)
        for key in ("items", "additionalItems", "contains", "not"):
            if isinstance(node.get(key), dict):
                _strictify_schema(node[key])
        for key in ("anyOf", "allOf", "oneOf", "prefixItems"):
            if isinstance(node.get(key), list):
                for v in node[key]:
                    _strictify_schema(v)
    return node


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        model_id: str = "moonshotai/kimi-k2.5",
        base_url: str = _DEFAULT_BASE_URL,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        map_model: bool = True,
    ):
        self.api_key = api_key
        # ``map_model=False`` keeps the model id verbatim — needed for custom
        # OpenAI-compatible proxies whose model names contain a version dot
        # (e.g. "kimi-k2.5"), which the bedrock→OpenRouter mapper would mangle.
        self.model_id = _map_model_id(model_id) if map_model else model_id
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        # Reasoning toggle. kimi-k2.6 (and other hybrid models) spend
        # reasoning_tokens even on trivial replies, which are billed at the
        # (expensive) output rate. Set OPENROUTER_DISABLE_REASONING=1 to send
        # ``reasoning={"enabled": false}`` — verified to zero out reasoning
        # tokens on k2.6. NOTE: only ``{"enabled": false}`` actually stops
        # generation; ``exclude``/``effort``/``max_tokens:0`` still reason (and
        # bill). Disabling trades some reasoning quality for lower cost/latency.
        self.reasoning_enabled = os.environ.get(
            "OPENROUTER_DISABLE_REASONING", ""
        ).lower() not in ("1", "true", "yes", "on")
        # XML structured output (free text, no response_format constraint) — more
        # robust for weak models than JSON. Enable with STRUCTURED_FORMAT=xml.
        self.xml_mode = os.environ.get("OPENROUTER_STRUCTURED_FORMAT", "").lower() == "xml"
        # OpenRouter recommends (optional) attribution headers; harmless if set.
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/continual-learning-bench",
                "X-Title": "continual-learning-bench",
            },
        )

    def _create(self, messages, max_tokens, temperature, response_format=None):
        kwargs: dict[str, Any] = dict(
            model=self.model_id,
            messages=messages,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature if temperature is not None else self.temperature,
        )
        if response_format:
            kwargs["response_format"] = response_format
        extra_body: dict[str, Any] = {}
        if not self.reasoning_enabled:
            extra_body["reasoning"] = {"enabled": False}
        # MiniMax emits inline <think> reasoning that derails structured JSON;
        # its API takes a provider-specific switch to suppress it entirely.
        if "minimax" in self.base_url.lower() or "minimax" in self.model_id.lower():
            extra_body["thinking"] = {"type": "disabled"}
        # Pin provider(s) to avoid OpenRouter's default quantized-backend roulette
        # (empty/degenerate responses). Comma list in OPENROUTER_PROVIDER, in order,
        # no fallback to unlisted providers.
        provider: dict[str, Any] = {}
        provider_env = os.environ.get("OPENROUTER_PROVIDER", "").strip()
        if provider_env:
            names = [p.strip() for p in provider_env.split(",") if p.strip()]
            provider["order"] = names
            provider["allow_fallbacks"] = False
        # Route only to providers that actually support the requested params
        # (e.g. response_format json_schema). Preferred over hard-pinning a single
        # provider: OpenRouter spreads across all capable backends with fallback,
        # avoiding single-provider overload AND the empty/truncated replies from
        # incapable ones. On by default; disable with OPENROUTER_REQUIRE_PARAMS=0.
        if os.environ.get("OPENROUTER_REQUIRE_PARAMS", "0").lower() in (
            "1", "true", "yes", "on",
        ):
            provider["require_parameters"] = True
        if provider:
            extra_body["provider"] = provider
        if extra_body:
            kwargs["extra_body"] = extra_body
        # Per-call timeout so a hung provider connection doesn't block the worker
        # for the SDK default (~600s). A hung call raises → caught by chat()'s
        # retry loop → resample. Override via CLBENCH_LLM_TIMEOUT.
        kwargs["timeout"] = float(os.environ.get("CLBENCH_LLM_TIMEOUT", "240"))
        return self._client.chat.completions.create(**kwargs)

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        retries: int = 12,
        json_mode: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        msgs = list(messages)
        # NB: do NOT use OpenRouter's ``response_format={"type":"json_object"}``
        # for the kimi route — its constrained decoder frequently emits
        # valid-but-empty objects (e.g. {"name":":"}), silently dropping content.
        # Prompt-only JSON (parsed by ``_extract_json``, which strips code fences)
        # is far more reliable. So we never send response_format.
        response_format = None
        if json_mode or json_schema:
            instr = (
                "Respond ONLY with a single valid JSON object. No prose, no code "
                "fences, no markdown, no headings, no emojis, and no <think> tags. "
                "Put any reasoning INSIDE the JSON (e.g. a 'reasoning' field), never "
                "outside it."
            )
            if json_schema:
                instr += " It MUST conform to this JSON schema:\n" + json.dumps(
                    json_schema, ensure_ascii=False
                )
                # Force structured content via json_SCHEMA mode (NOT the buggy
                # json_object mode). This reliably prevents empty / reasoning-only
                # replies on providers that support it (gpt-5-mini, deepseek via
                # Baidu). The prompt instruction above stays as a backup.
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "strict": True,
                        # Rewrite to OpenAI's strict subset (additionalProperties:false
                        # + required-all + strip unsupported keywords) so strict
                        # providers (Azure/OpenAI) accept complex Pydantic schemas
                        # like cohort's 108-field submission instead of 400-ing.
                        "schema": _strictify_schema(copy.deepcopy(json_schema)),
                    },
                }
            msgs = msgs + [{"role": "system", "content": instr}]

        base_t = self.temperature if temperature is None else temperature
        last_err: Exception | None = None
        for attempt in range(retries):
            # bump temperature slightly on retries to break a bad draw, but never
            # below the configured value
            t = base_t if attempt == 0 else min(max(base_t, 0.3) + 0.3 * attempt, 1.0)
            try:
                resp = self._create(msgs, max_tokens, t, response_format)
                text = resp.choices[0].message.content or ""
                # Empty content when JSON was requested = a degenerate/overloaded
                # reply (some providers, e.g. deepseek via Baidu under burst load,
                # 200-OK with an empty body). Treat it as retryable so the backoff
                # below gives the provider time to recover, instead of returning ""
                # and forcing a no-JSON parse failure upstream.
                if (json_mode or json_schema) and not text.strip():
                    raise RuntimeError("empty content from provider (JSON expected)")
                u = resp.usage
                usage = {
                    "input_tokens": getattr(u, "prompt_tokens", 0) if u else 0,
                    "output_tokens": getattr(u, "completion_tokens", 0) if u else 0,
                    "model": self.model_id,
                }
                return text, usage
            except Exception as e:  # noqa: BLE001
                last_err = e
                logger.warning("[OpenRouter] attempt %d/%d failed: %s", attempt + 1, retries, e)
                time.sleep(min(2 ** attempt, 16))
        raise RuntimeError(f"OpenRouter API error after {retries} attempts: {last_err}")

    def chat_json(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        retries: int = 12,
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # XML mode: render the schema as tags, send as free text, parse tags back.
        if self.xml_mode and json_schema:
            instr = _schema_to_xml_instruction(json_schema)
            xmsgs = messages + [{"role": "system", "content": instr}]
            last_err: Exception | None = None
            for attempt in range(retries):
                text, usage = self.chat(xmsgs, max_tokens=max_tokens, retries=retries)
                if text.strip():
                    d = _xml_parse_to_dict(text, json_schema)
                    if d:  # got at least one recognized tag
                        return d, usage
                    last_err = RuntimeError("no XML tags parsed")
                else:
                    last_err = RuntimeError("empty content")
                # empty / degenerate reply — back off so the provider recovers
                time.sleep(min(2 ** attempt, 16))
            raise RuntimeError(f"OpenRouter chat_json (xml) failed after {retries} tries: {last_err}")
        # Resample on a malformed-but-200 reply: a fresh draw usually parses.
        last_err = None
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
        raise RuntimeError(f"OpenRouter chat_json could not parse after {retries} tries: {last_err}")

    def chat_structured(
        self,
        messages: list[dict[str, str]],
        response_schema: type[BaseModel],
        max_tokens: int | None = None,
        retries: int = 12,
    ) -> tuple[BaseModel, dict[str, Any]]:
        schema = response_schema.model_json_schema()
        last_err: Exception | None = None
        # XML mode: tags → dict → pydantic (coerced). Free text, no response_format.
        if self.xml_mode:
            instr = _schema_to_xml_instruction(schema)
            xmsgs = messages + [{"role": "system", "content": instr}]
            for attempt in range(retries):
                t = None if attempt == 0 else min(0.3 + 0.3 * attempt, 1.0)
                try:
                    text, usage = self.chat(xmsgs, max_tokens=max_tokens, temperature=t, retries=6)
                    if not text.strip():
                        raise RuntimeError("empty content from provider")
                    d = _xml_parse_to_dict(text, schema)
                    return validate_with_coercion(json.dumps(d), response_schema), usage
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    # empty / unparseable reply — back off so the provider recovers
                    time.sleep(min(2 ** attempt, 16))
            raise RuntimeError(f"OpenRouter structured call (xml) failed: {last_err}")
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
        raise RuntimeError(f"OpenRouter structured call failed: {last_err}")
