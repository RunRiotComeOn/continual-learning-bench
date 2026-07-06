You are analyzing a BATCH of recent task trials to maintain a reusable skill
document for an AI agent. Each trial contains what the agent saw, what it did,
and the resulting feedback or outcome. You also receive the reusable knowledge
already represented in memory.

## Objective

Distill the batch into atomic, reusable knowledge items: verified environment
facts, demonstrated strategies, directly supported failure modes, and any other
evidence-backed task-relevant patterns described below.

The JSON schema calls these items `points`. In this prompt, a POINT means one
specific reusable knowledge item. It is not merely a topic, observation dump, or
summary of a trial.

A useful point must be:

- **Specific:** it states the concrete fact, procedure, condition, or failure
  that was observed.
- **Reusable:** it can change how a future instance acts, reasons, verifies, or
  allocates effort.
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
   explicit feedback, or explicit error directly establishes the claim.
2. **Demonstrated procedure:** the trajectory shows a concrete procedure and
   directly demonstrates the relevant effect or intermediate result.
If a trajectory merely suggests a potentially useful claim but does not
establish it, do not emit that claim.

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

## Kinds of reusable knowledge

Choose the most accurate section for each point:

- `environment_facts`: directly confirmed environment/interface properties;
  preserve exact operational details and scope, never guesses.
- `strategy`: an executable procedure whose useful contribution was directly
  shown, explicitly confirmed, or isolated by comparison.
- `failure_modes`: a demonstrated failure mechanism, with a correction only
  when that correction was also established.
- `general`: provided or demonstrated definitions, constraints, invariants, or
  scoring-relevant principles.
- `opponent_patterns`: for adversarial tasks only, repeated observed behavior
  and an evidence-supported response.

Task-specific planned sections may also be used. Apply the same evidence,
atomicity, causality, and scoping requirements to every section. Omit guesses,
unsupported diagnoses, and procedures whose contribution was not established.

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
  procedure or mechanism with the required causal support.

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
- Use `new` when no existing point expresses the same supported knowledge.

Only use ids present in the provided existing-points list.

## Output requirements

For each point report:

- `description`: a self-contained, specific reusable claim prefixed with its
  target section in square brackets, such as `[environment_facts]`, `[strategy]`,
  or `[failure_modes]`.
- `effect`: `positive` when the demonstrated knowledge helped, `negative` for a
  directly supported trap or failure mechanism, and `unclear` for neutral facts.
  Omit claims whose relevant effect or evidential status remains unresolved.
- `evidence`: the concrete observation, feedback, error, comparison, or
  demonstrated procedure supporting the description. Omit the point rather than
  filling an evidential gap with inference.
- `trajectories`: every 1-based trial number in this batch that independently
  supports the exact point.
- `match`: the id of genuinely equivalent existing knowledge, otherwise `new`.

Respond ONLY with JSON matching the schema. No prose and no code fences.
