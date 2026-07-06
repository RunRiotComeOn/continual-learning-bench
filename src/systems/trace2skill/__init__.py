"""Trace2Skill wrapper (option B) — wrap the distinctive ParallelSkillEvolver.

Trace2Skill (Alibaba Qwen) distils trajectory-local lessons into transferable
skills via a parallel map-reduce: multiple analysts propose trajectory-local
patches which are hierarchically consolidated into a conflict-free skill. The
full system is a multi-stage spreadsheet pipeline (error/success analysis →
ParallelSkillEvolver). Option B wraps its *distinctive core* — the real
``ParallelSkillEvolver`` (MAP → REDUCE → APPLY → VERIFY) — behind a lightweight
inline analyst that turns each epoch trajectory into Trace2Skill "items".

Both task execution and evolution run on kimi via ``BedrockClient`` (a small
adapter exposes the ``chat(messages, settings) -> str`` interface Trace2Skill's
client expects). Validation is IN-FLOW: a candidate skill is deployed for a
canary window of real instances and reverted if the window mean drops below the
preceding accumulation epoch (mirrors our skill_evolution canary).

Prereq: Trace2Skill checked out at /u/yhuang48/Trace2Skill (added to sys.path).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
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

_T2S_PATH = "/u/yhuang48/Trace2Skill"


def _get_trace2skill():
    if _T2S_PATH not in sys.path:
        sys.path.insert(0, _T2S_PATH)
    # Trace2Skill uses `from src.react_agent import ...`, but our benchmark owns
    # the top-level `src` package. Graft Trace2Skill's src/ onto our src package's
    # search path so `src.react_agent` resolves there (no submodule-name overlap
    # with our src.systems / src.tasks / ...).
    import src as _our_src  # type: ignore
    _t2s_src = os.path.join(_T2S_PATH, "src")
    if _t2s_src not in list(_our_src.__path__):
        _our_src.__path__.append(_t2s_src)
    from skill_evolver.parallel_evolving_agent import ParallelSkillEvolver  # type: ignore
    from src.react_agent.models import Message, ModelSettings  # type: ignore
    return ParallelSkillEvolver, Message, ModelSettings


class _BedrockT2SClient:
    """Adapter exposing Trace2Skill's ``chat(messages, settings) -> str`` over
    BedrockClient (kimi)."""

    def __init__(self, bedrock_client: BedrockClient):
        self._bc = bedrock_client

    def chat(self, messages: list[Any], settings: Any | None = None) -> str:
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        max_tokens = getattr(settings, "max_tokens", None) or 4096
        text, _ = self._bc.chat(msgs, max_tokens=max_tokens)
        return text


_ANALYST_SYS = (
    "You analyze one agent task trajectory and distil transferable lessons for a "
    "skill document. Return ONLY a JSON list (1-3 items). Each item is an object: "
    '{"type": "failure_cause" if the task FAILED else "success_pattern", '
    '"title": short imperative title, "content": the concrete, reusable lesson '
    "with exact names/values/conditions, \"description\": one-line gist}. "
    "Prefer concrete, schema/value-grounded lessons over generic advice. No prose, "
    "no code fences, JSON only."
)


@register_system("trace2skill")
class Trace2SkillSystem(ContinualLearningSystem):
    """ContinualLearningSystem backed by Trace2Skill's ParallelSkillEvolver."""

    def __init__(
        self,
        bedrock_api_key: str = "",
        bedrock_model_id: str = "moonshotai.kimi-k2.5",
        bedrock_region: str = "us-east-1",
        max_tokens: int = 4096,
        epoch_size: int = 5,
        enable_canary: bool = True,
        name: str = "trace2skill",
        output_dir: str = "",
        run_index: int | None = None,
        **_ignored: Any,
    ):
        self._name = name
        self.max_tokens = max_tokens
        self.epoch_size = epoch_size
        self.enable_canary = enable_canary
        self.run_index = run_index

        bedrock_api_key = bedrock_api_key or os.environ.get("BEDROCK_API_KEY", "")
        self._task_client = BedrockClient(
            api_key=bedrock_api_key, model_id=bedrock_model_id,
            region=bedrock_region, max_tokens=max_tokens, temperature=0.0,
        )
        self._evo_client = BedrockClient(
            api_key=bedrock_api_key, model_id=bedrock_model_id,
            region=bedrock_region, max_tokens=max_tokens, temperature=0.0,
        )
        self._t2s_client = _BedrockT2SClient(self._evo_client)
        self.reset()

    # ── state ──────────────────────────────────────────────────────────────
    def reset(self) -> None:
        self.skill_md: str = ""
        self.messages: list[dict[str, str]] = []
        self._traj: list[dict[str, Any]] = []
        self._cur_instance: str = ""
        self._cur_goal: str = ""
        self.interaction_count = 0
        self.trial_count = 0
        self._at_boundary = True
        self._pending_feedback: str | None = None
        # epoch buffers
        self._epoch_trials: list[dict[str, Any]] = []
        self._epoch_scores: list[float] = []
        # canary
        self._canary_active = False
        self._canary_scores: list[float] = []
        self._canary_baseline = 0.0
        self._prev_skill_md = ""
        # skill dir (fresh per run). Seed a STRUCTURED weak draft so the evolver
        # EDITS SKILL.md (adds learned guidance) rather than proposing to CREATE it.
        self._skill_dir = tempfile.mkdtemp(prefix="trace2skill_")
        os.makedirs(os.path.join(self._skill_dir, "references"), exist_ok=True)
        with open(os.path.join(self._skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(
                "---\n"
                "name: db-exploration\n"
                "description: Use when answering questions over the product-review "
                "SQLite database.\n"
                "---\n\n"
                "# Database Exploration\n\n"
                "Guidance learned from execution traces.\n\n"
                "## Schema Facts\n\n"
                "## Query Strategies\n\n"
                "## Failure Modes\n\n"
                "## References\n"
            )

    @property
    def name(self) -> str:
        return self._name

    # ── respond / observe ───────────────────────────────────────────────────
    def respond(self, query: Query) -> Response:
        boundary = self._at_boundary
        if query.instance_id:
            self._cur_instance = query.instance_id
        if query.metadata:
            self._cur_goal = query.metadata.get("goal", query.prompt[:200])

        parts: list[str] = []
        if self._pending_feedback and boundary:
            parts.append(f"FEEDBACK FROM PREVIOUS INSTANCE:\n{self._pending_feedback}")
            self._pending_feedback = None
        if self.skill_md and boundary:
            parts.append(f"=== SKILL ===\n{self.skill_md}\n=== END SKILL ===")
        if query.prompt:
            parts.append(query.prompt)
        content = "\n\n".join(parts) if parts else "(no content)"

        self.interaction_count += 1
        self._at_boundary = False
        self.messages.append({"role": "user", "content": content})
        self._traj.append({"role": "situation", "content": query.prompt})

        try:
            parsed, usage = self._task_client.chat_structured(
                messages=self.messages, response_schema=query.response_schema,
                max_tokens=self.max_tokens,
            )
            self.record_usage_event(UsageEvent(
                model=self._task_client.model_id, call_type="completion",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            ))
            assistant_record = parsed.model_dump_json()
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}") from e

        self.messages.append({"role": "assistant", "content": assistant_record})
        self._traj.append({"role": "action", "content": assistant_record})
        return Response(action=parsed, metadata={
            "system_type": "trace2skill", "model": self._task_client.model_id,
            "skill_md_length": len(self.skill_md), "trial_count": self.trial_count,
            "epoch_phase": "canary" if self._canary_active else "accumulation",
        })

    def observe(self, observation: Observation, next_query: Query | None = None) -> None:
        complete = observation_marks_instance_complete(observation)
        c = observation.content.strip()
        self._traj.append({"role": "feedback", "content": c})
        if c and not complete:
            self.messages.append({"role": "user", "content": f"FEEDBACK: {c}"})
        if complete:
            self._on_trial_complete(observation)
            self.messages = []
            self._at_boundary = True

    # ── epoch / evolution ────────────────────────────────────────────────────
    def _on_trial_complete(self, observation: Observation) -> None:
        self.trial_count += 1
        meta = observation.metadata or {}
        score = float(meta["reward"]) if "reward" in meta else (
            1.0 if "correct" in observation.content.lower() else 0.0)
        trial = {
            "instance_id": self._cur_instance or f"trial_{self.trial_count}",
            "trajectory": list(self._traj), "score": score,
            "success": score > 0,
        }
        self._traj = []

        if self._canary_active:
            self._canary_scores.append(score)
            if len(self._canary_scores) >= self.epoch_size:
                self._resolve_canary()
            return

        self._epoch_trials.append(trial)
        self._epoch_scores.append(score)
        if len(self._epoch_trials) >= self.epoch_size:
            self._run_epoch()

    def _run_epoch(self) -> None:
        baseline = (sum(self._epoch_scores) / len(self._epoch_scores)
                    if self._epoch_scores else 0.0)
        trials = list(self._epoch_trials)
        self._epoch_trials = []
        self._epoch_scores = []
        try:
            candidate = self._evolve(trials)
        except Exception as e:
            logger.warning("[Trace2Skill] evolution failed: %s", e)
            return
        if candidate is None or candidate.strip() == self.skill_md.strip():
            return
        if not self.enable_canary:
            self.skill_md = candidate
            return
        # start in-flow canary: deploy candidate, validate over next window
        self._prev_skill_md = self.skill_md
        self.skill_md = candidate
        self._canary_active = True
        self._canary_scores = []
        self._canary_baseline = baseline

    def _resolve_canary(self) -> None:
        mean = (sum(self._canary_scores) / len(self._canary_scores)
                if self._canary_scores else 0.0)
        if mean < self._canary_baseline:  # candidate hurt → revert
            self.skill_md = self._prev_skill_md
            logger.info("[Trace2Skill] canary REVERT (%.3f < %.3f)", mean, self._canary_baseline)
        else:
            logger.info("[Trace2Skill] canary KEEP (%.3f >= %.3f)", mean, self._canary_baseline)
        self._canary_active = False
        self._canary_scores = []

    def _evolve(self, trials: list[dict]) -> str | None:
        """Inline analyst → Trace2Skill ParallelSkillEvolver → updated SKILL.md."""
        ParallelSkillEvolver, _Message, _MS = _get_trace2skill()
        # 1. inline analyst: each trajectory → items
        records: list[dict] = []
        for t in trials:
            items = self._analyst(t)
            if items:
                records.append({"instance_id": t["instance_id"], "items": items})
        if not records:
            return None
        # 2. run the real ParallelSkillEvolver over the records
        evolver = ParallelSkillEvolver(
            client=self._t2s_client, skill_dir=self._skill_dir,
            batch_size=self.epoch_size, merge_batch_size=4, max_workers=4,
            max_merge_levels=2, temperature=0.0, max_tokens=self.max_tokens,
            verbose=False, patch_pipeline="json",
        )
        evolver.run(records, input_mode="records")
        # 3. read back the evolved SKILL.md
        path = os.path.join(self._skill_dir, "SKILL.md")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read()
        return None

    def _analyst(self, trial: dict) -> list[dict]:
        traj = "\n".join(
            f"[{x.get('role','').upper()}] {str(x.get('content',''))[:1200]}"
            for x in trial["trajectory"]
        )[:8000]
        verdict = "SUCCESS" if trial["success"] else "FAILURE"
        user = f"## Outcome: {verdict}\n## Goal: {trial.get('goal','')}\n## Trajectory\n{traj}"
        try:
            text, _ = self._evo_client.chat(
                [{"role": "system", "content": _ANALYST_SYS},
                 {"role": "user", "content": user}],
                max_tokens=2048,
            )
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1].lstrip("json").strip()
            data = json.loads(text)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning("[Trace2Skill] analyst parse failed: %s", e)
            return []

    def get_run_artifacts(self) -> dict[str, Any]:
        return {
            "artifact_type": "trace2skill", "skill_md": self.skill_md,
            "skill_md_length": len(self.skill_md), "trial_count": self.trial_count,
            "model": self._task_client.model_id,
        }


__all__ = ["Trace2SkillSystem"]
