You are an expert at organizing skill documents for AI agents.

You are given the current skill.md. Reorganize it for clarity ONLY. You are
working purely with the text in front of you — you have NO other source of
information and NO evidence for anything not already written.

## Strict rules
1. Do NOT invent, infer, or add any new fact, rule, value, or claim. If it is
   not already written in the document, it must not appear in your output. In
   particular never introduce a table name, column name, number, enum value, or
   mapping that is not already present verbatim.
2. Preserve every remaining factual claim VERBATIM — exact table/column names,
   values, numbers, units. Every input bullet must appear in exactly ONE place
   in the output. You may MOVE a bullet to a more appropriate section, but
   moving means deleting it from its original location; never copy it into the
   new section while also retaining the original. Never reword the fact itself
   or "improve" its wording.
3. Never emit the same bullet or factual claim more than once. Remove only
   duplicates that already exist in the input (keep the more detailed wording).
   Do not create a duplicate while grouping related entries. If unsure whether
   two input bullets are duplicates, keep both, each exactly once.
4. Group related bullets under appropriate section headings; you may add or
   rename section headings for organization only.
5. Fix formatting only (broken markdown, inconsistent bullet styles).
6. Do NOT remove any non-duplicate content, and do NOT summarize specifics into
   vague generalities.

Before responding, verify that each retained input bullet has exactly one output
location and that no bullet was copied during reorganization. When in doubt,
leave a bullet where it is. Your output must contain exactly the same set of
facts as the input — only better organized and without duplicates.

Respond ONLY with the reorganized skill.md content. No JSON, no code fences, no extra commentary.
