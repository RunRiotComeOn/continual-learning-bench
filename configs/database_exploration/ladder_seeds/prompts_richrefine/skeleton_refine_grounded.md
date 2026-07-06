You are an expert at maintaining a skill document for an AI agent.

You are given the current skill.md (built incrementally from extracted skill
edits, which may include mistaken or hallucinated claims) together with several
RECENT task trials — each showing what the agent actually did and the outcome.
Your job is to reorganize AND fact-check the document against this evidence.

This is a REFERENCE the agent reads before each task, so RETENTION of useful,
concrete detail matters more than brevity. Do NOT over-compress: a fact the agent
can actually act on (with its values, the column/table it applies to, and the
wrong-vs-right contrast that earns reward) is worth keeping in full.

## Requirements
1. ENRICH: mine the recent trials for concrete, stable, reusable facts the
   document is missing, and record them VERBATIM — exact table names, full column
   lists with types, key/value mappings, units, enum values, join keys,
   category-to-group mappings, and any quirk a successful query revealed. Record
   the actual schema/values an action confirmed; do not summarize specifics away.
2. KEEP INTERPRETATION RULES WITH EVIDENCE: for every trial where an answer was
   wrong then fixed, or a phrasing was ambiguous, record a rule of the form
   "<question intent> → use <correct column/filter/table> (not <the tempting wrong
   one>); evidence: <wrong value> vs <correct value>, Trial N". KEEP the citing
   values and the wrong-vs-right contrast — that evidence IS the content.
3. DO NOT OVER-COMPRESS: keep enough wording for each entry to be self-contained
   and actionable. You may merge two entries that state the SAME fact, but do not
   strip an entry down to a bare phrase that loses its values, its scope (which
   table/column it applies to), or its evidence. Err on the side of keeping detail.
4. DE-DUPLICATE ONLY EXACT REPEATS: if the same concrete fact appears twice
   word-for-word, keep it once. Otherwise keep both — two related-but-distinct
   facts are not redundancy.
5. CORRECT or REMOVE entries the recent trials contradict (a named table/column
   does not exist, or a value differs from what an entry asserts). Fix or delete.
6. REMOVE only clear unverified guesses / hallucinations — claims stated as fact
   but contradicted or never demonstrated. Do not delete a useful, evidence-backed
   entry merely to make the document shorter.
7. Keep the document coherent and internally consistent — never assert two
   contradictory things at once; keep the version the recent trials support.

The goal: a RICH, actionable reference — every distinct verified fact and
interpretation rule kept with its concrete values and evidence. Completeness of
distinct, actionable detail matters; only exact repetition is waste.

Respond ONLY with the complete reorganized skill.md content. No JSON, no code
fences, no extra commentary.
