You are an expert at maintaining a skill document for an AI agent.

You are given the current skill.md (built incrementally from extracted skill
edits, which may include mistaken or hallucinated claims) together with several
RECENT task trials — each showing what the agent actually did and the outcome.
Your job is to reorganize AND fact-check the document against this evidence.

The document holds TWO kinds of content; treat them DIFFERENTLY:

  • SCHEMA FACTS — static properties of the environment (table names, column
    lists + types, units, enum values, join keys, category-to-group mappings).
  • INTERPRETATION RULES — how to read a QUESTION and map it to the right query
    decision: which column/filter/table a given question intent actually
    requires, what a tricky phrasing really means, and the traps that produced a
    WRONG answer until corrected. These are the lessons that earn reward on
    recurring question types, and they are usually missing or under-recorded.

## Requirements
1. ENRICH SCHEMA: mine the trials for concrete, stable schema facts the document
   is missing and record them VERBATIM — exact table/column names, types,
   key/value mappings, units, enums, join keys. Record what an action confirmed;
   do not vague-summarize.
2. MINE INTERPRETATION RULES — do this aggressively; it is the main gap. For
   every trial where an answer was wrong then fixed, where a question phrasing
   was ambiguous, or where the agent had to choose between similar
   columns/tables/filters, record a rule of the form:
   "<question intent / phrasing> → use <correct column/filter/table/reading>
   (not <the tempting wrong one>); evidence: <wrong value> vs <correct value>,
   Trial N". KEEP the citing values and the wrong-vs-right contrast — for these
   rules that evidence IS the content, not padding. Prefer concrete question
   patterns over generic advice.
3. NO REDUNDANCY — state each distinct fact or rule EXACTLY ONCE, in the single
   most appropriate section; never echo the same item across "facts" / "rules" /
   "strategy" / "failure modes". If a section would only repeat what another
   gives, leave it short.
4. BE COMPACT — for SCHEMA FACTS only: a terse phrase, drop the "why" (e.g.
   "fdbk_g1 joins on item_id (not ref_id)"). Do NOT apply this trimming to
   interpretation rules: keep their question pattern, the correct reading, and
   the wrong-vs-right evidence intact.
5. CORRECT or REMOVE entries the trials contradict (a named table/column does
   not exist, or a value differs from what an entry asserts).
6. REMOVE unverified guesses / hallucinations — claims stated as fact but never
   corroborated by a successful action. Do not keep a fact just because it is
   already there.
7. Keep evidence-supported items verbatim; prefer items supported by more than
   one trial; word single-trial observations tentatively. Keep the document
   coherent — never assert two contradictory things at once.

The goal: a tight reference whose schema facts are deduped and terse, AND whose
interpretation rules are thoroughly mined and kept with their wrong-vs-right
evidence. Completeness of DISTINCT items matters; repetition does not.

Respond ONLY with the complete reorganized skill.md content. No JSON, no code
fences, no extra commentary.
