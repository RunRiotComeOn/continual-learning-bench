You are editing a skill.md document. You are given the current document and a
list of ENTRIES TO REMOVE (claims that recent evidence has falsified).

Return the document with EXACTLY those entries deleted and EVERYTHING ELSE
preserved VERBATIM:
- Remove the bullet/line(s) corresponding to each listed entry (match by meaning;
  the wording in the document may differ slightly from the listed text).
- Do NOT add, reword, summarize, reorder, or "improve" any other content.
- If removing entries leaves a section header with no entries under it, you may
  drop that empty header; otherwise leave all structure intact.
- Do not introduce any new fact, table, column, value, or claim.

Respond ONLY with the resulting skill.md content. No JSON, no code fences, no
commentary.
