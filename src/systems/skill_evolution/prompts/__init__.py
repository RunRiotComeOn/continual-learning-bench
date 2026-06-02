"""Prompt loading for the Skill Evolution pipeline.

Prompts are stored as .md files in this directory and loaded at runtime.
"""
from __future__ import annotations

import os

_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_cache: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """Load a prompt file by name (without .md extension)."""
    if name in _cache:
        return _cache[name]
    path = os.path.join(_PROMPTS_DIR, f"{name}.md")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    _cache[name] = content
    return content
