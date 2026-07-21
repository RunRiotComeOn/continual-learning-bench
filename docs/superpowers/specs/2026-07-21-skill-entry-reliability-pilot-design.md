# Skill Entry Reliability Pilot Design

## Objective

Evaluate the final SkillOpt skill documents from the two GPT-5-mini poker runs
with a reproducible entry-level diagnostic. The pilot should estimate how much
of each document is contradicted, overgeneralized, unexecutable, inert, or not
yet testable. It must not present observational evidence as causal evidence.

The two inputs are:

- `results/validation/exploitable_poker/skillopt_poker_gpt5/run_0/skill_opt_ckpt/skill_v0004_accept.md`
- `results/validation/exploitable_poker/skillopt_poker_gpt5/run_1/skill_opt_ckpt/skill_v0005_accept_new_best.md`

## Unit of Analysis

The unit is an atomic, actionable or factual entry rather than a Markdown
bullet. Compound bullets are split when their clauses have different
conditions, recommendations, or falsifiers. Headings and unchanged template
boilerplate are reported separately and excluded from the unreliable-entry
denominator.

Each entry receives a claim card with:

- claim type: factual, strategy, procedure/interface, or boilerplate;
- source context: the task variant and epoch from which it first appeared;
- claimed scope: the conditions stated in the entry, with an omitted condition
  interpreted as universal over the task variants;
- recommendation or asserted fact;
- expected effect;
- falsification criterion.

## Evidence Levels

The pilot reports evidence levels explicitly.

1. **Deterministic interface validation.** Compare procedural claims with the
   task response schema, prompt fields, system-visible fields, and callable
   tools. This can conclusively identify nonexistent APIs, inaccessible fields,
   and schema conflicts.
2. **Environment-policy validation.** Compare opponent-conditioned claims with
   the deterministic opponent policies. This can conclusively identify claims
   that contradict a policy, such as trying to create fold equity against an
   opponent that always calls.
3. **Observational future validation.** Use interactions after an entry was
   introduced to measure applicability, action uptake, outcomes, and failures.
   This supports consistency or contradiction findings but does not isolate the
   entry's causal contribution.
4. **Paired counterfactual validation.** On matched held-out instances, replay
   the same model and initial state with the entry present and absent. Only this
   level supports a causal reward-effect estimate.

The initial pilot completes levels 1--3 for every entry. Level 4 is a separate,
costed extension because it requires new model calls; the pilot identifies a
small stratified set of entries for that replay rather than silently launching
external calls.

## Labels

Each evaluable entry receives one primary label:

- `reliable`: supported throughout its claimed scope at the available evidence
  level;
- `contradicted`: directly false under later observations or environment truth;
- `harmful`: paired replay gives sufficiently confident negative reward effect;
- `overgeneralized`: supported in a source-like subdomain but contradicted or
  harmful elsewhere inside its stated scope;
- `unexecutable`: depends on an unavailable tool or field, conflicts with the
  schema, or requests an impossible execution sequence;
- `inert`: paired or observational tests show no detectable behavioral uptake;
- `insufficient_test`: too few applicable future cases to classify.

`harmful` is reserved for paired counterfactual evidence. In the levels 1--3
pilot, apparently damaging entries are described as `risk-inducing` rather than
causally harmful.

## Metrics

For each document, report:

1. **Unreliable Entry Rate (UER)**

   ```text
   (contradicted + overgeneralized + unexecutable + harmful)
   / evaluable non-boilerplate entries
   ```

2. **Overgeneralization Rate (OGR)**

   ```text
   overgeneralized / entries with cross-condition tests
   ```

3. **Evaluation Coverage**

   ```text
   evaluable non-boilerplate entries / all non-boilerplate entries
   ```

4. Counts by label, claim type, source variant, and evidence level.

The report includes both atomic-entry-weighted and token-weighted rates. The
first answers how often extraction fails; the second captures how much prompt
space unreliable content occupies. Neither is treated as behavioral severity,
which requires paired replay.

## Validation Procedure

1. Diff checkpoints to identify when each final entry first appeared.
2. Atomize both final documents and create claim cards.
3. Validate interface claims against task and system code.
4. Validate opponent-policy claims against all three deterministic variants.
5. Match each entry to post-introduction interactions and summarize observed
   uptake and outcomes by variant.
6. Assign provisional labels with an evidence-level field and a concise reason.
7. Independently re-label a stratified sample, emphasizing compound and
   overgeneralized entries, and report agreement.
8. Produce per-document summaries and a list of entries recommended for paired
   counterfactual replay.

## Quality Controls

- `insufficient_test` is never counted as unreliable.
- Success of the batch or document is not evidence for every entry within it.
- An entry omitted from the model's actions is not declared reliable.
- Source-context validity does not justify a universal scope.
- Compound entries are split before counting so one good clause cannot hide a
  bad clause.
- All automated labels retain the matched evidence and can be manually audited.

## Deliverables

- A machine-readable entry audit for both documents.
- A concise Markdown report with UER, OGR, coverage, label counts, evidence
  levels, and representative failure cases.
- A proposed paired-replay sample covering high-impact, overgeneralized, and
  apparently reliable controls.

