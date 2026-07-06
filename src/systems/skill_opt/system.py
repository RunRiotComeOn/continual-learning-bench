"""SkillOpt system: trajectory-driven skill document optimization.

Wraps SkillOpt's ReflACT pipeline (reflect → aggregate → select → update)
into the ContinualLearningSystem interface, with a canary-epoch validation
gate that mirrors SkillOpt's trainer.py evaluate_gate logic but adapted for
the sequential streaming setting (no static held-out set).

Pipeline per update cycle
-------------------------
  Normal epoch   — run ``epoch_size`` instances with current skill, collect
                   trajectories and scores.
  Reflect stage  — run SkillOpt pipeline on normal-epoch records to produce
                   a candidate skill document.
  Canary epoch   — run next ``epoch_size`` instances with the candidate skill,
                   collect scores.
  Gate           — compare canary_mean vs current_score:
                     accept_new_best : canary > current AND canary > best
                     accept          : canary > current
                     reject          : canary <= current  → revert to current
                   best_skill is maintained separately and never regressed.

Install prerequisites:
    pip install -e /path/to/SkillOpt
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from ...interface import (
    ContinualLearningSystem,
    Observation,
    Query,
    Response,
    observation_marks_instance_complete,
)
from ...registry import register_system
from ...usage import UsageEvent
from ..skill_evolution.bedrock_client import BedrockClient

logger = logging.getLogger(__name__)

_MISSING_MSG = (
    "skillopt is not installed. Install it with:\n"
    "  pip install -e /path/to/SkillOpt\n"
    "then re-run your benchmark command."
)

_INITIAL_SKILL_TEMPLATE = """\
# Task Skill

## Overview
This skill document is automatically populated during the benchmark run.

## Strategy
- Analyze the task carefully before acting.
- Use available context and prior feedback to improve responses.

