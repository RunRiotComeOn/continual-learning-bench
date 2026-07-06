"""Leave-one-out ablation from batch-full on database_exploration.

Drop ONE mechanism from the working full system (which has ground_refine + canary)
and measure the paired Δ vs full. Unlike the build-up ladder (order-dependent),
this gives each mechanism's marginal value IN the working system.

Finding: count / match / gate are ALL load-bearing — dropping any one lowers
reward (count & match significantly; gate borderline). So the b2 dip in the
build-up (where adding count+match+gate together HURT, with no refine yet) was a
context effect: the gate starves the doc when nothing refills it. With grounded
refine present, the gate is a net positive. None of the three is inherently bad.
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

# label -> (group, color, seed note)
BARS = [
    ("batch-full",  "2026-06-12T14-13-52.388463Z", "tab:red",    16),
    ("− count",     "2026-06-13T10-56-58.022515Z", "tab:brown",  16),
    ("− match",     "2026-06-13T17-52-22.420921Z", "tab:olive",   8),
    ("− gate",      "2026-06-13T18-37-25.069187Z", "tab:gray",    8),
]


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


R = {lbl: load(g) for lbl, g, _, _ in BARS}
post = {lbl: R[lbl][:, MIG:].mean(1) for lbl, _, _, _ in BARS}
full = post["batch-full"]

fig, ax = plt.subplots(figsize=(8.5, 6))
xs = np.arange(len(BARS))
for i, (lbl, _, color, sd) in enumerate(BARS):
    m, h = ci(post[lbl])
    ax.bar(i, m, 0.62, yerr=h, color=color, capsize=4, alpha=0.9)
    txt = f"{m:+.3f}\nn={sd}"
    if lbl != "batch-full":
        n = min(len(post[lbl]), len(full))
        d = post[lbl][:n] - full[:n]
        dm, _ = ci(d)
        _, p = stats.ttest_rel(post[lbl][:n], full[:n])
        sig = "p<.05" if p < 0.05 else ("~p=%.2f" % p)
        txt = f"{m:+.3f} (n={sd})\nΔ={dm:+.3f}\n{sig}"
    ax.text(i, m + h + 0.004, txt, ha="center", va="bottom", fontsize=8.5)
ax.axhline(ci(full)[0], color="tab:red", ls="--", alpha=0.5)
ax.set_xticks(xs); ax.set_xticklabels([b[0] for b in BARS], fontsize=10)
ax.set_ylabel("post-migration reward (mean ± 95%CI)")
ax.set_ylim(0, max(ci(post[l])[0] + ci(post[l])[1] for l, _, _, _ in BARS) + 0.06)
ax.set_title("Leave-one-out from batch-full (database_exploration)\n"
             "count / match / gate are all load-bearing — none is the b2 dip's cause",
             fontsize=12)
ax.grid(alpha=0.3, axis="y")
ax.text(0.015, 0.97,
        "b2 dip reconciled: gate hurts ONLY without grounded refine\n"
        "(starves the doc); with refine present, gate is a net positive.\n"
        "no_match / no_gate are 8-seed; full / no_count 16-seed.",
        transform=ax.transAxes, fontsize=7.5, va="top",
        bbox=dict(boxstyle="round", fc="white", ec="grey", alpha=0.85))

fig.tight_layout()
out = f"{ROOT}/leave_one_out.png"
fig.savefig(out, dpi=130)
print("wrote", out)
