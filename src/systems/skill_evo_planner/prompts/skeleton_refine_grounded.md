You are an expert at maintaining a skill document for an AI agent.

You are given the current skill.md (built incrementally from extracted skill
edits, which may include mistaken or hallucinated claims) together with several
RECENT task trials — each showing what the agent actually did and the outcome.
Your job is to reorganize AND fact-check the document against this evidence.

## Requirements
1. ENRICH: mine the recent trials for concrete, stable, reusable facts the
   document is missing, and record them VERBATIM — exact table names, full
   column lists with types, key/value mappings, units, enum values, join keys,
   category-to-group mappings, and any quirk a successful query revealed. Record
   the actual schema/values an action confirmed; do not summarize specifics away
   into vague generalities.
2. NO REDUNDANCY — this is critical. State each distinct fact EXACTLY ONCE, in
   the single most appropriate section, and never restate it elsewhere. Do not
   echo the same schema/join-key/price-column/timestamp fact as a "fact" AND a
   "rule" AND a "strategy" AND a "failure mode". A reference section holds the
   raw fact; a procedural section may name a technique but must not re-list the
   facts the reference already gives. If a section would only repeat facts stated
   elsewhere, leave it short or empty rather than padding it.
3. BE COMPACT: write each entry as a terse bullet — a phrase or single clause,
   not a multi-sentence paragraph. Capture the fact and drop the explanation
   (e.g. "fdbk_g1 joins on item_id (not ref_id)" — not a sentence restating why).
4. CORRECT or REMOVE entries the recent trials contradict. If a trial shows a
   claim is wrong (e.g. a query failed because a named table/column does not
   exist, or a value differs from what an entry asserts), fix it or delete it.
5. REMOVE claims that look like unverified guesses or hallucinations — anything
   stated as a confirmed fact but never corroborated by an actual successful
   action in any trial. Do not preserve a fact just because it is already there.
6. Keep concrete, stable, evidence-supported properties verbatim. Omit
   unsupported or unresolved claims rather than wording them tentatively.
7. Keep the document coherent and internally consistent — it must not assert two
   contradictory things at once. When entries conflict, keep the version the
   recent trials support and drop the other.

The goal is a tight, non-redundant reference: every distinct verified fact
present exactly once, nothing padded or repeated. Completeness of DISTINCT facts
matters; restating a fact you already recorded does not.

Respond ONLY with the complete reorganized skill.md content. No JSON, no code
fences, no extra commentary.
