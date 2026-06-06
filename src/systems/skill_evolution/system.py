"""Skill Evolution system — integrates with the continual-learning-bench interface.

Epoch-based skill evolution with deferred, parallelized pipeline stages:

    [── accumulation epoch (N trials) ──][── canary epoch (M trials) ──]
      task execution only (fast)           task execution only (fast)
      buffer trial records                 buffer trial records
      at epoch end:                        at epoch end:
        parallel B on all N trials           parallel B on all M trials
        batch C (one canonicalize pass)      batch C
        trigger check (D)                    Δeffect → promote/revert (F)

B (extraction) runs in parallel via ThreadPoolExecutor.
Both windows feed candidates into the aggregator (no data wasted).

Calls Amazon Bedrock Converse API directly.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from pydantic import BaseModel

from ...interface import (
    ContinualLearningSystem,
    Observation,
    Query,
    Response,
    observation_marks_instance_complete,
)
from ...registry import register_system
from ...usage import UsageEvent
from .bedrock_client import BedrockClient
from .pipeline import (
    stage_a_init_skeleton,
    stage_b_extract_candidates,
    stage_c_canonicalize,
    stage_d_trigger_and_update,
    stage_decay,
    stage_f_promote_or_revert,
    stage_g_refine_skeleton,
)
from .types import Aggregator, Candidate, CanaryState, TrialRecord

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CONTEXT = 128_000


@register_system("skill_evolution")
class SkillEvolutionSystem(ContinualLearningSystem):
    """LLM system with a self-evolving skill.md document.

    Evolution uses an epoch-based loop with deferred parallel processing.
    Within an epoch the skill.md is frozen — only task execution LLM calls
    happen. At epoch boundaries, extraction (B) runs in parallel across all
    buffered trials, then canonicalization (C) and trigger/promote logic
    run once.
    """

    def __init__(
        self,
        bedrock_api_key: str = "",
        bedrock_model_id: str = "moonshotai.kimi-k2.5",
        bedrock_region: str = "us-east-1",
        optimizer_model_id: str = "",
        max_tokens: int = 4096,
        context_window: int = _DEFAULT_MAX_CONTEXT,
        system_prompt: str = "",
        name: str = "skill_evolution",
        reserve_tokens: int = 500,
        trigger_threshold: int = 10,
        accumulation_batch_size: int = 5,
        canary_window_size: int = 5,
        refine_interval: int = 50,
        extract_workers: int = 5,
        fast_promote_multiplier: float = 2.0,
        decay_threshold: int = 3,
        clear_context_between_instances: bool = True,
        stateless: bool = False,
        output_dir: str = "",
        run_index: int | None = None,
    ):
        self._name = name
        # When the benchmark runs multiple independent rollouts in parallel,
        # each gets its own run_index. Namespace the snapshot directory by it so
        # the per-run skill.md / aggregator.json snapshots don't clobber each
        # other. Single runs (run_index None) keep the flat output_dir.
        if output_dir and run_index is not None:
            output_dir = os.path.join(output_dir, f"run_{run_index}")
        self.run_index = run_index
        self.output_dir = output_dir
        self.fast_promote_multiplier = fast_promote_multiplier
        self.decay_threshold = decay_threshold
        self.system_prompt = system_prompt
        self.clear_context_between_instances = clear_context_between_instances
        self.stateless = stateless
        self.trigger_threshold = trigger_threshold
        self.accumulation_batch_size = accumulation_batch_size
        self.canary_window_size = canary_window_size
        self.refine_interval = refine_interval
        self.extract_workers = extract_workers
        self.max_tokens = max_tokens
        self.context_window = context_window
        self.reserve_tokens = reserve_tokens

        self._task_client = BedrockClient(
            api_key=bedrock_api_key,
            model_id=bedrock_model_id,
            region=bedrock_region,
            max_tokens=max_tokens,
        )
        opt_model = optimizer_model_id or bedrock_model_id
        self._optimizer_client = BedrockClient(
            api_key=bedrock_api_key,
            model_id=opt_model,
            region=bedrock_region,
            max_tokens=max_tokens,
        )

        # Skill evolution state
        self.skill_md: str = ""
        self.aggregator = Aggregator(trigger_threshold=trigger_threshold)
        self.canary = CanaryState()
        self._skeleton_initialized: bool = False

        # Epoch buffer: trial records + scores accumulated within current epoch
        self._epoch_buffer: list[TrialRecord] = []
        self._epoch_scores: list[float] = []
        self._epoch_counter: int = 0

        # Per-trial trajectory accumulation
        self._current_trajectory: list[dict[str, Any]] = []
        self._current_instance_id: str = ""
        self._current_task_type: str = ""
        self._current_goal: str = ""

        # Conversation context
        self.messages: list[dict[str, str]] = []

        # Counters
        self.interaction_count: int = 0
        self.trial_count: int = 0
        self._at_instance_boundary: bool = True
        self._pending_feedback: str | None = None
        self._task_description: str = ""

    # ── respond / observe ─────────────────────────────────────────────────

    def respond(self, query: Query) -> Response:
        instance_boundary = self._at_instance_boundary

        if query.instance_id:
            self._current_instance_id = query.instance_id
        if query.metadata:
            self._current_task_type = query.metadata.get("task_type", "")
            self._current_goal = query.metadata.get("goal", query.prompt[:200])

        if not self._task_description and query.prompt:
            self._task_description = query.prompt[:2000]

        query_parts = []
        if self._pending_feedback and instance_boundary:
            query_parts.append(
                f"FEEDBACK FROM PREVIOUS INSTANCE:\n{self._pending_feedback}"
            )
            self._pending_feedback = None

        if self.skill_md and instance_boundary:
            query_parts.append(
                f"=== SKILL DOCUMENT ===\n{self.skill_md}\n=== END SKILL DOCUMENT ==="
            )

        if query.prompt:
            query_parts.append(query.prompt)

        query_content = "\n\n".join(query_parts) if query_parts else "(no content)"

        self.interaction_count += 1
        self._at_instance_boundary = False

        self._add_message("user", query_content)
        self._current_trajectory.append({
            "role": "situation",
            "content": query.prompt,
        })

        try:
            self._truncate_context()
            llm_messages = [*self._system_messages(), *self.messages]

            parsed, usage = self._task_client.chat_structured(
                messages=llm_messages,
                response_schema=query.response_schema,
                max_tokens=self.max_tokens,
            )
            self.record_usage_event(UsageEvent(
                model=self._task_client.model_id,
                call_type="completion",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            ))
            action = parsed
            assistant_record = parsed.model_dump_json()
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}") from e

        self._add_message("assistant", assistant_record)
        self._current_trajectory.append({
            "role": "action",
            "content": assistant_record,
        })

        epoch_size = (
            self.canary_window_size if self.canary.active
            else self.accumulation_batch_size
        )
        return Response(
            action=action,
            metadata={
                "interaction_count": self.interaction_count,
                "system_type": "skill_evolution",
                "model": self._task_client.model_id,
                "skill_md": self.skill_md,
                "skill_md_length": len(self.skill_md),
                "aggregator_size": len(self.aggregator.canonicals),
                "canary_active": self.canary.active,
                "trial_count": self.trial_count,
                "epoch_phase": "canary" if self.canary.active else "accumulation",
                "epoch_progress": f"{len(self._epoch_buffer)}/{epoch_size}",
            },
        )

    def observe(
        self, observation: Observation, next_query: Query | None = None
    ) -> None:
        instance_complete = observation_marks_instance_complete(observation)
        content = observation.content.strip()

        self._current_trajectory.append({
            "role": "feedback",
            "content": content,
        })

        if content and not (self.stateless and instance_complete):
            if instance_complete and self.clear_context_between_instances:
                self._pending_feedback = content
            else:
                self._add_message("user", f"FEEDBACK: {content}")

        if instance_complete:
            if not self.stateless:
                self._on_trial_complete(observation)
            if self.clear_context_between_instances:
                self.messages = []
            self._at_instance_boundary = True

    # ── Core evolution loop ───────────────────────────────────────────────

    def _on_trial_complete(self, observation: Observation) -> None:
        """Buffer trial and process at epoch boundaries."""
        self.trial_count += 1

        outcome_meta = observation.metadata or {}
        score = 0.0
        if "reward" in outcome_meta:
            score = float(outcome_meta["reward"])
        elif "correct" in observation.content.lower():
            score = 1.0

        trial = TrialRecord(
            trial_id=self._current_instance_id or f"trial_{self.trial_count}",
            task_type=self._current_task_type,
            trajectory=list(self._current_trajectory),
            final_outcome={
                "success": score > 0,
                "score": score,
                "feedback": observation.content[:500],
            },
            goal=self._current_goal,
        )
        self._current_trajectory = []

        # Stage A: init skeleton once (first trial only, can't defer)
        if not self._skeleton_initialized:
            try:
                self.skill_md = stage_a_init_skeleton(
                    task_description=self._task_description,
                    sample_trajectories=[trial],
                    bedrock_client=self._optimizer_client,
                )
                self._skeleton_initialized = True
                self._save_snapshot("skeleton_init")
                logger.info(
                    "[SkillEvolution] Initialized skill.md skeleton (%d chars)",
                    len(self.skill_md),
                )
            except Exception as e:
                logger.warning("[SkillEvolution] Skeleton init failed: %s", e)

        # Buffer trial + score (B+C deferred to epoch boundary)
        self._epoch_buffer.append(trial)
        self._epoch_scores.append(score)

        # Check epoch boundary
        epoch_size = (
            self.canary_window_size if self.canary.active
            else self.accumulation_batch_size
        )
        if len(self._epoch_buffer) >= epoch_size:
            self._process_epoch_boundary()

    def _process_epoch_boundary(self) -> None:
        """Run deferred B+C in parallel, then phase-specific logic."""
        self._epoch_counter += 1
        n = len(self._epoch_buffer)
        phase = "canary" if self.canary.active else "accumulation"
        logger.info(
            "[SkillEvolution] Epoch %d boundary (%s, %d trials) — running parallel B+C",
            self._epoch_counter,
            phase,
            n,
        )

        # ── Parallel Stage B ──
        all_candidates = self._parallel_extract(self._epoch_buffer)

        # ── Stage C: canonicalize with epoch tracking ──
        if all_candidates:
            try:
                self.aggregator = stage_c_canonicalize(
                    candidates=all_candidates,
                    aggregator=self.aggregator,
                    bedrock_client=self._optimizer_client,
                    current_epoch=self._epoch_counter,
                )
                logger.info(
                    "[SkillEvolution] Canonicalized %d candidates → %d canonicals",
                    len(all_candidates),
                    len(self.aggregator.canonicals),
                )
            except Exception as e:
                logger.warning("[SkillEvolution] Canonicalization failed: %s", e)

        # ── Phase-specific boundary logic ──
        if self.canary.active:
            self._canary_epoch_end()
        else:
            self._accumulation_epoch_end()

        # ── Decay: remove stale canonicals from skill.md ──
        if self.skill_md and self.decay_threshold > 0:
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
                    logger.info(
                        "[SkillEvolution] Decayed %d stale canonicals: %s",
                        len(removed),
                        removed,
                    )
            except Exception as e:
                logger.warning("[SkillEvolution] Decay failed: %s", e)

        # ── Periodic skeleton refinement ──
        if (
            self.trial_count > 0
            and self.trial_count % self.refine_interval == 0
            and self.skill_md
            and not self.canary.active
        ):
            try:
                self.skill_md = stage_g_refine_skeleton(
                    current_skill_md=self.skill_md,
                    bedrock_client=self._optimizer_client,
                )
                logger.info("[SkillEvolution] Refined skill.md skeleton")
            except Exception as e:
                logger.warning("[SkillEvolution] Skeleton refinement failed: %s", e)

    def _parallel_extract(self, trials: list[TrialRecord]) -> list[Candidate]:
        """Run Stage B in parallel across all trials in the epoch."""
        all_candidates: list[Candidate] = []

        def _extract_one(trial: TrialRecord) -> list[Candidate]:
            return stage_b_extract_candidates(
                trial=trial,
                bedrock_client=self._optimizer_client,
            )

        workers = min(self.extract_workers, len(trials))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_extract_one, trial): trial.trial_id
                for trial in trials
            }
            for future in as_completed(futures):
                tid = futures[future]
                try:
                    candidates = future.result()
                    all_candidates.extend(candidates)
                    logger.info(
                        "[SkillEvolution] Extracted %d candidates from %s",
                        len(candidates),
                        tid,
                    )
                except Exception as e:
                    logger.warning(
                        "[SkillEvolution] Extraction failed for %s: %s", tid, e
                    )

        return all_candidates

    def _accumulation_epoch_end(self) -> None:
        """At accumulation epoch boundary: check triggers → maybe enter canary.

        High-confidence canonicals (q >= threshold * fast_promote_multiplier)
        are fast-promoted directly. The rest go through canary validation.
        """
        baseline_score = (
            sum(self._epoch_scores) / len(self._epoch_scores)
            if self._epoch_scores
            else 0.0
        )
        logger.info(
            "[SkillEvolution] Accumulation epoch done (%d trials, baseline=%.3f)",
            len(self._epoch_scores),
            baseline_score,
        )

        try:
            v_new, canary_edits, fast_ids = stage_d_trigger_and_update(
                aggregator=self.aggregator,
                current_skill_md=self.skill_md,
                bedrock_client=self._optimizer_client,
                fast_promote_multiplier=self.fast_promote_multiplier,
            )
        except Exception as e:
            logger.warning("[SkillEvolution] Trigger/update failed: %s", e)
            v_new, canary_edits, fast_ids = None, [], []

        self._epoch_buffer = []
        self._epoch_scores = []

        if v_new is None:
            return

        if fast_ids:
            logger.info(
                "[SkillEvolution] Fast-promoted %d high-confidence canonicals: %s",
                len(fast_ids),
                fast_ids,
            )

        self.skill_md = v_new

        if canary_edits:
            self.canary.start(
                v_old=self.skill_md,
                v_new=v_new,
                edits=canary_edits,
                window_size=self.canary_window_size,
                baseline_score=baseline_score,
            )
            self._save_snapshot("canary_start")
            logger.info(
                "[SkillEvolution] %d edits → canary (baseline=%.3f), %d fast-promoted",
                len(canary_edits),
                baseline_score,
                len(fast_ids),
            )
        else:
            self._save_snapshot("fast_promote")
            logger.info(
                "[SkillEvolution] All %d edits fast-promoted, no canary needed",
                len(fast_ids),
            )

    def _canary_epoch_end(self) -> None:
        """At canary epoch boundary: compute Δeffect → promote or revert."""
        for s in self._epoch_scores:
            self.canary.record_score(s)

        delta = self.canary.delta_effect
        logger.info(
            "[SkillEvolution] Canary epoch done (mean=%.3f, baseline=%.3f, Δ=%.3f)",
            self.canary.canary_mean,
            self.canary.baseline_score,
            delta,
        )

        new_deployed = stage_f_promote_or_revert(
            canary=self.canary,
            aggregator=self.aggregator,
        )
        self.skill_md = new_deployed

        action = "PROMOTED" if delta >= 0 else "REVERTED"
        self._save_snapshot(f"canary_{action.lower()}")
        logger.info("[SkillEvolution] %s canary edits (Δ=%.3f)", action, delta)

        self.canary.clear()
        self._epoch_buffer = []
        self._epoch_scores = []

    # ── Reset / metadata ──────────────────────────────────────────────────

    def reset(self) -> None:
        self.messages = []
        self.skill_md = ""
        self.aggregator = Aggregator(trigger_threshold=self.trigger_threshold)
        self.canary = CanaryState()
        self._skeleton_initialized = False
        self._epoch_buffer = []
        self._epoch_scores = []
        self._epoch_counter = 0
        self._current_trajectory = []
        self._current_instance_id = ""
        self._current_task_type = ""
        self._current_goal = ""
        self.interaction_count = 0
        self.trial_count = 0
        self._at_instance_boundary = True
        self._pending_feedback = None
        self._task_description = ""

    @property
    def name(self) -> str:
        return self._name

    def get_run_artifacts(self) -> dict[str, Any]:
        self._save_snapshot("final")
        return {
            "artifact_type": "skill_evolution",
            "skill_md": self.skill_md,
            "skill_md_length": len(self.skill_md),
            "aggregator": self.aggregator.to_dict(),
            "trial_count": self.trial_count,
            "interaction_count": self.interaction_count,
            "model": self._task_client.model_id,
            "optimizer_model": self._optimizer_client.model_id,
            "canary_active": self.canary.active,
        }

    def _save_snapshot(self, label: str) -> None:
        """Persist skill.md and aggregator to output_dir for inspection."""
        out = self.output_dir
        if not out:
            return
        os.makedirs(out, exist_ok=True)
        # Always overwrite the latest skill.md
        skill_path = os.path.join(out, "skill.md")
        with open(skill_path, "w", encoding="utf-8") as f:
            f.write(self.skill_md)
        # Write a versioned snapshot
        snap_path = os.path.join(out, f"skill_t{self.trial_count:04d}_{label}.md")
        with open(snap_path, "w", encoding="utf-8") as f:
            f.write(self.skill_md)
        # Write aggregator state
        import json
        agg_path = os.path.join(out, "aggregator.json")
        with open(agg_path, "w", encoding="utf-8") as f:
            json.dump(self.aggregator.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("[SkillEvolution] Saved snapshot '%s' to %s", label, out)

    # ── Context management ────────────────────────────────────────────────

    def _system_messages(self) -> list[dict[str, str]]:
        if not self.system_prompt:
            return []
        return [{"role": "system", "content": self.system_prompt}]

    def _add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self._truncate_context()

    def _truncate_context(self) -> None:
        max_chars = (self.context_window - self.reserve_tokens) * 4
        while len(self.messages) > 1:
            total = sum(len(m["content"]) for m in self.messages)
            if total <= max_chars:
                break
            self.messages.pop(0)
