"""Planner-designed skeleton skill evolution.

Motivation
----------
In the parent ``skill_evo_planner_audit`` the skill.md skeleton is created by
Stage A from the FIRST trial alone (n=1, noisy) and produces only coarse,
generic ``##`` sections. Extraction then tags each fact to a section freely and
refine renames sections ad hoc. Two consequences observed empirically:

1. Section structure is unstable / generic, so there is no explicit slot for the
   *answer layer* — the concrete values/results the task is actually scored on.
   On cohort_studies the survival-number slots stayed empty; only schema /
   failure-mode facts (which repeat across trials and so canonicalize easily)
   ever landed in skill.md.
2. Extraction has no task-specific target to dig toward.

This system moves skeleton design to the **planner**, run once on the FIRST FULL
BATCH:

- The planner reads the whole first batch and emits a skeleton with ``##``
  sections AND ``###`` task-specific subsections (grounded in what the
  trajectories actually reveal), explicitly scaffolding both the reference layer
  and the answer/result layer.
- That skeleton becomes ``self.skill_md`` (the scaffold) and its heading taxonomy
  becomes the ``focus_plan`` threaded into batch-summarize extraction, so
  extraction targets the designed slots.
- Refine is constrained to be **additive**: it may add ``###`` subsections but
  may never delete an existing ``##``/``###`` heading (skeleton stays stable
  within a run, while new study/entity families can still be discovered). This
  is enforced by the overridden ``skeleton_refine.md`` prompt in ``prompts/``.

Everything else (parallel extract, canonicalize, fast-promote, per-entry
contradiction audit, no canary) is inherited unchanged from
``skill_evo_planner_audit``.
"""

from __future__ import annotations

import inspect
import logging
import os
import re
from typing import Any

from ...registry import register_system
from ..skill_evo_planner.batch_system import stage_bc_batch_summarize
from ..skill_evo_planner.pipeline import (
    _chat,
    _chat_json,
    _strip_open_questions_sections,
    fmt_trajectory,
)
from ..skill_evo_planner.prompts import load_prompt
from ..skill_evo_planner.types import Canonical, TrialRecord
from ..skill_evo_planner_audit.system import (
    SkillEvoPlannerAuditSystem,
    remove_entries,
    _published_init_signature as _audit_init_signature,
)

TRACKS = ("factual", "strategy", "failure")

_CLASSIFY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "factual_track_enabled": {"type": "boolean"},
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string"},
                    "track": {"type": "string", "enum": list(TRACKS)},
                },
                "required": ["section", "track"],
            },
        },
    },
    "required": ["assignments"],
}


def _top_sections(skeleton: str) -> list[list[str]]:
    """[ [section_name, first_desc_line], ... ] for top-level ## sections."""
    secs: list[list[str]] = []
    for raw in skeleton.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            secs.append([line[3:].strip(), ""])
        elif secs and not secs[-1][1] and (line.startswith("<!--") or line.startswith("- ")):
            secs[-1][1] = line.strip("<!->").strip()[:160]
    return secs


def classify_sections(skeleton, client, prompt_dir, objective_name, task_description="") -> tuple:
    """Planner assigns each top-level section to a track and judges whether the
    factual track is worth running. Returns (track_map, factual_enabled)."""
    import json as _json

    secs = [s for s in _top_sections(skeleton) if s[0] != objective_name]
    m: dict[str, str] = {}
    factual_enabled = True
    if secs:
        try:
            sysp = load_prompt("classify_tracks", prompt_dir)
            brief = (task_description or "").strip()[:1200]
            user = (
                (f"## Task brief\n{brief}\n\n" if brief else "")
                + "## Sections\n"
                + _json.dumps(
                    [{"section": n, "description": d} for n, d in secs],
                    ensure_ascii=False, indent=2,
                )
            )
            parsed = _chat_json(client, sysp, user, max_tokens=2000, json_schema=_CLASSIFY_SCHEMA)
            if isinstance(parsed, dict):
                if parsed.get("factual_track_enabled") is False:
                    factual_enabled = False
                for a in parsed.get("assignments", []):
                    if a.get("section") and a.get("track") in TRACKS:
                        m[a["section"].strip()] = a["track"]
        except Exception:
            pass
    # deterministic fallback for anything unassigned
    for n, _d in secs:
        if n not in m:
            ln = n.lower()
            m[n] = ("strategy" if "strateg" in ln
                    else "failure" if any(k in ln for k in ("fail", "mistake", "pitfall", "trap"))
                    else "factual")
    return m, factual_enabled


