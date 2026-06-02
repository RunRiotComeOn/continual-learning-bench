"""Skill Evolution pipeline stages A-G.

Each stage is a function that takes inputs and returns outputs as defined in
the spec. All LLM-dependent stages accept a `bedrock_client` parameter.
"""
from __future__ import annotations

import json
import logging
from typing import Any

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

# avoid circular import — BedrockClient is passed as argument
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bedrock_client import BedrockClient


# ── Trajectory formatting ──────────────────────────────────────────────────

_MAX_TRAJ_CHARS = 15_000


def fmt_trajectory(trajectory: list[dict[str, Any]], max_chars: int = _MAX_TRAJ_CHARS) -> str:
    """Format a trajectory into a structured narrative for the analyst.

    The trajectory alternates situation → action → feedback entries.
    For poker, this produces a readable hand history showing what the
    agent saw, what it decided, and what the opponent did.
    """
    lines: list[str] = []
    for item in trajectory:
        if not isinstance(item, dict):
            continue
        role = item.get("role", "")
        content = str(item.get("content", ""))

        if role == "situation":
            lines.append(f"[SITUATION] {content}")
        elif role == "action":
            try:
                action_data = json.loads(content)
                thinking = action_data.get("thinking", "")
                act = action_data.get("action", "")
                amount = action_data.get("amount")
                act_str = f"{act} {amount}" if amount else act
                lines.append(f"[AGENT THINKING] {thinking}")
                lines.append(f"[AGENT ACTION] {act_str}")
            except (json.JSONDecodeError, TypeError):
                lines.append(f"[AGENT ACTION] {content}")
        elif role == "feedback":
            lines.append(f"[OUTCOME] {content}")
        else:
            lines.append(f"[{role.upper()}] {content}")

    text = "\n".join(lines)
    if len(text) > max_chars:
        half = max_chars // 2
        text = text[:half] + "\n...[truncated]...\n" + text[-half:]
    return text


def _chat(client: BedrockClient, system: str, user: str, max_tokens: int = 4096) -> str:
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
    max_tokens: int = 2048,
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
    parsed, _ = client.chat_json(messages, max_tokens=max_tokens, json_schema=json_schema)
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
                    "effect": {"type": "string", "enum": ["positive", "negative", "unclear"]},
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
) -> str:
    """Generate the initial skill.md skeleton from task description + samples."""
    system_prompt = load_prompt("skeleton_init")
    trajs_text = ""
    for i, trial in enumerate(sample_trajectories[:3], 1):
        traj_str = fmt_trajectory(trial.trajectory)
        outcome = trial.final_outcome
        trajs_text += (
            f"\n### Sample Trajectory {i}\n"
            f"Outcome: {outcome}\n"
            f"{traj_str}\n"
        )

    user = (
        f"## Task Description\n{task_description}\n\n"
        f"## Sample Trajectories\n{trajs_text}"
    )
    skeleton = _chat(bedrock_client, system_prompt, user, max_tokens=2048)
    return skeleton.strip()


# ── Stage B: LLM Extraction → Atomic Candidates ──────────────────────────

def stage_b_extract_candidates(
    trial: TrialRecord,
    bedrock_client: BedrockClient,
) -> list[Candidate]:
    """Extract atomic candidate skill edits from a single trajectory."""
    system_prompt = load_prompt("extract_candidates")
    traj_text = fmt_trajectory(trial.trajectory)
    user = (
        f"## Task Type: {trial.task_type}\n"
        f"## Goal: {trial.goal}\n"
        f"## Outcome: {trial.final_outcome}\n\n"
        f"## Trajectory\n{traj_text}"
    )
    result = _chat_json(
        bedrock_client, system_prompt, user,
        json_schema=EXTRACT_CANDIDATES_SCHEMA,
    )
    candidates = []
    for c in result.get("candidates", []):
        candidates.append(
            Candidate(
                description=c.get("description", ""),
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
) -> Aggregator:
    """Align candidates to existing canonicals or mint new ones.

    Tracks which epoch each canonical was last reinforced in, so the
    decay mechanism can detect stale entries.
    """
    system_prompt = load_prompt("canonicalize_judge")

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
                bedrock_client, system_prompt, user,
                max_tokens=1024,
                json_schema=CANONICALIZE_SCHEMA,
            )
        except Exception as e:
            logger.warning("[canonicalize] LLM call failed: %s — creating new", e)
            result = {"match_id": "new"}

        match_id = result.get("match_id", "new")

        if match_id != "new" and match_id in aggregator.canonicals:
            canon = aggregator.canonicals[match_id]
            canon.quantity += 1
            canon.effect_history.append(candidate.effect)
            canon.last_reinforced_epoch = current_epoch
            canon.epochs_since_reinforce = 0
            if candidate.evidence:
                canon.evidence_snippets.append(candidate.evidence)
                if len(canon.evidence_snippets) > 10:
                    canon.evidence_snippets = canon.evidence_snippets[-10:]
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
            )
            existing_list.append(
                {"canonical_id": cid, "description": candidate.description}
            )
            reinforced_this_epoch.add(cid)

    for cid, canon in aggregator.canonicals.items():
        if cid not in reinforced_this_epoch:
            canon.epochs_since_reinforce += 1

    return aggregator


