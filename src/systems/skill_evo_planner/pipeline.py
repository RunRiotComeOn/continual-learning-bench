"""Skill Evolution pipeline stages A-G.

Each stage is a function that takes inputs and returns outputs as defined in
the spec. All LLM-dependent stages accept a `bedrock_client` parameter.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from .prompts import load_prompt
from .types import (
    Aggregator,
    CanaryEdit,
    CanaryState,
    Candidate,
    Canonical,
    TrialRecord,
)

logger = logging.getLogger(__name__)

_OPEN_QUESTIONS_TAG = re.compile(r"^\[open[\s_-]*questions?\]", re.IGNORECASE)
_OPEN_QUESTIONS_HEADING = re.compile(r"^##\s+open[\s_-]*questions?\s*$", re.IGNORECASE)


def _targets_open_questions(description: str) -> bool:
    """Return whether a generated memory item targets open questions."""
    return bool(_OPEN_QUESTIONS_TAG.match(description.strip()))


def _strip_open_questions_sections(skill_md: str) -> str:
    """Remove level-two open-question sections and all of their contents."""
    kept: list[str] = []
    skipping = False
    for line in skill_md.splitlines():
        is_level_two_heading = line.startswith("## ")
        if _OPEN_QUESTIONS_HEADING.match(line.strip()):
            while kept and not kept[-1].strip():
                kept.pop()
            skipping = True
            continue
        if skipping:
            if not is_level_two_heading:
                continue
            skipping = False
            if kept and kept[-1].strip():
                kept.append("")
        kept.append(line)
    return "\n".join(kept).strip()


# avoid circular import — BedrockClient is passed as argument
if TYPE_CHECKING:
    from .bedrock_client import BedrockClient


# ── Trajectory formatting ──────────────────────────────────────────────────


def fmt_trajectory(
    trajectory: list[dict[str, Any]], max_chars: int | None = None
) -> str:
    """Render the same message transcript retained by the ICL baseline.

    The structured response schema is supplied out-of-band on each model call;
    ICL does not append it to message history, so it is intentionally omitted
    here too. Default formatting is lossless. Callers may request an explicit
    character cap when they knowingly prefer truncation over transcript parity.
    """
    lines: list[str] = []
    for item in trajectory:
        if not isinstance(item, dict):
            continue
        role = item.get("role", "")
        content = str(item.get("content", ""))

        if role == "situation":
            lines.append(f"[USER]\n{content}")
        elif role == "action":
            lines.append(f"[ASSISTANT]\n{content}")
        elif role == "feedback":
            lines.append(f"[USER]\nFEEDBACK: {content}")

    text = "\n".join(lines)
    if max_chars is not None and len(text) > max_chars:
        half = max_chars // 2
        text = text[:half] + "\n...[truncated]...\n" + text[-half:]
    return text


def _chat(client: BedrockClient, system: str, user: str, max_tokens: int = 8192) -> str:
    """Simple text chat via Bedrock."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    text, _ = client.chat(messages, max_tokens=max_tokens)
    return text


def _chat_json(
    client: BedrockClient,
    system: str,
    user: str,
    max_tokens: int = 8192,
    json_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Chat via Bedrock with schema-enforced JSON output.

    Args:
        json_schema: JSON Schema dict. When provided, uses Bedrock's
            outputConfig.textFormat.json_schema for server-side enforcement.
            Falls back to json_mode (valid JSON, no schema) when None.
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    parsed, _ = client.chat_json(
        messages, max_tokens=max_tokens, json_schema=json_schema
    )
    return parsed


# ── JSON Schemas for pipeline stages ──────────────────────────────────────

EXTRACT_CANDIDATES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidates": {
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
                },
                "required": ["description", "effect", "evidence"],
            },
        }
    },
    "required": ["candidates"],
}

CANONICALIZE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "match_id": {"type": "string"},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
        "update_op": {"type": "string", "enum": ["add", "refine", "replace"]},
    },
    "required": ["match_id", "confidence", "reasoning", "update_op"],
}


# ── Stage A: Skill.md Initialization ──────────────────────────────────────


