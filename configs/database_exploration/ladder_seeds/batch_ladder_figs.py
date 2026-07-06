"""Build-up ablation ladder for the batch-summarize "full" on database_exploration.

Decomposes batch-full into one-mechanism-per-rung, naive -> batch-full, all at
16 paired seeds. Shows post-migration reward (mean +/- 95%CI) with the adjacent
paired Delta annotated between rungs (which mechanism actually moves reward).

Finding: the ladder is NON-monotonic. batch formation (b1) nudges up; the
corroboration gate alone (b2) significantly HURTS (thr=5 starves the doc with no
refine to refill it); grounded refine (b3) recovers to ~naive; and the canary
step is the dominant, only-significant positive jump to batch-full.
"""
from __future__ import annotations

import glob
import gzip
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

ART = "results/database_exploration/viewer_artifact_{g}_*.json.gz"
MIG = 20
ROOT = "results/ladder_seeds/database_exploration"

# rung label -> (group id, color, "what this rung adds")
RUNGS = [
    ("naive (oc)",       "2026-06-13T07-34-45.198535Z", "tab:orange", "outcome-only floor; naive→b1 also bundles trace access"),
    ("b1 raw-form",      "2026-06-14T08-32-05.930092Z", "tab:olive",  "batch summarize + raw-append (no generate_update/init; all else OFF)"),
    ("b2 +gate",         "2026-06-12T19-41-18.351524Z", "tab:brown",  "+ trajectory count + cross-epoch match + thr5 gate"),
    ("b3 +ground",       "2026-06-12T21-24-44.065798Z", "tab:green",  "+ grounded refine"),
    ("b4 +canary=full",  "2026-06-12T14-13-52.388463Z", "tab:red",    "+ canary validation"),
]
ORDER = [r[0] for r in RUNGS]


def rewards(tr):
    o = tr.get("instance_outcomes") or tr["result"]["instance_outcomes"]
    o = sorted(o, key=lambda x: x["instance_index"])
    return np.array([float(x["reward"]) for x in o])


def load(g):
    d = json.load(gzip.open(sorted(glob.glob(ART.format(g=g)))[0]))
    return np.stack([rewards(rt["trace"]) for rt in d["run_traces"]])


def ci(a):
    a = np.asarray(a, float)
    return a.mean(), 1.96 * a.std(ddof=1) / np.sqrt(len(a))


R = {lbl: load(g) for lbl, g, _, _ in RUNGS}
post = {lbl: R[lbl][:, MIG:].mean(1) for lbl in ORDER}

fig, ax = plt.subplots(figsize=(11, 6))
xs = np.arange(len(ORDER))
means, errs = [], []
for i, lbl in enumerate(ORDER):
    m, h = ci(post[lbl])
    means.append(m); errs.append(h)
    ax.bar(i, m, 0.6, yerr=h, color=RUNGS[i][2], capsize=4, alpha=0.9)
    ax.text(i, m + h + 0.004, f"{m:+.3f}", ha="center", va="bottom", fontsize=9, fontweight="bold")

# naive reference line
ax.axhline(means[0], color="tab:orange", ls="--", alpha=0.5)

# adjacent paired Δ annotations (arrows between consecutive rungs)
ytop = max(m + e for m, e in zip(means, errs)) + 0.03
for i in range(1, len(ORDER)):
    a, b = ORDER[i], ORDER[i - 1]
    d = post[a] - post[b]
    dm, dh = ci(d)
    _, p = stats.ttest_rel(post[a], post[b])
    sig = "p<.05" if p < 0.05 else "n.s."
    col = "green" if dm > 0 else "red"
    y = ytop + 0.012 * (i % 2)
    ax.annotate("", xy=(i, y), xytext=(i - 1, y),
                arrowprops=dict(arrowstyle="->", color=col, lw=1.4))
    ax.text(i - 0.5, y + 0.003, f"Δ={dm:+.3f}\n({sig})", ha="center", va="bottom",
            fontsize=8, color=col)

ax.set_xticks(xs)
ax.set_xticklabels([f"{r[0]}" for r in RUNGS], rotation=12, fontsize=9)
ax.set_ylabel("post-migration reward (mean ± 95%CI, n=16)")
ax.set_ylim(0, ytop + 0.05)
ax.set_title("Batch-summarize build-up ablation (database_exploration, 16 paired seeds)\n"
             "non-monotonic: gate alone hurts; canary is the dominant significant jump",
             fontsize=12)
ax.grid(alpha=0.3, axis="y")

# footnote with each-vs-naive(reflect floor)
lines = []
floor = ORDER[0]
for lbl in ORDER[1:]:
    d = post[lbl] - post[floor]
    dm, dh = ci(d); _, p = stats.ttest_rel(post[lbl], post[floor])
    lines.append(f"{lbl} vs {floor}: {dm:+.3f} ({'p<.05' if p < 0.05 else 'n.s.'})")
ax.text(0.015, 0.97, "\n".join(lines), transform=ax.transAxes, fontsize=7.5,
        va="top", ha="left", bbox=dict(boxstyle="round", fc="white", ec="grey", alpha=0.8))

fig.tight_layout()
out = f"{ROOT}/batch_ladder.png"
fig.savefig(out, dpi=130)
print("wrote", out)
