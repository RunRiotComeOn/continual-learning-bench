"""Planner extraction + per-entry contradiction audit.

Extends ``skill_evo_planner`` with a smarter, entry-level validation that runs at
each epoch boundary (instead of the old whole-document before/after comparison).

At each boundary the order is:

1. ``batch_summarize`` accumulates this batch's canonicals (counting only).
2. **Entry audit (this module):** every ACTIVE entry in skill.md is judged
   against the recent trials — confirm / contradict / neutral (reward-free, from
   trajectory evidence only). The resulting removals/reinforcements are APPLIED
   to skill.md FIRST.
3. **Then** this batch's triggered canonicals + their operations are applied on
   top of the already-audited skill.md (inherited ``_accumulation_epoch_end``,
   which reads ``self.skill_md`` as ``v_old``).

Removal is conservative: a contradiction only deletes an entry once it has been
contradicted ``contradiction_threshold`` times (a separate, configurable
threshold from the canonical ``trigger_threshold``). A single failed query is
treated as noise. ``neutral`` entries are left untouched — there is no decay
(never used); only proven-wrong entries are removed. Structure-only refine and
no-canary are inherited from the planner.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
from typing import Any

from ...registry import register_system
from ..skill_evo_planner.pipeline import _chat, _chat_json, fmt_trajectory
from ..skill_evo_planner.prompts import load_prompt
from ..skill_evo_planner.system import (
    SkillEvoPlannerSystem,
    _published_init_signature as _planner_init_signature,
)
from ..skill_evo_planner.types import Canonical, TrialRecord

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))


ENTRY_AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "verdict": {
                        "type": "string",
                        "enum": ["confirm", "contradict", "neutral"],
                    },
                    "evidence": {"type": "string"},
                },
                "required": ["id", "verdict"],
            },
        }
    },
    "required": ["verdicts"],
}


def audit_entries(
    skill_md: str,
    active: list[Canonical],
    trials: list[TrialRecord],
    bedrock_client: Any,
    prompt_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Judge each active entry against the recent trials (confirm/contradict/neutral)."""
    system_prompt = load_prompt("entry_audit", prompt_dir)
    entries = [
        {
            "id": c.canonical_id,
            "claim": c.description,
            # the observations that originally supported this entry, so the
            # auditor can flag a CONTRADICT only on a genuine same-subject conflict
            "recorded_evidence": c.evidence_snippets[-3:],
        }
        for c in active
    ]
    trajs = "\n".join(
        f"### Trial {i}\n{fmt_trajectory(t.trajectory)}"
        for i, t in enumerate(trials, 1)
    )
    user = (
        "## Current skill.md entries (audit each by id)\n"
        f"{json.dumps(entries, ensure_ascii=False, indent=2)}\n\n"
        f"## Recent trials\n{trajs or '(none)'}"
    )
    parsed = _chat_json(
        bedrock_client,
        system_prompt,
        user,
        max_tokens=8192,
        json_schema=ENTRY_AUDIT_SCHEMA,
    )
    return parsed.get("verdicts", []) if isinstance(parsed, dict) else []


def remove_entries(
    skill_md: str,
    claims: list[str],
    bedrock_client: Any,
    prompt_dir: str | None = None,
) -> str:
    """Deletion-only rewrite: drop the listed entries, keep everything else verbatim."""
    system_prompt = load_prompt("remove_entries", prompt_dir)
    user = (
        f"## skill.md\n{skill_md}\n\n"
        "## Entries to REMOVE (delete these, keep all else verbatim)\n"
        + "\n".join(f"- {c}" for c in claims)
    )
    return _chat(bedrock_client, system_prompt, user, max_tokens=8192).strip()


