"""Validate and summarize atomic-entry reliability audits."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

LABELS = (
    "reliable",
    "contradicted",
    "harmful",
    "overgeneralized",
    "unexecutable",
    "inert",
    "insufficient_test",
)
LABEL_SET = set(LABELS)
UNRELIABLE_LABELS = {
    "contradicted",
    "harmful",
    "overgeneralized",
    "unexecutable",
}
UNEVALUATED_LABELS = {"insufficient_test"}
REQUIRED_ENTRY_FIELDS = {
    "id",
    "text",
    "source_lines",
    "claim_type",
    "source_context",
    "claimed_scope",
    "expected_effect",
    "falsifier",
    "label",
    "evidence_level",
    "cross_condition_tested",
    "token_count",
    "reason",
    "evidence_refs",
    "paired_replay_candidate",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_audit(data: dict[str, object]) -> None:
    """Raise ``ValueError`` when an audit cannot support reported metrics."""
    _require(data.get("schema_version") == 1, "schema_version must be 1")
    max_level = data.get("max_evidence_level")
    _require(_is_int(max_level) and 0 <= max_level <= 4, "invalid max_evidence_level")
    documents = data.get("documents")
    _require(isinstance(documents, list) and documents, "documents must be nonempty")

    document_ids: set[str] = set()
    for document in documents:
        _require(isinstance(document, dict), "each document must be an object")
        document_id = document.get("document_id")
        _require(isinstance(document_id, str) and document_id, "invalid document_id")
        _require(
            document_id not in document_ids, f"duplicate document id: {document_id}"
        )
        document_ids.add(document_id)
        _require(isinstance(document.get("path"), str), f"{document_id}: invalid path")
        entries = document.get("entries")
        _require(isinstance(entries, list), f"{document_id}: entries must be a list")

        entry_ids: set[str] = set()
        for entry in entries:
            _require(isinstance(entry, dict), f"{document_id}: entry must be an object")
            missing = REQUIRED_ENTRY_FIELDS - set(entry)
            _require(not missing, f"{document_id}: missing fields {sorted(missing)}")
            entry_id = entry["id"]
            _require(isinstance(entry_id, str) and entry_id, "invalid entry id")
            _require(
                entry_id not in entry_ids,
                f"{document_id}: duplicate entry id: {entry_id}",
            )
            entry_ids.add(entry_id)

            label = entry["label"]
            _require(
                label in LABEL_SET, f"{document_id}/{entry_id}: unknown label {label}"
            )
            evidence_level = entry["evidence_level"]
            _require(
                _is_int(evidence_level) and 0 <= evidence_level <= max_level,
                f"{document_id}/{entry_id}: invalid evidence_level",
            )
            if label == "harmful":
                _require(
                    evidence_level == 4 and max_level == 4,
                    f"{document_id}/{entry_id}: harmful requires evidence level 4",
                )

            source_lines = entry["source_lines"]
            _require(
                isinstance(source_lines, list)
                and len(source_lines) == 2
                and all(_is_int(line) and line > 0 for line in source_lines)
                and source_lines[0] <= source_lines[1],
                f"{document_id}/{entry_id}: invalid source_lines",
            )
            _require(
                _is_int(entry["token_count"]) and entry["token_count"] > 0,
                f"{document_id}/{entry_id}: token_count must be positive",
            )
            _require(
                isinstance(entry["cross_condition_tested"], bool),
                f"{document_id}/{entry_id}: invalid cross_condition_tested",
            )
            _require(
                isinstance(entry["paired_replay_candidate"], bool),
                f"{document_id}/{entry_id}: invalid paired_replay_candidate",
            )
            evidence_refs = entry["evidence_refs"]
            _require(
                isinstance(evidence_refs, list)
                and all(isinstance(ref, str) and ref for ref in evidence_refs),
                f"{document_id}/{entry_id}: invalid evidence_refs",
            )
            if entry["claim_type"] != "boilerplate":
                _require(
                    bool(evidence_refs),
                    f"{document_id}/{entry_id}: evidence_refs must be nonempty",
                )


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def compute_document_metrics(document: dict[str, object]) -> dict[str, object]:
    """Compute label counts, UER, OGR, coverage, and token-weighted UER."""
    entries = document["entries"]
    assert isinstance(entries, list)
    substantive = [entry for entry in entries if entry["claim_type"] != "boilerplate"]
    evaluable = [
        entry for entry in substantive if entry["label"] not in UNEVALUATED_LABELS
    ]
    unreliable = [entry for entry in evaluable if entry["label"] in UNRELIABLE_LABELS]
    cross_tested = [entry for entry in evaluable if entry["cross_condition_tested"]]
    cross_overgeneralized = [
        entry for entry in cross_tested if entry["label"] == "overgeneralized"
    ]
    evaluable_tokens = sum(entry["token_count"] for entry in evaluable)
    unreliable_tokens = sum(entry["token_count"] for entry in unreliable)
    counts = Counter(entry["label"] for entry in substantive)

    return {
        "total_entries": len(entries),
        "total_non_boilerplate": len(substantive),
        "evaluable_entries": len(evaluable),
        "unreliable_entries": len(unreliable),
        "cross_condition_entries": len(cross_tested),
        "overgeneralized_cross_condition_entries": len(cross_overgeneralized),
        "uer": _ratio(len(unreliable), len(evaluable)),
        "confirmed_unreliable_rate": _ratio(len(unreliable), len(substantive)),
        "ogr": _ratio(len(cross_overgeneralized), len(cross_tested)),
        "evaluation_coverage": _ratio(len(evaluable), len(substantive)),
        "token_weighted_uer": _ratio(unreliable_tokens, evaluable_tokens),
        "label_counts": {label: counts[label] for label in LABELS},
    }


def _format_ratio(numerator: int, denominator: int) -> str:
    if not denominator:
        return "n/a"
    return f"{numerator}/{denominator} ({100 * numerator / denominator:.1f}%)"


def _format_optional_percent(value: object) -> str:
    return "n/a" if value is None else f"{100 * float(value):.1f}%"


def render_report(data: dict[str, object]) -> str:
    """Render deterministic Markdown with summary and per-entry evidence tables."""
    validate_audit(data)
    documents = data["documents"]
    assert isinstance(documents, list)
    lines = [
        "# Skill Entry Reliability Audit",
        "",
        "This level-1--3 pilot uses interface checks, deterministic environment ",
        "policies, and observational future traces. No entry is labelled `harmful`; ",
        "that label requires level-4 paired counterfactual replay.",
        "",
        "## Label definitions",
        "",
        *[f"- `{label}`" for label in LABELS],
        "",
        "## Summary",
        "",
        "| Document | UER | Confirmed / all | OGR | Coverage | Token-weighted UER |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    metrics_by_document: list[tuple[dict[str, Any], dict[str, object]]] = []
    for document in documents:
        metrics = compute_document_metrics(document)
        metrics_by_document.append((document, metrics))
        lines.append(
            "| {document_id} | {uer} | {confirmed} | {ogr} | {coverage} | "
            "{token_uer} |".format(
                document_id=document["document_id"],
                uer=_format_ratio(
                    metrics["unreliable_entries"], metrics["evaluable_entries"]
                ),
                confirmed=_format_ratio(
                    metrics["unreliable_entries"], metrics["total_non_boilerplate"]
                ),
                ogr=_format_ratio(
                    metrics["overgeneralized_cross_condition_entries"],
                    metrics["cross_condition_entries"],
                ),
                coverage=_format_ratio(
                    metrics["evaluable_entries"], metrics["total_non_boilerplate"]
                ),
                token_uer=_format_optional_percent(metrics["token_weighted_uer"]),
            )
        )

    pooled_metrics = compute_document_metrics(
        {"entries": [entry for document in documents for entry in document["entries"]]}
    )
    lines.append(
        "| **All documents (micro)** | {uer} | {confirmed} | {ogr} | "
        "{coverage} | {token_uer} |".format(
            uer=_format_ratio(
                pooled_metrics["unreliable_entries"],
                pooled_metrics["evaluable_entries"],
            ),
            confirmed=_format_ratio(
                pooled_metrics["unreliable_entries"],
                pooled_metrics["total_non_boilerplate"],
            ),
            ogr=_format_ratio(
                pooled_metrics["overgeneralized_cross_condition_entries"],
                pooled_metrics["cross_condition_entries"],
            ),
            coverage=_format_ratio(
                pooled_metrics["evaluable_entries"],
                pooled_metrics["total_non_boilerplate"],
            ),
            token_uer=_format_optional_percent(pooled_metrics["token_weighted_uer"]),
        )
    )

    lines.extend(
        [
            "",
            "UER is conditional on evaluability: `insufficient_test` entries are ",
            "excluded from its denominator. Coverage must therefore be reported ",
            "beside UER; a high UER with low coverage means that the tested subset ",
            "failed, not that the same fraction of the whole document is known to fail.",
            "`Confirmed / all` is the conservative observed fraction of all substantive ",
            "entries already assigned an unreliable label; unevaluated entries remain ",
            "unknown rather than being treated as reliable.",
        ]
    )

    relabel_check = data.get("relabel_check")
    if isinstance(relabel_check, dict):
        sample_size = relabel_check.get("sample_size")
        agreements = relabel_check.get("agreements")
        agreement = (
            _format_ratio(agreements, sample_size)
            if _is_int(agreements) and _is_int(sample_size)
            else "not reported"
        )
        lines.extend(
            [
                "",
                "## Label-review check",
                "",
                f"Agreement before resolution: {agreement}.",
                "",
                str(relabel_check.get("review_note", "No review note supplied.")),
            ]
        )
        disagreements = relabel_check.get("disagreements_resolved")
        if isinstance(disagreements, list) and disagreements:
            lines.extend(
                [
                    "",
                    "Resolved disagreements:",
                    "",
                    *[f"- {item}" for item in disagreements],
                ]
            )

    for document, metrics in metrics_by_document:
        lines.extend(
            [
                "",
                f"## {document['document_id']}",
                "",
                f"Source: `{document['path']}`",
                "",
                "### Label counts",
                "",
                "| Label | Count |",
                "|---|---:|",
                *[
                    f"| `{label}` | {metrics['label_counts'][label]} |"
                    for label in LABELS
                ],
                "",
                "### Entry audit",
                "",
                "| ID | Lines | Type | Label | Level | Reason |",
                "|---|---:|---|---|---:|---|",
            ]
        )
        for entry in document["entries"]:
            reason = str(entry["reason"]).replace("|", "\\|").replace("\n", " ")
            line_range = "–".join(str(line) for line in entry["source_lines"])
            lines.append(
                f"| {entry['id']} | {line_range} | {entry['claim_type']} | "
                f"`{entry['label']}` | {entry['evidence_level']} | {reason} |"
            )

        candidates = [
            entry for entry in document["entries"] if entry["paired_replay_candidate"]
        ]
        lines.extend(["", "### Paired-replay candidates", ""])
        if candidates:
            lines.extend(f"- `{entry['id']}`: {entry['text']}" for entry in candidates)
        else:
            lines.append("None.")

    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    data = json.loads(args.input_json.read_text(encoding="utf-8"))
    validate_audit(data)
    report = render_report(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