def stage_a_init_skeleton(
    task_description: str,
    sample_trajectories: list[TrialRecord],
    bedrock_client: BedrockClient,
    prompt_dir: str | None = None,
) -> str:
    """Generate the initial skill.md skeleton from task description + samples."""
    system_prompt = load_prompt("skeleton_init", prompt_dir)
    trajs_text = ""
    for i, trial in enumerate(sample_trajectories[:3], 1):
        traj_str = fmt_trajectory(trial.trajectory)
        outcome = trial.final_outcome
        trajs_text += f"\n### Sample Trajectory {i}\nOutcome: {outcome}\n{traj_str}\n"

    user = (
        f"## Task Description\n{task_description}\n\n"
        f"## Sample Trajectories\n{trajs_text}"
    )
    skeleton = _chat(bedrock_client, system_prompt, user, max_tokens=8192)
    return _strip_open_questions_sections(skeleton)


# ── Stage B: LLM Extraction → Atomic Candidates ──────────────────────────


def stage_b_extract_candidates(
    trial: TrialRecord,
    bedrock_client: BedrockClient,
    prompt_dir: str | None = None,
) -> list[Candidate]:
    """Extract atomic candidate skill edits from a single trajectory."""
    system_prompt = load_prompt("extract_candidates", prompt_dir)
    traj_text = fmt_trajectory(trial.trajectory)
    user = (
        f"## Task Type: {trial.task_type}\n"
        f"## Goal: {trial.goal}\n"
        f"## Outcome: {trial.final_outcome}\n\n"
        f"## Trajectory\n{traj_text}"
    )
    result = _chat_json(
        bedrock_client,
        system_prompt,
        user,
        json_schema=EXTRACT_CANDIDATES_SCHEMA,
    )
    candidates = []
    for c in result.get("candidates", []):
        description = c.get("description", "")
        if _targets_open_questions(description):
            continue
        candidates.append(
            Candidate(
                description=description,
                effect=c.get("effect", "unclear"),
                evidence=c.get("evidence", ""),
                source_trial_id=trial.trial_id,
            )
        )
    return candidates


# ── Stage C: Canonicalization ─────────────────────────────────────────────


