"""Planner-designed skeleton variant of the skill-evolution system.

The skeleton (sections + task-specific subsections) is designed by the planner
from the FIRST BATCH of trajectories, then used as both the skill.md scaffold and
the extraction slot taxonomy. See ``system.py``.
"""

from __future__ import annotations

from .system import SkillEvoPlannerTriSystem

__all__ = ["SkillEvoPlannerTriSystem"]
