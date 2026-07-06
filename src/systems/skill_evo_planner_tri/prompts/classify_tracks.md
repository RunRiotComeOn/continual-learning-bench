You are assigning each section of a skill-document skeleton to ONE of three
knowledge tracks, so that three separate extraction passes each own their sections.

The three tracks:
- `factual` — reusable factual/structural knowledge about the fixed environment
  and the concrete values it yields (schemas, fields, encodings, keys, formats,
  cached results, reference data).
- `strategy` — how to act: procedures, decision policies, principles, the method
  for producing values, effort/budget trade-offs, safe defaults.
- `failure` — failure modes, traps, common mistakes to avoid (with corrections).

You are given the task brief plus the skeleton's top-level `## section` headings
(each with its short description). Assign EVERY listed section to exactly one track
by its purpose. Its subsections inherit the same track. A reference/schema/cache/
data section is `factual`; a how-to/phase/procedure section is `strategy`; a
mistakes/pitfalls section is `failure`. When a section is ambiguous, pick the track
whose extraction would most naturally own its content.

## Whether the factual track is worth running
Also judge the TASK as a whole. Some tasks are essentially **pure-strategy /
decision problems**: the environment facts are trivial, fixed, and fully given up
front (e.g. the rules of a game), so there is no meaningful *reusable factual
knowledge to accumulate across instances* — what varies and what skill must
capture is HOW to act. For such tasks set `factual_track_enabled` to false; the
factual extraction pass will then be skipped so effort concentrates on strategy
and failure modes. Set it to true (the default) whenever the task yields real,
accumulable environmental facts (schemas, data values, discovered structure).
When you set it false, do NOT assign any section to `factual` (route a genuinely
reference-like section to `strategy`, or leave it out).

Return ONLY JSON matching the schema: `factual_track_enabled` (bool) plus one
`assignments` object per section
(`{"section": "<exact heading text without ##>", "track": "factual|strategy|failure"}`).
No prose.
