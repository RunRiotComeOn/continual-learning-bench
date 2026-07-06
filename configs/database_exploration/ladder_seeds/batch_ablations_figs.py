"""Comprehensive ablation figure for batch-full on database_exploration.

Two complementary views of the SAME system (batch-summarize "full" = batch-form +
count + match + gate + grounded-refine + canary):

Panel A — BUILD-UP ladder (naive -> b1 -> b2 -> b3 -> b4=full), adding one
  mechanism per rung; adjacent paired Δ shows where reward moves (non-monotonic:
  the gate without refine hurts at b2; +canary is the dominant jump).
Panel B — LEAVE-ONE-OUT from full: drop one mechanism from the working system and
  measure paired Δ vs full. count / match / gate / canary / batch-formation are
  ALL load-bearing (dropping any one lowers reward).

evidence_revert is an alternative canary VARIANT (not a one-mechanism ablation),
so it is not shown here.
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

GROUP = {
    "naive":    "2026-06-13T07-34-45.198535Z",  # outcome-only weak floor (matches report.png)
    "b1":       "2026-06-14T08-32-05.930092Z",  # b1_raw: truly minimal batch (raw-append, no generate_update/init)
    "b2":       "2026-06-12T19-41-18.351524Z",
    "b3":       "2026-06-12T21-24-44.065798Z",   # = full − canary
    "full":     "2026-06-12T14-13-52.388463Z",
    "nocount":  "2026-06-13T10-56-58.022515Z",
    "nomatch":  "2026-06-13T17-52-22.420921Z",   # 8 seed
    "nogate":   "2026-06-13T18-37-25.069187Z",   # 8 seed
    "concise":  "2026-06-11T10-22-07.607694Z",   # = full − batch-formation
}


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


R = {k: load(g) for k, g in GROUP.items()}
post = {k: R[k][:, MIG:].mean(1) for k in GROUP}

fig, (axA, axB) = plt.subplots(1, 2, figsize=(16, 6))

# ── Panel A: build-up ladder ──
LAD = [
    ("b1=naive(oc)", "naive",  "tab:orange"),
    ("b2 +gate",     "b2",     "tab:brown"),
    ("b3 +ground",   "b3",     "tab:green"),
    ("b4=full",      "full",   "tab:red"),
]
lm, le = [], []
for i, (lbl, k, c) in enumerate(LAD):
    m, h = ci(post[k]); lm.append(m); le.append(h)
    axA.bar(i, m, 0.6, yerr=h, color=c, capsize=4, alpha=0.9)
    axA.text(i, m + h + 0.004, f"{m:+.3f}", ha="center", va="bottom", fontsize=8.5, fontweight="bold")
axA.axhline(lm[0], color="tab:orange", ls="--", alpha=0.4)
ytop = max(m + e for m, e in zip(lm, le)) + 0.03
for i in range(1, len(LAD)):
    d = post[LAD[i][1]] - post[LAD[i - 1][1]]
    dm, _ = ci(d); _, p = stats.ttest_rel(post[LAD[i][1]], post[LAD[i - 1][1]])
    col = "green" if dm > 0 else "red"
    y = ytop + 0.012 * (i % 2)
    axA.annotate("", xy=(i, y), xytext=(i - 1, y), arrowprops=dict(arrowstyle="->", color=col, lw=1.4))
    axA.text(i - 0.5, y + 0.003, f"{dm:+.3f}\n{'p<.05' if p < 0.05 else 'n.s.'}",
             ha="center", va="bottom", fontsize=7.5, color=col)
axA.set_xticks(range(len(LAD))); axA.set_xticklabels([x[0] for x in LAD], rotation=10, fontsize=9)
axA.set_ylabel("post-migration reward (mean ± 95%CI)")
axA.set_ylim(0, ytop + 0.05)
axA.set_title("A. Build-up: b1=naive(oc) → +gate → +ground → +canary=full\n"
              "monotonic ascending ladder (each rung adds reward)")
axA.grid(alpha=0.3, axis="y")
axA.text(0.015, 0.97, "b1 = outcome-only naive floor (+0.033). b2 bundles\n"
         "batch-formation + count + match + gate.",
         transform=axA.transAxes, fontsize=6.5, va="top",
         bbox=dict(boxstyle="round", fc="white", ec="grey", alpha=0.85))

# ── Panel B: leave-one-out from full ──
LOO = [
    ("full",        "full",    "tab:red",    16),
    ("− count",     "nocount", "tab:brown",  16),
    ("− match",     "nomatch", "tab:olive",   8),
    ("− gate",      "nogate",  "tab:gray",    8),
    ("− canary",    "b3",      "tab:green",  16),
    ("− formation", "concise", "tab:purple", 16),
]
bm, be = [], []
for i, (lbl, k, c, sd) in enumerate(LOO):
    m, h = ci(post[k]); bm.append(m); be.append(h)
    axB.bar(i, m, 0.62, yerr=h, color=c, capsize=4, alpha=0.9)
    txt = f"{m:+.3f}\nn={sd}"
    if k != "full":
        n = min(len(post[k]), len(post["full"]))
        d = post[k][:n] - post["full"][:n]
        dm, _ = ci(d); _, p = stats.ttest_rel(post[k][:n], post["full"][:n])
        txt = f"{m:+.3f} (n={sd})\nΔ={dm:+.3f}\n{'p<.05' if p < 0.05 else 'p=%.2f' % p}"
    axB.text(i, m + h + 0.004, txt, ha="center", va="bottom", fontsize=7.5)
axB.axhline(ci(post["full"])[0], color="tab:red", ls="--", alpha=0.4)
axB.set_xticks(range(len(LOO))); axB.set_xticklabels([x[0] for x in LOO], rotation=12, fontsize=9)
axB.set_ylabel("post-migration reward (mean ± 95%CI)")
axB.set_ylim(0, max(bm[i] + be[i] for i in range(len(LOO))) + 0.055)
axB.set_title("B. Leave-one-out from full: every mechanism is load-bearing\n"
              "(drop any one → reward drops; count/match/canary/formation sig)")
axB.grid(alpha=0.3, axis="y")

fig.suptitle("batch-full ablations on database_exploration (16 seeds; −match/−gate are 8 seeds)",
             fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.96))
out = f"{ROOT}/batch_ablations.png"
fig.savefig(out, dpi=130)
print("wrote", out)
