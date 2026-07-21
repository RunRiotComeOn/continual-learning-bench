# Skill Entry Reliability Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a reproducible level-1--3 reliability audit of the two final SkillOpt poker documents, including atomic-entry labels, evidence references, UER, OGR, coverage, and a paired-replay candidate list.

**Architecture:** A small standalone Python scorer validates a human/LLM-produced JSON audit and deterministically computes document-level metrics. The audit JSON keeps every semantic judgment and evidence reference inspectable; a generated Markdown report presents the results without claiming causal harm. Existing checkpoint diffs, task interfaces, deterministic opponent policies, and post-introduction traces provide the evidence.

**Tech Stack:** Python 3.13 standard library, pytest 9, Ruff, JSON, Markdown.

## Global Constraints

- Treat an atomic claim, not a Markdown bullet, as the unit of analysis.
- Exclude headings and unchanged template boilerplate from the unreliable-entry denominator.
- Use only the labels `reliable`, `contradicted`, `harmful`, `overgeneralized`, `unexecutable`, `inert`, and `insufficient_test`.
- Reserve `harmful` for paired counterfactual evidence; this pilot performs levels 1--3 and therefore must not emit `harmful` labels.
- Never count `insufficient_test` as unreliable.
- Report both atomic-entry-weighted and token-weighted rates.
- Preserve evidence level and concrete repository/trace references for every non-boilerplate entry.
- Do not modify either source checkpoint or the raw trace files.

---

## File Structure

- Create `scripts/skill_reliability_audit.py`: validate the audit schema, compute metrics, and render the report.
- Create `tests/test_skill_reliability_audit.py`: focused tests for denominators, UER, OGR, token weighting, forbidden causal labels, and evidence requirements.
- Create `analysis/skill_reliability/skillopt_poker_gpt5_entries.json`: atomic claim cards and level-1--3 judgments for both runs.
- Create `analysis/skill_reliability/skillopt_poker_gpt5_report.md`: generated paper-facing pilot report.

### Task 1: Deterministic Audit Scorer

**Files:**
- Create: `scripts/skill_reliability_audit.py`
- Create: `tests/test_skill_reliability_audit.py`

**Interfaces:**
- Consumes: an audit JSON object with `schema_version`, `documents`, and per-document `entries`.
- Produces: `validate_audit(data: dict[str, object]) -> None`, `compute_document_metrics(document: dict[str, object]) -> dict[str, object]`, `render_report(data: dict[str, object]) -> str`, and a CLI accepting `INPUT_JSON --output OUTPUT_MD`.

- [ ] **Step 1: Write failing validation and metric tests**

Add tests with a minimal audit fixture and exact expected values:

```python
import pytest

from scripts.skill_reliability_audit import compute_document_metrics, validate_audit


def _entry(entry_id, label, tokens, *, cross=False, boilerplate=False):
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
    assert metrics["ogr"] == 1 / 2
    assert metrics["evaluation_coverage"] == 3 / 4
    assert metrics["token_weighted_uer"] == 50 / 60


def test_level_three_pilot_rejects_harmful_label():
    data = {
        "schema_version": 1,
        "max_evidence_level": 3,
        "documents": [{
            "document_id": "run_0",
            "path": "skill.md",
            "entries": [_entry("a", "harmful", 10)],
        }],
    }
    with pytest.raises(ValueError, match="requires evidence level 4"):
        validate_audit(data)
```

Also test that non-boilerplate entries require nonempty `evidence_refs`, unknown labels fail validation, zero cross-condition tests yield `ogr=None`, and report rendering prints counts as both `n/N` and percentages.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```bash
uv run pytest tests/test_skill_reliability_audit.py -v
```

Expected: collection fails because `scripts.skill_reliability_audit` does not exist.

- [ ] **Step 3: Implement schema validation and metrics**

Implement constants and functions with these exact rules:

```python
LABELS = {
    "reliable",
    "contradicted",
    "harmful",
    "overgeneralized",
    "unexecutable",
    "inert",
    "insufficient_test",
}
UNRELIABLE_LABELS = {
    "contradicted",
    "harmful",
    "overgeneralized",
    "unexecutable",
}
UNEVALUATED_LABELS = {"insufficient_test"}


def validate_audit(data: dict[str, object]) -> None:
    """Raise ValueError when an audit cannot support the reported metrics."""


def compute_document_metrics(document: dict[str, object]) -> dict[str, object]:
    """Compute label counts, UER, OGR, coverage, and token-weighted UER."""


def render_report(data: dict[str, object]) -> str:
    """Render deterministic Markdown with summary and per-entry evidence tables."""
```

