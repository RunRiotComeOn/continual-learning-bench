# Skill Entry Reliability Pilot Results

## Scope and metrics

This pilot audits the final `skill.md` documents produced by two SkillOpt runs
on `exploitable_poker` with GPT-5. Each independent recommendation, asserted
mechanism, runtime requirement, fallback rule, or output-format requirement is
treated as an atomic entry. Headings and unchanged template boilerplate are
excluded from the reliability denominators.

The audit uses interface checks, deterministic opponent policies, and
observational post-introduction traces (evidence levels 1--3). It reports:

- **Unreliable Entry Rate (UER):** confirmed unreliable entries divided by
  evaluable substantive entries. Entries labelled `insufficient_test` are not
  included in this denominator.
- **Confirmed / all:** confirmed unreliable entries divided by all substantive
  entries. This is a conservative observed fraction; unevaluated entries remain
  unknown rather than being counted as reliable.
- **Coverage:** evaluable substantive entries divided by all substantive
  entries.
- **Overgeneralization Rate (OGR):** overgeneralized entries divided by the
  evaluable entries subjected to a cross-condition check.
- **Token-weighted UER:** the same conditional unreliable rate weighted by
  whitespace-separated entry length.

The unreliable labels in this pilot are `contradicted`, `overgeneralized`, and
`unexecutable`. No entry is labelled `harmful`, because that label is reserved
for level-4 paired counterfactual evidence.

## Results

| Document | Substantive | Evaluable | Confirmed unreliable | UER | Confirmed / all | OGR | Coverage | Token-weighted UER |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `skillopt_poker_gpt5_run_0` | 48 | 40 | 24 | 24/40 (60.0%) | 24/48 (50.0%) | 5/20 (25.0%) | 40/48 (83.3%) | 60.3% |
| `skillopt_poker_gpt5_run_1` | 11 | 4 | 4 | 4/4 (100.0%) | 4/11 (36.4%) | 4/4 (100.0%) | 4/11 (36.4%) | 100.0% |
| **Micro aggregate** | **59** | **44** | **28** | **28/44 (63.6%)** | **28/59 (47.5%)** | **9/24 (37.5%)** | **44/59 (74.6%)** | **63.7%** |

Across the two documents, 28 of 44 evaluable entries were unreliable. More
conservatively, 28 of all 59 substantive entries were already confirmed
unreliable, even though the 15 unevaluated entries were left as unknown.

## What failed

### Run 0

The 48 substantive entries comprise 16 `reliable`, 15 `unexecutable`, 5
`overgeneralized`, 4 `contradicted`, and 8 `insufficient_test` entries. The
largest failure category is therefore not merely questionable poker advice,
but instructions that the evaluated system cannot carry out.

Representative unexecutable entries require the model to:

- invoke a nonexistent `reset_per_hand` tool;
- read opponent-stack or `legal_actions` fields that SkillOpt does not expose
  to the task model;
- write persistent internal logs or timestamps without a logging or clock
  interface; or
- return an action-only object even though the declared `PokerAction` schema
  requires a `thinking` field.

The contradicted entries include converting an explicitly supplied minimum
raise value to null and discarding learned opponent information whenever a
transient hand-state field changes. The latter conflicts directly with the
benchmark's cross-hand adaptation objective.

The overgeneralized entries exhibit the failure mode that motivated this
diagnostic: a locally plausible observation is written as a broad strategy.
Examples include preferring small bets to induce calls against an opponent that
calls independently of bet size, treating weak-pair check/call play as a
general rule without price or opponent conditions, continuing turn value bets
only after improving, and using a bare one-pair threshold for river thin value.

### Run 1

The 11 substantive entries comprise 4 `overgeneralized` and 7
`insufficient_test` entries. All four evaluable entries failed, producing a
conditional UER of 100%. Coverage, however, is only 4/11 (36.4%). The correct
interpretation is therefore that **all four evaluable entries were
overgeneralized**, not that every entry in the document has been shown to be
wrong.

The four failures generalize from a special LAG-opponent context: they omit
value 3-bets from a restrictive 3-bet rule, turn a local flop-float exploit into
generic flop/turn check-call advice, treat an opponent check as general support
for a half-pot bet, and infer universal river fold equity from multi-street
passivity. These rules do not transfer to the deterministic calling-station or
fit-or-fold policies without additional opponent conditions.

## Causal boundary

Levels 1--3 can establish that an entry conflicts with the runtime interface,
contradicts a deterministic environment policy, or fails to generalize across
known conditions. They do not isolate the entry's causal effect on reward.
Consequently, this pilot makes no `harmful` assignments and does not claim that
the 28 unreliable entries have already been proven to reduce performance.

That stronger claim requires paired counterfactual replay: run the same future
instances with matched randomness while changing only whether the audited
entry is injected. The detailed audit records replay candidates for this next
stage.

## Paper-facing interpretation

The most defensible diagnostic statement from this pilot is:

> Across two final SkillOpt poker documents, 28 of 44 evaluable atomic entries
> (63.6%) were contradicted, overgeneralized, or unexecutable. Even when 15
> entries without sufficient evidence were retained as unknown, 28 of all 59
> substantive entries (47.5%) were already confirmed unreliable.

UER and coverage should always be reported together. UER measures failure
among entries that the available validation procedure can adjudicate, while
Confirmed / all gives the conservative observed prevalence in the complete
document. This pairing prevents a low-coverage system from appearing
definitively worse merely because a small tested subset has a high failure
rate.

For evaluations spanning multiple systems and tasks, these entry-level
statistics should remain the primary diagnostic and be reported as
distributions across runs, systems, and tasks. Micro-aggregated rates are useful
secondary summaries but can otherwise be dominated by systems that produce
longer documents.

## Limitations and next step

- This pilot covers one system-task-model combination and two runs; it
  demonstrates the diagnostic but does not estimate cross-system or cross-task
  prevalence.
- The 27/30 (90.0%) agreement figure is a second-pass self-review check, not
  independent human or LLM inter-annotator agreement.
- Observational traces do not isolate the reward effect of individual entries.
- Token weighting uses whitespace-separated entry lengths and is a robustness
  view, not a tokenizer-specific measurement.

The next experiment should apply the same atomic-entry audit to multiple
systems and tasks, then run paired replay for a stratified sample of entries,
including overgeneralized, apparently reliable, and insufficiently tested
controls.

## Artifacts

- [Machine-readable atomic-entry audit](../analysis/skill_reliability/skillopt_poker_gpt5_entries.json)
- [Generated detailed audit report](../analysis/skill_reliability/skillopt_poker_gpt5_report.md)
