"""Local batch-summarize base for skill_evo_planner.

Hypothesis under test: the per-trajectory ATOMIC extraction (stage B) + pairwise
LLM canonicalization (stage C) is the weak link — atomizing each trajectory in
isolation loses cross-trial structure, and pairwise dedup is noisy.

This system replaces B+C with ONE batch-level pass: the model sees ALL
trajectories in the epoch at once, distills them into POINTS (granularity of its
own choosing — atomic or a small cluster), reports for each point WHICH of the
batch's trajectories exhibit it (the occurrence count), and maps it to an
existing canonical or "new". That count feeds the SAME aggregator quantity and
the SAME trigger_threshold gate; everything downstream (trigger/promote D,
canary F, decay, grounded refine G) is inherited UNCHANGED from the best
non-naive flow (grounded-refine "concise": ground_refine + canary + thr gate).

This module is copied into skill_evo_planner so the package does not
depend on sibling system implementations.
"""

from __future__ import annotations

import logging
import os
from copy import deepcopy
from typing import Any

from .pipeline import (
    _chat_json,
    _targets_open_questions,
    fmt_trajectory,
    stage_d_trigger_and_update,
    stage_decay,
    stage_f_evidence_revert,
    stage_f_promote_or_revert,
)
from .base_system import SkillEvolutionSystem
from .prompts import load_prompt
from .types import Aggregator, Canonical, TrialRecord

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))


BATCH_SUMMARIZE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "effect": {
                        "type": "string",
                        "enum": ["positive", "negative", "unclear"],
                    },
                    "evidence": {"type": "string"},
                    "trajectories": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "match": {"type": "string"},
                    "update_op": {
                        "type": "string",
                        "enum": ["add", "refine", "replace"],
                    },
                    "support_type": {
                        "type": "string",
                        "enum": ["authoritative", "inferred"],
                    },
                },
                "required": ["description", "effect", "trajectories", "match"],
            },
        }
    },
    "required": ["points"],
}


