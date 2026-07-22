# Skill Entry Reliability Results Note Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a concise English paper-facing note that records the verified results of the two-run SkillOpt poker reliability pilot.

**Architecture:** Add one standalone Markdown document under `docs/`. Derive every quantitative statement from the existing audit JSON and generated detailed report, and link both artifacts as the underlying sources of record.

**Tech Stack:** Markdown, JSON, `jq`, existing Python audit CLI, Git.

## Global Constraints

- Write the results note in English at `docs/skill-entry-reliability-pilot-results.md`.
- Preserve the distinction between conditional UER and the confirmed-unreliable fraction over all substantive entries.
- Do not label any entry `harmful` without level-4 paired counterfactual replay.
- State that the 90% label-review agreement is second-pass self-review, not independent inter-annotator agreement.
- Do not modify raw traces, final SkillOpt checkpoints, or entry labels.

---

### Task 1: Write and Verify the Results Note

**Files:**
- Create: `docs/skill-entry-reliability-pilot-results.md`
- Read: `analysis/skill_reliability/skillopt_poker_gpt5_entries.json`
- Read: `analysis/skill_reliability/skillopt_poker_gpt5_report.md`

**Interfaces:**
- Consumes: validated per-entry labels and deterministic report metrics.
- Produces: a standalone English Markdown summary for paper writing.

- [ ] **Step 1: Independently extract the quantitative results**

Run:

```bash
jq -r '
  .documents[] |
  [.document_id,
   ([.entries[] | select(.claim_type != "boilerplate")] | length),
   ([.entries[] | select(.claim_type != "boilerplate" and .label != "insufficient_test")] | length),
   ([.entries[] | select(.claim_type != "boilerplate" and (.label == "contradicted" or .label == "harmful" or .label == "overgeneralized" or .label == "unexecutable"))] | length)] |
  @tsv
' analysis/skill_reliability/skillopt_poker_gpt5_entries.json
```

Expected:

```text
skillopt_poker_gpt5_run_0  48  40  24
skillopt_poker_gpt5_run_1  11   4   4
```

- [ ] **Step 2: Create the results note**

Write these sections:

1. `# Skill Entry Reliability Pilot Results`
2. `## Scope and metrics`, defining UER, Confirmed / all, coverage, OGR, and token-weighted UER.
3. `## Results`, containing the exact per-run and micro-aggregate table from the generated report.
4. `## What failed`, recording run 0 label counts and examples of unexecutable, contradicted, and overgeneralized entries, followed by the run 1 label counts and low-coverage interpretation.
5. `## Causal boundary`, explaining why no entry is labelled harmful at evidence levels 1--3.
6. `## Paper-facing interpretation`, including the conservative conclusion that 28 of 59 substantive entries were already confirmed unreliable.
7. `## Limitations and next step`, identifying self-review and paired replay as limitations.
8. `## Artifacts`, linking `../analysis/skill_reliability/skillopt_poker_gpt5_entries.json` and `../analysis/skill_reliability/skillopt_poker_gpt5_report.md`.

- [ ] **Step 3: Verify report consistency and links**

Run:

```bash
tmp_report=$(mktemp)
uv run python scripts/skill_reliability_audit.py \
  analysis/skill_reliability/skillopt_poker_gpt5_entries.json \
  --output "$tmp_report"
cmp "$tmp_report" analysis/skill_reliability/skillopt_poker_gpt5_report.md
test -f analysis/skill_reliability/skillopt_poker_gpt5_entries.json
test -f analysis/skill_reliability/skillopt_poker_gpt5_report.md
git diff --check
```

Expected: all commands exit with status 0 and `cmp` prints no differences.

- [ ] **Step 4: Commit the results note**

```bash
git add docs/skill-entry-reliability-pilot-results.md
git commit -m "Document SkillOpt poker reliability pilot results"
```

Expected: the commit contains only the English results note.