Validation must require unique entry IDs within each document, positive integer `token_count`, a two-integer `source_lines`, evidence levels in `0..4`, and evidence level 4 for `harmful`. Treat `claim_type == "boilerplate"` as excluded. Compute token-weighted UER only over evaluable non-boilerplate entries. Compute OGR over evaluable entries where `cross_condition_tested` is true.

Add an `argparse` CLI that reads UTF-8 JSON, calls `validate_audit`, renders the report, creates the output parent directory, writes UTF-8 Markdown, and prints the output path.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run:

```bash
uv run pytest tests/test_skill_reliability_audit.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Format, lint, and commit the scorer**

Run:

```bash
uv run ruff format scripts/skill_reliability_audit.py tests/test_skill_reliability_audit.py
uv run ruff check scripts/skill_reliability_audit.py tests/test_skill_reliability_audit.py
git add scripts/skill_reliability_audit.py tests/test_skill_reliability_audit.py
git commit -m "Add skill reliability audit scorer"
```

Expected: Ruff reports no errors and the commit contains only the scorer and its tests.

### Task 2: Atomic SkillOpt Poker Audit

**Files:**
- Create: `analysis/skill_reliability/skillopt_poker_gpt5_entries.json`
- Read: `results/validation/exploitable_poker/skillopt_poker_gpt5/run_0/skill_opt_ckpt/skill_v0001_accept_new_best.md`
- Read: `results/validation/exploitable_poker/skillopt_poker_gpt5/run_0/skill_opt_ckpt/skill_v0002_accept.md`
- Read: `results/validation/exploitable_poker/skillopt_poker_gpt5/run_0/skill_opt_ckpt/skill_v0004_accept.md`
- Read: `results/validation/exploitable_poker/skillopt_poker_gpt5/run_1/skill_opt_ckpt/skill_v0005_accept_new_best.md`
- Read: `results/exploitable_poker/traces/2026-07-12T20-11-29.402524Z/run_0000.json`
- Read: `results/exploitable_poker/traces/2026-07-12T20-11-29.402524Z/run_0001.json`
- Read: `src/tasks/exploitable_poker/task.py`
- Read: `src/tasks/exploitable_poker/opponents.py`
- Read: `src/systems/skill_opt/system.py`

**Interfaces:**
- Consumes: final skills, checkpoint history, deterministic task contracts, opponent policies, and post-introduction traces.
- Produces: schema-version-1 JSON accepted by `validate_audit` and containing an auditable claim card for every atomic entry.

- [ ] **Step 1: Establish checkpoint provenance**

Run checkpoint diffs and extract response metadata transitions:

```bash
diff -u \
  results/validation/exploitable_poker/skillopt_poker_gpt5/run_0/skill_opt_ckpt/skill_v0001_accept_new_best.md \
  results/validation/exploitable_poker/skillopt_poker_gpt5/run_0/skill_opt_ckpt/skill_v0002_accept.md
diff -u \
  results/validation/exploitable_poker/skillopt_poker_gpt5/run_0/skill_opt_ckpt/skill_v0002_accept.md \
  results/validation/exploitable_poker/skillopt_poker_gpt5/run_0/skill_opt_ckpt/skill_v0004_accept.md
jq -r '.interactions[] | [.query.instance_index, .query.instance_id,
  .response.metadata.mode, .response.metadata.step,
  .response.metadata.skill_len] | @tsv' \
  results/exploitable_poker/traces/2026-07-12T20-11-29.402524Z/run_0000.json \
  | uniq
```

Expected: run 0 entries separate into calling-station-era v1, LAG-era v2, and fit-or-fold-era v4 additions; run 1's accepted final entry set originates at step 5 in the final LAG stage.

- [ ] **Step 2: Create the audit JSON with atomic claim cards**

Create this top-level shape:

```json
{
  "schema_version": 1,
  "max_evidence_level": 3,
  "audit_scope": "SkillOpt poker final documents; deterministic interface and policy checks plus observational future traces",
  "documents": [
    {
      "document_id": "skillopt_poker_gpt5_run_0",
      "path": "results/validation/exploitable_poker/skillopt_poker_gpt5/run_0/skill_opt_ckpt/skill_v0004_accept.md",
      "entries": []
    },
    {
      "document_id": "skillopt_poker_gpt5_run_1",
      "path": "results/validation/exploitable_poker/skillopt_poker_gpt5/run_1/skill_opt_ckpt/skill_v0005_accept_new_best.md",
      "entries": []
    }
  ]
}
```

Split every independent recommendation, asserted mechanism, runtime requirement, fallback rule, and output-format requirement. Preserve `source_lines`, use stable IDs `r0-e001` and `r1-e001`, and calculate `token_count` by whitespace-separated tokens over `text`. Include template sentences as `claim_type="boilerplate"`, `evidence_level=0`, and exclude them through the scorer rather than silently dropping them.

For each non-boilerplate entry, populate all claim-card fields plus:

```json
{
  "label": "overgeneralized",
  "evidence_level": 2,
  "cross_condition_tested": true,
  "reason": "The rule is plausible in its LAG source context but its omitted opponent condition claims applicability to all variants.",
  "evidence_refs": [
    "src/tasks/exploitable_poker/opponents.py:73",
    "results/exploitable_poker/traces/2026-07-12T20-11-29.402524Z/run_0001.json:step5"
  ],
  "paired_replay_candidate": true
}
```

Use deterministic labels where possible: nonexistent `reset_per_hand`, invisible `Opponent_stacks`/`Legal_actions`, and action-only JSON conflicting with required `thinking` are `unexecutable`; universal fold-equity or sizing claims contradicted by the always-call policy are `overgeneralized` or `contradicted` according to whether a narrower source scope remains valid. Use `insufficient_test` rather than guessing when neither code nor future cases test the claim.

- [ ] **Step 3: Validate the complete audit JSON**

Run:

```bash
uv run python scripts/skill_reliability_audit.py \
  analysis/skill_reliability/skillopt_poker_gpt5_entries.json \
  --output /tmp/skillopt_poker_gpt5_report.md
