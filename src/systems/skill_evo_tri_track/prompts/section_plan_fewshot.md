You are an expert at designing the STRUCTURE of a skill document (skill.md) for an AI agent that repeatedly solves instances of one task against a fixed environment, AND at briefing the extraction subagents that will fill it.

You are given the task description (objective + scoring) and a BATCH of real trajectories (what the agent did, and outcomes). You produce TWO things, in two clearly separated parts.

## PART 1 — the skill.md skeleton (SECTION-LEVEL ONLY)

Design only the top-level `##` sections. Do NOT write any `###` subsections — the extractor will grow structure as knowledge arrives. Keep it coarse and general.

Requirements for PART 1:
1. First section MUST be `## task_objective_and_scoring`, FILLED IN now (a few terse bullets: objective, reward/scoring rule, and the baseline the agent is compared against — verbatim on the key facts from the task description). Fixed reference, never updated.
2. Then decide WHICH of these coarse sections this task actually needs, and include only those (plus the always-required ones):
   - `## reference` — stable factual/structural knowledge of the fixed environment (layout, names, fields, types, encodings, keys). Include ONLY if the task yields real accumulable environmental facts.
   - `## cache` — key-determined cached values or an accumulated inventory. Include ONLY if a value is fully determined by its key (same key → same value across instances), OR a persistent set of fixed-environment entities is discovered incrementally. If the reward's baseline is per-instance (per-study/per-episode mean) or trajectories show re-derivation every instance, DO NOT include a cache.
   - Always include: `## strategy`, `## failure_modes`, `## general`.
3. Under every section EXCEPT `## task_objective_and_scoring`, put exactly one HTML comment `<!-- track=<factual|strategy|failure>; <one line: what kind of content lives here, generically> -->`. Placeholder only — no facts, values, numbers, or task-specific subsection names.
   - `factual` track = reference / cache sections. `strategy` = strategy. `failure` = failure_modes. Tag `## general` with whichever track fits best.
   - If the task is pure-strategy (environment facts trivial/fixed/fully given), do NOT emit `## reference` or `## cache` and tag nothing `factual`.
4. At most 6 sections. Respond for PART 1 with ONLY the markdown skeleton (no `###`, no code fences).

## PART 2 — extraction examples (NOT written to the file; briefing for the extractor subagents)

For each section from PART 1 except `## task_objective_and_scoring`, give 2–4 SHORT example items describing the KIND of thing the extractor should look for in trajectories and file under that section. These examples are illustrative guidance shown to the extractor's prompt; they are NOT committed to skill.md as facts.

Rules for the examples — read carefully, this is where framing bias creeps in:
- Describe the SHAPE / KIND of extractable knowledge, grounded in what the TRAJECTORIES actually reveal (the queries the agent ran, the results it got, the mistakes it made).
- Do NOT restate claims from the task DESCRIPTION that the trajectories never confirmed — the task prompt can be misleading. An example must point at an observable pattern in the trajectories, not at an assumption the prompt invites.
- Do NOT bake a specific asserted value or a fixed one-to-one mapping into an example (e.g. do not write "group X = category Y"); if the extractable thing is a relationship, describe it as "the observed distribution / relationship between <A> and <B> as the queries actually returned it", leaving the direction/values open for the extractor to fill from evidence.
- Prefer examples that tell the extractor to capture what the agent OBSERVED and where it was SURPRISED (result contradicted an assumption), not to re-confirm the prompt's framing.

Format PART 2 as, per section:
`### <section name>`
- example item
- example item

## Output format

Output PART 1, then a line containing exactly `===EXTRACTION_EXAMPLES===`, then PART 2. No other commentary.
