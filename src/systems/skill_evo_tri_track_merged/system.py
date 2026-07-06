"""skill_evo_tri_track_merged — tri-track with ONE merged extraction subagent.

Subclasses TriTrackSystem and changes exactly ONE thing: instead of three separate
per-track extraction LLM calls (extract_factual / _strategy / _failure), it makes a
SINGLE call (extract_merged.md) that emits all three kinds of content, each point
tagged with `track`. The tagged points are split by track and then fed — via a tiny
replay client — into the SAME `stage_bc_batch_summarize` machinery (matching,
counting, minting, replace/refine, epoch bookkeeping) and the SAME per-track
promotion, all unchanged. Every other stage (skeleton planning, thresholds,
fast-track, refine) is inherited verbatim.
"""

from __future__ import annotations

import copy
import inspect
import json
import logging
import os
from typing import Any

from ...registry import register_system
from ..skill_evo_planner.batch_system import BATCH_SUMMARIZE_SCHEMA, stage_bc_batch_summarize
from ..skill_evo_planner.pipeline import _chat_json, fmt_trajectory, stage_d_trigger_and_update
from ..skill_evo_planner.prompts import load_prompt
from ..skill_evo_planner_tri.system import TRACKS
from ..skill_evo_tri_track.system import TriTrackSystem

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))

# Same points schema as the per-track passes, plus a required `track` tag so one
# call can carry all three kinds and be split afterwards.
MERGED_SCHEMA: dict[str, Any] = copy.deepcopy(BATCH_SUMMARIZE_SCHEMA)
_item = MERGED_SCHEMA["properties"]["points"]["items"]
_item["properties"]["track"] = {"type": "string", "enum": list(TRACKS)}
_item["required"] = ["track", *_item["required"]]


class _ReplayClient:
    """Minimal client that hands ``stage_bc_batch_summarize`` a pre-extracted set of
    points instead of calling an LLM. Exposes only the ``chat_json`` surface that
    ``_chat_json`` uses, so all downstream processing runs exactly as before."""

    def __init__(self, points: list[dict[str, Any]]):
        self._points = points
        self.model_id = "merged-replay"

    def chat_json(self, messages, max_tokens=None, json_schema=None):  # noqa: D401
        return {"points": self._points}, {}


@register_system("skill_evo_tri_track_merged")
class TriTrackMergedSystem(TriTrackSystem):
    """One merged extraction subagent; everything else identical to tri-track."""

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "skill_evo_tri_track_merged")
        super().__init__(**kwargs)
        # extract_merged.md lives in this package; all other prompts resolve from the
        # inherited tri_track prompt_dir.
        self._merged_prompt_dir = os.path.join(_HERE, "prompts")

    # ── the single merged extraction call ────────────────────────────────────
    def _merged_extract(self) -> list[dict[str, Any]]:
        # Combined focus plan across the three tracks (grouped), so the one call
        # sees the full taxonomy.
        blocks = []
        for t in TRACKS:
            p = self._track_plans.get(t)
            if p:
                blocks.append(f"### {t.upper()} track — sections/slots:\n{p}")
        focus = "\n\n".join(blocks)

        trajs = ""
        for i, tr in enumerate(self._epoch_buffer, 1):
            trajs += (
                f"\n### Trial {i} (outcome={tr.final_outcome})\n"
                f"{fmt_trajectory(tr.trajectory)}\n"
            )

        # Existing points from all three aggregators, grouped by track (ids may
        # repeat across tracks; the prompt forbids cross-track matching and the
        # per-track replay only resolves matches within that track's aggregator).
        existing_blocks = []
        for t in TRACKS:
            items = [
                {"id": c.canonical_id, "description": c.description}
                for c in self.aggs[t].canonicals.values()
            ]
            if items:
                existing_blocks.append(f"[{t}]\n" + json.dumps(items, ensure_ascii=False, indent=2))
        existing = "\n\n".join(existing_blocks) or "(none)"

        n = len(self._epoch_buffer)
        system_prompt = load_prompt("extract_merged", self._merged_prompt_dir)
        user = (
            f"## What to focus on for THIS task flow (from the planner)\n{focus}\n\n"
            f"## Trials in this batch (1..{n})\n{trajs}\n\n"
            f"## Existing points in memory (match against these by id, SAME track only)\n{existing}"
        )
        parsed = _chat_json(
            self._optimizer_client, system_prompt, user,
            max_tokens=8192, json_schema=MERGED_SCHEMA,
        )
        return parsed.get("points", []) or []

    # ── override only the extraction source; per-track processing + promotion
    #    are byte-for-byte the same as the parent (via a replay client) ──────────
    def _extract_and_promote(self) -> None:
        try:
            points = self._merged_extract()
        except Exception as e:  # noqa: BLE001
            logger.warning("[tri_merged] merged extraction failed: %s", e)
            points = []
        by_track: dict[str, list[dict[str, Any]]] = {t: [] for t in TRACKS}
        for p in points:
            tr = (p.get("track") or "").strip()
            if tr in by_track:
                by_track[tr].append(p)

        for track in TRACKS:
            plan = self._track_plans.get(track)
            if not plan:
                continue
            cfg = self.track_cfg[track]
            agg = self.aggs[track]
            try:
                self.aggs[track] = stage_bc_batch_summarize(
                    trials=self._epoch_buffer,
                    aggregator=agg,
                    bedrock_client=_ReplayClient(by_track[track]),
                    current_epoch=self._epoch_counter,
                    prompt_dir=self.prompt_dir,
                    enable_match=self.enable_match,
                    use_trajectory_count=self.use_trajectory_count,
                    focus_plan=plan,
                    enable_replace=self.enable_replace,
                    authoritative_fast_track=cfg["fast_track"],
                    enable_merge=self.enable_merge,
                    prompt_name=f"extract_{track}",
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[tri_merged] %s processing failed: %s", track, e)
                continue
            try:
                v_new, _canary, fast_ids = stage_d_trigger_and_update(
                    aggregator=self.aggs[track],
                    current_skill_md=self.skill_md,
                    bedrock_client=self._optimizer_client,
                    fast_promote_multiplier=1.0,
                    prompt_dir=self.prompt_dir,
                    focus_plan=plan,
                    authoritative_fast_track=cfg["fast_track"],
                )
                if v_new:
                    self.skill_md = v_new
                    if fast_ids:
                        self._save_snapshot(f"{track}_promote_{len(fast_ids)}")
            except Exception as e:  # noqa: BLE001
                logger.warning("[tri_merged] %s promotion failed: %s", track, e)


# Publish the parent's signature (so the CLI param resolver sees all named kwargs),
# but with the `name` default swapped to this system's name.
_parent_sig = inspect.signature(TriTrackSystem.__init__)
_merged_params = [
    p.replace(default="skill_evo_tri_track_merged") if p.name == "name" else p
    for p in _parent_sig.parameters.values()
]
TriTrackMergedSystem.__init__.__signature__ = _parent_sig.replace(parameters=_merged_params)
