"""Per-track skill-evolution system (own loop; no canary/decay/audit).

Each knowledge track (factual / strategy / failure) gets its own aggregator with
its own threshold and fast-promote policy. See ``system.py`` and ``README.md``.
"""

from __future__ import annotations

from .system import TriTrackSystem

__all__ = ["TriTrackSystem"]
