You design the skeleton of `skill.md` for an agent that repeatedly solves
instances from the same task stream.

Input: the task description plus a batch of real trajectories.
Output: markdown section headings and placeholder comments only.

Your goal is to create the memory slots a good learner would want to keep after
the raw trajectories are deleted.

## First Decide What Memory Is Needed

Use the scoring rule and the trajectories. Do not design a generic notebook.
Choose only the memory types that will improve future decisions.

1. **Objective and scoring**
   Always record the task objective, scoring rule, and baseline/reference policy
   from the task description. This section is filled now and frozen.

2. **Reference**
   Stable environment structure: schemas, fields, encodings, units, tool
   semantics, output format, fixed constraints. Use this when the task has
   reusable facts the agent must learn once and reuse.

3. **Cache or inventory**
   Key-determined stored values: the same key gives the same value later.
   This includes a persistent set of objects discovered across instances.
   Example shape: an accumulated inventory keyed by object identity.
   Do not cache per-instance statistics or sample-derived values.

4. **Working model**
   Uncertain reusable beliefs: the same target recurs, but each instance gives
   only noisy, biased, or partial evidence. Create this when future performance
   depends on carrying forward current best estimates or hypotheses and revising
   them over time. The placeholder must say what the key is, what value/belief is
   stored, what provenance/confidence is tracked, and how new evidence updates it.
   Tag this section as `strategy`, not `factual`.

5. **Strategy**
   Procedures and decision policies: how to act, what to probe, when to stop, how
   to use the stored memory, and what fallback to use when confidence is low.
   Make task-specific subsections for recurring phases or decision points.
   If optimal behavior is conditioned on an observable per-instance context
   (opponent, regime, source, study type, etc.), partition strategy by that key
   only when different values need different or contradictory actions.

6. **Failure modes**
   Reusable traps and corrections: what mistake hurts score, when it happens, and
   how to avoid it.

## Guardrails

- Do not write facts, estimates, or learned values into placeholders.
- Ground section choices in the trajectories, except objective/scoring which comes
  from the task description.
- Prefer compact state over verbose notes. Ask: "What table, inventory, model, or
  rule would I want before the next instance?"
- If a value is not key-determined but should be remembered as a current best
  estimate, use a working-model section.
- If wrong answers are penalized, include an explicit low-regret fallback in
  strategy. If the baseline is itself losing, do not call passive behavior safe.
- Keep granularity reusable: no one-off sections for individual instances.

## Track Tags

Every section except `## task_objective_and_scoring` must start its HTML comment
with one track tag:

- `track=factual;` for reference facts and key-determined cache/inventory content.
- `track=strategy;` for working models, procedures, decision policies, and fallbacks.
- `track=failure;` for traps and corrections.

Subsections inherit the section's track.

## Required Output

1. Use markdown `##` for sections and `###` for subsections.
2. First section must be `## task_objective_and_scoring`, filled with terse bullets
   for objective, reward/scoring, baseline/reference policy, and hard constraints.
3. Include `## general`, `## strategy`, and `## failure_modes`.
4. Include `## reference` only if stable reusable structure exists.
5. Include a cache/inventory section only if key-determined content exists.
6. Include a task-specific working-model section only if uncertain reusable
   beliefs or estimates must be carried forward.
7. Under every other section and subsection, include exactly one HTML comment
   describing what concrete content belongs there. Section comments must begin
   with the track tag.
8. At most 8 total `##` sections and at most 6 `###` subsections under any section.

Respond ONLY with the markdown skeleton. No JSON, no code fences, no commentary.