```

Expected: exit code 0; no missing evidence, duplicate IDs, forbidden labels, or invalid denominators.

- [ ] **Step 4: Perform an independent stratified relabel check**

Re-read at least 20% of entries, including every `overgeneralized` entry, every `unexecutable` entry, and a random sample of `reliable`/`insufficient_test` entries. Record at top level:

```json
"relabel_check": {
  "sample_size": 0,
  "agreements": 0,
  "agreement_rate": 0.0,
  "disagreements_resolved": []
}
```

Set the final values to the actual review counts. Any disagreement must be resolved by updating the entry label/reason or documenting why the original label remains.

- [ ] **Step 5: Commit the audit data**

Run:

```bash
git add analysis/skill_reliability/skillopt_poker_gpt5_entries.json
git commit -m "Add SkillOpt poker entry reliability audit"
```

Expected: the commit contains only the machine-readable audit.

### Task 3: Generate and Verify the Pilot Report

**Files:**
- Create: `analysis/skill_reliability/skillopt_poker_gpt5_report.md`
- Modify: `analysis/skill_reliability/skillopt_poker_gpt5_entries.json` only if report verification exposes an audit inconsistency.

**Interfaces:**
- Consumes: the validated audit JSON and scorer from Tasks 1--2.
- Produces: deterministic Markdown with per-run UER, OGR, coverage, token-weighted UER, evidence-level caveats, per-entry results, and paired-replay candidates.

- [ ] **Step 1: Generate the report**

Run:

```bash
uv run python scripts/skill_reliability_audit.py \
  analysis/skill_reliability/skillopt_poker_gpt5_entries.json \
  --output analysis/skill_reliability/skillopt_poker_gpt5_report.md
```

Expected: report contains both document IDs, all seven label names, UER, OGR, evaluation coverage, token-weighted UER, and an explicit statement that no causal `harmful` conclusion was made.

- [ ] **Step 2: Verify generated values against an independent JSON query**

Run:

```bash
jq -r '.documents[] | [.document_id,
  ([.entries[] | select(.claim_type != "boilerplate")] | length),
  ([.entries[] | select(.claim_type != "boilerplate" and .label != "insufficient_test")] | length),
  ([.entries[] | select(.label == "contradicted" or .label == "overgeneralized" or .label == "unexecutable")] | length)] | @tsv' \
  analysis/skill_reliability/skillopt_poker_gpt5_entries.json
```

Expected: the raw total/evaluable/unreliable counts match the report before percentage rounding.

- [ ] **Step 3: Run focused and full verification**

Run:

```bash
uv run pytest tests/test_skill_reliability_audit.py -v
uv run ruff check scripts/skill_reliability_audit.py tests/test_skill_reliability_audit.py
uv run ruff format --check scripts/skill_reliability_audit.py tests/test_skill_reliability_audit.py
git diff --check
```

Expected: all tests pass, Ruff reports no errors or formatting changes, and `git diff --check` is silent.

- [ ] **Step 4: Commit the generated report**

Run:

```bash
git add analysis/skill_reliability/skillopt_poker_gpt5_report.md
git commit -m "Report SkillOpt poker reliability pilot"
```

Expected: the commit contains only the generated report.

- [ ] **Step 5: Hand off the causal extension without running it**

Summarize the highest-priority `paired_replay_candidate=true` entries, the held-out variant strata required for each, and estimated model-call counts for entry-on/off pairs. State that this pilot's UER/OGR findings are level-1--3 diagnostic evidence and that behavioral severity remains unmeasured until the user authorizes external replay calls.
