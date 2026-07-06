You are an expert at organizing skill documents for AI agents.

You are given the current skill.md. Its `##` section and `###` subsection headings form a deliberately designed skeleton. Reorganize the CONTENT for clarity ONLY. You are working purely with the text in front of you — you have NO other source of information and NO evidence for anything not already written.

## Strict rules
1. Do NOT invent, infer, or add any new fact, rule, value, or claim. If it is not already written in the document, it must not appear in your output. In particular never introduce a table name, column name, number, enum value, or mapping that is not already present verbatim.
2. PRESERVE THE SKELETON. Every `##` section heading and every `###` subsection heading already present MUST appear in your output, unchanged, even if its slot is currently empty (keep its `<!-- -->` placeholder comment when empty). Never delete or rename an existing heading.
3. You MAY ADD new `###` subsection headings under an existing `##` section when several bullets clearly form a new recurring sub-group that has no home yet. Give an added subsection a concrete, task-specific heading. Never add a new top-level `##` section.
4. Preserve every factual claim VERBATIM — exact table/column names, values, numbers, units. Every input bullet must appear in exactly ONE place in the output. You may MOVE a bullet to a more appropriate (sub)section, but moving means deleting it from its original location; never copy it into the new location while also retaining the original. Never reword the fact itself.
5. Never emit the same bullet or factual claim more than once. Remove only duplicates that already exist in the input (keep the more detailed wording). Do not create a duplicate while grouping.
6. Fix formatting only (broken markdown, inconsistent bullet styles). Do NOT remove any non-duplicate content, and do NOT summarize specifics into vague generalities.

Before responding, verify that (a) every input heading is still present, and (b) each retained input bullet has exactly one output location. When in doubt, leave a bullet where it is.

Respond ONLY with the reorganized skill.md content. No JSON, no code fences, no extra commentary.
