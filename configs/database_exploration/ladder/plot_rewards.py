"""Plot reward-vs-instance curves for the database_exploration ladder run.

Reads each rung's viewer artifact, extracts per-instance rewards (ordered by
instance_index), and plots:
  (1) cumulative running-mean reward per rung (the learning curve)
  (2) rolling-window (w=8) mean reward per rung

Usage: python configs/database_exploration/ladder/plot_rewards.py
"""
from __future__ import annotations

import glob
import gzip
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# rung -> run group timestamp (from each run's log)
RUNGS = {
    "L0 stateless": "2026-06-08T20-18-11.255486Z",
    "R0 naive": "2026-06-08T21-15-15.010553Z",
    "R1 +init": "2026-06-08T21-29-59.917526Z",
    "R2 +extract": "2026-06-08T21-46-33.506364Z",
    "R3 +canon": "2026-06-08T22-05-36.839297Z",
    "R4 +gate": "2026-06-08T22-25-26.068428Z",
    "R5 +canary": "2026-06-08T22-43-17.306867Z",
    "R6 full": "2026-06-08T20-18-11.322794Z",
}
ART = "results/database_exploration/viewer_artifact_{g}_*.json.gz"


def rewards_by_index(trace: dict) -> np.ndarray:
    outs = trace.get("instance_outcomes") or trace["result"]["instance_outcomes"]
    outs = sorted(outs, key=lambda o: o["instance_index"])
    return np.array([float(o["reward"]) for o in outs])


def load(group: str):
    path = sorted(glob.glob(ART.format(g=group)))[0]
    d = json.load(gzip.open(path))
    run = rewards_by_index(d["run_traces"][0]["trace"])
    base = rewards_by_index(d["baseline_trace"]) if d.get("baseline_trace") else None
    return run, base


def rolling(a: np.ndarray, w: int = 8) -> np.ndarray:
    out = np.full_like(a, np.nan, dtype=float)
    for i in range(len(a)):
        lo = max(0, i - w + 1)
        out[i] = a[lo : i + 1].mean()
    return out


cmap = plt.get_cmap("tab10")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

for i, (name, g) in enumerate(RUNGS.items()):
    run, base = load(g)
    x = np.arange(1, len(run) + 1)
    cum = np.cumsum(run) / x
    style = dict(color=cmap(i % 10), lw=2)
    if name == "R6 full":
        style.update(color="black", lw=3)
    if name == "L0 stateless":
        style.update(color="grey", lw=2, ls="--")
    ax1.plot(x, cum, label=name, **style)
    ax2.plot(x, rolling(run), label=name, **style)

for ax, title in (
    (ax1, "Cumulative running-mean reward"),
    (ax2, "Rolling-mean reward (window=8)"),
):
    ax.set_xlabel("instance index (presentation order)")
    ax.set_ylabel("reward")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=2)

fig.suptitle(
    "database_exploration ladder — reward over instances (runs=1, noisy)",
    fontsize=13,
)
fig.tight_layout()
out = "results/ladder/database_exploration/reward_curves.png"
fig.savefig(out, dpi=130)
print("wrote", out)
