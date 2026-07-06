You are maintaining a skill document from a BATCH of recent task trials. In ONE pass
you extract THREE kinds of content and label each point with its `track`. Keep the
three kinds strictly separated — every point must declare exactly one `track`, and a
point of one kind must never be written as another.

The three tracks:

## track = "factual" — reusable FACTS (knowledge), never a tactic or a mistake
An unconditionally true property of the fixed environment: table/field/column names,
types, encodings, units, keys, formats, category/enum values, schema quirks, and —
only when a value is KEY-DETERMINED (the same key always yields the same value in a
later instance) — cached lookup values (with provenance). A fact never tells the
agent what to DO and has no activation condition and no downside.
- Reusability test: it must still hold / be re-queryable by the same key in a FUTURE
  different instance. NEVER record running totals, cumulative state (scores, profit/
  loss, stacks), per-instance value sequences, play-by-play logs, or one-off events.
- A statistic ESTIMATED from one instance's sample (a rate, mean, proportion, count,
  survival curve, score) is NOT key-determined even if its key recurs — do NOT cache
  it; leave the slot empty rather than fill it with resampled numbers.
- `effect` is usually `unclear`; `support_type` is `authoritative` (facts rest on
  direct tool/schema/result observation). A single observing trial is enough.

## track = "strategy" — HOW to act: a CONDITIONAL bet, not a fact
A chosen action/policy that pays off only WHEN its precondition holds. Every strategy
point's `description` MUST carry (1) its ACTIVATION CONDITION (the observable
situation where it applies) and (2) its DOWNSIDE / safe fallback when the condition
is not met. A bare universal imperative ("always do X", "always be more aggressive")
with no condition and no downside is the core failure — it will fire exactly where it
backfires; do not emit it. If a tactic would fire *always* it is really a fact (mark
it factual) or an over-general liability (drop it).
- Mine deliberately for: exploration (what to probe first, when to stop), execution/
  procedure (the recipe/operator/formula), planning (sequence phases under budget),
  decision policy (what to choose at a recurring choice point + safe default),
  verification. Don't collapse everything into one generic "do the task" entry.
- Exploit CONFIRMED weaknesses in the direction OPPOSITE the observed error: if a
  counterpart under-responds/concedes, PRESS; if it over-commits/over-bluffs, do NOT
  match — CAP your exposure and let them overextend. Reserve caution for genuinely
  UNKNOWN/unconfirmed counterparts, never as the standing default against a
  confirmed-exploitable one.
- Identity/type conditioning: if the task carries a per-instance counterpart/regime/
  identity whose optimal exploitation differs by value, PREFIX the description with
  `[vs <identity>]` (and `[type=<archetype>]` when the type is confirmed); never state
  an identity-specific rule globally, and never match/merge points across different
  identities/types even if the decision point looks the same.
- `effect` is `positive` if shown to help else `unclear`; `support_type` usually
  `inferred`. When unsure a differentiating action pays off, prefer the low-regret
  safe/abstain default the scoring implies.

## track = "failure" — a demonstrated MISTAKE to avoid (with correction if shown)
A trap, mis-step, mistaken assumption, or action that led to a worse outcome — as a
GENERAL reusable lesson, never a per-instance anecdote. Strip any "In Trial 4 the
agent…" lead-in and state the rule directly; the trial number / blow-by-blow goes in
`evidence` only. Attribute to a component only when the trajectory ISOLATES it (a
failed final outcome alone does not prove which step caused it).
- `effect` is `negative`. `support_type` = `authoritative` ONLY when a HARD signal
  demonstrates the trap (explicit error/exception, tool/environment rejection, a
  result unambiguously wrong vs a known-correct value); otherwise `inferred` (a trap
  you diagnosed by interpretation must recur across trials before it is trusted).

## Shared rules for every point
- **Planner taxonomy.** The `What to focus on for THIS task flow` block is grouped by
  track. Tag each point's `description` with its `[section ▸ subsection]` from that
  track's slots. A slot may yield nothing this batch; do not invent content to fill it.
- **trajectories**: the 1-based trials that independently exhibit this point (drives
  the count).
- **match**: an existing point id (from the "Existing points" block) with the SAME
  subject/scope AND the SAME track — else `new`. NEVER match a point to an existing id
  of a DIFFERENT track. Match a fact by the role/subject it describes (a renamed/
  changed object is the same subject); match a strategy by the scoped decision point;
  match a failure by the mechanism.
- **update_op**: `add` (new, or re-observed with nothing new) | `refine` (same point +
  extra supported detail → write the FULL enriched text, keep prior detail) | `replace`
  (the matched point is no longer current: a result/schema contradicts it, the object
  was renamed/superseded, or a trial shows the stated strategy/warned-action was
  actually wrong). Never enrich by appending instance-specific enumerations.
- Keep each section coherent: reconcile opposite advice for the same decision point
  into ONE conditioned rule via refine/replace rather than piling up contradictions.

## Output (JSON only, schema-matching `points`)
Emit a single `points` array covering ALL three tracks. Each point:
`track` (`factual` | `strategy` | `failure`), `description` (prefixed with its
`[section ▸ subsection]` tag, stated concretely), `effect`, `evidence`,
`trajectories`, `match`, `update_op`, `support_type`. No prose, no code fences.
