# Skill Entry Reliability Results Note Design

## Goal

Add a concise English results note under `docs/` that records the findings of
the two-run SkillOpt poker reliability pilot in a form suitable for later paper
writing.

## Output

Create `docs/skill-entry-reliability-pilot-results.md` as a standalone results
document. Keep the machine-readable audit and generated detailed report as the
sources of record, and link to them with repository-relative paths.

## Content

The note will contain:

- a table reporting substantive entries, evaluable entries, confirmed
  unreliable entries, UER, confirmed-unreliable rate, coverage, OGR, and
  token-weighted UER for each run and the micro aggregate;
- label counts and representative failure modes for each run;
- an explicit explanation that UER is conditional on evaluability and that the
  second run's 100% UER applies to only four evaluable entries;
- the distinction between demonstrated unreliability at evidence levels 1--3
  and causal harm, which requires level-4 paired counterfactual replay;
- a paper-ready diagnostic conclusion and limitations, including that the
  reported 90% review agreement came from second-pass self-review rather than
  independent annotators.

## Source of Truth

All numbers must match
`analysis/skill_reliability/skillopt_poker_gpt5_entries.json` and the
deterministically generated
`analysis/skill_reliability/skillopt_poker_gpt5_report.md`. The results note
must not introduce new entry labels or causal claims.

## Verification

Regenerate the detailed report, independently recompute the entry counts from
the audit JSON, check repository-relative links, and run Markdown diff checks.
