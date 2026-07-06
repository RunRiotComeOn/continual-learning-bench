"""Planner-guided batch skill evolution (no validation stage).

Motivation
----------
Two observations drive this system:

1. ``refine_grounded`` was originally added because the per-trajectory extraction
   under-mined the trials — but feeding trajectories to an LLM rewrite turned out
   to *inject* hallucinated facts (it confabulates schema it was told to "enrich"
   from). So here refine is structure-only (no trajectories).
2. The ``batch_summarize`` extraction itself still under-mines: it doesn't know
   what is worth digging for in a given task flow.

The fix is a **planner**: once (or periodically), an LLM looks at the task
description + a few example trials and produces a compact list of DIMENSIONS —
the specific kinds of information this task flow rewards capturing. That plan is
then threaded *consistently* through the whole pipeline so every stage shares one
taxonomy:

- ``batch_summarize`` uses the plan as a mining checklist (dig for those
  dimensions; tag each point to a planned section);
- ``stage_d`` doc-update organizes the document by the planned sections;
- aggregator canonicals carry their section tag, so updates land consistently;
- structure-only refine then just reorganizes within that structure.

There is intentionally **no validation stage** for now: ``enable_canary=False``
makes every triggered canonical apply directly (fast-promote), so we can study
planner-driven formation without the gate confound.
"""

from __future__ import annotations

import inspect
import logging
import os
from typing import Any

from ...registry import register_system
from .base_system import SkillEvolutionSystem
from .batch_system import SkillEvoBatchSystem
from .pipeline import _chat_json, _targets_open_questions, fmt_trajectory
from .prompts import load_prompt
from .types import TrialRecord

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "dimensions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "what_to_capture": {"type": "string"},
                },
                "required": ["name", "what_to_capture"],
            },
        }
    },
    "required": ["dimensions"],
}


def generate_focus_plan(
    task_description: str,
    trials: list[TrialRecord],
    bedrock_client: Any,
    prompt_dir: str | None = None,
    max_samples: int = 3,
) -> str:
    """Ask the planner what information THIS task flow rewards capturing.

    Returns a compact markdown bullet list (dimension -> what to capture) that is
    injected verbatim into the batch-summarize and doc-update prompts so every
    stage shares one section taxonomy.
    """
    system_prompt = load_prompt("planner", prompt_dir)
    trajs = ""
    for i, t in enumerate(trials[:max_samples], 1):
        trajs += f"\n### Example trial {i} (outcome={t.final_outcome})\n{fmt_trajectory(t.trajectory)}\n"
    user = (
        f"## Task description\n{task_description or '(unknown)'}\n\n"
        f"## Example trials\n{trajs or '(none)'}"
    )
    parsed = _chat_json(
        bedrock_client,
        system_prompt,
        user,
        max_tokens=8192,
        json_schema=PLAN_SCHEMA,
    )
    dims = parsed.get("dimensions", []) if isinstance(parsed, dict) else []
    lines = [
        f"- {(d.get('name') or '').strip()}: {(d.get('what_to_capture') or '').strip()}"
        for d in dims
        if isinstance(d, dict) and (d.get("name") or "").strip()
        and not _targets_open_questions(f"[{d.get('name') or ''}]")
    ]
    return "\n".join(lines)


@register_system("skill_evo_planner")
class SkillEvoPlannerSystem(SkillEvoBatchSystem):
    """Batch skill evolution guided by a task-flow planner; no validation gate."""

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "skill_evo_planner")
        kwargs.setdefault("prompt_dir", os.path.join(_HERE, "prompts"))
        # No validation stage: every triggered canonical fast-promotes.
        kwargs.setdefault("enable_canary", False)
        # Refine = structure-only (no trajectories) so it can't re-inject facts.
        kwargs.setdefault("ground_refine", False)
        # 0 => build the plan once (at the first epoch boundary) and keep it;
        # >0 => regenerate the plan every N trials so it can track drift.
        self.planner_interval = int(kwargs.pop("planner_interval", 0))
        self.planner_samples = int(kwargs.pop("planner_samples", 3))
        super().__init__(**kwargs)
        self.focus_plan: str = ""
        self._plan_history: list[dict[str, Any]] = []

    def _maybe_update_plan(self) -> None:
        due = (not self.focus_plan) or (
            self.planner_interval > 0
            and self.trial_count > 0
            and self.trial_count % self.planner_interval == 0
        )
        if not due or not self._epoch_buffer:
            return
        try:
            plan = generate_focus_plan(
                task_description=self._task_description,
                trials=list(self._epoch_buffer),
                bedrock_client=self._optimizer_client,
                prompt_dir=self.prompt_dir,
                max_samples=self.planner_samples,
            )
        except Exception as e:
            logger.warning("[SkillEvoPlanner] planner failed: %s", e)
            return
        if plan and plan != self.focus_plan:
            self.focus_plan = plan
            self._plan_history.append({"trial": self.trial_count, "plan": plan})
            logger.info(
                "[SkillEvoPlanner] focus plan updated at trial %d (%d dims)",
                self.trial_count,
                len(plan.splitlines()),
            )

    def _process_epoch_boundary(self) -> None:
        # Build/refresh the plan BEFORE the batch-summarize pass so this epoch's
        # extraction is already guided by it.
        self._maybe_update_plan()
        super()._process_epoch_boundary()

    def get_run_artifacts(self) -> dict[str, Any]:
        artifacts = super().get_run_artifacts()
        artifacts["focus_plan"] = self.focus_plan
        artifacts["plan_history"] = self._plan_history
        artifacts["validation_mode"] = "none_planner_guided_formation"
        return artifacts


def _published_init_signature() -> inspect.Signature:
    """Expose constructor params to the CLI/config resolver (see siblings)."""
    # This system has no validation stage and uses structure-only refine, so
    # override those two base defaults in the PUBLISHED signature too — otherwise
    # the CLI resolver fills the base defaults (enable_canary=True,
    # ground_refine=False) and passes them explicitly, defeating __init__'s
    # setdefault. (Still overridable via config.)
    _default_override = {
        "enable_canary": False,
        "ground_refine": False,
        "trigger_threshold": 3,
    }
    base_params = [
        (
            p.replace(default=_default_override[p.name])
            if p.name in _default_override
            else p
        )
        for p in inspect.signature(SkillEvolutionSystem.__init__).parameters.values()
        if p.kind
        not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
    ]
    extra_knobs = [
        inspect.Parameter(
            name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=annot
        )
        for name, default, annot in (
            ("use_trajectory_count", True, bool),
            ("raw_append", False, bool),
            ("skillopt_gate", False, bool),
            ("refine_in_canary", False, bool),
            ("planner_interval", 0, int),
            ("planner_samples", 3, int),
            ("enable_replace", False, bool),
            ("authoritative_fast_track", False, bool),
        )
    ]
    return inspect.Signature(base_params + extra_knobs)


SkillEvoPlannerSystem.__init__.__signature__ = _published_init_signature()


__all__ = ["SkillEvoPlannerSystem", "generate_focus_plan"]
