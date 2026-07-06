"""Average cumulative reward vs instance index, per rung (mean +/- 95% CI across
seeds). Cumulative = running sum of per-instance reward; the slope is the local
reward rate, the gap at t=40 is total reward earned over the run.
"""
from __future__ import annotations

import glob
import gzip
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

GROUPS = {
    "L0 stateless":   ("2026-06-10T03-38-50.490073Z", "grey"),
    "R0 naive":       ("2026-06-11T03-48-25.465582Z", "tab:orange"),
    "R6 full":        ("2026-06-10T04-56-37.695111Z", "tab:blue"),
    "R2 passthru":    ("2026-06-10T17-09-09.713157Z", "tab:red"),
    "R6 full+ground": ("2026-06-11T04-54-14.060887Z", "tab:cyan"),
    "R6 ground concise": ("2026-06-11T10-22-07.607694Z", "limegreen"),
}
ART = "results/database_exploration/viewer_artifact_{g}_*.json.gz"
MIG = 20


def rewards(trace):
    outs = trace.get("instance_outcomes") or trace["result"]["instance_outcomes"]
    outs = sorted(outs, key=lambda o: o["instance_index"])
    return np.array([float(o["reward"]) for o in outs])


def load(g):
    d = json.load(gzip.open(sorted(glob.glob(ART.format(g=g)))[0]))
    return np.stack([rewards(rt["trace"]) for rt in d["run_traces"]])


fig, ax = plt.subplots(figsize=(9, 6))
x = np.arange(1, 41)
print(f"  {'rung':16s} {'n':>3s}  {'total reward (cum@40)':>24s}")
for name, (g, color) in GROUPS.items():
    runs = load(g)                      # (n, 40)
    cum = np.cumsum(runs, axis=1)       # (n, 40)
    m = cum.mean(axis=0)
    se = 1.96 * cum.std(axis=0, ddof=1) / np.sqrt(len(runs))
    ls = "--" if name == "L0 stateless" else "-"
    ax.plot(x, m, ls, color=color, lw=2, label=f"{name} (n={len(runs)})")
    ax.fill_between(x, m - se, m + se, color=color, alpha=0.15)
    print(f"  {name:16s} {len(runs):>3d}  {m[-1]:>14.3f} +/- {se[-1]:.3f}")

ax.axvline(MIG, color="r", alpha=0.4, lw=1.2)
ax.text(MIG, ax.get_ylim()[1] * 0.02, " migration", color="r", fontsize=8)
ax.set_xlabel("instance index")
ax.set_ylabel("cumulative reward (mean +/- 95%CI)")
ax.set_title("Average cumulative reward — database_exploration schema-drift")
ax.legend(fontsize=9); ax.grid(alpha=0.3)
fig.tight_layout()
out = "results/ladder_seeds/database_exploration/cumreward.png"
fig.savefig(out, dpi=130)
print("wrote", out)
