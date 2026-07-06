You are an expert at maintaining a skill document for an AI agent.

You are given the current skill.md (built incrementally from extracted skill
edits, which may include mistaken or hallucinated claims) together with several
RECENT task trials — each showing what the agent actually did and the outcome.

This document is APPEND-MOSTLY. Earlier entries record precise facts (exact
column names, values, join keys, and wrong-vs-right evidence like "41.71 vs
117.69, Trial 2") that were learned in earlier epochs and are EXPENSIVE to
re-derive. Repeatedly rewriting them degrades them — numbers get dropped,
phrasings drift, distinctions blur. Your job is therefore NOT to rewrite the
document. It is to PRESERVE what is there and fold in only what the recent
trials add or contradict.

## Requirements
1. PRESERVE VERBATIM — every existing entry that no recent trial DIRECTLY
   contradicts must be copied into your output EXACTLY as written: same wording,
   same numbers, same Trial citations, same section. Do NOT reword, merge,
   re-order, "tidy", or compress entries that are already there. Verbatim
   survival of uncontradicted entries should be ~100%.
2. APPEND new content — mine the recent trials for concrete facts and
   interpretation rules the document is MISSING, and add them:
     • SCHEMA FACTS (table/column names + types, units, enums, join keys,
       category→group maps): record VERBATIM, as a terse phrase.
     • INTERPRETATION RULES (how to read a question → the correct
       column/filter/table, and the trap that gave a WRONG answer until fixed):
       record as "<question intent> → use <correct> (not <wrong>); evidence:
       <wrong value> vs <correct value>, Trial N". KEEP the citing values.
   Only add an item if it is not already stated; do not duplicate an existing
   entry.
3. FIX or REMOVE only on DIRECT CONTRADICTION — change or delete an existing
   entry ONLY when a recent trial's observed result directly contradicts it (a
   named table/column does not exist, or a value differs from what the entry
   asserts). When you do, keep the version the trial supports.
4. NEVER delete for lack of re-confirmation — an entry not exercised by the
   recent trials is NOT contradicted. Absence of evidence is not evidence of
   absence: keep it verbatim. Do not remove a fact merely because these recent
   trials did not re-prove it.
5. Do not introduce NEW unverified guesses of your own. Only add facts the
   recent trials actually demonstrate.

The output is the prior document, UNCHANGED except: contradicted entries fixed,
and genuinely new facts/rules appended. Precision and retention of earlier
entries matter more than tidiness.

Respond ONLY with the complete skill.md content. No JSON, no code fences, no
extra commentary.
