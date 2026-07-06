You are extracting ONLY **reusable factual knowledge** from a BATCH of recent
task trials, to maintain one section-family of a skill document. Ignore strategy
and failure-mode content entirely — other passes handle those.

## What counts as factual knowledge (emit ONLY this)
Stable, reusable properties of the fixed environment and the concrete values it
yields: table/field/column names, types, encodings, units, keys, formats,
category/enum values, schema quirks, and — when the task rewards producing values
whose key fully determines them — cached result values (keyed, with provenance).
NOT a procedure, NOT a "what to do", NOT a mistake-to-avoid.

## The reusability test (reject transient per-instance bookkeeping)
A fact must REUSE: it must still hold, or be re-queryable by the same key, in a
FUTURE instance beyond the one that produced it. Before emitting, ask "will this
help on a later, different instance?" If it only describes what happened in one
instance, DROP it. In particular NEVER record:
- running totals or cumulative state that only moves forward (scores, profit/loss,
  stack/balance, step counts) — e.g. "total went 220 → 225 → 205 …";
- per-instance value sequences or play-by-play logs (per-step, per-hand, per-turn
  outcomes), and instance/hand/round numbering or ordering;
- one-off events tied to a specific instance ("instance 27 auto-resolved").
A cached value is allowed ONLY when the key DETERMINES the value: re-observing the
SAME key in a LATER, different instance must yield the SAME value (a fixed lookup —
e.g. an encoding, a schema constant, a rule output). If the value is a statistic
ESTIMATED from one instance's data or sample (a rate, mean, proportion, survival
curve, count, score, or outcome that would come out DIFFERENT if that instance were
re-drawn or re-sampled), it is NOT key-determined even when the key itself recurs —
do NOT cache it. A recurring key with a re-sampled value is transient, not a fact.
Keep facts about the FIXED environment (rules, schema, encodings, stable
opponent/entity tendencies), not the moving record or sample of a single
playthrough.

This holds EVEN when a planner slot invites accumulation. A section named "cache",
"inventory", "accumulated", "observed values", etc. still admits ONLY key-determined
values (a transmitter really present at a frequency; a fixed lookup). It must NOT be
filled with sample-estimated statistics — survival/mortality rates, per-cohort means,
proportions, counts, or study-wide aggregates computed from one dataset's sample —
because re-running that study re-draws the sample and the numbers change. If such a
slot would only hold sample statistics, leave it EMPTY this batch rather than fill
it; an empty slot beats a slot full of stale resampled numbers.

## Evidence
Emit a fact only when an environment/tool result, provided schema, or explicit
feedback directly establishes it (authoritative observation). A value/result a
query returned is an authoritative observation of that value. Never invent or
infer a value/field/mapping not shown. A single trial that observes a fact is
enough.

## Planner sections (this track)
Use the `What to focus on for THIS task flow` block as your section taxonomy and
coverage checklist. Tag each point to the matching `section ▸ subsection`. Do not
invent content to fill a slot; a slot may yield nothing this batch.

## Counting / matching / op
- `trajectories`: every 1-based trial that independently observes the exact fact
  (count drives quantity).
- `match`: an existing point id with the SAME fact/scope, else `new`. Match by the
  underlying ROLE/SUBJECT the fact describes, not its surface name: if the
  environment renamed or swapped the object an existing point is about (e.g. the
  same logical table/field/entity now appears under a different name, or its
  schema/type/value changed), that is still the SAME subject — match the stale
  point, do not treat the new name as a brand-new `new` subject.
- `update_op`: `add` (new, or re-observed with nothing new) | `refine` (same fact
  + extra supported detail → write the FULL enriched fact, keep existing detail) |
  `replace` (the matched fact is no longer current — a result/schema directly
  CONTRADICTS it (corrected value), OR the environment changed under you so the
  recorded object/name/value has been renamed, superseded, or no longer exists).
  In the expired/renamed case, point `match` at the now-stale entry and `replace`
  it with the current fact so the old one is RETIRED — never leave the obsolete
  entry alive by emitting the current fact as a parallel `new` point. Use replace
  only on a genuine same-subject conflict or supersession (same logical
  role/object), not for enrichment.
  A `refine` must keep the fact reusable: NEVER enrich by appending instance-specific
  enumerations — hand/row/trial/step numbers, per-instance value sequences, "...in
  this batch", "Hand 92: 995 → 990". If the only new content is transient
  bookkeeping, emit nothing for that point (no refine). The enriched fact must still
  pass the reusability test on its own.
- `support_type`: `authoritative` for these facts (they rest on direct observation).

## Output (JSON only, schema-matching `points`)
Each point: `description` (prefixed with its `[section ▸ subsection]` tag, the fact
stated concretely/verbatim on values), `effect` (usually `unclear` for neutral
facts), `evidence` (the concrete observation), `trajectories`, `match`,
`update_op`, `support_type`. No prose, no code fences.