def build_track_plans(skeleton, section_track, objective_name) -> dict:
    """Split the flattened focus-plan lines into per-track focus plans."""
    plans: dict[str, list[str]] = {t: [] for t in TRACKS}
    for ln in skeleton_to_focus_plan(skeleton).splitlines():
        body = ln[2:] if ln.startswith("- ") else ln
        sec = body.split("▸")[0].split(":")[0].strip()
        if sec == objective_name:
            continue
        plans[section_track.get(sec, "factual")].append(ln)
    return {t: "\n".join(v) for t, v in plans.items() if v}


_TRACK_TAG_RE = re.compile(r"track\s*=\s*(factual|strategy|failure)\s*;?\s*", re.I)


def resolve_section_tracks(
    skeleton, client, prompt_dir, objective_name, task_description=""
) -> tuple:
    """Merged planner+routing: read each section's track from the tag the skeleton
    planner already wrote in its `<!-- -->` comment (one pass designs the structure
    AND assigns tracks). Falls back to the separate ``classify_tracks`` LLM call only
    for a legacy/untagged skeleton. Returns ``(section_track, factual_enabled,
    cleaned_skeleton)`` with the ``track=`` tags stripped out of the skeleton."""
    section_track: dict[str, str] = {}
    current = None
    for raw in skeleton.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            current = line[3:].strip()
        elif line.startswith("<!--") and current and current not in section_track:
            m = _TRACK_TAG_RE.search(line)
            if m:
                section_track[current] = m.group(1).lower()
    if section_track:
        cleaned = _TRACK_TAG_RE.sub("", skeleton)
        factual_enabled = "factual" in section_track.values()
        return section_track, factual_enabled, cleaned
    # Legacy skeleton with no inline tags: fall back to the separate classifier.
    track_map, factual_enabled = classify_sections(
        skeleton, client, prompt_dir, objective_name, task_description=task_description
    )
    return track_map, factual_enabled, skeleton


logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))


COUNTED_AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "audits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "contradict_trials": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "evidence": {"type": "string"},
                },
                "required": ["id", "contradict_trials"],
            },
        }
    },
    "required": ["audits"],
}