def stage_c_canonicalize(
    candidates: list[Candidate],
    aggregator: Aggregator,
    bedrock_client: BedrockClient,
    current_epoch: int = 0,
    prompt_dir: str | None = None,
) -> Aggregator:
    """Align candidates to existing canonicals or mint new ones.

    Tracks which epoch each canonical was last reinforced in, so the
    decay mechanism can detect stale entries.
    """
    system_prompt = load_prompt("canonicalize_judge", prompt_dir)

    existing_list = [
        {"canonical_id": c.canonical_id, "description": c.description}
        for c in aggregator.canonicals.values()
    ]

    reinforced_this_epoch: set[str] = set()

    for candidate in candidates:
        if not existing_list:
            cid = aggregator.mint_id()
            aggregator.canonicals[cid] = Canonical(
                canonical_id=cid,
                description=candidate.description,
                effect_valence=candidate.effect,
                evidence_snippets=[candidate.evidence],
                quantity=1,
                effect_history=[candidate.effect],
                last_reinforced_epoch=current_epoch,
                epochs_since_reinforce=0,
                contributing_trials=[candidate.source_trial_id],
            )
            existing_list.append(
                {"canonical_id": cid, "description": candidate.description}
            )
            reinforced_this_epoch.add(cid)
            continue

        existing_text = json.dumps(existing_list, ensure_ascii=False, indent=2)
        user = (
            f"## New Candidate\n{candidate.description}\n\n"
            f"## Existing Canonicals\n{existing_text}"
        )
        try:
            result = _chat_json(
                bedrock_client,
                system_prompt,
                user,
                max_tokens=8192,
                json_schema=CANONICALIZE_SCHEMA,
            )
        except Exception as e:
            logger.warning("[canonicalize] LLM call failed: %s — creating new", e)
            result = {"match_id": "new"}

        match_id = result.get("match_id", "new")
        update_op = result.get("update_op", "add")

        if match_id != "new" and match_id in aggregator.canonicals:
            canon = aggregator.canonicals[match_id]
            contradicts = (
                update_op == "replace"
                and candidate.description.strip() != canon.description.strip()
            )
            if contradicts:
                # The candidate corrects/supersedes the matched fact. Overwrite
                # the content in place and reset its evidence — the old snippets
                # no longer support the new claim.
                if canon.status == "active_in_skillmd":
                    # An outdated version is live in skill.md: carry the old text
                    # and a pending replace so stage_d swaps that line out, and
                    # re-open the canonical for triggering.
                    canon.superseded_text = canon.description
                    canon.pending_op = "replace"
                    canon.status = "waiting"
                canon.description = candidate.description
                canon.effect_valence = candidate.effect
                canon.evidence_snippets = (
                    [candidate.evidence] if candidate.evidence else []
                )
                canon.effect_history = [candidate.effect]
                # The content changed, so corroboration restarts from this
                # candidate — the prior contributions supported the old text.
                canon.contributing_trials = [candidate.source_trial_id]
                # Keep the running view in sync for later candidates this epoch.
                for entry in existing_list:
                    if entry["canonical_id"] == match_id:
                        entry["description"] = candidate.description
                        break
            else:
                canon.effect_history.append(candidate.effect)
                canon.contributing_trials.append(candidate.source_trial_id)
                if candidate.evidence:
                    canon.evidence_snippets.append(candidate.evidence)
                    if len(canon.evidence_snippets) > 10:
                        canon.evidence_snippets = canon.evidence_snippets[-10:]
                if (
                    update_op == "refine"
                    and candidate.description.strip()
                    != canon.description.strip()
                ):
                    if canon.status == "active_in_skillmd":
                        canon.superseded_text = canon.description
                        canon.pending_op = "refine"
                        canon.status = "waiting"
                    canon.description = candidate.description
                    for entry in existing_list:
                        if entry["canonical_id"] == match_id:
                            entry["description"] = candidate.description
                            break
            canon.quantity += 1
            canon.last_reinforced_epoch = current_epoch
            canon.epochs_since_reinforce = 0
            reinforced_this_epoch.add(match_id)
        else:
            cid = aggregator.mint_id()
            aggregator.canonicals[cid] = Canonical(
                canonical_id=cid,
                description=candidate.description,
                effect_valence=candidate.effect,
                evidence_snippets=[candidate.evidence],
                quantity=1,
                effect_history=[candidate.effect],
                last_reinforced_epoch=current_epoch,
                epochs_since_reinforce=0,
                contributing_trials=[candidate.source_trial_id],
            )
            existing_list.append(
                {"canonical_id": cid, "description": candidate.description}
            )
            reinforced_this_epoch.add(cid)

    for cid, canon in aggregator.canonicals.items():
        if cid not in reinforced_this_epoch:
            canon.epochs_since_reinforce += 1

    return aggregator


# ── Stage C (ablation): passthrough — no LLM dedup ────────────────────────


def stage_c_passthrough(
    candidates: list[Candidate],
    aggregator: Aggregator,
    current_epoch: int = 0,
) -> Aggregator:
    """C-off ablation: every candidate becomes its own canonical.

    Skips the LLM canonicalization/dedup pass entirely. Each candidate mints a
    fresh canonical with quantity=1, so nothing is ever corroborated above 1.
    Pair this with trigger_threshold=1 so edits can still fire.
    """
    for candidate in candidates:
        cid = aggregator.mint_id()
        aggregator.canonicals[cid] = Canonical(
            canonical_id=cid,
            description=candidate.description,
            effect_valence=candidate.effect,
            evidence_snippets=[candidate.evidence] if candidate.evidence else [],
            quantity=1,
            effect_history=[candidate.effect],
            last_reinforced_epoch=current_epoch,
            epochs_since_reinforce=0,
            contributing_trials=[candidate.source_trial_id],
        )
    return aggregator


# ── Stage B+C+D (ablation): naive single-shot reflection ──────────────────


