You are maintaining a long-lived REFERENCE document (skill.md) that an AI agent
reads before each task. You are given the current skill.md (built from extracted
edits, which may contain mistakes) together with several RECENT task trials
(what the agent did + the outcome). Your job is to FACT-CHECK and ENRICH the
document — NOT to shorten it.

This document is a reference, not a summary. RETENTION of concrete, actionable
detail is the whole point. Brevity is NOT a goal and is NOT rewarded.

## HARD LENGTH RULE (read first)
- The document you output MUST be **at least as long** as the document you were
  given. Default to GROWING it by adding facts mined from the recent trials.
- You may make the document shorter ONLY by:
  (a) collapsing two entries that state **exactly the same fact** (a true
      word-for-word / value-for-value duplicate), OR
  (b) removing/​correcting a claim that the RECENT TRIALS **directly
      contradict** (a named table/column that does not exist, or a value the
      evidence shows is wrong).
- Any other shortening is FORBIDDEN. Do NOT paraphrase to save words. Do NOT
  "tighten" prose. Do NOT drop examples, values, units, column lists, evidence
  citations, or wrong-vs-right contrasts. If you are unsure whether two entries
  are true duplicates, KEEP BOTH.

## What to DO
1. ENRICH (primary job): mine the recent trials for concrete, stable, reusable
   facts the document is missing, and add them VERBATIM — exact table names, full
   column lists with types, key/value mappings, units, enum values, join keys,
   category→group mappings, timestamp encodings, and any quirk a successful query
   revealed. Record the actual schema/values an action confirmed.
2. KEEP INTERPRETATION RULES WITH EVIDENCE: for every trial where an answer was
   wrong then fixed, or a phrasing was ambiguous, ensure there is a rule of the
   form "<question intent> → use <correct column/filter/table> (not <the tempting
   wrong one>); evidence: <wrong value> vs <correct value>, Trial N". KEEP the
   citing values and the wrong-vs-right contrast — that evidence IS the content.
3. MERGE-ONLY consolidation: the ONLY consolidation you may perform is folding
   exact duplicates together. Two related-but-distinct facts are NOT redundant —
   keep both in full.
4. CORRECT in place: when the recent trials contradict an entry, fix the value or
   delete just that wrong claim — do not delete the surrounding correct detail.
5. Keep the document coherent and internally consistent: never assert two
   contradictory things at once; keep the version the recent trials support.

## Self-check before answering
- Is your output at least as long as the input? If not, you over-compressed —
  add back the concrete detail you dropped.
- Did every deletion fall under rule (a) exact-duplicate or (b)
  evidence-contradicted? If not, restore it.

Respond ONLY with the complete reorganized skill.md content. No JSON, no code
fences, no commentary.
