You are extracting ONLY **failure modes / common mistakes to avoid** from a BATCH
of recent task trials, to maintain one section-family of a skill document. Ignore
plain facts and general strategy — other passes handle those.

## What counts as a failure mode (emit ONLY this)
A demonstrated way the agent goes wrong and should avoid: a trap, a mis-step, a
mistaken assumption, an action that led to a worse outcome — ideally with the
correction when the trials also establish it. NOT a neutral fact, NOT a general
procedure that simply worked (that's the strategy track).

## State the GENERAL lesson, never a per-instance anecdote
A failure mode must be a REUSABLE rule that applies to a future, different instance.
State the trap and correction as a general pattern. NEVER narrate one episode:
no instance/hand/row/trial/step numbers, no "In Hand 54, hero raised KJs then lost
140 chips on the river", no blow-by-blow of a single playthrough. Use a concrete
example only as compact `evidence`, not as the `description`. If you cannot state
the lesson without naming a specific instance or recounting one episode's
play-by-play, it is an anecdote — distil it to the underlying pattern, or drop it.
Strip any "In Trial 4 …" / "the agent then …" lead-in from the `description` and
state the rule directly. Rewrite, e.g.:
  BAD : "In Trial 4 the agent assumed the grouping was A×B (32 cells) and failed."
  GOOD: "Do not infer the grouping/structure from surface columns alone; confirm it
         against the authoritative source first, since a wrong structure invalidates
         the result."
The trial number and blow-by-blow go in `evidence` if anywhere, never the rule.

## Evidence
Emit a failure mode only when the trials demonstrate the mechanism: an explicit
error/wrong result tied to a specific action/assumption, or a clear comparison
showing the action hurt. A failed final outcome alone does NOT prove which step
caused it — attribute to a component only when the trajectory isolates it. Include
a correction only if it too is established; otherwise state just the trap.

## Planner sections (this track)
Use the `What to focus on for THIS task flow` block (the failure-mode slots) as
your section taxonomy. Tag each point to the matching `section ▸ subsection`.

## Counting / matching / op
- `trajectories`: trials that independently demonstrate the same failure mechanism.
- `match`: an existing failure point with the same mechanism/scope, else `new`.
- `update_op`: `add` | `refine` (same failure + extra supported detail or a newly
  established correction → write the FULL enriched entry, keep existing detail) |
  `replace` (a trial shows the warned-against action was actually fine → corrected).
  Note: a failure entry is NOT contradicted merely because recent trials avoided
  the mistake; keep it as a warning unless positively shown wrong.
- `support_type`: set `authoritative` ONLY when the trap is established by a HARD,
  directly-shown signal — an explicit error/exception, a tool/environment rejection,
  or a result unambiguously wrong against a known-correct value — i.e. the mechanism
  is DEMONSTRATED, not interpreted; such a grounded failure is trustworthy from one
  trial. Use `inferred` (the default) for a trap you DIAGNOSED by interpreting why an
  outcome was poor; an inferred trap must recur across trials before it is trusted, so
  do not inflate one bad outcome into a firm rule by mislabeling it authoritative.

## Output (JSON only, schema-matching `points`)
Each point: `description` (prefixed with its `[section ▸ subsection]` tag; the trap,
plus correction if established), `effect` `negative` for the trap, `evidence`,
`trajectories`, `match`, `update_op`, `support_type`. No prose, no code fences.