def stage_bc_batch_summarize(
    trials: list[TrialRecord],
    aggregator: Aggregator,
    bedrock_client: Any,
    current_epoch: int = 0,
    prompt_dir: str | None = None,
    enable_match: bool = True,
    use_trajectory_count: bool = True,
    focus_plan: str = "",
    enable_replace: bool = False,
    authoritative_fast_track: bool = False,
    enable_merge: bool = False,
    prompt_name: str = "batch_summarize",
) -> Aggregator:
    """Replace stage B + stage C with one batch-level summarize-and-count pass.

    The model distills the whole batch into points, counting how many of the
    batch's trajectories exhibit each, and aligns each to an existing canonical
    (cross-epoch) or mints a new one. The trajectory-occurrence count is added to
    the canonical's ``quantity`` so the existing trigger_threshold gate is
    unchanged. Mirrors stage_c's epoch-tracking bookkeeping.

    Ablation knobs (for the batch ladder):
      enable_match=False        — never align to existing canonicals (every point
                                  mints a fresh one): cross-epoch dedup OFF.
      use_trajectory_count=False — each point contributes 1 to quantity regardless
                                  of how many trajectories exhibit it: counting OFF.
    """
    if not trials:
        return aggregator

    n = len(trials)
    system_prompt = load_prompt(prompt_name, prompt_dir)

    trajs_text = ""
    for i, trial in enumerate(trials, 1):
        trajs_text += (
            f"\n### Trial {i} (outcome={trial.final_outcome})\n"
            f"{fmt_trajectory(trial.trajectory)}\n"
        )
    existing = [
        {"id": c.canonical_id, "description": c.description}
        for c in aggregator.canonicals.values()
    ]
    import json as _json

    plan_block = (
        f"## What to focus on for THIS task flow (from the planner)\n{focus_plan}\n\n"
        if focus_plan
        else ""
    )
    user = (
        f"{plan_block}"
        f"## Trials in this batch (1..{n})\n{trajs_text}\n\n"
        f"## Existing points in memory (match against these by id)\n"
        f"{_json.dumps(existing, ensure_ascii=False, indent=2) or '(none)'}"
    )

    try:
        parsed = _chat_json(
            bedrock_client,
            system_prompt,
            user,
            max_tokens=8192,
            json_schema=BATCH_SUMMARIZE_SCHEMA,
        )
        points = parsed.get("points", [])
    except Exception as e:
        logger.warning("[batch_summarize] LLM call failed: %s — no update", e)
        return aggregator

    reinforced: set[str] = set()
    for p in points:
        desc = (p.get("description") or "").strip()
        if not desc or _targets_open_questions(desc):
            continue
        effect = p.get("effect", "unclear")
        evidence = (p.get("evidence") or "").strip()
        # 1-based trial indices that exhibit this point → contributing trial ids
        idxs = sorted(
            {
                int(t)
                for t in p.get("trajectories", [])
                if isinstance(t, (int, float)) and 1 <= int(t) <= n
            }
        )
        contributing = [trials[i - 1].trial_id for i in idxs]
        count = (len(contributing) or 1) if use_trajectory_count else 1
        match = (p.get("match") or "new").strip()
        if not enable_match:
            match = "new"

        update_op = (p.get("update_op") or "add").strip()
        support_type = (p.get("support_type") or "inferred").strip()
        # Authoritative facts are fixed at quantity=1 (a single tool/schema
        # observation is enough); they reach skill.md via the fast-track gate, not
        # by out-accumulating. Only gated on the flag so default behavior is intact.
        authoritative = authoritative_fast_track and support_type == "authoritative"
        if match != "new" and match in aggregator.canonicals:
            canon = aggregator.canonicals[match]
            contradicts = (
                enable_replace
                and update_op == "replace"
                and desc != canon.description.strip()
            )
            if contradicts:
                # Same subject, conflicting claim: the new point corrects/supersedes
                # the matched fact. Overwrite content in place; the correction rides
                # the incumbent's accumulated quantity (no re-accumulation needed),
                # so a single grounded counterexample beats a stale high-count fact.
                # Mirrors stage_c_canonicalize's replace path.
                if canon.status == "active_in_skillmd":
                    canon.superseded_text = canon.description
                    canon.pending_op = "replace"
                    canon.status = "waiting"
                canon.description = desc
                canon.effect_valence = effect
                canon.evidence_snippets = [evidence] if evidence else []
                canon.effect_history = [effect]
                canon.contributing_trials = list(contributing)
                canon.support_type = support_type
                canon.last_reinforced_epoch = current_epoch
                canon.epochs_since_reinforce = 0
                reinforced.add(match)
            else:
                # Authoritative facts stay capped at quantity=1 (no accumulation).
                if not authoritative:
                    canon.quantity += count
                canon.effect_history.append(effect)
                canon.contributing_trials.extend(contributing)
                canon.support_type = support_type
                if evidence:
                    canon.evidence_snippets.append(evidence)
                    if len(canon.evidence_snippets) > 10:
                        canon.evidence_snippets = canon.evidence_snippets[-10:]
                canon.last_reinforced_epoch = current_epoch
                canon.epochs_since_reinforce = 0
                reinforced.add(match)
                # update_op="refine" (peer of add/replace): the matched point
                # restates the entry WITH new supported detail and supplies the
                # full enriched text — adopt it in place so the canonical GROWS
                # ("do A" -> "do A then B") instead of freezing at first write.
                #
                # If the old canonical is already live in skill.md, re-open it
                # for Stage D. Otherwise the aggregator would carry the refined
                # text while the deployed skill.md still showed the stale text.
                # Gated by enable_merge; the new desc rides the accumulated quantity.
                if (
                    enable_merge
                    and update_op == "refine"
                    and desc
                    and desc != canon.description.strip()
                ):
                    if canon.status == "active_in_skillmd":
                        canon.superseded_text = canon.description
                        canon.pending_op = "refine"
                        canon.status = "waiting"
                    canon.description = desc
        else:
            cid = aggregator.mint_id()
            aggregator.canonicals[cid] = Canonical(
                canonical_id=cid,
                description=desc,
                effect_valence=effect,
                evidence_snippets=[evidence] if evidence else [],
                quantity=1 if authoritative else count,
                effect_history=[effect],
                last_reinforced_epoch=current_epoch,
                epochs_since_reinforce=0,
                support_type=support_type,
                contributing_trials=contributing,
            )
            reinforced.add(cid)

    for cid, canon in aggregator.canonicals.items():
        if cid not in reinforced:
            canon.epochs_since_reinforce += 1

    logger.info(
        "[batch_summarize] %d points from %d trials → %d canonicals",
        len(points),
        n,
        len(aggregator.canonicals),
    )
    return aggregator