def stage_naive_reflect(
    current_skill_md: str,
    trials: list[TrialRecord],
    bedrock_client: BedrockClient,
    prompt_dir: str | None = None,
) -> str:
    """B-off ablation: revise skill.md directly from a batch of trials.

    Replaces the whole extract → canonicalize → trigger → canary flow with a
    single reflect-and-edit pass, matching the design of simpler skill systems.
    """
    system_prompt = load_prompt("naive_reflect", prompt_dir)
    trajs_text = ""
    for i, trial in enumerate(trials, 1):
        traj_str = fmt_trajectory(trial.trajectory)
        trajs_text += f"\n### Trial {i} (outcome={trial.final_outcome})\n{traj_str}\n"
    user = (
        f"## Current Skill.md\n{current_skill_md or '(empty)'}\n\n"
        f"## Recent Trials\n{trajs_text}"
    )
    updated = _chat(bedrock_client, system_prompt, user, max_tokens=8192)
    return _strip_open_questions_sections(updated)


# ── Stage D: Trigger Check + Skill.md Update ─────────────────────────────


def stage_d_trigger_and_update(
    aggregator: Aggregator,
    current_skill_md: str,
    bedrock_client: BedrockClient,
    fast_promote_multiplier: float = 2.0,
    prompt_dir: str | None = None,
    focus_plan: str = "",
    authoritative_fast_track: bool = False,
) -> tuple[str | None, list[CanaryEdit], list[str]]:
    """Check triggers and generate updated skill.md.

    Canonicals with quantity >= threshold are triggered. Among those,
    canonicals with quantity >= threshold * fast_promote_multiplier are
    **fast-promoted** directly into skill.md (skipping canary validation).
    The rest go through the normal canary path.

    Returns (v_new, canary_edits, fast_promoted_ids).
    - v_new includes fast-promoted edits baked in.
    - canary_edits lists only the edits that still need canary validation.
    - fast_promoted_ids lists canonical IDs that were fast-promoted.
    """
    current_skill_md = _strip_open_questions_sections(current_skill_md)
    fast_threshold = int(aggregator.trigger_threshold * fast_promote_multiplier)

    fast_promote: list[Canonical] = []
    canary_candidates: list[Canonical] = []

    for canon in aggregator.canonicals.values():
        if canon.status != "waiting":
            continue
        if _targets_open_questions(canon.description):
            continue
        # Authoritative facts (tool/schema/error-established) are trustworthy on a
        # single observation, so they fast-promote regardless of accumulated
        # quantity — only inferred claims need the quantity-based corroboration gate.
        if authoritative_fast_track and canon.support_type == "authoritative":
            fast_promote.append(canon)
        elif canon.quantity >= fast_threshold:
            fast_promote.append(canon)
        elif canon.quantity >= aggregator.trigger_threshold:
            canary_candidates.append(canon)

    if not fast_promote and not canary_candidates:
        return None, [], []

    system_prompt = load_prompt("generate_update", prompt_dir)
    all_triggered_info = []
    canary_edits = []
    fast_promoted_ids = []

    def _resolve_op(canon: Canonical) -> str:
        # A pending "replace" (the canonical was corrected mid-life) takes
        # precedence; otherwise infer add vs refine from the effect history.
        if canon.pending_op:
            return canon.pending_op
        positive_count = sum(1 for e in canon.effect_history if e == "positive")
        negative_count = sum(1 for e in canon.effect_history if e == "negative")
        return "add" if positive_count >= negative_count else "refine"

    def _build_info(canon: Canonical, op: str, **extra: object) -> dict:
        info = {
            "canonical_id": canon.canonical_id,
            "description": canon.description,
            "update_op": op,
            "quantity": canon.quantity,
            "evidence_sample": canon.evidence_snippets[:3],
            # Soft corroboration signal for the writer: across how many distinct
            # instances this claim has been observed. Higher = more trustworthy
            # as a firm fact; low = still tentative.
            "distinct_instances": canon.distinct_instances,
            **extra,
        }
        if op == "replace" and canon.superseded_text:
            info["replaces"] = canon.superseded_text
        return info

    for canon in fast_promote:
        op = _resolve_op(canon)
        all_triggered_info.append(_build_info(canon, op, fast_promote=True))
        canon.status = "active_in_skillmd"
        canon.pending_op = None
        canon.superseded_text = ""
        fast_promoted_ids.append(canon.canonical_id)

    for canon in canary_candidates:
        op = _resolve_op(canon)
        all_triggered_info.append(_build_info(canon, op))
        canon.status = "triggered"
        canary_edits.append(
            CanaryEdit(
                canonical_id=canon.canonical_id,
                op=op,
                content=canon.description,
            )
        )
        canon.pending_op = None
        canon.superseded_text = ""

    plan_block = (
        f"## Section plan for THIS task flow (organize the doc by these)\n{focus_plan}\n\n"
        if focus_plan
        else ""
    )
    user = (
        f"{plan_block}"
        f"## Current Skill.md\n{current_skill_md}\n\n"
        f"## Triggered Canonicals\n{json.dumps(all_triggered_info, ensure_ascii=False, indent=2)}"
    )
    v_new = _chat(bedrock_client, system_prompt, user, max_tokens=8192)
    return (
        _strip_open_questions_sections(v_new),
        canary_edits,
        fast_promoted_ids,
    )


