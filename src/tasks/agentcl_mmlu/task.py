"""AgentCL — MMLU(-Pro) subset as a continual-learning task.

Dataset: ``osunlp/AgentCL`` (default split, 300 rows) — MMLU-Pro-style
multiple-choice questions grouped by domain (economics, engineering, philosophy,
100 each). Each instance is ONE question: the system reads the question + options
and submits a single letter; it then receives correct/incorrect feedback (with the
correct letter) before the next question. Because questions are independent
knowledge but domains arrive in blocks, this tests whether a system can accumulate
reusable domain knowledge / solving strategy across a sequence — the regime where
ICL's raw-recency advantage is weakest.

Reward = accuracy (1.0 correct, 0.0 wrong). r_max = 1.0.
"""

from __future__ import annotations

import json
import os
import string
from typing import Any, Optional

from pydantic import BaseModel, Field

from ...interface import (
    ContinualLearningTask,
    EvalMetrics,
    InstanceOutcome,
    Observation,
    Query,
    Response,
    TaskAgentBrief,
    TaskResult,
    TaskStepResult,
    format_task_agent_brief,
)
from ...registry import register_task

_HERE = os.path.dirname(__file__)
_DEFAULT_DATA = os.path.join(
    _HERE, "..", "..", "..", "data", "agentcl_mmlu", "mmlu.json"
)


class MMLUAnswer(BaseModel):
    """One multiple-choice answer."""

    reasoning: str = Field(description="Brief rationale for the choice.")
    answer: str = Field(
        description="The single letter of the chosen option (e.g. 'A', 'B', …)."
    )


def _letters(n: int) -> list[str]:
    return list(string.ascii_uppercase[:n])


def _render_question(row: dict[str, Any]) -> str:
    opts = row["options"]
    lines = [row["question"], ""]
    for letter, opt in zip(_letters(len(opts)), opts):
        lines.append(f"{letter}. {opt}")
    return "\n".join(lines)


def _parse_letter(raw: str, n_options: int) -> Optional[str]:
    """Pull the first valid option letter out of a free-text answer field."""
    if not raw:
        return None
    valid = set(_letters(n_options))
    for ch in raw.strip().upper():
        if ch in valid:
            return ch
    return None


@register_task("agentcl_mmlu")
class AgentCLMMLUTask(ContinualLearningTask):
    r_max = 1.0

    def __init__(
        self,
        num_instances: int = 300,
        seed: int = 42,
        data_path: Optional[str] = None,
        schedule: Optional[str] = None,  # accepted for CLI parity; unused
        **kwargs: Any,
    ):
        self.seed = seed
        self.schedule = schedule
        path = data_path or _DEFAULT_DATA
        with open(path) as f:
            self._all: list[dict[str, Any]] = json.load(f)
        self._canonical_n = min(num_instances, len(self._all))
        self.num_instances = self._canonical_n
        self.instances: list[dict[str, Any]] = []
        self.current_instance_idx = 0
        self._instance_outcomes: list[InstanceOutcome] = []

    # ── lifecycle ──────────────────────────────────────────────────────────
    def build_canonical_run_state(self) -> None:
        # Canonical order = dataset order (domain-blocked: econ, eng, phil).
        self.instances = list(self._all[: self._canonical_n])
        self.current_instance_idx = 0
        self._instance_outcomes = []

    def build_current_query(self) -> Query:
        row = self.instances[self.current_instance_idx]
        body = (
            "Answer the following multiple-choice question. Respond with the single "
            "letter of the correct option.\n\n" + _render_question(row)
        )
        if self.current_instance_idx == 0:
            brief = self.get_agent_brief()
            if brief is not None:
                body = f"{format_task_agent_brief(brief)}\n\n{body}"
        return Query(
            prompt=body,
            instance_id=f"agentcl_mmlu:{row['question_id']}",
            instance_index=self.canonical_instance_index(self.current_instance_idx),
            metadata={
                "category": row.get("category", ""),
                "n_options": len(row["options"]),
                "active_instance_idx": self.current_instance_idx,
            },
            response_schema=MMLUAnswer,
        )

    def step(self, response: Response) -> TaskStepResult:
        row = self.instances[self.current_instance_idx]
        gt = str(row["answer"]).strip().upper()
        pred = _parse_letter(getattr(response.action, "answer", ""), len(row["options"]))
        correct = pred is not None and pred == gt
        reward = 1.0 if correct else 0.0

        outcome = InstanceOutcome(
            instance_id=f"agentcl_mmlu:{row['question_id']}",
            instance_index=self.canonical_instance_index(self.current_instance_idx),
            reward=reward,
            success=correct,
            raw_metric_name="accuracy",
            raw_metric_value=reward,
            raw_metric_higher_is_better=True,
            metadata={"category": row.get("category", ""), "predicted": pred, "answer": gt},
        )
        self._instance_outcomes.append(outcome)

        verdict = "CORRECT" if correct else "INCORRECT"
        obs = Observation(
            content=f"{verdict}. The correct answer was {gt}.",
            instance_complete=True,
            metadata={"reward": reward, "correct": correct, "instance_complete": True},
        )

        self.current_instance_idx += 1
        done = self.current_instance_idx >= len(self.instances)
        next_query = None if done else self.build_current_query()
        return TaskStepResult(
            observation=obs, next_query=next_query, done=done, instance_outcome=outcome
        )

    def evaluate(self) -> TaskResult:
        outs = self._instance_outcomes
        n = len(outs)
        total = sum(o.reward for o in outs)
        acc = total / n if n else 0.0
        # per-category accuracy
        cat: dict[str, list[float]] = {}
        for o in outs:
            cat.setdefault((o.metadata or {}).get("category", "?"), []).append(o.reward)
        cat_acc = {k: round(sum(v) / len(v), 4) for k, v in cat.items()}

        eval_metrics = EvalMetrics(
            loss_curve=[1.0 - o.reward for o in outs],  # per-instance error
            optimal_performance=float(n),  # all correct
            actual_performance=round(total, 6),
            extra={f"acc_{k}": v for k, v in cat_acc.items()},
        )
        return TaskResult(
            metrics={
                "accuracy": round(acc, 6),
                "num_instances": n,
                "num_correct": int(total),
                "category_accuracy": cat_acc,
            },
            summary=(
                f"Answered {n} MMLU questions; accuracy {acc:.4f} "
                f"({int(total)}/{n}). Per-category: {cat_acc}"
            ),
            eval_metrics=eval_metrics,
            instance_outcomes=outs,
        )

    # ── metadata ───────────────────────────────────────────────────────────
    @property
    def name(self) -> str:
        return "agentcl_mmlu"

    @property
    def description(self) -> str:
        return (
            "AgentCL MMLU(-Pro) subset: 300 domain-blocked multiple-choice "
            "questions answered sequentially with correctness feedback."
        )

    def get_agent_brief(self) -> TaskAgentBrief:
        return TaskAgentBrief(
            objective=(
                "Answer a sequence of multiple-choice knowledge questions "
                "(economics, engineering, philosophy). After each answer you are "
                "told whether it was correct and what the right option was; use "
                "that running feedback to answer later questions better."
            ),
            instance_unit="One multiple-choice question.",
            reward_definition=(
                "Accuracy: 1.0 for the correct option letter, 0.0 otherwise. "
                "Higher is better."
            ),
            completion_definition="An instance completes when you submit one letter.",
            constraints=[
                "Respond with exactly one option letter.",
                "No tools; answer from knowledge and accumulated feedback.",
            ],
        )
