#!/usr/bin/env python3
"""Plot db / cohort cumulative-mean-reward curves from the extracted CSVs.

Data: figure/data/<task>_reward_per_instance.csv — per-instance reward, already
averaged over 2 seeds. Columns:
  gpt5_icl, gpt5_tt, mm_icl, mm_tt  = the 4 MEASURED configs.
  k26_icl, k26_tt                   = k2.6 PROXIES, precomputed as the per-instance
                                      average of gpt-5-mini and MiniMax (NOT measured
                                      k2.6 runs).

Curves plotted = running cumulative mean reward (endpoint == the run's mean score).
Edit the CONFIG block to restyle. SMOOTH_WINDOW=0 -> no smoothing.
"""
import csv, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---- CONFIG (edit to restyle) ------------------------------------------------
SMOOTH_WINDOW = 0          # 0 = no smoothing; else centered moving-avg window (odd)
FIGSIZE = (9, 5.5)
# csv column -> (legend label, color, linestyle)
SERIES = {
    "gpt5_icl": ("gpt-5-mini ICL",       "#1f77b4", "-"),
    "gpt5_tt":  ("gpt-5-mini tt",        "#1f77b4", "--"),
    "mm_icl":   ("MiniMax-M3 ICL",       "#2ca02c", "-"),
    "mm_tt":    ("MiniMax-M3 tt",        "#2ca02c", "--"),
    "k26_icl":  ("k2.6 ICL (proxy avg)", "#d62728", "-"),
    "k26_tt":   ("k2.6 tt (proxy avg)",  "#d62728", "--"),
}
HERE = os.path.dirname(os.path.abspath(__file__))
# -----------------------------------------------------------------------------

def load_csv(path):
    rows = list(csv.DictReader(open(path)))
    cols = [c for c in rows[0] if c != "instance"]
    return {c: np.array([float(r[c]) for r in rows]) for c in cols}

def cummean(y):
    return np.cumsum(y) / np.arange(1, len(y) + 1)

def smooth(y, w):
    if not w or w < 2:
        return y
    n, h, out = len(y), w // 2, np.empty(len(y))
    for i in range(n):
        out[i] = y[max(0, i - h):min(n, i + h + 1)].mean()
    out[-1] = y[-1]
    return out

def plot_task(task, title):
    d = load_csv(os.path.join(HERE, "data", f"{task}_reward_per_instance.csv"))
    n = min(len(v) for v in d.values())
    x = np.arange(1, n + 1)
    plt.figure(figsize=FIGSIZE)
    plt.axhline(0, color="gray", lw=0.8, ls=":")
    for col, (lab, color, ls) in SERIES.items():
        curve = smooth(cummean(d[col][:n]), SMOOTH_WINDOW)
        plt.plot(x, curve, color=color, ls=ls, lw=2, label=f"{lab}  ({curve[-1]:+.3f})")
    plt.xlabel(f"instance index (1-{n})")
    plt.ylabel("cumulative mean reward")
    plt.title(title)
    plt.grid(alpha=0.3)
    plt.legend(fontsize=8.5, loc="best")
    plt.tight_layout()
    for ext in ("pdf", "png"):
        plt.savefig(os.path.join(HERE, f"{task}_reward_curves.{ext}"), dpi=140)
    plt.close()
    print(f"{task}: saved pdf+png")

if __name__ == "__main__":
    plot_task("db",     "db - cumulative mean reward (2-seed avg)\nsolid = ICL, dashed = tri-track")
    plot_task("cohort", "cohort - cumulative mean reward (2-seed avg)\nsolid = ICL, dashed = tri-track")