# ── Decay: remove stale canonicals from skill.md ─────────────────────────


def stage_decay(
    aggregator: Aggregator,
    current_skill_md: str,
    bedrock_client: BedrockClient,
    decay_threshold: int = 3,
) -> tuple[str, list[str]]:
    """Remove active canonicals that haven't been reinforced for decay_threshold epochs.

    Returns (updated_skill_md, list of removed canonical IDs).
    """
    stale_ids: list[str] = []
    stale_descriptions: list[str] = []

    for cid, canon in aggregator.canonicals.items():
        if (
            canon.status == "active_in_skillmd"
            and canon.epochs_since_reinforce >= decay_threshold
        ):
            stale_ids.append(cid)
            stale_descriptions.append(canon.description)
            canon.status = "waiting"
            canon.quantity = 0
            canon.epochs_since_reinforce = 0

    if not stale_ids:
        return current_skill_md, []

    system_prompt = (
        "You are editing a skill document. Remove the following stale entries "
        "from the document. Keep all other content unchanged. Return the "
        "updated document only, no commentary.\n\n"
        "## Entries to remove\n" + "\n".join(f"- {d}" for d in stale_descriptions)
    )
    user = f"## Current Skill.md\n{current_skill_md}"
    updated = _chat(bedrock_client, system_prompt, user, max_tokens=8192)

    logger.info(
        "[decay] Removed %d stale canonicals: %s",
        len(stale_ids),
        stale_ids,
    )
    return updated.strip(), stale_ids


# ── Stage F: Promote / Revert based on canary Δeffect ─────────────────────


def stage_f_promote_or_revert(
    canary: CanaryState,
    aggregator: Aggregator,
) -> str:
    """Promote or revert canary edits based on epoch-level Δeffect.

    Compares mean(canary_scores) against baseline_score from the
    preceding accumulation epoch.

    Returns the new deployed skill.md.
    """
    delta = canary.delta_effect

    if delta >= 0:
        for edit in canary.edits:
            if edit.canonical_id in aggregator.canonicals:
                aggregator.canonicals[edit.canonical_id].status = "active_in_skillmd"
        return canary.v_new
    else:
        for edit in canary.edits:
            if edit.canonical_id in aggregator.canonicals:
                aggregator.canonicals[edit.canonical_id].status = "waiting"
                aggregator.canonicals[edit.canonical_id].quantity = 0
        return canary.v_old


EVIDENCE_REVERT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "canonical_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["falsified", "kept"]},
                    "reason": {"type": "string"},
                },
                "required": ["canonical_id", "verdict"],
            },
        },
        "skill_md": {"type": "string"},
    },
    "required": ["verdicts", "skill_md"],
}


