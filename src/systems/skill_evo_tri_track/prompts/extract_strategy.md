You are extracting ONLY **strategies and principles** from a BATCH of recent task
trials, to maintain one section-family of a skill document. Ignore plain facts and
failure-modes — other passes handle those. This track is routinely under-built, so
mine it as hard as facts.

## Knowledge vs tactic — a strategy is a CONDITIONAL bet, not a fact
Hold these two apart sharply; this pass emits ONLY the second.
- **Knowledge (a fact)** — an unconditionally true property of the fixed
  environment (the factual pass owns it). It applies identically every time and
  there is no downside to "applying" it.
- **Tactic (a strategy)** — a chosen ACTION/policy that pays off only WHEN its
  precondition holds. A tactic is a bet: an upside where it fits and a real
  DOWNSIDE where it does not. Writing a tactic as if it were a fact — a bare
  universal imperative ("always do X", "always act more aggressively/finely") with
  no activation condition and no stated downside — is the core failure, because
  the document will then apply it blindly in exactly the situations where it
  BACKFIRES, often for more loss than its wins are worth.

So every strategy point you emit MUST carry, inside its `description`, both:
1. its ACTIVATION CONDITION — the observable situation in which it applies; and
2. its DOWNSIDE / fallback — where it backfires, and the safe default to use instead
   when the condition is not met.
A "tactic" that cannot name a discriminating condition — one that would fire
*always* — is either really a fact (hand it to the factual pass) or an over-general
liability; do NOT emit it as a standing rule. When it is unclear whether a more
aggressive/differentiating action actually pays off, the reward-aware default is the
low-regret action the scoring implies (frequently: take the conservative/baseline
action and ABSTAIN from the bet), never the aggressive action captured as universal.

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

## Exploit confirmed weaknesses — match the response to the DIRECTION of the error
The lowest-regret response depends on the reward baseline AND on WHICH WAY the
counterpart/regime/environment is exploitable. Once the trajectories CONFIRM an
exploitable error, convert it into the reward-maximizing response it implies — which
is sometimes MORE assertive and sometimes LESS. The response must be OPPOSITE to the
observed error; do NOT extract one fixed posture ("always press" or "always play
safe") uniformly. Capture the opposing direction:
- the counterpart errs on the PERMISSIVE/under-responsive side (concedes too readily,
  accepts unfavourable terms, fails to punish): PRESS the advantage — extract maximum
  value and apply pressure where they will not make you pay for it. Holding back here
  forfeits reward they would have conceded, so do NOT capture a withholding/cautious
  posture as the strategy.
- the counterpart errs on the OVER-ASSERTIVE side (over-commits, over-escalates,
  over-claims/bluffs, raises the stakes beyond what its position justifies): do NOT
  match it. Matching escalation with escalation — committing heavily on marginal
  strength into their pressure — is the losing line. Instead CAP YOUR OWN EXPOSURE,
  let them overextend, and capture value defensively: commit only with a position
  strong enough to beat the over-claim, and let their over-commitment pay you off.
  Against a confirmed over-aggressor this restraint IS the exploit, not a passive
  forfeit — it banks their mistakes while dodging the rare case where their
  assertiveness is genuine.
Reserve caution ("withhold/abstain when unsure") for genuinely UNKNOWN counterparts
or unconfirmed reads — never as the standing default against a confirmed-exploitable
one. This is grounded extraction: the confirmed error is the observation; the
reward-maximizing response — assertive OR restrained, per the error's direction —
is what it licenses.

## Planner sections (this track)
Use the `What to focus on for THIS task flow` block (the strategy decision-points/
phases) as your section taxonomy. Tag each point to the matching `section ▸
subsection`. A slot may yield nothing this batch.

## Context-keyed partitioning (when strategy is identity/regime-conditioned)
TRIGGER: the plan is identity-conditioned if it contains any subsection about
MODELING or EXPLOITING a named per-instance counterpart/opponent/regime/source
(e.g. `opponent_exploitation_tom`, a `<key>=<value>` subsection, or any subsection
named after the per-instance identity), OR each trial's situation carries a salient
per-instance identity (e.g. a line like "Opponent: <name>") whose optimal
exploitation differs by value. When triggered, treat the strategy as conditioned on
that identity and do ALL of the following:
- For EACH trial, read the identity value from its situation/prompt.
- PREFIX every strategy point's `description` with `[vs <identity>]` (after the
  section tag), so the rule is explicitly scoped to that identity.
- NEVER state an identity-specific exploitation as a global rule, and NEVER
  match/merge a point with one under a DIFFERENT identity, even if the decision point
  (the recurring choice/phase) looks the same — opposite identities demand opposite
  actions, and merging them re-creates the cross-contamination this scoping prevents.
  Two points are the "same" (matchable) only if they share BOTH the decision point
  AND the identity value.
- Genuinely identity-INDEPENDENT mechanics (e.g. fixed bet-sizing math, legal-move
  rules) may stay unscoped; everything that depends on reading/exploiting the
  counterpart must be scoped.
The consolidation rule below applies ONLY within the same identity value.

## Type-keyed generalization (different counterpart TYPES → different strategies)
A per-instance counterpart/regime usually belongs to a behavioral TYPE/archetype that
its actions reveal, and the reward-relevant strategy (and which facts matter) is
determined by that TYPE, not by the name. Different types call for different — often
opposite — responses, so a single global rule across types is wrong. When the trials
let you read a counterpart's type:
- ALSO emit the exploitation as a TYPE-scoped rule, prefixed `[type=<archetype>]`
  (alongside the `[vs <identity>]` reads), stating the response that type licenses, so
  it TRANSFERS to any counterpart later classified as that type instead of being
  relearned from zero. Likewise, type-relevant counterpart FACTS (what tends to be
  true of that type) can be captured type-scoped.
- Keep a raw, not-yet-generalized read scoped to the specific identity
  (`[vs <identity>]`); promote it to a `[type=…]` rule only once the behavior that
  DEFINES the type is confirmed by the trajectories.
- A newly-encountered identity starts UNKNOWN (use the unknown/unconfirmed default);
  once its actions reveal a known type, switch to that type's strategy. Never match or
  merge across DIFFERENT types, just as with different identities.

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
