You are analyzing a BATCH of recent task trials to maintain a skill memory for
an AI agent. You see several trial trajectories at once (each shows what the
agent saw, did, and the outcome) plus the list of POINTS already in memory.

Your job: distill the batch into a list of POINTS — the reusable lessons, facts,
and interpretation rules worth remembering — and, for each, report HOW MANY of
these trials exhibit it and whether it matches an existing point.

A POINT may be a single atomic fact OR a small coherent cluster of closely
related observations — choose whichever granularity makes the point most useful
and self-contained. Do not over-shard one idea into many near-duplicates, and do
not merge unrelated ideas into one blob.

Kinds of points to mine (mix both):
  • SCHEMA FACTS — stable properties of the environment (table/column names +
    types, units, enum values, join keys, category→group maps). Record VERBATIM.
  • INTERPRETATION RULES — how to read a question and map it to the right query
    decision: which column/filter/table a phrasing actually needs, and the trap
    that produced a WRONG answer until corrected. Record as
    "<question intent> → use <correct> (not <wrong>); evidence: <wrong> vs
    <correct>, Trial N". KEEP the citing values.

For EACH point report:
  • description — the point, stated VERBATIM and self-contained.
  • effect — "positive" (helped / was the correct move), "negative" (a trap or
    mistake to avoid), or "unclear".
  • evidence — the concrete observation(s) supporting it, with values.
  • trajectories — the list of 1-based trial numbers (from THIS batch) in which
    this point actually appears or is demonstrated. This count is what decides
    whether the point is robust enough to promote, so be accurate: include a
    trial only if its trajectory genuinely exhibits the point.
  • match — if the point is the SAME lesson as one already in memory, put that
    point's id here so its count accumulates; otherwise put "new". Only use an id
    that appears in the provided existing-points list.

Count broadly across trajectories but honestly: a point seen in many trials is
trustworthy; a one-off is tentative. Do not pad counts.

Respond ONLY with JSON matching the schema. No prose, no code fences.
