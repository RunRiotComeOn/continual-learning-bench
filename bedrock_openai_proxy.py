#!/usr/bin/env python3
"""
Minimal local proxy: translates OpenAI /v1/chat/completions → Bedrock Converse API.

Allows litellm (and any OpenAI-compatible client) to call a Bedrock Bearer-token
gateway by running this proxy on localhost and pointing OPENAI_BASE_URL at it.

Usage (background, with a ready-signal):
    uv run python bedrock_openai_proxy.py --port 18765 &
    # Wait for "Bedrock proxy ready" line before starting the benchmark.

Environment variables read (all optional — CLI flags take precedence):
    BEDROCK_API_KEY   Bearer token for the gateway
    BEDROCK_REGION    AWS region  (default: us-east-1)
    BEDROCK_MODEL     Default model if not specified in the request
                      (default: moonshotai.kimi-k2.5)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import requests as _requests
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_API_KEY = os.environ.get("BEDROCK_API_KEY", "")
DEFAULT_REGION  = os.environ.get("BEDROCK_REGION", "us-east-1")
DEFAULT_MODEL   = os.environ.get("BEDROCK_MODEL", "moonshotai.kimi-k2.5")

# Module-level config set by _configure() before the server starts
_api_key: str = DEFAULT_API_KEY
_region: str  = DEFAULT_REGION
_default_model: str = DEFAULT_MODEL


# ── Translation helpers ───────────────────────────────────────────────────────

def _normalize_temperature(model: str, temperature: float | None) -> float:
    """Force temperature=1 for kimi models (gateway requirement)."""
    if temperature is None:
        return 1.0
    m = (model or "").lower()
    if m.startswith("kimi-") or m.startswith("moonshotai."):
        return 1.0
    return temperature


def _to_converse_payload(body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Convert an OpenAI chat-completion request body to a Bedrock Converse payload.

    Returns (model_id, converse_payload).
    """
    model = str(body.get("model") or _default_model)
    # litellm prefixes model with 'openai/' — strip it
    model = model.removeprefix("openai/")

    messages_in: list[dict] = body.get("messages") or []
    system_parts: list[str] = []
    bedrock_messages: list[dict] = []

    for m in messages_in:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        if role == "system":
            system_parts.append(str(content))
        else:
            bedrock_messages.append({
                "role": role,
                "content": [{"text": str(content)}],
            })

    temperature = _normalize_temperature(model, body.get("temperature"))
    max_tokens = int(body.get("max_tokens") or body.get("max_completion_tokens") or 8192)

    payload: dict[str, Any] = {
        "messages": bedrock_messages,
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system_parts:
        payload["system"] = [{"text": "\n\n".join(system_parts)}]

    return model, payload


def _from_converse_response(model: str, converse_resp: dict[str, Any]) -> dict[str, Any]:
    """Convert a Bedrock Converse response to an OpenAI chat-completion response."""
    blocks = (converse_resp.get("output") or {}).get("message", {}).get("content") or []
    text = "".join(
        b["text"] for b in blocks
        if isinstance(b, dict) and isinstance(b.get("text"), str)
    )
    usage = converse_resp.get("usage") or {}
    prompt_tokens    = usage.get("inputTokens", 0)
    completion_tokens = usage.get("outputTokens", 0)

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="bedrock-openai-proxy")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid JSON body"})

    try:
        model, payload = _to_converse_payload(body)
    except Exception as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})

    endpoint = (
        f"https://bedrock-runtime.{_region}.amazonaws.com"
        f"/model/{model}/converse"
    )
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_api_key}",
    }

    last_err: str = ""
    for attempt in range(4):
        try:
            resp = _requests.post(endpoint, headers=headers, json=payload, timeout=120.0)
            if resp.status_code == 200:
                openai_resp = _from_converse_response(model, resp.json())
                return JSONResponse(content=openai_resp)
            last_err = f"Bedrock {resp.status_code}: {resp.text[:400]}"
            if resp.status_code < 500:
                return JSONResponse(
                    status_code=resp.status_code,
                    content={"error": {"message": last_err, "type": "bedrock_error"}},
                )
        except Exception as exc:
            last_err = str(exc)
        time.sleep(2 ** attempt)

    return JSONResponse(
        status_code=503,
        content={"error": {"message": f"Bedrock request failed: {last_err}", "type": "service_unavailable"}},
    )


@app.get("/v1/models")
async def list_models() -> JSONResponse:
    return JSONResponse(content={
        "object": "list",
        "data": [{"id": _default_model, "object": "model", "created": 0, "owned_by": "bedrock"}],
    })


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


# ── Entry point ───────────────────────────────────────────────────────────────

def _configure(args: argparse.Namespace) -> None:
    global _api_key, _region, _default_model
    _api_key = args.api_key or DEFAULT_API_KEY
    _region  = args.region  or DEFAULT_REGION
    _default_model = args.model or DEFAULT_MODEL


def main() -> None:
    parser = argparse.ArgumentParser(description="Bedrock-to-OpenAI local proxy")
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--region", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    _configure(args)

    print(
        f"Bedrock proxy ready on http://localhost:{args.port}/v1  "
        f"(model={_default_model}, region={_region})",
        flush=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