def audit_entries_counted(
    skill_md: str,
    active: list,
    trials: list,
    bedrock_client: Any,
    prompt_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Count-based audit (symmetric to batch_summarize). For each active entry, the
    LLM inspects EVERY trial in the batch and returns the 1-based trial numbers that
    give dump-evidence (same-scope explicit contradiction). The caller accumulates
    len(contradict_trials) toward dump_threshold."""
    import json as _json

    system_prompt = load_prompt("entry_audit", prompt_dir)
    entries = [
        {
            "id": c.canonical_id,
            "claim": c.description,
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
        f"{_json.dumps(entries, ensure_ascii=False, indent=2)}\n\n"
        f"## Trials in this batch (1..{len(trials)})\n{trajs or '(none)'}"
    )
    parsed = _chat_json(
        bedrock_client,
        system_prompt,
        user,
        max_tokens=8192,
        json_schema=COUNTED_AUDIT_SCHEMA,
    )
    return parsed.get("audits", []) if isinstance(parsed, dict) else []


def generate_skeleton_plan(
    task_description: str,
    trials: list[TrialRecord],
    bedrock_client: Any,
    prompt_dir: str | None = None,
    max_samples: int = 5,
) -> str:
    """Design the skill.md skeleton (sections + task-specific subsections).

    Reads a full batch of trajectories and returns a markdown skeleton with empty
    placeholder slots. Used as both the skill.md scaffold and (via its heading
    taxonomy) the extraction focus plan.
    """
    system_prompt = load_prompt("skeleton_plan", prompt_dir)
    trajs = ""
    for i, t in enumerate(trials[:max_samples], 1):
        trajs += (
            f"\n### Example trial {i} (outcome={t.final_outcome})\n"
            f"{fmt_trajectory(t.trajectory)}\n"
        )
    user = (
        f"## Task description\n{task_description or '(unknown)'}\n\n"
        f"## Example trials (a full batch)\n{trajs or '(none)'}"
    )
    skeleton = _chat(bedrock_client, system_prompt, user, max_tokens=8192)
    return _strip_open_questions_sections(skeleton).strip()


def skeleton_to_focus_plan(skeleton: str) -> str:
    """Flatten skeleton headings into a section ▸ subsection checklist.

    Threaded verbatim into batch-summarize / doc-update so every fact is tagged to
    a designed slot. Each line is ``section`` or ``section ▸ subsection`` followed
    by the placeholder description (so the extractor knows what belongs where).
    """
    lines: list[str] = []
    current_section = ""
    pending_desc = ""

    def _flush(label: str) -> None:
        nonlocal pending_desc
        if not label:
            return
        if pending_desc:
            lines.append(f"- {label}: {pending_desc}")
        else:
            lines.append(f"- {label}")
        pending_desc = ""

    pending_label = ""
    for raw in skeleton.splitlines():
        line = raw.strip()
        if line.startswith("### "):
            _flush(pending_label)
            pending_label = f"{current_section} ▸ {line[4:].strip()}"
        elif line.startswith("## "):
            _flush(pending_label)
            current_section = line[3:].strip()
            pending_label = current_section
        elif line.startswith("<!--") and pending_label:
            pending_desc = line.strip("<!->").strip()
    _flush(pending_label)
    return "\n".join(lines)


@register_system("skill_evo_planner_tri")
class SkillEvoPlannerTriSystem(SkillEvoPlannerAuditSystem):
    """Planner designs the skeleton (sections + task-specific subsections) from
    the first batch; skeleton drives extraction; refine is additive-only."""

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "skill_evo_planner_tri")
        kwargs.setdefault("prompt_dir", os.path.join(_HERE, "prompts"))
        # Skeleton is built from the first BATCH at the first epoch boundary, not
        # from trial 1 — disable the trial-1 Stage A init.
        kwargs.setdefault("enable_init", False)
        # enable_merge: grow matched canonicals (old+new -> enriched) instead of
        # freezing at first write. Handled by the shared batch system (pops it).
        kwargs.setdefault("enable_merge", True)
        # Validation (contradiction audit) is OFF by default in val2 — probes
        # showed it is inert in-flow (no replay). Flip on to A/B it.
        self.enable_audit = bool(kwargs.pop("enable_audit", False))
        # Count-based validation: each batch, the auditor COUNTS how many of the
        # batch's trajectories give dump-evidence for each canonical; that count
        # accumulates per canonical, and the canonical is removed only once the
        # accumulated count reaches dump_threshold (symmetric to batch_summarize's
        # support-counting on the formation side).
        self.dump_threshold = int(kwargs.pop("dump_threshold", 3))
        super().__init__(**kwargs)
        self._skeleton_built = False
        self._dump_tally: dict[str, int] = {}
        self._track_plans: dict[str, str] = {}
        self._factual_enabled: bool = True

    def _run_entry_audit(self) -> None:
        if not self.enable_audit:
            return
        active = [
            c
            for c in self.aggregator.canonicals.values()
            if c.status == "active_in_skillmd"
        ]
        trials = list(getattr(self, "_recent_trials", []))
        if not active or not self.skill_md or not trials:
            return
        try:
            audits = audit_entries_counted(
                self.skill_md, active, trials, self._optimizer_client, self.prompt_dir
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[val2] counted audit failed: %s", e)
            return
        amap = {a.get("id"): a for a in audits if isinstance(a, dict) and a.get("id")}
        to_remove: list[Canonical] = []
        n_dump_evidence = 0
        for c in active:
            cnt = len((amap.get(c.canonical_id, {}) or {}).get("contradict_trials") or [])
            if cnt <= 0:
                continue
            n_dump_evidence += cnt
            self._dump_tally[c.canonical_id] = (
                self._dump_tally.get(c.canonical_id, 0) + cnt
            )
            if self._dump_tally[c.canonical_id] >= self.dump_threshold:
                to_remove.append(c)
        logger.info(
            "[val2] counted audit: %d active, %d dump-evidence counts, %d removed",
            len(active),
            n_dump_evidence,
            len(to_remove),
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
        except Exception as e:  # noqa: BLE001
            logger.warning("[val2] removal failed: %s", e)
            return
        for c in to_remove:
            c.status = "waiting"
            c.quantity = 0
            c.pending_op = None
            self._dump_tally.pop(c.canonical_id, None)
        self._save_snapshot(f"counted_audit_removed_{len(to_remove)}")

    @staticmethod
    def _is_openai_model(model_id: str) -> bool:
        m = (model_id or "").lower()
        return m.startswith(("gpt", "openai/", "o1", "o3", "o4"))

    def _make_client(self, api_key, model_id, region, max_tokens, temperature):
        """Route OpenAI model ids to the litellm-backed OpenAIChatClient; otherwise
        fall back to the default Bedrock client."""
        if self._is_openai_model(model_id):
            from .openai_client import OpenAIChatClient

            return OpenAIChatClient(
                api_key=api_key,
                model_id=model_id,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        return super()._make_client(api_key, model_id, region, max_tokens, temperature)
        # The planner fills `## task_objective_and_scoring` from the brief at
        # skeleton time; it is frozen and re-asserted after every doc rewrite so
        # the agent keeps seeing the objective/reward/baseline even on later
        # instances whose prompt no longer repeats the brief.
        self._frozen_objective = ""

    _OBJECTIVE_HEADER = "## task_objective_and_scoring"

    def _extract_section(self, md: str, header: str) -> str:
        """Return the `header` section (heading + body) up to the next `## `."""
        m = re.search(
            rf"^{re.escape(header)}\b.*?(?=\n## |\Z)", md, flags=re.S | re.M
        )
        return m.group(0).strip() if m else ""

    def _reassert_objective(self) -> None:
        """Force the frozen objective section back to its original text."""
        if not self._frozen_objective or self._frozen_objective in self.skill_md:
            return
        # Drop any drifted copy of the section, then prepend the frozen original.
        stripped = re.sub(
            rf"^{re.escape(self._OBJECTIVE_HEADER)}\b.*?(?=\n## |\Z)",
            "",
            self.skill_md,
            flags=re.S | re.M,
        ).strip()
        self.skill_md = self._frozen_objective.rstrip() + "\n\n" + stripped

    def _maybe_update_plan(self) -> None:
        """Override the planner: on the first epoch boundary design the skeleton
        from the whole batch and derive the focus plan from it. Build once."""
        if self._skeleton_built or not self._epoch_buffer:
            return
        try:
            skeleton = generate_skeleton_plan(
                task_description=self._task_description,
                trials=list(self._epoch_buffer),
                bedrock_client=self._optimizer_client,
                prompt_dir=self.prompt_dir,
                max_samples=len(self._epoch_buffer),
            )
        except Exception as e:
            logger.warning("[PlannerSkeleton] skeleton planning failed: %s", e)
            return
        if not skeleton:
            return
        # The planner designs the skeleton AND tags each section with its extraction
        # track in the SAME pass; resolve_section_tracks reads those tags (falling
        # back to a separate classifier only for an untagged skeleton) and strips the
        # tags from the doc before it becomes skill.md.
        obj_name = self._OBJECTIVE_HEADER.replace("## ", "").strip()
        self._factual_enabled = True
        try:
            section_track, self._factual_enabled, skeleton = resolve_section_tracks(
                skeleton, self._optimizer_client, self.prompt_dir, obj_name,
                task_description=self._task_description,
            )
            raw_plans = build_track_plans(skeleton, section_track, obj_name)
        except Exception as e:  # noqa: BLE001
            logger.warning("[tri] track resolution failed: %s", e)
            raw_plans = {}
        self.skill_md = skeleton
        # Freeze the planner-filled objective/scoring section.
        self._frozen_objective = self._extract_section(skeleton, self._OBJECTIVE_HEADER)
        plan = skeleton_to_focus_plan(skeleton)
        # Carry the objective/scoring into extraction so it judges reusability
        # against the actual reward/baseline.
        self.focus_plan = (
            (self._frozen_objective + "\n\n" + plan) if self._frozen_objective else plan
        )
        # Planner may judge the task pure-strategy and switch off the factual track.
        if not self._factual_enabled:
            raw_plans.pop("factual", None)
        pre = (self._frozen_objective + "\n\n") if self._frozen_objective else ""
        self._track_plans = {t: pre + p for t, p in raw_plans.items()}
        self._skeleton_built = True
        self._plan_history.append({"trial": self.trial_count, "plan": self.focus_plan})
        self._save_snapshot("skeleton_plan_init")
        logger.info(
            "[tri] skeleton built; factual_track=%s; track sizes: %s",
            self._factual_enabled,
            {t: len(p.splitlines()) for t, p in raw_plans.items()},
        )

    def _summarize_batch(self) -> None:
        """Three category-specific extraction passes (factual / strategy / failure),
        each with its own prompt and its track's sections, into one aggregator."""
        track_plans = getattr(self, "_track_plans", None)
        if not track_plans:
            return super()._summarize_batch()
        for track in TRACKS:
            plan = track_plans.get(track)
            if not plan:
                continue
            try:
                self.aggregator = stage_bc_batch_summarize(
                    trials=self._epoch_buffer,
                    aggregator=self.aggregator,
                    bedrock_client=self._optimizer_client,
                    current_epoch=self._epoch_counter,
                    prompt_dir=self.prompt_dir,
                    enable_match=self.enable_canonicalize,
                    use_trajectory_count=self.use_trajectory_count,
                    focus_plan=plan,
                    enable_replace=self.enable_replace,
                    authoritative_fast_track=self.authoritative_fast_track,
                    enable_merge=self.enable_merge,
                    prompt_name=f"extract_{track}",
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[tri] %s extraction failed: %s", track, e)

    def _process_epoch_boundary(self) -> None:
        # After extraction/update/refine mutate skill.md, restore the frozen
        # objective so it is never edited away.
        super()._process_epoch_boundary()
        self._reassert_objective()

    def reset(self) -> None:
        super().reset()
        self._skeleton_built = False
        self._frozen_objective = ""
        self._dump_tally = {}

    def get_run_artifacts(self) -> dict[str, Any]:
        artifacts = super().get_run_artifacts()
        artifacts["validation_mode"] = "counted_batch_audit"
        artifacts["dump_threshold"] = self.dump_threshold
        return artifacts


def _published_init_signature() -> inspect.Signature:
    """Inherit the audit signature, but publish enable_init=False as the default."""
    params = []
    for p in _audit_init_signature().parameters.values():
        if p.name == "enable_init":
            p = p.replace(default=False)
        params.append(p)
    params.append(
        inspect.Parameter(
            "enable_audit", inspect.Parameter.KEYWORD_ONLY, default=False, annotation=bool
        )
    )
    params.append(
        inspect.Parameter(
            "dump_threshold", inspect.Parameter.KEYWORD_ONLY, default=3, annotation=int
        )
    )
    params.append(
        inspect.Parameter(
            "enable_merge", inspect.Parameter.KEYWORD_ONLY, default=True, annotation=bool
        )
    )
    return inspect.Signature(params)


SkillEvoPlannerTriSystem.__init__.__signature__ = _published_init_signature()


__all__ = [
    "SkillEvoPlannerTriSystem",
    "generate_skeleton_plan",
    "skeleton_to_focus_plan",
    "resolve_section_tracks",
]
