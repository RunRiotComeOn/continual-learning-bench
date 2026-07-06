You are analyzing a BATCH of recent task trials to maintain a reusable skill
document for an AI agent. Each trial contains what the agent saw, what it did,
and the resulting feedback or outcome. You also receive the reusable knowledge
already represented in memory.

## Objective

Distill the batch into atomic, reusable knowledge items, giving equal weight to
WHAT-IS and HOW-TO: verified environment facts, cached result values for
recurring entities, reusable strategies/procedures for the task's decision-points,
and directly supported failure modes (see "Filling the planner's task-specific
slots" below), plus any other evidence-backed task-relevant pattern.

The JSON schema calls these items `points`. In this prompt, a POINT means one
specific reusable knowledge item. It is not merely a topic, observation dump, or
summary of a trial.

A useful point must be:

- **Specific:** it states the concrete fact, procedure, condition, failure, or
  produced value that was observed.
- **Reusable:** it can change how a future instance acts, reasons, verifies, or
  allocates effort. A concrete value computed for an entity that RECURS across
  instances is reusable: a later instance facing the same entity can reuse the
  value instead of recomputing it.
- **Grounded:** its claim is no stronger than the evidence visible in the
  trajectories.
- **Scoped:** it preserves relevant conditions, stages, versions, or contexts
  instead of presenting a conditional observation as a universal rule.
- **Atomic:** it expresses one independently supportable claim. A small cluster
  is allowed only when its parts form one inseparable procedure or relationship
  supported by the same evidence.

Skip a point when the batch provides nothing specific and reusable. Quality and
evidence matter more than producing many points.

## Evidence standard

Separate direct observation from interpretation. The following are acceptable
forms of support:

1. **Authoritative observation:** an environment/tool result, provided schema,
   explicit feedback, or explicit error directly establishes the claim. A
   concrete value returned by a query/tool (a count, an aggregate, an estimate,
   a result row) is an authoritative observation of that value.
2. **Demonstrated procedure:** the trajectory shows a concrete procedure and
   directly demonstrates the relevant effect or intermediate result.
3. **Observed approach in a successful instance:** the concrete procedure/choice
   the agent actually took at a given decision-point in a trial that succeeded.
   This is weaker than (1)–(2): it does NOT prove the procedure CAUSED success.
   You may still capture it as reusable strategy, but you MUST scope it honestly
   as observed (e.g. "approach used in the successful trials at <phase>: …"),
   never assert it as a proven cause. A single successful trial is enough to
   record an honestly-scoped observed approach.
If a trajectory merely suggests a potentially useful claim but does not
establish it (and was not even an approach actually taken in a successful run),
do not emit that claim.

The final outcome is evidence about the attempt as a whole, not automatic
evidence about every action or assumption inside it:

- A failed final outcome proves only that the overall attempt was unsuccessful.
  It does NOT prove which particular action, assumption, mapping, parameter,
  filter, calculation, intermediate result, or other component caused failure.
- A successful final outcome proves only that the overall attempt succeeded. It
  does NOT prove that every action, assumption, or intermediate step was useful
  or correct.
- Attribute success or failure to a specific component only when the trajectory
  establishes that connection through explicit feedback/error, a directly
  conflicting observation, or a clear comparison or correction that isolates
  the relevant change.
- Without such evidence, describe the overall approach as successful or failed
  only if that observation is independently reusable; otherwise omit it. Never
  invent a replacement value, corrected rule, or causal explanation from the
  outcome mismatch alone.

Evidence must identify the concrete trajectory observation supporting the exact
claim. Do not cite an agent's unsupported hypothesis as if it were an
environment observation.

## Planner checklist

If a `What to focus on for THIS task flow (from the planner)` block is present,
use it as a coverage checklist and section taxonomy. Actively inspect the
trajectories for its dimensions and tag points to the corresponding planned
sections when appropriate.

The planner block does not lower the evidence standard. It cannot require a
fact, causal explanation, correction, or failure diagnosis that the trajectories
do not establish. Do not invent content merely to fill a planned section; a
dimension may produce no points in this batch.

## Filling the planner's task-specific slots

The planner taxonomy has two kinds of task-specific slots. Fill BOTH with equal
diligence — do not over-produce facts and skimp on strategy.

**Answer/cache slots** (when present): subsections that STORE the concrete values
the task rewards producing, keyed by an entity that recurs across instances.
- Record the OBSERVED VALUE verbatim, tagged to the matching slot, carrying
  (a) the KEY — which recurring entity/sub-group it is for, and (b) the
  PROVENANCE — which source/instance produced it.
- A single trial that observed the value is sufficient. Never round, average, or
  fabricate a value; omit if never observed.

**Accumulated-inventory slots** (a slot whose job is to hold a persistent SET of
members the environment reveals incrementally): YOU maintain this set — do not
report on whether the agent maintained it. The agent in the trials may never have
tracked anything across instances; that is irrelevant. Build the inventory
directly from the environment's observations:
- Take the UNION of members observed across the trials in this batch. Emit one
  point per member, keyed by its identity, recording its stable properties
  verbatim — even if no agent ever reused or tracked it. (Do NOT emit a meta
  point like "no inventory was demonstrated"; that is not the inventory's
  content — the members are.)
- A member observed in even one trial belongs in the set. A member's ABSENCE
  from other trials does NOT exclude it: the set is the long-run/cumulative one,
  and members may be observable only intermittently. Only drop a member when a
  trial gives POSITIVE evidence it no longer exists (e.g. an explicit
  not-found), never on mere absence.
- Match an existing inventory member by identity (so re-observations reinforce
  it); a genuinely new member is a new point.

**Strategy slots** (the decision-point/phase subsections): subsections that STORE
how to act. These are routinely under-filled — mine the trajectories for them as
hard as for facts.
- For each strategy subsection, find the procedure/choice the agent used at that
  decision-point and what it led to, and emit a point tagged to that subsection.
- Capture both: a procedure whose contribution was shown/compared, AND the
  approach actually taken in successful instances (scoped honestly as observed,
  per Evidence rule 3). A single successful trial is enough for the latter.
- Include the reusable *method* for producing a per-instance value here (it
  cannot be cached, but the method to recompute it is reusable).

## Kinds of reusable knowledge

Choose the most accurate section for each point:

- `environment_facts`: directly confirmed environment/interface properties;
  preserve exact operational details and scope, never guesses.
- `strategy`: an executable procedure for a decision-point/phase — either one
  whose useful contribution was directly shown/isolated by comparison, OR the
  approach actually taken at that decision-point in successful instances
  (scoped honestly as observed, per Evidence-standard rule 3). Capture the
  reusable *method* for producing a per-instance value here too.
- `failure_modes`: a demonstrated failure mechanism, with a correction only
  when that correction was also established.
- `general`: provided or demonstrated definitions, constraints, invariants, or
  scoring-relevant principles.
- `opponent_patterns`: for adversarial tasks only, repeated observed behavior
  and an evidence-supported response.

Task-specific planned sections — both answer/cache slots AND strategy
decision-point/phase slots — may also be used, and should be filled with equal
diligence (see "Filling the planner's task-specific slots" above). Apply the
evidence, atomicity, and scoping requirements to every section; for strategy,
honestly-scoped observed approaches (Evidence rule 3) are allowed.

## Counting support across trajectories

For every point, inspect every trial in the batch and list all 1-based trial
numbers that independently support the exact claim.

- Include a trial only when it provides evidence for that point, not merely
  because it has the same final success/failure label.
- Multiple failed attempts using the same component do not establish that the
  component caused each failure.
- Multiple successful attempts using the same component do not establish that
  the component caused each success.
- For a verified fact, count trials that directly observe or re-observe it.
- For a strategy or failure mode, count trials that demonstrate the same scoped
  procedure or mechanism with the required causal support. For an
  honestly-scoped observed approach (Evidence rule 3), count the successful
  trials in which that approach was actually taken (a single one is enough).
- For a cached value, count trials that authoritatively observed that exact
  value for that exact key (often just one).

The length of `trajectories` is added to the aggregator as the occurrence count,
so unsupported or loosely related trials must never be included to raise a
point's confidence. Do not pad counts. If no listed trial supports the point,
do not emit it.

## Matching existing knowledge

Set `match` to an existing point id only when the new evidence supports the same
claim, with compatible scope and meaning. Shared vocabulary or subject matter is
not enough.

- Do not match a contradictory claim merely because it concerns the same
  subject.
- Do not use an unsupported claim to reinforce established knowledge.
- When direct new evidence conflicts with existing knowledge, emit a distinct,
  explicitly scoped point rather than falsely reinforcing the existing one.
- For a cached value, match an existing cached point only when it has the SAME
  key (same recurring entity/sub-group); a value for a different key is a new
  point even within the same slot.
- Use `new` when no existing point expresses the same supported knowledge.

Only use ids present in the provided existing-points list.

## Output requirements

For each point report:

- `description`: a self-contained, specific reusable claim prefixed with its
  target section in square brackets. Tag to a planned subsection with `▸`, e.g.
  a cached value `[answer_cache ▸ <slot>] key=<entity>; from <provenance>: <values verbatim>`,
  or a strategy `[strategy ▸ <decision-point>] <procedure/choice; scope it, e.g. "observed in successful trials">`.
  Plain section tags (`[environment_facts]`, `[failure_modes]`) are fine when no subsection applies.
- `effect`: `positive` when the demonstrated knowledge helped, `negative` for a
  directly supported trap or failure mechanism, and `unclear` for neutral facts
  (cached values are typically `unclear`). Omit claims whose relevant effect or
  evidential status remains unresolved.
- `evidence`: the concrete observation, feedback, error, comparison, or
  demonstrated procedure supporting the description. Omit the point rather than
  filling an evidential gap with inference.
- `trajectories`: every 1-based trial number in this batch that independently
  supports the exact point.
- `match`: the id of genuinely equivalent existing knowledge, otherwise `new`.
- `update_op`: how this point updates the matched entry — one of three peers:
    - `add` — `match` is `new` (brand-new knowledge), OR it re-observes an existing
      entry but adds NOTHING new (just reinforces it). Use `add` by default.
    - `refine` — `match` is an existing id AND this point restates the SAME claim
      but with extra supported detail the entry lacks (an extra step, condition,
      value, or refinement). When you use `refine`, write `description` as the
      FULL ENRICHED entry: keep all of the existing entry's supported detail and
      fold in the new detail (e.g. "do A" + observed "then B under C" →
      "do A; then B under C"). Do not drop existing detail; add only what the
      trials support. This is how an entry GROWS over time.
    - `replace` — `match` is an existing id AND the new evidence CONTRADICTS/
      corrects it (same subject, conflicting fact); `description` is the corrected
      entry. Use only on a genuine same-scope conflict, not for enrichment.
- `support_type`: `authoritative` when the point records a value or property an
  environment/tool result, provided schema, or explicit feedback directly
  established (this includes every answer/cache value — a query/tool result for a
  recurring entity). Use `inferred` for strategies, failure diagnoses, and any
  claim resting on interpretation rather than a direct authoritative observation.

Respond ONLY with JSON matching the schema. No prose and no code fences.
