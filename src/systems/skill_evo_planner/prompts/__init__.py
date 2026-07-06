"""Prompt loading for the self-contained skill_evo_new_validation pipeline.

Prompts are stored as .md files in this directory and loaded at runtime.
"""

from __future__ import annotations

import os

_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_cache: dict[tuple[str, str], str] = {}


def load_prompt(name: str, prompt_dir: str | None = None) -> str:
    """Load a prompt file by name (without .md extension).

    Args:
        name: prompt filename without the ``.md`` extension.
        prompt_dir: optional override directory. When given and it contains
            ``<name>.md``, that copy is used; otherwise this package's local
            prompt is used.
    """
    key = (prompt_dir or "", name)
    if key in _cache:
        return _cache[key]

    search: list[str] = []
    if prompt_dir:
        search.append(os.path.join(prompt_dir, f"{name}.md"))
    search.append(os.path.join(_PROMPTS_DIR, f"{name}.md"))

    for path in search:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                content = f.read()
            _cache[key] = content
            return content

    raise FileNotFoundError(f"Prompt '{name}' not found in {search}")