## Notes
*(Updated automatically by SkillOpt)*
"""


@dataclass
class _GateResult:
    action: str          # "accept_new_best" | "accept" | "reject"
    current_skill: str
    current_score: float
    best_skill: str
    best_score: float
    best_step: int


def _evaluate_gate(
    candidate_skill: str,
    cand_score: float,
    current_skill: str,
    current_score: float,
    best_skill: str,
    best_score: float,
    best_step: int,
    global_step: int,
) -> _GateResult:
    if cand_score > current_score:
        if cand_score > best_score:
            return _GateResult(
                action="accept_new_best",
                current_skill=candidate_skill,
                current_score=cand_score,
                best_skill=candidate_skill,
                best_score=cand_score,
                best_step=global_step,
            )
        return _GateResult(
            action="accept",
            current_skill=candidate_skill,
            current_score=cand_score,
            best_skill=best_skill,
            best_score=best_score,
            best_step=best_step,
        )
    return _GateResult(
        action="reject",
        current_skill=current_skill,
        current_score=current_score,
        best_skill=best_skill,
        best_score=best_score,
        best_step=best_step,
    )


def _get_skillopt():
    try:
        from skillopt.gradient.reflect import run_minibatch_reflect  # type: ignore[import]
        from skillopt.gradient.aggregate import merge_patches  # type: ignore[import]
        from skillopt.optimizer.clip import rank_and_select  # type: ignore[import]
        from skillopt.optimizer.skill import apply_patch_with_report  # type: ignore[import]
        from skillopt.model import (  # type: ignore[import]
            set_optimizer_backend,
            set_optimizer_deployment,
            configure_azure_openai,
        )
        return (
            run_minibatch_reflect,
            merge_patches,
            rank_and_select,
            apply_patch_with_report,
            set_optimizer_backend,
            set_optimizer_deployment,
            configure_azure_openai,
        )
    except ImportError as exc:
        raise ImportError(_MISSING_MSG) from exc


@register_system("skill_opt")
class SkillOptSystem(ContinualLearningSystem):
    """SkillOpt-backed continual learning system with canary-epoch validation.

    Maintains a plain-Markdown skill document prepended to every new instance.
    Each update cycle consists of two epochs:

    1. **Normal epoch** (``epoch_size`` instances) — collect trajectories with
       the current skill, then run the SkillOpt pipeline to produce a candidate.
    2. **Canary epoch** (``epoch_size`` instances) — run instances with the
       candidate skill to evaluate it.  The gate then decides:
       - ``accept_new_best``: candidate beats current AND beats all-time best
       - ``accept``: candidate beats current
       - ``reject``: revert to current skill

    ``best_skill`` is maintained independently and never regresses.

    Parameters
    ----------
    bedrock_api_key, bedrock_model_id, bedrock_region :
        Credentials for the task-execution LLM via Amazon Bedrock.
    opt_api_key, opt_base_url, opt_model :
        Credentials for the optimizer LLM (any OpenAI-compatible endpoint).
        When empty, falls back to the same Bedrock model.
    epoch_size :
        Instances per epoch (both normal and canary use the same size).
    edit_budget :
        Maximum edits the optimizer may apply per cycle.
    minibatch_size :
        Trajectories per analyst call.
    workers :
        Parallel analyst calls.
    output_dir :
        If set, checkpoints skills at ``{output_dir}/skill_opt_ckpt/``.
    run_index :
        Isolates output dirs for parallel rollouts.
    """

    def __init__(
        self,
        bedrock_api_key: str = "",
        bedrock_model_id: str = "moonshotai.kimi-k2.5",
        bedrock_region: str = "us-east-1",
        max_tokens: int = 4096,
        context_window: int = 128_000,
        reserve_tokens: int = 500,
        opt_api_key: str = "",
        opt_base_url: str = "",
        opt_model: str = "gpt-4o",
        epoch_size: int = 10,
        edit_budget: int = 4,
        minibatch_size: int = 4,
        workers: int = 4,
        system_prompt: str = "",
        name: str = "skill_opt",
        output_dir: str = "",
        run_index: int | None = None,
    ):
        bedrock_api_key = bedrock_api_key or os.environ.get("BEDROCK_API_KEY", "")

        self._name = name
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.context_window = context_window
        self.reserve_tokens = reserve_tokens
        self.epoch_size = epoch_size
        self.edit_budget = edit_budget
        self.minibatch_size = minibatch_size
        self.workers = workers

        self._opt_api_key = opt_api_key
        self._opt_base_url = opt_base_url
        self._opt_model = opt_model
        self._bedrock_api_key = bedrock_api_key
        self._bedrock_region = bedrock_region
        self._bedrock_model_id = bedrock_model_id

        if output_dir and run_index is not None:
            output_dir = os.path.join(output_dir, f"run_{run_index}")
        self.output_dir = output_dir
        self._ckpt_dir = os.path.join(output_dir, "skill_opt_ckpt") if output_dir else ""
        if self._ckpt_dir:
            os.makedirs(self._ckpt_dir, exist_ok=True)

        self._task_client = BedrockClient(
            api_key=bedrock_api_key,
            model_id=bedrock_model_id,
            region=bedrock_region,
            max_tokens=max_tokens,
        )

        # ── Skill state ────────────────────────────────────────────────────
        self.skill_content: str = _INITIAL_SKILL_TEMPLATE   # current active skill
        self._best_skill: str = _INITIAL_SKILL_TEMPLATE
        self._current_score: float = 0.0   # estimated from last normal epoch
        self._best_score: float = 0.0
        self._best_step: int = 0
        self._step: int = 0                # total accepted updates

        # ── State machine ──────────────────────────────────────────────────
        # "normal"  : collecting trajectories with skill_content
        # "canary"  : collecting trajectories with _candidate_skill
        self._mode: str = "normal"
        self._candidate_skill: str = ""

        # Normal-epoch accumulation (fed into pipeline)
        self._epoch_records: list[dict] = []
        self._epoch_scores: list[float] = []

        # Canary-epoch accumulation (gate validation only, not fed into pipeline)
        self._canary_scores: list[float] = []

        # ── Per-instance state ─────────────────────────────────────────────
        self._current_trajectory: list[dict] = []
        self._current_instance_id: str = ""
        self._turn_index: int = 0
        self._task_description: str = ""

        # ── Conversation context ───────────────────────────────────────────
        self.messages: list[dict] = []

        # ── Counters ───────────────────────────────────────────────────────
        self._at_instance_boundary: bool = True
        self.interaction_count: int = 0
        self.trial_count: int = 0

    # ── ContinualLearningSystem interface ─────────────────────────────────

    def respond(self, query: Query) -> Response:
        instance_boundary = self._at_instance_boundary
        self.interaction_count += 1
        self._at_instance_boundary = False

        if query.instance_id:
            self._current_instance_id = query.instance_id
        if not self._task_description and query.prompt:
            self._task_description = query.prompt[:1000]

        # Inject the currently active skill at the start of each new instance
        active_skill = self._active_skill()
        query_parts: list[str] = []
        if active_skill and instance_boundary:
            query_parts.append(
                f"=== SKILL DOCUMENT ===\n{active_skill}\n=== END SKILL DOCUMENT ==="
            )
        if query.prompt:
            query_parts.append(query.prompt)
        query_content = "\n\n".join(query_parts) if query_parts else "(no content)"

        self._turn_index += 1
        self._add_message("user", query_content)

        self._current_trajectory.append({
            "step": self._turn_index,
            "action": "(pending)",
            "env_feedback": query.prompt or "",
        })

        self._truncate_context()
        llm_messages = [*self._system_messages(), *self.messages]
        try:
            parsed, usage = self._task_client.chat_structured(
                messages=llm_messages,
                response_schema=query.response_schema,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            raise RuntimeError(f"LLM call failed: {exc}") from exc

        self.record_usage_event(UsageEvent(
            model=self._task_client.model_id,
            call_type="completion",
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        ))

        assistant_record = parsed.model_dump_json()
        self._add_message("assistant", assistant_record)
        if self._current_trajectory:
            self._current_trajectory[-1]["action"] = assistant_record

        return Response(
            action=parsed,
            metadata={
                "interaction_count": self.interaction_count,
                "system_type": "skill_opt",
                "model": self._task_client.model_id,
                "mode": self._mode,
                "skill_len": len(active_skill),
                "step": self._step,
                "trial_count": self.trial_count,
                "epoch_progress": self._epoch_progress(),
            },
        )

    def observe(
        self, observation: Observation, next_query: Query | None = None
    ) -> None:
        instance_complete = observation_marks_instance_complete(observation)
        content = observation.content.strip()

        if self._current_trajectory:
            self._current_trajectory[-1]["env_feedback"] = content

        if content and not instance_complete:
            self._add_message("user", f"FEEDBACK: {content}")

        if instance_complete:
            self._on_trial_complete(observation)
            self.messages = []
            self._at_instance_boundary = True

    def reset(self) -> None:
        self.messages = []
        self._current_trajectory = []
        self._current_instance_id = ""
        self._turn_index = 0
        self._at_instance_boundary = True
        self.interaction_count = 0

    @property
    def name(self) -> str:
        return self._name

    def get_run_artifacts(self) -> dict[str, Any]:
        return {
            "artifact_type": "skill_opt",
            "skill_content": self.skill_content,
            "best_skill": self._best_skill,
            "skill_len": len(self.skill_content),
            "current_score": self._current_score,
            "best_score": self._best_score,
            "best_step": self._best_step,
            "step": self._step,
            "trial_count": self.trial_count,
            "mode": self._mode,
        }

    # ── Trial dispatch ─────────────────────────────────────────────────────

    def _on_trial_complete(self, observation: Observation) -> None:
        self.trial_count += 1
        self._turn_index = 0

        outcome_meta = observation.metadata or {}
        score = 0.0
        if "reward" in outcome_meta:
            score = float(outcome_meta["reward"])
        elif "correct" in observation.content.lower():
            score = 1.0

        if self._mode == "normal":
            self._on_normal_trial(score)
        else:
            self._on_canary_trial(score)

        self._current_trajectory = []
        self._current_instance_id = ""

    def _on_normal_trial(self, score: float) -> None:
        instance_id = self._current_instance_id or f"trial_{self.trial_count}"
        record = {
            "id": instance_id,
            "hard": int(score >= 1.0),
            "soft": min(max(score, 0.0), 1.0),
            "task_description": self._task_description,
            "n_turns": len(self._current_trajectory),
            "conversation": list(self._current_trajectory),
        }
        self._epoch_records.append(record)
        self._epoch_scores.append(score)

        if len(self._epoch_records) >= self.epoch_size:
            self._close_normal_epoch()

    def _on_canary_trial(self, score: float) -> None:
        self._canary_scores.append(score)

        if len(self._canary_scores) >= self.epoch_size:
            self._close_canary_epoch()

    # ── Epoch logic ────────────────────────────────────────────────────────

    def _close_normal_epoch(self) -> None:
        records = list(self._epoch_records)
        scores = list(self._epoch_scores)
        self._epoch_records = []
        self._epoch_scores = []

        epoch_mean = sum(scores) / len(scores) if scores else 0.0
        self._current_score = epoch_mean

        logger.info(
            "[SkillOpt] Normal epoch end: %d records, mean=%.4f. Running pipeline.",
            len(records), epoch_mean,
        )

        try:
            candidate = self._run_pipeline(records)
        except Exception as exc:
            logger.warning("[SkillOpt] Pipeline failed: %s. Staying in normal mode.", exc)
            return

        if not candidate or candidate == self.skill_content:
            logger.info("[SkillOpt] No candidate produced. Staying in normal mode.")
            return

        # Candidate ready — enter canary mode
        self._candidate_skill = candidate
        self._mode = "canary"
        self._canary_scores = []
        logger.info(
            "[SkillOpt] Candidate ready (%d chars). Entering canary mode.",
            len(candidate),
        )

    def _close_canary_epoch(self) -> None:
        canary_scores = list(self._canary_scores)
        self._canary_scores = []
        candidate = self._candidate_skill
        self._candidate_skill = ""
        self._mode = "normal"

        canary_mean = sum(canary_scores) / len(canary_scores) if canary_scores else 0.0
        self._step += 1

        gate = _evaluate_gate(
            candidate_skill=candidate,
            cand_score=canary_mean,
            current_skill=self.skill_content,
            current_score=self._current_score,
            best_skill=self._best_skill,
            best_score=self._best_score,
            best_step=self._best_step,
            global_step=self._step,
        )

        logger.info(
            "[SkillOpt] Gate %s: canary=%.4f vs current=%.4f (best=%.4f @ step %d)",
            gate.action.upper(),
            canary_mean,
            self._current_score,
            self._best_score,
            self._best_step,
        )

        self.skill_content = gate.current_skill
        self._current_score = gate.current_score
        self._best_skill = gate.best_skill
        self._best_score = gate.best_score
        self._best_step = gate.best_step

        if gate.action in ("accept", "accept_new_best"):
            self._save_checkpoint(label=gate.action)

    # ── Pipeline ───────────────────────────────────────────────────────────

    def _run_pipeline(self, records: list[dict]) -> str | None:
        (
            run_minibatch_reflect,
            merge_patches,
            rank_and_select,
            apply_patch_with_report,
            set_optimizer_backend,
            set_optimizer_deployment,
            configure_azure_openai,
        ) = _get_skillopt()

        if self._opt_api_key or self._opt_base_url:
            set_optimizer_backend("openai_chat")
            set_optimizer_deployment(self._opt_model)
            configure_azure_openai(
                optimizer_endpoint=self._opt_base_url or "https://api.openai.com/v1",
                optimizer_api_key=self._opt_api_key,
                optimizer_auth_mode="openai_compatible",
            )
        else:
            import skillopt.model.bedrock_backend as _bb
            _bb.BEDROCK_API_KEY = self._bedrock_api_key
            _bb.BEDROCK_REGION = self._bedrock_region
            _bb.OPTIMIZER_DEPLOYMENT = self._bedrock_model_id
            set_optimizer_backend("bedrock")
            set_optimizer_deployment(self._bedrock_model_id)

        with tempfile.TemporaryDirectory(prefix="skillopt_bench_") as tmpdir:
            pred_dir = os.path.join(tmpdir, "predictions")
            patches_dir = os.path.join(tmpdir, "patches")

            for rec in records:
                item_dir = os.path.join(pred_dir, str(rec["id"]))
                os.makedirs(item_dir, exist_ok=True)
                with open(os.path.join(item_dir, "conversation.json"), "w", encoding="utf-8") as f:
                    json.dump(rec["conversation"], f, ensure_ascii=False)

            result_dicts = [
                {
                    "id": r["id"],
                    "hard": r["hard"],
                    "soft": r["soft"],
                    "task_description": r.get("task_description", ""),
                    "n_turns": r.get("n_turns", 0),
                }
                for r in records
            ]

            # ① REFLECT
            raw_patches = run_minibatch_reflect(
                results=result_dicts,
                skill_content=self.skill_content,
                prediction_dir=pred_dir,
                patches_dir=patches_dir,
                workers=self.workers,
                failure_only=False,
                minibatch_size=self.minibatch_size,
                edit_budget=self.edit_budget,
            )

        failure_patches = [p for p in raw_patches if p and p.get("source_type") == "failure"]
        success_patches = [p for p in raw_patches if p and p.get("source_type") == "success"]

        if not failure_patches and not success_patches:
            return None

        # ② AGGREGATE
        merged = merge_patches(
            self.skill_content,
            failure_patches,
            success_patches,
            batch_size=8,
            verbose=False,
            workers=self.workers,
        )
        if not merged:
            return None

        # ③ SELECT
        ranked = rank_and_select(
            self.skill_content,
            merged,
            max_edits=self.edit_budget,
        )

        # ④ UPDATE
        candidate, _ = apply_patch_with_report(self.skill_content, ranked)
        return candidate if candidate != self.skill_content else None

    # ── Checkpoint ─────────────────────────────────────────────────────────

    def _save_checkpoint(self, label: str = "") -> None:
        if not self._ckpt_dir:
            return
        try:
            suffix = f"_{label}" if label else ""
            path = os.path.join(self._ckpt_dir, f"skill_v{self._step:04d}{suffix}.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.skill_content)
        except OSError as exc:
            logger.warning("[SkillOpt] Failed to save checkpoint: %s", exc)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _active_skill(self) -> str:
        """Return the skill currently being evaluated (candidate during canary)."""
        if self._mode == "canary":
            return self._candidate_skill
        return self.skill_content

    def _epoch_progress(self) -> str:
        if self._mode == "canary":
            return f"canary {len(self._canary_scores)}/{self.epoch_size}"
        return f"normal {len(self._epoch_records)}/{self.epoch_size}"

    def _system_messages(self) -> list[dict]:
        if not self.system_prompt:
            return []
        return [{"role": "system", "content": self.system_prompt}]

    def _add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def _truncate_context(self) -> None:
        from ..utils import count_tokens
        reserved = self.reserve_tokens + self.max_tokens
        limit = self.context_window - reserved
        while len(self.messages) > 2:
            try:
                tokens = sum(
                    count_tokens(self._task_client.model_id, m["content"])
                    for m in self.messages
                )
                if tokens <= limit:
                    break
            except Exception:
                break
            self.messages.pop(0)