# ── Stage D: Trigger Check + Skill.md Update ─────────────────────────────

def stage_d_trigger_and_update(
    aggregator: Aggregator,
    current_skill_md: str,
    bedrock_client: BedrockClient,
    fast_promote_multiplier: float = 2.0,
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
    fast_threshold = int(aggregator.trigger_threshold * fast_promote_multiplier)

    fast_promote: list[Canonical] = []
    canary_candidates: list[Canonical] = []

    for canon in aggregator.canonicals.values():
        if canon.status != "waiting":
            continue
        if canon.quantity >= fast_threshold:
            fast_promote.append(canon)
        elif canon.quantity >= aggregator.trigger_threshold:
            canary_candidates.append(canon)

    if not fast_promote and not canary_candidates:
        return None, [], []

    system_prompt = load_prompt("generate_update")
    all_triggered_info = []
    canary_edits = []
    fast_promoted_ids = []

    for canon in fast_promote:
        positive_count = sum(1 for e in canon.effect_history if e == "positive")
        negative_count = sum(1 for e in canon.effect_history if e == "negative")
        op = "add" if positive_count >= negative_count else "refine"
        all_triggered_info.append({
            "canonical_id": canon.canonical_id,
            "description": canon.description,
            "update_op": op,
            "quantity": canon.quantity,
            "evidence_sample": canon.evidence_snippets[:3],
            "fast_promote": True,
        })
        canon.status = "active_in_skillmd"
        fast_promoted_ids.append(canon.canonical_id)

    for canon in canary_candidates:
        positive_count = sum(1 for e in canon.effect_history if e == "positive")
        negative_count = sum(1 for e in canon.effect_history if e == "negative")
        op = "add" if positive_count >= negative_count else "refine"
        all_triggered_info.append({
            "canonical_id": canon.canonical_id,
            "description": canon.description,
            "update_op": op,
            "quantity": canon.quantity,
            "evidence_sample": canon.evidence_snippets[:3],
        })
        canon.status = "triggered"
        canary_edits.append(
            CanaryEdit(
                canonical_id=canon.canonical_id,
                op=op,
                content=canon.description,
            )
        )

    user = (
        f"## Current Skill.md\n{current_skill_md}\n\n"
        f"## Triggered Canonicals\n{json.dumps(all_triggered_info, ensure_ascii=False, indent=2)}"
    )
    v_new = _chat(bedrock_client, system_prompt, user, max_tokens=4096)
    return v_new.strip(), canary_edits, fast_promoted_ids


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
        "## Entries to remove\n"
        + "\n".join(f"- {d}" for d in stale_descriptions)
    )
    user = f"## Current Skill.md\n{current_skill_md}"
    updated = _chat(bedrock_client, system_prompt, user, max_tokens=4096)

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


# ── Stage G: Refine Skill.md Skeleton ─────────────────────────────────────

def stage_g_refine_skeleton(
    current_skill_md: str,
    bedrock_client: BedrockClient,
) -> str:
    """Reorganize skill.md for clarity after promote/revert cycles."""
    system_prompt = load_prompt("skeleton_refine")
    user = f"## Current Skill.md\n{current_skill_md}"
    refined = _chat(bedrock_client, system_prompt, user, max_tokens=4096)
    return refined.strip()