class SkillEvoBatchSystem(SkillEvolutionSystem):
    """skill_evolution with B+C replaced by a single batch-level summarize pass."""

    # NOTE: deliberately NOT @functools.wraps(SkillEvolutionSystem.__init__) —
    # filter_init_params (src/runs/common.py) calls inspect.signature, which
    # follows __wrapped__ to the parent signature; with wraps it would drop new
    # params (use_trajectory_count) before they reach here. A bare (self,
    # **kwargs) signature exposes VAR_KEYWORD so all config params pass through.
    def __init__(self, **kwargs):
        kwargs.setdefault("name", "skill_evo_planner")
        # batch_summarize.md lives here; everything else (skeleton_refine_grounded
        # etc.) falls back per-file to the shared concise prompts.
        kwargs.setdefault("prompt_dir", os.path.join(_HERE, "prompts"))
        # Batch-ladder ablation knob (the others — enable_canonicalize=match,
        # trigger_threshold=gate, ground_refine, enable_canary — are base params).
        self.use_trajectory_count = kwargs.pop("use_trajectory_count", True)
        # raw_append: at an accumulation epoch boundary, write triggered points
        # into skill.md by RAW-APPENDING their description text, skipping the
        # stage_d generate_update LLM pass. Makes b1 a truly minimal batch floor
        # ("distill points + dump text", no per-epoch LLM doc-writing).
        self.raw_append = kwargs.pop("raw_append", False)
        # skillopt_gate: replace our canary's Δ≥0 promote/revert with SkillOpt's
        # evaluate_gate decision IN THE FLOW (unpaired): carry a current_score
        # forward, accept the candidate doc only if cand_score > current_score,
        # and track a global best (best-tracking). Exp A: isolates the VALIDATION
        # decision rule (formation/refine identical to batch-full).
        self.skillopt_gate = kwargs.pop("skillopt_gate", False)
        # Kept for config compatibility. Refine is now tied to accepted updates:
        # it runs only after an update has been enabled, never while validation is
        # still deciding whether that update should survive.
        self.refine_in_canary = kwargs.pop("refine_in_canary", False)
        # enable_replace: in the batch summarize pass, honor the judge's
        # update_op="replace" so a conflicting same-subject point supersedes the
        # matched canonical in place (instead of piling up as a parallel line).
        # Default OFF keeps existing behavior identical.
        self.enable_replace = kwargs.pop("enable_replace", False)
        # authoritative_fast_track: env facts the judge tags support_type=
        # "authoritative" promote at quantity=1 (and are capped there), so a single
        # tool/schema-established fact reaches skill.md without out-accumulating;
        # only inferred claims keep the quantity gate. Default OFF.
        self.authoritative_fast_track = kwargs.pop("authoritative_fast_track", False)
        # enable_merge: when a new point matches an existing canonical and adds
        # NEW evidence-supported detail, merge old+new into a richer description
        # (instead of discarding the new wording and only bumping quantity). Lets
        # strategy entries grow ("do A" -> "do A then B"). Default OFF.
        self.enable_merge = kwargs.pop("enable_merge", False)
        super().__init__(**kwargs)

    def _maybe_refine_after_update(self, label: str) -> None:
        """Run refine after every accepted update (no separate interval gate)."""
        if not self.skill_md:
            return
        from .pipeline import (
            stage_g_refine_grounded,
            stage_g_refine_skeleton,
        )

        try:
            if self.ground_refine:
                self.skill_md = stage_g_refine_grounded(
                    current_skill_md=self.skill_md,
                    trials=getattr(self, "_recent_trials", []),
                    bedrock_client=self._optimizer_client,
                    prompt_dir=self.prompt_dir,
                )
            else:
                self.skill_md = stage_g_refine_skeleton(
                    current_skill_md=self.skill_md,
                    bedrock_client=self._optimizer_client,
                    prompt_dir=self.prompt_dir,
                )
            self._save_snapshot(f"{label}_refine")
            logger.info("[SkillEvoBatch] refine after accepted update (%s)", label)
        except Exception as e:
            logger.warning("[SkillEvoBatch] post-update refine failed: %s", e)

    def _canary_epoch_end(self) -> None:
        if not self.skillopt_gate:
            for s in self._epoch_scores:
                self.canary.record_score(s)

            if self.evidence_revert:
                edit_ids = {edit.canonical_id for edit in self.canary.edits}
                self.skill_md = stage_f_evidence_revert(
                    canary=self.canary,
                    trials=getattr(self, "_recent_trials", []),
                    aggregator=self.aggregator,
                    bedrock_client=self._optimizer_client,
                    prompt_dir=self.prompt_dir,
                )
                accepted = any(
                    self.aggregator.canonicals.get(cid) is not None
                    and self.aggregator.canonicals[cid].status == "active_in_skillmd"
                    for cid in edit_ids
                )
                self.canary.clear()
                self._save_snapshot("canary_evidence_revert")
                if accepted:
                    self._maybe_refine_after_update("canary_evidence_revert")
                self._epoch_buffer = []
                self._epoch_scores = []
                return

            delta = self.canary.delta_effect
            logger.info(
                "[SkillEvoBatch] Canary epoch done (mean=%.3f, baseline=%.3f, Δ=%.3f)",
                self.canary.canary_mean,
                self.canary.baseline_score,
                delta,
            )
            self.skill_md = stage_f_promote_or_revert(
                canary=self.canary,
                aggregator=self.aggregator,
            )
            accepted = delta >= 0
            action = "PROMOTED" if accepted else "REVERTED"
            self._save_snapshot(f"canary_{action.lower()}")
            logger.info("[SkillEvoBatch] %s canary edits (Δ=%.3f)", action, delta)
            self.canary.clear()
            if accepted:
                self._maybe_refine_after_update("canary_promoted")
            self._epoch_buffer = []
            self._epoch_scores = []
            return

        # SkillOpt-style gate ported to the flow (accept-if-better + best-track).
        for s in self._epoch_scores:
            self.canary.record_score(s)
        cand = self.canary.canary_mean
        if not hasattr(self, "_so_current"):
            self._so_current = self.canary.baseline_score
            self._so_best = self.canary.baseline_score
            self._so_best_skill = self.canary.v_old
        if cand > self._so_current:
            for edit in self.canary.edits:
                c = self.aggregator.canonicals.get(edit.canonical_id)
                if c is not None:
                    c.status = "active_in_skillmd"
            self.skill_md = self.canary.v_new
            self._so_current = cand
            action = "accept"
            if cand > self._so_best:
                self._so_best = cand
                self._so_best_skill = self.canary.v_new
                action = "accept_new_best"
        else:
            for edit in self.canary.edits:
                c = self.aggregator.canonicals.get(edit.canonical_id)
                if c is not None:
                    c.status = "waiting"
                    c.quantity = 0
            self.skill_md = self.canary.v_old
            action = "reject"
        logger.info(
            "[SkillEvoBatch] skillopt_gate %s (cand=%.3f cur=%.3f best=%.3f)",
            action,
            cand,
            self._so_current,
            self._so_best,
        )
        self._save_snapshot(f"skillopt_gate_{action}")
        self.canary.clear()
        if action.startswith("accept"):
            self._maybe_refine_after_update(f"skillopt_gate_{action}")
        self._epoch_buffer = []
        self._epoch_scores = []

    def _accumulation_epoch_end(self) -> None:
        if not self.raw_append:
            baseline_score = (
                sum(self._epoch_scores) / len(self._epoch_scores)
                if self._epoch_scores
                else 0.0
            )
            logger.info(
                "[SkillEvoBatch] Accumulation epoch done (%d trials, baseline=%.3f)",
                len(self._epoch_scores),
                baseline_score,
            )
            v_old = self.skill_md
            effective_multiplier = (
                self.fast_promote_multiplier if self.enable_canary else 1.0
            )
            fast_threshold = int(
                self.aggregator.trigger_threshold * effective_multiplier
            )
            fast_ids_pre = {
                c.canonical_id
                for c in self.aggregator.canonicals.values()
                if c.status == "waiting" and c.quantity >= fast_threshold
            }
            canary_ids_pre = {
                c.canonical_id
                for c in self.aggregator.canonicals.values()
                if (
                    c.status == "waiting"
                    and c.quantity >= self.aggregator.trigger_threshold
                    and c.canonical_id not in fast_ids_pre
                )
            }

            v_fast = v_old
            if fast_ids_pre and canary_ids_pre:
                fast_only = deepcopy(self.aggregator)
                for cid in canary_ids_pre:
                    fast_only.canonicals[cid].status = "triggered"
                try:
                    v_fast, _, _ = stage_d_trigger_and_update(
                        aggregator=fast_only,
                        current_skill_md=v_old,
                        bedrock_client=self._optimizer_client,
                        fast_promote_multiplier=effective_multiplier,
                        prompt_dir=self.prompt_dir,
                        focus_plan=getattr(self, "focus_plan", ""),
                        authoritative_fast_track=self.authoritative_fast_track,
                    )
                    v_fast = v_fast or v_old
                except Exception as e:
                    logger.warning(
                        "[SkillEvoBatch] Fast-only update for canary base failed: %s",
                        e,
                    )
                    v_fast = v_old

            try:
                v_new, canary_edits, fast_ids = stage_d_trigger_and_update(
                    aggregator=self.aggregator,
                    current_skill_md=v_old,
                    bedrock_client=self._optimizer_client,
                    fast_promote_multiplier=effective_multiplier,
                    prompt_dir=self.prompt_dir,
                    focus_plan=getattr(self, "focus_plan", ""),
                    authoritative_fast_track=self.authoritative_fast_track,
                )
            except Exception as e:
                logger.warning("[SkillEvoBatch] Trigger/update failed: %s", e)
                v_new, canary_edits, fast_ids = None, [], []

            self._epoch_buffer = []
            self._epoch_scores = []

            if v_new is None:
                return

            if fast_ids:
                logger.info(
                    "[SkillEvoBatch] Fast-promoted %d high-confidence canonicals: %s",
                    len(fast_ids),
                    fast_ids,
                )

            # Hook: subclasses may gate the update (e.g. replay-validation) and
            # return v_old to reject. Default is a no-op that adopts v_new.
            self.skill_md = self._validate_update(v_old, v_new)

            if canary_edits:
                self.canary.start(
                    v_old=v_fast if fast_ids else v_old,
                    v_new=v_new,
                    edits=canary_edits,
                    window_size=self.canary_window_size,
                    baseline_score=baseline_score,
                )
                self._save_snapshot("canary_start")
                logger.info(
                    "[SkillEvoBatch] %d edits → canary (baseline=%.3f), %d fast-promoted",
                    len(canary_edits),
                    baseline_score,
                    len(fast_ids),
                )
                return

            self._save_snapshot("fast_promote")
            logger.info(
                "[SkillEvoBatch] All %d edits fast-promoted, no canary needed",
                len(fast_ids),
            )
            if self.skill_md != v_old:
                self._maybe_refine_after_update("fast_promote")
            return
        # raw-append path: dump newly-triggered canonical descriptions verbatim,
        # no LLM integration, no canary.
        triggered = [
            c
            for c in self.aggregator.canonicals.values()
            if c.status == "waiting" and c.quantity >= self.trigger_threshold
        ]
        if triggered:
            block = "\n".join(f"- {c.description}" for c in triggered)
            self.skill_md = (
                (self.skill_md + "\n" + block).strip() if self.skill_md else block
            )
            for c in triggered:
                c.status = "active_in_skillmd"
            self._save_snapshot("raw_append")
            self._maybe_refine_after_update("raw_append")
        self._epoch_buffer = []
        self._epoch_scores = []

    def _validate_update(self, v_old: str, v_new: str) -> str:
        """Decide which skill.md to commit after a batch update. Default adopts the
        new version unconditionally. Replay-validation subclasses override this to
        re-run the just-finished batch under v_old vs v_new and keep v_old if the
        update does not improve the batch reward."""
        return v_new

    def _summarize_batch(self) -> None:
        """Single batch-summarize pass over the whole epoch buffer. Subclasses may
        override (e.g. to run several category-specific passes)."""
        self.aggregator = stage_bc_batch_summarize(
            trials=self._epoch_buffer,
            aggregator=self.aggregator,
            bedrock_client=self._optimizer_client,
            current_epoch=self._epoch_counter,
            prompt_dir=self.prompt_dir,
            enable_match=self.enable_canonicalize,
            use_trajectory_count=self.use_trajectory_count,
            focus_plan=getattr(self, "focus_plan", ""),
            enable_replace=self.enable_replace,
            authoritative_fast_track=self.authoritative_fast_track,
            enable_merge=self.enable_merge,
        )

    def _process_epoch_boundary(self) -> None:
        """Same boundary as the parent, but B+C → one batch summarize pass."""
        self._epoch_counter += 1
        n = len(self._epoch_buffer)
        self._recent_trials = list(self._epoch_buffer)
        phase = "canary" if self.canary.active else "accumulation"
        logger.info(
            "[SkillEvoBatch] Epoch %d boundary (%s, %d trials) — batch summarize",
            self._epoch_counter,
            phase,
            n,
        )

        # ── B+C replacement: batch-level summarize-and-count pass(es) ──
        try:
            self._summarize_batch()
        except Exception as e:
            logger.warning("[SkillEvoBatch] Batch summarize failed: %s", e)

        # ── Phase-specific boundary logic (inherited, unchanged) ──
        if self.canary.active:
            self._canary_epoch_end()
        else:
            self._accumulation_epoch_end()

        # ── Decay (inherited logic) ──
        if self.skill_md and self.decay_threshold > 0 and not self.canary.active:
            try:
                updated_md, removed = stage_decay(
                    aggregator=self.aggregator,
                    current_skill_md=self.skill_md,
                    bedrock_client=self._optimizer_client,
                    decay_threshold=self.decay_threshold,
                )
                if removed:
                    self.skill_md = updated_md
                    self._save_snapshot(f"decay_removed_{len(removed)}")
            except Exception as e:
                logger.warning("[SkillEvoBatch] Decay failed: %s", e)


__all__ = ["SkillEvoBatchSystem", "stage_bc_batch_summarize"]
