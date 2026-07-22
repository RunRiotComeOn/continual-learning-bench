import pytest

from scripts.skill_reliability_audit import (
    compute_document_metrics,
    render_report,
    validate_audit,
)


def _entry(
    entry_id: str,
    label: str,
    tokens: int,
    *,
    cross: bool = False,
    boilerplate: bool = False,
) -> dict[str, object]:
    return {
        "id": entry_id,
        "text": f"claim {entry_id}",
        "source_lines": [1, 1],
        "claim_type": "boilerplate" if boilerplate else "strategy",
        "source_context": "test",
        "claimed_scope": "all variants",
        "expected_effect": "test effect",
        "falsifier": "test falsifier",
        "label": label,
        "evidence_level": 0 if boilerplate else 2,
        "cross_condition_tested": cross,
        "token_count": tokens,
        "reason": "template" if boilerplate else "supported by test evidence",
        "evidence_refs": [] if boilerplate else ["tests:fixture"],
        "paired_replay_candidate": False,
    }


def _audit(entries: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "max_evidence_level": 3,
        "audit_scope": "test audit",
        "documents": [
            {
                "document_id": "run_0",
                "path": "skill.md",
                "entries": entries,
            }
        ],
    }


def test_metrics_exclude_boilerplate_and_untested_entries():
    document = {
        "document_id": "run_0",
        "path": "skill.md",
        "entries": [
            _entry("a", "reliable", 10, cross=True),
            _entry("b", "overgeneralized", 30, cross=True),
            _entry("c", "unexecutable", 20),
            _entry("d", "insufficient_test", 40),
            _entry("e", "reliable", 100, boilerplate=True),
        ],
    }

    metrics = compute_document_metrics(document)

    assert metrics["total_non_boilerplate"] == 4
    assert metrics["evaluable_entries"] == 3
    assert metrics["unreliable_entries"] == 2
    assert metrics["uer"] == 2 / 3
    assert metrics["confirmed_unreliable_rate"] == 2 / 4
    assert metrics["ogr"] == 1 / 2
    assert metrics["evaluation_coverage"] == 3 / 4
    assert metrics["token_weighted_uer"] == 50 / 60
    assert metrics["label_counts"] == {
        "reliable": 1,
        "contradicted": 0,
        "harmful": 0,
        "overgeneralized": 1,
        "unexecutable": 1,
        "inert": 0,
        "insufficient_test": 1,
    }


def test_level_three_pilot_rejects_harmful_label():
    data = _audit([_entry("a", "harmful", 10)])

    with pytest.raises(ValueError, match="requires evidence level 4"):
        validate_audit(data)


def test_non_boilerplate_entry_requires_evidence_reference():
    entry = _entry("a", "reliable", 10)
    entry["evidence_refs"] = []

    with pytest.raises(ValueError, match="evidence_refs"):
        validate_audit(_audit([entry]))


def test_unknown_label_fails_validation():
    with pytest.raises(ValueError, match="unknown label"):
        validate_audit(_audit([_entry("a", "probably_ok", 10)]))


def test_duplicate_entry_id_fails_validation():
    with pytest.raises(ValueError, match="duplicate entry id"):
        validate_audit(_audit([_entry("a", "reliable", 10)] * 2))


def test_ogr_is_none_without_cross_condition_tests():
    document = {
        "document_id": "run_0",
        "path": "skill.md",
        "entries": [_entry("a", "reliable", 10)],
    }

    assert compute_document_metrics(document)["ogr"] is None


def test_report_renders_counts_percentages_and_causal_caveat():
    data = _audit(
        [
            _entry("a", "reliable", 10, cross=True),
            _entry("b", "overgeneralized", 30, cross=True),
        ]
    )
    validate_audit(data)

    report = render_report(data)

    assert "run_0" in report
    assert "1/2 (50.0%)" in report
    assert "No entry is labelled `harmful`" in report
    assert "UER is conditional on evaluability" in report
    assert "Confirmed / all" in report
    assert "All documents (micro)" in report
    assert all(line == line.rstrip() for line in report.splitlines())
    for label in (
        "reliable",
        "contradicted",
        "harmful",
        "overgeneralized",
        "unexecutable",
        "inert",
        "insufficient_test",
    ):
        assert f"`{label}`" in report


def test_report_renders_relabel_check_when_present():
    data = _audit([_entry("a", "reliable", 10)])
    data["relabel_check"] = {
        "sample_size": 10,
        "agreements": 9,
        "agreement_rate": 0.9,
        "disagreements_resolved": ["b: overgeneralized -> insufficient_test"],
        "review_note": "Second-pass self-review, not independent annotation.",
    }

    report = render_report(data)

    assert "## Label-review check" in report
    assert "9/10 (90.0%)" in report
    assert "not independent annotation" in report
    assert "overgeneralized -> insufficient_test" in report
