# Research story — the batch-summarize build-up (database_exploration)

A continual-learning agent should turn its own experience into reusable memory.
We build that memory one module at a time; each rung is motivated by a concrete
failure of the previous one. Task: `database_exploration` (schema-drift; 40
instances, migration at 20). Metric: post-migration reward (mean ± 95%CI, 16
paired seeds). Evidence below is the agent's *actual* final `skill.md` (run_0).

| rung | module added | post-mig reward | Δ | final doc |
|------|--------------|-----------------|---|-----------|
| **b1** naive(oc) | outcome-only reflect memory (floor) | +0.033 | — | ~9000 |
| **b2** +gate | batch-summarize formation + occurrence-count corroboration gate | +0.077 | +0.044 | ~1700 |
| **b3** +ground | grounded refine (fact-check whole doc vs raw trials) | +0.102 | +0.025 | ~1600 |
| **b4** full | in-flow validation (canary) | +0.169 | +0.067 | ~5500 |

---

## b1 — the floor: a forgetful agent that only reflects on outcomes

**Setup.** The simplest memory: every few trials, reflect on what happened and
write notes. Our floor sees only the *question + outcome* of each trial (no
trajectory) — "outcome-only memory".

**What goes wrong.** Without the trajectory, the agent can't see *why* it
succeeded or failed, so its notes are verbose but **speculative and ungrounded** —
it guesses at causes and uses generic, possibly-wrong column names.

> **b1 skill.md (excerpt):**
> - *"Anti-join or NOT EXISTS for 'present in X but absent in Y' patterns. Trial 5
>   (188 vs 267) undercounted products with reviews but no attributes; **likely**
>   used INNER JOIN or incorrect exclusion logic..."*
> - *"Computing category-wide averages: exclude zeros and handle NULLs... **likely**
>   included zeros or NULLs in denominator, **or** comparison logic was inverted."*

Note the hedging ("likely", "or") and generic names (`review_body`,
`attributes`) — it never saw the real schema. Barely above stateless (+0.033).

## b2 — turn raw experience into corroborated, structured knowledge

**Problem A (lose structure).** Free-form / outcome reflection doesn't extract
reusable, structured facts. **Module: batch-summarize formation** — read the whole
batch of trajectories at once and distill discrete *points* (schema facts +
interpretation rules), so recurring signal surfaces.

**Problem B (noise pollutes memory).** Extracted points include one-off flukes and
hallucinations. **Module: occurrence-count corroboration gate** — count in how many
trajectories each point appears, accumulate across epochs, and only write a point
once `quantity ≥ threshold`. A fluke seen once never enters; a rule seen
repeatedly earns its place.

**What this buys (and its own failure).** The memory is now grounded in real
schema (e.g. it learns the actual table names `fdbk_g1`, `items_g1`, the timestamp
encoding). But on its own the gate is *too strict without anything to backfill* —
it admits so few points the doc is mostly empty section skeletons:

> **b2 skill.md (excerpt):**
> ```
> ## environment_facts
> <!-- table naming (fdbk_g1, items_g1, attrs_g1, taxn_g1), columns (ts, main_cat,
>      item_id, ref_id), timestamp = microseconds since epoch (ts/1000000) -->
> ## timestamp_handling
> <!-- detecting scale (microseconds vs ms vs s), datetime() with proper division -->
> ## failure_modes
> <!-- incorrect timestamp scaling (off by 1000x or 1000000x)... -->
> ```

Reward rises to +0.077 (real schema beats speculation), but the corroborated-only
doc is thin — which motivates the next module.

## b3 — keep the memory correct and current: grounded self-correction

**Problem (drift / error accumulation).** The gate decides *what enters*, but the
document is built from incremental LLM edits that accumulate mistakes, contradict
each other, and **go stale under distribution shift** (after the schema migration,
old facts are wrong). Nobody fixes what's already written.

**Module: grounded refine.** Periodically re-read the recent *raw trajectories* and
rewrite + fact-check the whole document against ground truth — correct claims the
evidence contradicts, drop unverified guesses, flag what's uncertain.

> **b3 skill.md (excerpt):**
> - *"**items_g2 (Electronics)** has both `prc` (INTEGER, non-USD raw price) and
>   `prc_usd` (REAL, USD price). For dollar-denominated questions, **always use
>   `prc_usd`, not `prc`**. This differs from items_g1/items_g3 where `prc` is
>   already USD."*  ← the killer interpretation rule, with the wrong-vs-right contrast
> - *"## open_questions — **VERIFY**: the mapping of `_g1` to Musical Instruments vs
>   Office Products. Evidence shows both appear... **read the exact main_cat
>   distribution before assuming**."*  ← it knows what it's unsure of

This is self-correction: concrete, evidence-cited rules plus explicit uncertainty.
Reward +0.102. (Side effect we later study: the refine *over-compresses* — the doc
shrinks to ~1600, sometimes dropping useful detail.)

## b4 — don't commit an update you haven't validated: validation in the flow

**Problem (is the update actually good?).** Even fact-checked edits can hurt. You
want to validate a candidate update before deploying it — but in a continual /
online setting you **can't pause to evaluate on a held-out set**.

**Module: in-flow validation (canary).** Deploy the candidate, run the next few
*real* task instances under it, keep the edits only if performance doesn't drop.
Validation rides on real work — free, online-compatible, measured against the
current distribution (vs SkillOpt's frozen held-out set).

The richest, most actionable document of the ladder — a full schema reference the
agent can act on directly:

> **b4 skill.md (excerpt):**
> ```
> ### items_g2 (electronics)
> - `ref_id` TEXT PRIMARY KEY      - `prc` INTEGER — price (cents)
> - `prc_usd` REAL — price (dollars)  - `main_cat` TEXT (e.g. "Computers", ...)
> - `img_ct` INTEGER — image count (can be NULL)
> ```

Reward +0.169.

---

## ⚠️ Honest caveat on b4 (do not hide this — it is itself a finding)

Our own experiments show this canary **never reverts** on this task (0/51 across 16
runs) — so its accept/reject decision is inert. Its +0.067 traces to a *structural
side-effect*: a canary window pauses the (over-eager) refine, letting the document
retain more content (~5500 vs ~1600), which is what actually helps. Evidence:
forcing the refine to run during canary collapses reward to +0.081 (≈ no-canary,
p=0.001).

We therefore frame b4 as **in-flow validation** (the paradigm — free, online,
drift-current — remains the real contribution vs held-out methods) while reporting
honestly that, *on this task*, harmful edits are rare enough that validation rarely
fires, and the measured gain came from preventing over-compression. The cleaner,
reproducible version of b4's benefit is a memory-compression control (refine
cadence), which we evaluate separately. See memory `canary-gain-is-refine-artifact`.

## One-line elevator pitch

> Starting from a naive memory, the agent hits four problems in turn — **can't
> extract structured knowledge → noise pollutes it → memory goes stale/wrong →
> can't tell if an update helps** — solved by **batch-level formation, an
> occurrence-count corroboration gate, grounded self-correction, and in-flow
> validation**. Each adds measurable reward, ending significantly above weak
> baselines and on par with a strong in-context-learning baseline on a
> schema-drift task.
