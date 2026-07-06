# Batch-summarize build-up ablation — exploration path (b1 → b4)

**Goal.** `skill_evo_batch` ("batch-full") is the first variant to significantly
beat naive on `database_exploration` (+0.064, p=0.018, 16 seeds). This ladder
*decomposes* it the way the R-ladder decomposes naive: start from the naive
floor and add **one mechanism per rung**, so each adjacent paired Δ tells us which
mechanism actually moves reward. Every rung is `skill_evo_batch` with config flags;
all at 16 paired seeds, post-migration reward.

| rung | what's ON | post-mig | Δ vs prev |
|------|-----------|----------|-----------|
| naive | single-shot reflect | +0.105 | — |
| **b1** | batch summarize only | +0.129 | +0.024 (n.s.) |
| **b2** | + count + match + gate(thr5) | +0.077 | **−0.052 (p=.023)** |
| **b3** | + grounded refine | +0.102 | +0.025 (n.s.) |
| **b4** | + canary = batch-full | +0.169 | **+0.067 (p=.009)** |

---

## naive → b1 : isolate "batch-level candidate formation"

**Question.** batch-full beats `concise` (same downstream: ground+canary+thr5), and
the *only* difference is the candidate-formation stage — per-trajectory atomic
extract + pairwise canonicalize (concise) vs one batch-level summarize-and-count
(batch). So the first thing to test in isolation is: **is seeing the whole batch at
once the lever, before any of the downstream machinery?**

**What we add / strip.** b1 keeps *only* the batch summarize call and strips
everything else: `use_trajectory_count=False`, `enable_canonicalize=False` (no
cross-epoch match), `trigger_threshold=1` (every point promoted immediately — gate
off), `ground_refine=False`, `enable_canary=False`, `refine_interval=NEVER`. So b1 =
"each epoch, summarize the whole batch into points and dump them all into the doc."

**Result.** +0.129, **+0.024 over naive but n.s.** Batch formation alone *nudges* up
(above naive nominally) but is not significant on its own.

## b1 → b2 : add corroboration (count + cross-epoch match + gate)

**Why this is the natural next step.** Once you can form candidates, the obvious next
mechanism is *trusting the repeated ones more*: count how many trajectories exhibit a
point (`use_trajectory_count=True`), match points to existing canonicals across epochs
so the count accumulates (`enable_canonicalize=True`), and only promote a point once it
clears `thr=5` (`trigger_threshold=5`). Hypothesis: the gate filters one-off noise and
keeps only robust, corroborated facts → cleaner doc → higher reward.

**Result.** +0.077, **−0.052 vs b1, p=0.023 — a significant DROP**, even below naive.
The hypothesis was wrong *in isolation*: the gate ALONE **starves the document**. With
thr=5 and no refine, a point must be seen in 5 trajectories before it ever enters the
doc, so the agent spends the early instances reading a nearly-empty skill.md. The
corroboration filter is real, but with nothing to backfill the withheld content it
costs more than it saves.

## b2 → b3 : add grounded refine

**Why.** b2 showed the gate's failure mode is a *sparse* doc. Grounded refine is the
natural fix: every few trials it reads the raw trial trajectories+outcomes and
rewrites/fact-checks the whole skill.md (`ground_refine=True`, `refine_interval=5`),
so the doc is repopulated from evidence regardless of what the gate has/hasn't
promoted. Hypothesis: refine refills the starved doc and undoes b2's damage.

**Result.** +0.102, +0.025 vs b2 (n.s.) — **recovers to ~naive level** (Δ vs naive
−0.003, n.s.). Confirmed: refine compensates for the gate's starvation. But on its own
the batch system is still only *at* naive, not above it.

## b3 → b4 : add canary (= batch-full)

**Why.** b3 has good candidates (batch-formed) and a healthy doc (refilled), but every
triggered edit is committed blind. Canary is the last mechanism: hold the new edits on
probation for a validation window and keep them only if they don't hurt
(`enable_canary=True`). Hypothesis: validation trims the edits that look corroborated
but actually regress.

**Result.** +0.169, **+0.067 vs b3, p=0.009 — the dominant, only-significant positive
jump.** This is where batch-full's win actually comes from.

---

## Synthesis: it's a synergy, not a single rung

The naïve reading "find the one rung that wins" is wrong here — the ladder is
**non-monotonic** and the win is an **interaction of batch-formation × canary**:

- batch formation alone (b1): +0.024, **n.s.**
- batch formation + canary (b4): +0.169 — canary adds **+0.067**
- *old* formation + canary (`concise`): +0.077 — i.e. canary on per-trajectory
  candidates was a **dead end** (earlier: `nocanary` tied `concise`).

So canary only pays off **once the candidates are clean enough to validate**. Earlier
in the project we wrote canary off as useless; that conclusion was an artifact of the
noisy per-trajectory candidate formation. Batch summarization raises candidate quality
enough that validation finally has real signal to act on. Neither batch formation nor
canary is individually significant over naive; **together** they are (+0.064, p=0.018).

The bare corroboration gate (b2) is an active liability without grounded refine to
backfill it.

Configs: `b1_summarize_raw.json`, `b2_count_gate.json`, `b3_ground.json`,
`r7_batch_summarize16.json` (b4). Figure: `batch_ladder.png` via `batch_ladder_figs.py`.
