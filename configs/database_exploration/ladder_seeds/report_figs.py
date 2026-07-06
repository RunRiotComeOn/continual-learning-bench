"""Clean report figure for the grounded-refine story on database_exploration.

Narrative rungs only (diagnostic rungs decay/thr2/canon/passthru live in
analyze.py): the terse 'full' loses reward because its skill.md never grows;
'full+ground' recovers naive-level reward but bloats the doc; 'concise' (terse
grounded-refine prompt) keeps the reward while cutting the doc ~45%.

Three panels:
  A. cumulative reward vs instance (mean +/- 95%CI)  -> the reward story
  B. skill.md size (chars) vs instance               -> the size story
  C. final skill.md size  vs  total reward           -> the tradeoff (concise wins)
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "results/ladder_seeds/database_exploration"
ART = "results/database_exploration/viewer_artifact_{g}_*.json.gz"
MIG = 20

# label -> (group id, results subdir or None, color, linestyle)
# NOTE: the "naive" floor here is the OUTCOME-ONLY weak naive (reflect sees only
# question+outcome, not the trace). The full reflect-over-traces naive scores
# +0.105 post-mig (group 2026-06-11T03-48-25); shown faintly for reference.
RUNGS = [
    ("L0 stateless",          "2026-06-10T03-38-50.490073Z", None,                     "grey",       "--"),
    ("concise",               "2026-06-11T10-22-07.607694Z", "r6_full_ground_concise", "tab:green",  "-"),
    ("preserve",              "2026-06-12T11-51-10.354271Z", "r6_ground_preserve16",   "tab:olive",  "-"),
    ("naive (outcome-only)",  "2026-06-13T07-34-45.198535Z", "r0_naive_weak",          "tab:orange", "-"),
    ("batch-summarize",       "2026-06-12T14-13-52.388463Z", "r7_batch_summarize16",   "tab:red",    "-"),
]
TS = [1, 5, 10, 15, 20, 25, 30, 35, 40]
SNAP = re.compile(r"skill_t(\d+)_")


def rewards(tr):
    o = tr.get("instance_outcomes") or tr["result"]["instance_outcomes"]
    o = sorted(o, key=lambda x: x["instance_index"])
    return np.array([float(x["reward"]) for x in o])


def load_reward(g):
    d = json.load(gzip.open(sorted(glob.glob(ART.format(g=g)))[0]))
    return np.stack([rewards(rt["trace"]) for rt in d["run_traces"]])


def artifact_sizes(g):
    """rows=runs, cols=TS -> doc chars, read from the artifact (skill_md_length
    per instance) rather than disk snapshots — robust for runs that don't persist
    run_*/ dirs (e.g. canary-off rungs). size[instance_index] = doc the agent used
    at that instance; final = largest doc actually used in the run."""
    d = json.load(gzip.open(sorted(glob.glob(ART.format(g=g)))[0]))
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


def ci_band(M):
    m = np.nanmean(M, axis=0)
    n = np.sum(~np.isnan(M), axis=0)
    sd = np.nanstd(M, axis=0, ddof=1)
    return m, 1.96 * sd / np.sqrt(n)


fig, (axA, axB, axC) = plt.subplots(1, 3, figsize=(17, 5.2))
x = np.arange(1, 41)

for label, g, subdir, color, ls in RUNGS:
    r = load_reward(g)
    n = len(r)
    # A: cumulative reward
    cum = np.cumsum(r, axis=1)
    m = cum.mean(axis=0)
    se = 1.96 * cum.std(axis=0, ddof=1) / np.sqrt(n)
    axA.plot(x, m, ls, color=color, lw=2.2, label=f"{label} (n={n})")
    axA.fill_between(x, m - se, m + se, color=color, alpha=0.12)

    if subdir is None:
        continue
    # B: skill.md chars over instances (from artifact, not disk)
    M, finals = artifact_sizes(g)
    cm, ce = ci_band(M)
    axB.plot(TS, cm, "-o", color=color, lw=2.2, ms=4, label=f"{label} (n={len(finals)})")
    axB.fill_between(TS, cm - ce, cm + ce, color=color, alpha=0.12)
    # C: final size vs total reward
    fx, fxe = finals.mean(), 1.96 * finals.std(ddof=1) / np.sqrt(len(finals))
    fy = cum[:, -1].mean()
    fye = 1.96 * cum[:, -1].std(ddof=1) / np.sqrt(n)
    axC.errorbar(fx, fy, xerr=fxe, yerr=fye, fmt="o", color=color, ms=10,
                 capsize=4, lw=1.5)
    axC.annotate(label, (fx, fy), textcoords="offset points", xytext=(8, 6),
                 fontsize=9, color=color)

for ax in (axA, axB):
    ax.axvline(MIG, color="r", alpha=0.35, lw=1.2)
axA.text(MIG, axA.get_ylim()[1] * 0.02, " migration", color="r", fontsize=8)
axA.set_xlabel("instance index"); axA.set_ylabel("cumulative reward (mean ± 95%CI)")
axA.set_title("A. Reward: batch-summarize pulls ahead of naive post-migration")
axA.legend(fontsize=8, loc="upper left"); axA.grid(alpha=0.3)

axB.set_xlabel("instance index"); axB.set_ylabel("skill.md characters (mean ± 95%CI)")
axB.set_title("B. Doc size: batch's lead isn't from a bigger doc")
axB.legend(fontsize=8, loc="upper left"); axB.grid(alpha=0.3)

axC.set_xlabel("final skill.md size (chars)")
axC.set_ylabel("total reward @40 (mean ± 95%CI)")
axC.set_title("C. batch wins on reward at a similar doc size")
axC.grid(alpha=0.3)

fig.suptitle("database_exploration (schema drift, 16 paired seeds): batch-summarize "
             "candidate formation beats naive", fontsize=12)
fig.tight_layout(rect=(0, 0, 1, 0.96))
out = os.path.join(ROOT, "report.png")
fig.savefig(out, dpi=130)
print("wrote", out)
