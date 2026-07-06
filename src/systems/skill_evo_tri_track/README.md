# skill_evo_tri_track

A self-contained, **per-track** skill-evolution system. It maintains one
self-evolving `skill.md`, but treats its three knowledge tracks —
**environmental fact / strategy / failure mode** — with *different* operations,
thresholds, and promotion policies, because they carry different kinds of
knowledge that deserve different evidence bars.

## Why this exists (the design thesis)

The shared `skill_evo_planner` family uses **one** aggregator with **one** global
`trigger_threshold` and **one** `authoritative_fast_track` flag for all content.
Analysis of the tri runs showed this conflates two very different things:

- **Authoritative environment facts** (a schema, a column type, a per-study cohort
  definition): true on a *single* grounded observation. A high global threshold
  *gates these out* — e.g. each cohort study is seen only 1–2 times, so its
  definition never reaches threshold 3 and sits "waiting" forever, exactly the
  most reusable knowledge being filtered away.
- **Strategy / exploitation reads** ("opponent tends to fold"): *probabilistic*
  tendencies, true on average, that an agent will over-apply into blow-ups if
  trusted from one sighting. These genuinely *need* repetition before promotion.

A single threshold cannot serve both. This system gives each track its own gate.

## Not built on the planner parent

`TriTrackSystem` extends only the abstract `ContinualLearningSystem`. It owns its
whole loop and **deliberately omits** every mechanism that is disabled in
`tri_keyed` anyway: there is **no canary/validation, no decay, no
contradiction-audit, no naive/raw-append/stateless** ablation path. It reuses only
stateless helper *functions* from the planner package (extraction, promotion,
skeleton design, refine) — not its class hierarchy.

## Per-track policy

| track | threshold (default) | fast-track | rationale |
|---|---|---|---|
| **factual** | **1** | **on** | a grounded environment fact is trustworthy on one sighting → promote immediately, no accumulation |
| **strategy** | **2** | off | a strategy is a probabilistic read → needs to recur before it's trusted; never promotes on a single observation |
| **failure** | **2** | **on** | a HARD/explicit failure (an error, a tool rejection, a result wrong against a known value → `support_type=authoritative`) promotes at once; an *inferred* trap waits for a 2nd confirmation |

"Fast-track" = a canonical the extractor tags `support_type=authoritative` is
promoted at `quantity=1`, bypassing the threshold (and is capped at quantity 1 so
it never over-accumulates). All thresholds/flags are config-overridable
(`factual_threshold`, `strategy_threshold`, `failure_threshold`,
`factual_fast_track`, `strategy_fast_track`, `failure_fast_track`).

### Per-track operations (in the `extract_<track>.md` prompts)

- **factual** — `add` / `refine` (enrich, keep prior detail) / **`replace`** =
  the recorded object/value is now *stale*: renamed, superseded, or no longer
  exists → point `match` at the obsolete entry and retire it (never leave it alive
  as a parallel point).
- **strategy** — `add` (new decision point) / `refine` (add the *discriminating
  condition*, grow the procedure) / **`replace`** = a trial shows the recorded
  approach was actually wrong/worse → corrected procedure.
- **failure** — `add` (new trap) / `refine` (narrow the trigger / add an
  established correction) / **`replace`** = a trial shows the warned-against action
  was actually fine → corrected. A failure entry is *not* contradicted just
  because recent trials avoided it.

## The loop

```
respond(query):   inject skill.md (+ a "facts stable / reads probabilistic" usage
                  note) → task LLM (Bedrock Converse) → buffer the trajectory
observe(obs):     on instance completion, store a TrialRecord; every
                  accumulation_batch_size instances → batch boundary

batch boundary:
  (first batch only) build skeleton:
      planner designs sections AND tags each section's track in ONE pass;
      resolve_section_tracks reads the inline `track=` tags (no 2nd classifier
      call), strips them, and splits the focus-plan per track.
  for each active track:
      stage_bc_batch_summarize  → extract points into THIS track's aggregator,
                                  with THIS track's fast-track flag
      stage_d_trigger_and_update (multiplier=1.0) → fold the track's triggered
                                  canonicals into the shared skill.md
  every refine_interval trials: structural refine of skill.md
  re-assert the frozen task_objective_and_scoring section
```

The `task_objective_and_scoring` section is filled once from the task description
and frozen (re-asserted after each edit so it is never rewritten away).

## Key config params

`bedrock_model_id`, `task_temperature`, `optimizer_temperature`,
`accumulation_batch_size` (default 5), `refine_interval` (default 5),
`clear_context_between_instances`, plus the per-track policy params above and
`enable_replace` / `enable_merge` / `enable_match` / `use_trajectory_count`.

## Artifacts

`get_run_artifacts()` and snapshots dump `skill.md` plus **one aggregator per
track** (`aggregator_factual.json` / `aggregator_strategy.json` /
`aggregator_failure.json`) so each track's canonicals, quantities, and statuses
can be inspected independently.
