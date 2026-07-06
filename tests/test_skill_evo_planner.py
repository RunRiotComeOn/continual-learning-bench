import re
from pathlib import Path
from unittest.mock import patch

from src.systems.skill_evo_planner.batch_system import stage_bc_batch_summarize
from src.systems.skill_evo_planner.pipeline import (
    _strip_open_questions_sections,
    fmt_trajectory,
    stage_a_init_skeleton,
    stage_b_extract_candidates,
)
from src.systems.skill_evo_planner.system import generate_focus_plan
from src.systems.skill_evo_planner.types import Aggregator, TrialRecord


_PROMPTS_DIR = (
    Path(__file__).resolve().parents[1] / "src/systems/skill_evo_planner/prompts"
)


def _trial() -> TrialRecord:
    return TrialRecord(
        trial_id="trial-1",
        task_type="test",
        trajectory=[],
        final_outcome={"success": False},
    )


def test_trajectory_matches_icl_message_transcript() -> None:
    trajectory = [
        {"role": "situation", "content": "Hand #1"},
        {"role": "response_schema", "content": '{"type":"object"}'},
        {"role": "action", "content": '{"action":"CHECK"}'},
        {"role": "feedback", "content": "Action taken"},
    ]

    assert fmt_trajectory(trajectory) == (
        "[USER]\nHand #1\n"
        '[ASSISTANT]\n{"action":"CHECK"}\n'
        "[USER]\nFEEDBACK: Action taken"
    )


def test_trajectory_is_not_truncated_by_default() -> None:
    content = "x" * 20_000

    formatted = fmt_trajectory([{"role": "situation", "content": content}])

    assert content in formatted
    assert "[truncated]" not in formatted


def test_strip_open_questions_sections_removes_entire_section() -> None:
    skill = (
        "## environment_facts\n- observed fact\n\n"
        "## Open Questions\n- unsupported hypothesis\n\n"
        "### nested heading\n- more speculation\n\n"
        "## strategy\n- demonstrated procedure\n"
    )

    assert _strip_open_questions_sections(skill) == (
        "## environment_facts\n- observed fact\n\n## strategy\n- demonstrated procedure"
    )


def test_skeleton_generation_strips_open_questions_section() -> None:
    generated = "## general\n\n## open_questions\n- placeholder\n\n## strategy"
    with patch("src.systems.skill_evo_planner.pipeline._chat", return_value=generated):
        skeleton = stage_a_init_skeleton("task", [_trial()], object())

    assert "open_questions" not in skeleton.lower()
    assert skeleton == "## general\n\n## strategy"


def test_candidate_extraction_drops_open_questions() -> None:
    parsed = {
        "candidates": [
            {
                "description": "[open_questions] unsupported hypothesis",
                "effect": "unclear",
                "evidence": "none",
            },
            {
                "description": "[strategy] demonstrated procedure",
                "effect": "positive",
                "evidence": "explicit feedback",
            },
        ]
    }
    with patch(
        "src.systems.skill_evo_planner.pipeline._chat_json", return_value=parsed
    ):
        candidates = stage_b_extract_candidates(_trial(), object())

    assert [candidate.description for candidate in candidates] == [
        "[strategy] demonstrated procedure"
    ]


def test_batch_summarize_drops_open_questions() -> None:
    parsed = {
        "points": [
            {
                "description": "[open_questions] unsupported hypothesis",
                "effect": "unclear",
                "evidence": "none",
                "trajectories": [1],
                "match": "new",
            },
            {
                "description": "[strategy] demonstrated procedure",
                "effect": "positive",
                "evidence": "explicit feedback",
                "trajectories": [1],
                "match": "new",
            },
        ]
    }
    with patch(
        "src.systems.skill_evo_planner.batch_system._chat_json",
        return_value=parsed,
    ):
        aggregator = stage_bc_batch_summarize([_trial()], Aggregator(), object())

    assert [c.description for c in aggregator.canonicals.values()] == [
        "[strategy] demonstrated procedure"
    ]


def test_focus_plan_drops_open_questions_dimension() -> None:
    parsed = {
        "dimensions": [
            {"name": "open_questions", "what_to_capture": "hypotheses"},
            {"name": "strategy", "what_to_capture": "procedures"},
        ]
    }
    with patch("src.systems.skill_evo_planner.system._chat_json", return_value=parsed):
        plan = generate_focus_plan("task", [_trial()], object())

    assert plan == "- strategy: procedures"


def test_planner_prompts_do_not_reference_open_questions() -> None:
    pattern = re.compile(r"open[\s_-]*questions?", re.IGNORECASE)

    for prompt_path in _PROMPTS_DIR.glob("*.md"):
        assert not pattern.search(prompt_path.read_text()), prompt_path
