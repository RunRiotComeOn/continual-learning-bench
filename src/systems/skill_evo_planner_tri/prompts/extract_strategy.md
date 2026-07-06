You are extracting ONLY **strategies and principles** from a BATCH of recent task
trials, to maintain one section-family of a skill document. Ignore plain facts and
failure-modes — other passes handle those. This track is routinely under-built, so
mine it as hard as facts.

## What counts as strategy/principle (emit ONLY this)
HOW to act to earn reward: the procedure/sequence that worked, the decision policy
at a recurring choice point, where to spend vs save effort, the safe default when
unsure, the reusable METHOD for producing a per-instance value, scoring-relevant
principles. NOT a static fact, NOT a mistake-to-avoid (that's the failure track).

## Kinds of strategy to actively mine for (cover each that the trials support)
Go through these types deliberately — they are easy to under-extract:
- **Exploration strategy** — how to gather the information the task needs
  efficiently: what to probe first, in what order, which checks are high-value,
  and when to STOP exploring and act (avoid wasted probing).
- **Execution / procedure strategy** — the concrete effective procedure that
  produces a correct result once the needed info is known (the recipe, the right
  tool/operator/formula to use, how to assemble the final answer/output).
- **Planning strategy** — how to manage the whole instance under its budget:
  decompose the goal, sequence the phases, allocate effort across sub-parts, and
  decide when to commit / submit / terminate.
- **Decision policy** — at a recurring choice point, what to choose given the
  observed situation, including the safe/lowest-regret default when unsure.
- **Verification strategy** — how to check or sanity-test a result before
  committing, when the cost of being wrong is high.
A strong skill has several of these per task; do not collapse everything into one
generic "do the task" entry. Tag each to the planner subsection it fits.

## Evidence (two acceptable forms)
1. A procedure whose useful contribution was directly shown / isolated by comparison.
2. The approach actually TAKEN at a decision-point in trials that SUCCEEDED — you
   may capture it, but scope it honestly as observed (e.g. "approach used in the
   successful trials at <phase>: …"), never as a proven cause. A single successful
   trial is enough for an honestly-scoped observed approach.
Do NOT trade scored quality for surface coverage: if the scoring penalizes being
wrong, the strategy for an output that cannot be reliably determined is the
lowest-regret safe default the scoring implies (conservative/abstain), NOT a
guessed or force-fit value. Capture that, not "produce something for everything".

## Planner sections (this track)
Use the `What to focus on for THIS task flow` block (the strategy decision-points/
phases) as your section taxonomy. Tag each point to the matching `section ▸
subsection`. A slot may yield nothing this batch.

## Keep the section coherent — consolidate, do not pile up contradictions
Before adding, check the existing points for the SAME decision point. Two bullets
that give opposite advice for the same situation (e.g. "raise marginal hands" vs
"check marginal hands") cause decision paralysis. If your point sharpens, narrows,
or corrects an existing one, use `refine`/`replace` to fold it into ONE coherent
rule that states the DISCRIMINATING condition (when to do which) — do not add a
second near-duplicate. Reserve `add` for a genuinely new, non-overlapping decision
point. Prefer one well-conditioned rule over many overlapping ones.

## Counting / matching / op
- `trajectories`: trials that demonstrate the same scoped procedure (or, for an
  observed approach, the successful trials that took it — one is enough).
- `match`: an existing strategy point with the same scoped intent OR the same
  decision point with differing advice (both must be reconciled), else `new`.
- `update_op`: `add` | `refine` (same strategy + extra supported step/condition, or
  reconciling two views of one decision point → write the FULL coherent procedure
  with the discriminating condition) | `replace` (a trial shows the stated approach
  was actually wrong/worse — corrected procedure).
- `support_type`: usually `inferred` (strategy rests on interpretation).

## Output (JSON only, schema-matching `points`)
Each point: `description` (prefixed with its `[section ▸ subsection]` tag; honestly
scoped), `effect` (`positive` if shown to help, else `unclear`), `evidence`,
`trajectories`, `match`, `update_op`, `support_type`. No prose, no code fences.
