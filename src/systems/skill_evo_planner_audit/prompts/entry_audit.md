You are auditing a skill document ENTRY BY ENTRY against the most recent task
trials. You are given a numbered list of entries — each has an id, a `claim`
(text currently written in skill.md), and `recorded_evidence` (the observations
that originally supported it) — plus the recent trial trajectories (what the
agent saw, did, and the outcome).

For EACH entry return one verdict, using ONLY hard evidence visible in these
trajectories:

- "contradict" — use this ONLY when a recent trial gives DIRECT, EXPLICIT proof
  that the claim is now FALSE. Exactly one of:
    (a) an explicit error showing a named object in the claim does not exist —
        e.g. "no such table: X", "no such column: Y"; OR
    (b) a concrete observed result that DIRECTLY CONFLICTS with the claim (or with
        its `recorded_evidence`) about THE SAME THING — e.g. the claim/evidence
        says a column is INTEGER but a result shows it is TEXT; the claim says a
        value/count is N but the same query now returns M; a table/column the
        claim says holds X now demonstrably holds something incompatible.
  You must be able to point to the specific conflicting line. Compare like with
  like: the trial must speak about the SAME table/column/value as the claim and
  disagree with it.

- "confirm" — a recent trial RE-OBSERVES the claim and it still holds (a query
  relying on it succeeded, or a result matches the recorded_evidence).

- "neutral" — anything else. This is the DEFAULT.

CRITICAL — these are NOT contradictions (return "neutral", never "contradict"):
- the entry was simply not used or not mentioned in the trials;
- a query returned only a SUBSET of what the entry lists (seeing some categories/
  columns does not disprove the others);
- the agent used a DIFFERENT table/column/approach this time;
- the trial is unrelated to the claim, or only partially overlaps;
- the claim is broader than what this trial happened to exercise.
Absence of reconfirmation is NOT evidence of conflict. When unsure, choose
"neutral". Only "contradict" on an unambiguous, same-subject conflict you can
quote.

For "confirm"/"contradict", include the VERBATIM conflicting/confirming quote
from the trajectory in `evidence`. For "neutral", evidence may be empty.

Return ONLY JSON matching the schema (one verdict per entry id). No prose.
