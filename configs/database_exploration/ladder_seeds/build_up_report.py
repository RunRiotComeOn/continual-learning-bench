"""Report-style 3-panel figure for the batch build-up ladder (b1→b4).

Ladder (monotonic): b1 = naive(outcome-only) → b2 +gate → b3 +ground → b4 = full.
Sizes (B/C) read from the run artifact (skill_md_length), robust to runs that
don't persist disk snapshots.

  A. cumulative reward vs instance (mean ± 95%CI)
  B. skill.md size (chars) vs instance
  C. final skill.md size vs total reward @40
"""
from __future__ import annotations

import glob
import gzip
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ART = "results/database_exploration/viewer_artifact_{g}_*.json.gz"
MIG = 20
ROOT = "results/ladder_seeds/database_exploration"
TS = [1, 5, 10, 15, 20, 25, 30, 35, 40]

# label -> (group, color)
RUNGS = [
    ("b1 = naive(oc)", "2026-06-13T07-34-45.198535Z", "tab:orange"),
    ("b2 +gate",       "2026-06-12T19-41-18.351524Z", "tab:brown"),
    ("b3 +ground",     "2026-06-12T21-24-44.065798Z", "tab:green"),
    ("b4 = full",      "2026-06-12T14-13-52.388463Z", "tab:red"),
]


def rewards(tr):
    o = tr.get("instance_outcomes") or tr["result"]["instance_outcomes"]
    o = sorted(o, key=lambda x: x["instance_index"])
    return np.array([float(x["reward"]) for x in o])


def load(g):
    return json.load(gzip.open(sorted(glob.glob(ART.format(g=g)))[0]))


def reward_mat(d):
    return np.stack([rewards(rt["trace"]) for rt in d["run_traces"]])


def size_mat(d):
    rows, finals = [], []
    for w in d["run_traces"]:
        size = {}
        for x in w["trace"]["interactions"]:
            q = x.get("query") or {}
            rm = (x.get("response") or {}).get("metadata") or {}
            ii, sl = q.get("instance_index"), rm.get("skill_md_length")
            if ii is not None and sl is not None:
                size[ii] = sl
        fin = max(size.values()) if size else 0.0
        finals.append(fin)
        rows.append([fin if t >= 40 else size.get(t, np.nan) for t in TS])
    return np.array(rows, float), np.array(finals, float)


def band(M):
    m = np.nanmean(M, axis=0)
    n = np.sum(~np.isnan(M), axis=0)
    sd = np.nanstd(M, axis=0, ddof=1)
    return m, 1.96 * sd / np.sqrt(n)


fig, (axA, axB, axC) = plt.subplots(1, 3, figsize=(17, 5.2))
x = np.arange(1, 41)

for label, g, color in RUNGS:
    d = load(g)
    r = reward_mat(d); n = len(r)
    cum = np.cumsum(r, axis=1)
    m = cum.mean(0); se = 1.96 * cum.std(0, ddof=1) / np.sqrt(n)
    axA.plot(x, m, color=color, lw=2.2, label=f"{label} (n={n})")
    axA.fill_between(x, m - se, m + se, color=color, alpha=0.12)

    M, finals = size_mat(d)
    cm, ce = band(M)
    axB.plot(TS, cm, "-o", color=color, lw=2.2, ms=4, label=f"{label} (n={n})")
    axB.fill_between(TS, cm - ce, cm + ce, color=color, alpha=0.12)
    fx, fxe = finals.mean(), 1.96 * finals.std(ddof=1) / np.sqrt(len(finals))
    fy = cum[:, -1].mean(); fye = 1.96 * cum[:, -1].std(ddof=1) / np.sqrt(n)
    axC.errorbar(fx, fy, xerr=fxe, yerr=fye, fmt="o", color=color, ms=10, capsize=4, lw=1.5)
    axC.annotate(label, (fx, fy), textcoords="offset points", xytext=(8, 6), fontsize=9, color=color)

for ax in (axA, axB):
    ax.axvline(MIG, color="r", alpha=0.35, lw=1.2)
axA.text(MIG, axA.get_ylim()[1] * 0.02, " migration", color="r", fontsize=8)
axA.set_xlabel("instance index"); axA.set_ylabel("cumulative reward (mean ± 95%CI)")
axA.set_title("A. Reward: monotonic build-up b1→b4 (each rung adds)")
axA.legend(fontsize=8, loc="upper left"); axA.grid(alpha=0.3)

axB.set_xlabel("instance index"); axB.set_ylabel("skill.md characters (mean ± 95%CI)")
axB.set_title("B. Doc size over instances")
axB.legend(fontsize=8, loc="upper left"); axB.grid(alpha=0.3)

axC.set_xlabel("final skill.md size (chars)")
axC.set_ylabel("total reward @40 (mean ± 95%CI)")
axC.set_title("C. Final size vs total reward")
axC.grid(alpha=0.3)

fig.suptitle("batch build-up ladder (database_exploration, 16 seeds): "
             "b1=naive(oc) → +gate → +ground → +canary=full", fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.96))
out = f"{ROOT}/build_up_report.png"
fig.savefig(out, dpi=130)
print("wrote", out)