@register_system("skill_evo_planner_audit")
class SkillEvoPlannerAuditSystem(SkillEvoPlannerSystem):
    """Planner extraction + per-entry contradiction audit (no canary, no decay)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "skill_evo_planner_audit")
        kwargs.setdefault("prompt_dir", os.path.join(_HERE, "prompts"))
        kwargs.setdefault("max_tokens", 8192)
        # Decay was never used; the contradiction audit handles removal instead.
        kwargs.setdefault("decay_threshold", 0)
        # Separate, configurable threshold: an entry must be contradicted this many
        # times before it is removed (a single failed query is treated as noise).
        self.contradiction_threshold = int(kwargs.pop("contradiction_threshold", 2))
        super().__init__(**kwargs)
        self._contradiction_counts: dict[str, int] = {}
        self._audit_log: list[dict[str, Any]] = []

    def _accumulation_epoch_end(self) -> None:
        # Audit + apply removals/reinforcements to skill.md FIRST, then let the
        # inherited update apply this batch's canonical operations on top.
        self._run_entry_audit()
        super()._accumulation_epoch_end()

    def _run_entry_audit(self) -> None:
        active = [
            c
            for c in self.aggregator.canonicals.values()
            if c.status == "active_in_skillmd"
        ]
        trials = list(getattr(self, "_recent_trials", []))
        if not active or not self.skill_md or not trials:
            return

        try:
            verdicts = audit_entries(
                self.skill_md, active, trials, self._optimizer_client, self.prompt_dir
            )
        except Exception as e:
            logger.warning("[PlannerAudit] entry audit failed: %s", e)
            return

        vmap = {v.get("id"): v for v in verdicts if isinstance(v, dict) and v.get("id")}
        to_remove: list[Canonical] = []
        n_confirm = n_contradict = 0
        for c in active:
            verdict = (vmap.get(c.canonical_id) or {}).get("verdict", "neutral")
            if verdict == "confirm":
                n_confirm += 1
                c.last_reinforced_epoch = self._epoch_counter
                c.epochs_since_reinforce = 0
                self._contradiction_counts[c.canonical_id] = 0
            elif verdict == "contradict":
                n_contradict += 1
                cnt = self._contradiction_counts.get(c.canonical_id, 0) + 1
                self._contradiction_counts[c.canonical_id] = cnt
                if cnt >= self.contradiction_threshold:
                    to_remove.append(c)
            # neutral: leave untouched (no decay)

        self._audit_log.append(
            {
                "epoch": self._epoch_counter,
                "n_active": len(active),
                "confirm": n_confirm,
                "contradict": n_contradict,
                "removed": [c.canonical_id for c in to_remove],
            }
        )

        if not to_remove:
            return
        try:
            self.skill_md = remove_entries(
                self.skill_md,
                [c.description for c in to_remove],
                self._optimizer_client,
                self.prompt_dir,
            )
        except Exception as e:
            logger.warning("[PlannerAudit] entry removal failed: %s", e)
        for c in to_remove:
            c.status = "waiting"
            c.quantity = 0
            c.pending_op = None
            self._contradiction_counts.pop(c.canonical_id, None)
        self._save_snapshot(f"entry_audit_removed_{len(to_remove)}")
        logger.info(
            "[PlannerAudit] audited %d entries (confirm=%d contradict=%d), removed %d",
            len(active),
            n_confirm,
            n_contradict,
            len(to_remove),
        )

    def get_run_artifacts(self) -> dict[str, Any]:
        artifacts = super().get_run_artifacts()
        artifacts["audit_log"] = self._audit_log
        artifacts["contradiction_threshold"] = self.contradiction_threshold
        artifacts["validation_mode"] = "per_entry_contradiction_audit"
        return artifacts


def _published_init_signature() -> inspect.Signature:
    """Planner's published params + audit-specific defaults."""
    params = []
    for p in _planner_init_signature().parameters.values():
        if p.name == "decay_threshold":
            p = p.replace(default=0)
        elif p.name == "max_tokens":
            p = p.replace(default=8192)
        params.append(p)
    params.append(
        inspect.Parameter(
            "contradiction_threshold",
            inspect.Parameter.KEYWORD_ONLY,
            default=2,
            annotation=int,
        )
    )
    return inspect.Signature(params)


SkillEvoPlannerAuditSystem.__init__.__signature__ = _published_init_signature()


__all__ = ["SkillEvoPlannerAuditSystem", "audit_entries", "remove_entries"]
