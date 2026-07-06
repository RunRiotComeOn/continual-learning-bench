"""skill_evo_tri_track_merged — tri-track, but ONE merged extraction subagent.

Identical to skill_evo_tri_track in every stage (skeleton planning, per-track
aggregators / thresholds / fast-track, promotion, refine). The ONLY difference:
the three per-track extraction passes (extract_factual / _strategy / _failure) are
replaced by a SINGLE LLM call that emits all three kinds of content in one pass,
each point tagged with its `track`. The tagged points are then split by track and
fed — unchanged — into the same per-track aggregator/promotion machinery.
"""

from __future__ import annotations

from .system import TriTrackMergedSystem

__all__ = ["TriTrackMergedSystem"]
