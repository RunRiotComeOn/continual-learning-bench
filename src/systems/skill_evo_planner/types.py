"""Data structures for the Skill Evolution pipeline.

Defines the core types: TrialRecord, Candidate, Canonical, CanonicalPlacement,
Aggregator, and CanaryState.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Trial
# ---------------------------------------------------------------------------


@dataclass
class TrialRecord:
    """One completed trial (task instance) with its trajectory and outcome."""

    trial_id: str
    task_type: str
    trajectory: list[dict[str, Any]]
    final_outcome: dict[str, Any]
    setting: str = ""
    goal: str = ""
    context: str = ""
    environment_shift: bool = False


# ---------------------------------------------------------------------------
# Candidate (extracted from a single trajectory)
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    """An atomic candidate skill edit extracted from one trajectory."""

    description: str
    effect: Literal["positive", "negative", "unclear"]
    evidence: str
    source_trial_id: str = ""


# ---------------------------------------------------------------------------
# Canonical (deduplicated, aggregated)
# ---------------------------------------------------------------------------


@dataclass
class Canonical:
    """A canonicalized rule aggregated from multiple candidates."""

    canonical_id: str
    description: str
    effect_valence: Literal["positive", "negative", "unclear"]
    evidence_snippets: list[str] = field(default_factory=list)
    quantity: int = 1
    status: Literal["waiting", "active_in_skillmd", "triggered"] = "waiting"
    effect_history: list[Literal["positive", "negative", "unclear"]] = field(
        default_factory=list
    )
    last_reinforced_epoch: int = 0
    epochs_since_reinforce: int = 0
    # When a candidate refines or supersedes a canonical that is already live in
    # skill.md, we overwrite the canonical description in place and carry a
    # pending op so stage_d re-opens the live entry and writes the change back.
    pending_op: Literal["add", "refine", "replace"] | None = None
    superseded_text: str = ""
    # "authoritative" = a fact established directly by a tool result / schema /
    # explicit error or feedback (a durable env fact or directly-observed value),
    # trustworthy on a single observation. "inferred" = a strategy, attribution,
    # or generalization that rests on interpretation and benefits from repeated
    # corroboration. Used by the authoritative-fast-track promotion gate.
    support_type: Literal["authoritative", "inferred"] = "inferred"
    # The distinct trials (instances) that reinforced this canonical. Surfaced
    # to the writer as a soft corroboration signal — how broadly a claim has
    # been observed — not as a hard gate.
    contributing_trials: list[str] = field(default_factory=list)

    @property
    def distinct_instances(self) -> int:
        """Number of distinct trials (instances) that reinforced this claim."""
        return len(set(self.contributing_trials))

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "description": self.description,
            "effect_valence": self.effect_valence,
            "evidence_snippets": self.evidence_snippets,
            "quantity": self.quantity,
            "status": self.status,
            "effect_history": self.effect_history,
            "last_reinforced_epoch": self.last_reinforced_epoch,
            "epochs_since_reinforce": self.epochs_since_reinforce,
            "pending_op": self.pending_op,
            "superseded_text": self.superseded_text,
            "support_type": self.support_type,
            "contributing_trials": self.contributing_trials,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Canonical:
        return cls(
            canonical_id=d["canonical_id"],
            description=d["description"],
            effect_valence=d.get("effect_valence", "unclear"),
            evidence_snippets=d.get("evidence_snippets", []),
            quantity=d.get("quantity", 1),
            status=d.get("status", "waiting"),
            effect_history=d.get("effect_history", []),
            last_reinforced_epoch=d.get("last_reinforced_epoch", 0),
            epochs_since_reinforce=d.get("epochs_since_reinforce", 0),
            pending_op=d.get("pending_op"),
            superseded_text=d.get("superseded_text", ""),
            support_type=d.get("support_type", "inferred"),
            contributing_trials=d.get("contributing_trials", []),
        )


# ---------------------------------------------------------------------------
# Canonical Placement (position in skill.md)
# ---------------------------------------------------------------------------


@dataclass
class CanonicalPlacement:
    """Tracks where a canonical entry is placed in skill.md."""

    canonical_id: str
    section: str
    anchor_position: int = 0
    role: str = ""


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


@dataclass
class Aggregator:
    """Accumulates canonicals and tracks trigger thresholds."""

    canonicals: dict[str, Canonical] = field(default_factory=dict)
    trigger_threshold: int = 10
    next_canonical_id: int = 1

    def mint_id(self) -> str:
        cid = f"c{self.next_canonical_id}"
        self.next_canonical_id += 1
        return cid

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonicals": {k: v.to_dict() for k, v in self.canonicals.items()},
            "trigger_threshold": self.trigger_threshold,
            "next_canonical_id": self.next_canonical_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Aggregator:
        agg = cls(
            trigger_threshold=d.get("trigger_threshold", 10),
            next_canonical_id=d.get("next_canonical_id", 1),
        )
        for k, v in d.get("canonicals", {}).items():
            agg.canonicals[k] = Canonical.from_dict(v)
        return agg


# ---------------------------------------------------------------------------
# Canary State
# ---------------------------------------------------------------------------


@dataclass
class CanaryEdit:
    """One edit in the canary version, tracked individually."""

    canonical_id: str
    op: Literal["add", "refine", "replace"]
    content: str


@dataclass
class CanaryState:
    """Tracks the canary validation window.

    The canary compares performance of v_new (with edits) against a
    baseline_score computed from the accumulation epoch that preceded it.
    """

    v_old: str = ""
    v_new: str = ""
    edits: list[CanaryEdit] = field(default_factory=list)
    baseline_score: float = 0.0
    canary_scores: list[float] = field(default_factory=list)
    window_size: int = 5
    active: bool = False

    def start(
        self,
        v_old: str,
        v_new: str,
        edits: list[CanaryEdit],
        window_size: int,
        baseline_score: float,
    ) -> None:
        self.v_old = v_old
        self.v_new = v_new
        self.edits = edits
        self.window_size = window_size
        self.baseline_score = baseline_score
        self.canary_scores = []
        self.active = True

    def record_score(self, score: float) -> None:
        self.canary_scores.append(score)
        if len(self.canary_scores) >= self.window_size:
            self.active = False

    @property
    def canary_mean(self) -> float:
        if not self.canary_scores:
            return 0.0
        return sum(self.canary_scores) / len(self.canary_scores)

    @property
    def delta_effect(self) -> float:
        return self.canary_mean - self.baseline_score

    def clear(self) -> None:
        self.v_old = ""
        self.v_new = ""
        self.edits = []
        self.canary_scores = []
        self.active = False
        self.baseline_score = 0.0