def stage_f_evidence_revert(
    canary: CanaryState,
    trials: list[TrialRecord],
    aggregator: Aggregator,
    bedrock_client: BedrockClient,
    prompt_dir: str | None = None,
) -> str:
    """Conservative evidence-based selective revert (replaces stage_f's gate).

    Instead of comparing the canary window's mean reward to a different batch of
    baseline questions (noisy, item-difficulty-confounded), inspect the window
    trajectories — run under v_new — and revert ONLY the probation edits the
    evidence clearly falsifies (the agent applied the claim and it errored /
    contradicted an observed result). Edits never exercised, or with no
    contradicting evidence, are KEPT. Returns the new deployed skill.md.
    """
    if not canary.edits:
        return canary.v_new

    edits_text = "\n".join(
        f"- [{e.canonical_id}] ({e.op}) {e.content}" for e in canary.edits
    )
    trajs_text = ""
    for i, trial in enumerate(trials, 1):
        trajs_text += (
            f"\n### Trial {i} (outcome={trial.final_outcome})\n"
            f"{fmt_trajectory(trial.trajectory)}\n"
        )
    system_prompt = load_prompt("canary_evidence_revert", prompt_dir)
    user = (
        f"## New document (with probation edits applied)\n{canary.v_new}\n\n"
        f"## Probation edits (just added — judge each)\n{edits_text}\n\n"
        f"## Trials run WITH the new document\n{trajs_text or '(none)'}"
    )

    edit_ids = {e.canonical_id for e in canary.edits}
    try:
        parsed = _chat_json(
            bedrock_client,
            system_prompt,
            user,
            max_tokens=8192,
            json_schema=EVIDENCE_REVERT_SCHEMA,
        )
        verdicts = parsed.get("verdicts", [])
        new_md = (parsed.get("skill_md") or "").strip()
    except Exception as e:  # conservative: on any failure, keep everything
        logger.warning("[evidence_revert] judge failed (%s) — keeping all edits", e)
        verdicts, new_md = [], ""

    falsified = {
        v["canonical_id"]
        for v in verdicts
        if v.get("verdict") == "falsified" and v.get("canonical_id") in edit_ids
    }
    # 疑罪从无: anything not explicitly falsified stays active in the doc.
    for edit in canary.edits:
        canon = aggregator.canonicals.get(edit.canonical_id)
        if canon is None:
            continue
        if edit.canonical_id in falsified:
            canon.status = "waiting"
            canon.quantity = 0
        else:
            canon.status = "active_in_skillmd"

    logger.info(
        "[evidence_revert] %d/%d probation edits falsified by evidence: %s",
        len(falsified),
        len(canary.edits),
        sorted(falsified) or "none",
    )

    if not falsified:
        return canary.v_new
    # guard against a truncated/gutted rewrite — never accept a doc that lost
    # most of its content; fall back to the un-reverted new version.
    if len(new_md) < 0.5 * len(canary.v_new):
        logger.warning("[evidence_revert] corrected doc too short — keeping v_new")
        return canary.v_new
    return new_md


# ── Stage G: Refine Skill.md Skeleton ─────────────────────────────────────


def stage_g_refine_skeleton(
    current_skill_md: str,
    bedrock_client: BedrockClient,
    prompt_dir: str | None = None,
) -> str:
    """Reorganize skill.md for clarity after promote/revert cycles."""
    system_prompt = load_prompt("skeleton_refine", prompt_dir)
    user = f"## Current Skill.md\n{current_skill_md}"
    refined = _chat(bedrock_client, system_prompt, user, max_tokens=8192)
    return _strip_open_questions_sections(refined)


def stage_g_refine_grounded(
    current_skill_md: str,
    trials: list[TrialRecord],
    bedrock_client: BedrockClient,
    prompt_dir: str | None = None,
) -> str:
    """Grounded refine: reorganize AND fact-check skill.md against recent trials.

    Unlike ``stage_g_refine_skeleton`` (which sees only the document text and is
    forbidden from removing anything), this pass also receives the recent trial
    trajectories + outcomes, so it can correct or drop claims the evidence
    contradicts — grafting naive reflection's self-correction onto the gated
    pipeline.
    """
    system_prompt = load_prompt("skeleton_refine_grounded", prompt_dir)
    trajs_text = ""
    for i, trial in enumerate(trials, 1):
        traj_str = fmt_trajectory(trial.trajectory)
        trajs_text += f"\n### Trial {i} (outcome={trial.final_outcome})\n{traj_str}\n"
    user = (
        f"## Current Skill.md\n{current_skill_md or '(empty)'}\n\n"
        f"## Recent Trials\n{trajs_text or '(none)'}"
    )
    refined = _chat(bedrock_client, system_prompt, user, max_tokens=8192)
    return _strip_open_questions_sections(refined)
