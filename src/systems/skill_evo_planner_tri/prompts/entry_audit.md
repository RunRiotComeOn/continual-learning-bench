You are auditing a skill-document, ENTRY BY ENTRY, against a BATCH of recent task
trials, to COUNT how much dump-evidence each entry has. This mirrors the
formation side (which counts how many trials SUPPORT a point); here you count how
many trials show an entry should be DUMPED. The caller accumulates these counts
across batches and only removes an entry once the total reaches a threshold — so
your job is to count honestly, not to decide removal.

You are given a numbered list of entries — each has an `id`, a `claim` (text in
skill.md), and `recorded_evidence` (the observations that originally supported
it) — plus the batch's trial trajectories (1-based).

## For EACH entry, output the 1-based trial numbers that give DUMP-EVIDENCE

A trial gives **dump-evidence** for an entry ONLY when, inside that trial, there
is DIRECT EXPLICIT proof the claim is now FALSE or no longer applies — exactly one of:
  (a) an explicit error showing a named object in the claim does not exist
      ("no such table/column: X"); OR
  (b) a concrete observed result that DIRECTLY CONFLICTS with the claim about THE
      SAME THING (claim says a column is INTEGER, a result shows TEXT; claim says
      a value/count is N, the same query now returns M; etc.).
List each such trial number once in `contradict_trials`. Inspect EVERY trial and
include ALL that independently provide dump-evidence — the count (the length of
the list) is the signal, so do not under- or over-count.

## SCOPE MUST MATCH (check this first, per entry)
If the claim is scoped to a particular context/condition/regime/subject (it names
the setting it holds in, e.g. "In <X>, …"), a trial can only be dump-evidence if
that trial is from the SAME scope. A trial under a different context does NOT
contradict a claim about another context — different contexts legitimately have
different facts. Exclude different-scope trials from `contradict_trials`.

## These are NOT dump-evidence (never count the trial):
- the entry was simply not used / not mentioned in the trial;
- a trial returned only a SUBSET of what the entry lists (seeing some does not disprove the rest);
- the agent used a different table/column/approach this time;
- the trial is from a different scope/context than the one the claim names;
- the claim is broader than what the trial exercised.
- **Failure-mode / corrective entries** (claims describing a mistake to avoid or a
  lesson, e.g. "agent failed to do X" / "doing Y leads to a bad outcome"): a trial
  NOT exhibiting the failure is NOT dump-evidence. Such an entry stays useful as a
  warning even when recent trials avoided the mistake. Only count a trial that
  POSITIVELY shows the lesson is wrong (the warned-against action was taken and was
  actually fine, or the prescribed fix demonstrably failed). Mere non-recurrence
  of the failure is NOT dump-evidence.

Absence of reconfirmation is NOT dump-evidence. When unsure, do not count it.

For entries with at least one dump-evidence trial, put a brief VERBATIM quote of
the strongest conflicting line in `evidence`. Entries with none get an empty
`contradict_trials` list.

Return ONLY JSON matching the schema (one object per entry id, with
`contradict_trials`). No prose.
