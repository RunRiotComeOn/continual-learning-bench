"""skill.md size dynamics: how the document grows with instances, and its final
size, per rung. Reads the per-trial snapshots (skill_tNNNN_*.md) each run writes.

For each run we take, at every trial boundary t in {1,5,10,...,40}, the LAST
snapshot written at that t (by mtime) = the document state after processing
trial t. We report chars and lines, mean +/- 95% CI across the run's seeds, plus
the final-state distribution.
"""
from __future__ import annotations

import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = "results/ladder_seeds/database_exploration"
SYSTEMS = {
    "R0 naive":       ("r0_naive", "tab:orange"),
    "R6 full":        ("r6_full", "tab:blue"),
    "R2 passthru":    ("r2_passthru", "tab:red"),
    "R6 full+ground": ("r6_full_ground", "tab:cyan"),
    "R6 ground concise": ("r6_full_ground_concise", "limegreen"),
}
TS = [1, 5, 10, 15, 20, 25, 30, 35, 40]
SNAP = re.compile(r"skill_t(\d+)_")


def run_curve(run_dir):
    """Return {t: (chars, lines)} using the last-written snapshot at each t."""
    by_t = {}  # t -> (mtime, path)
    for p in glob.glob(os.path.join(run_dir, "skill_t*.md")):
        m = SNAP.search(os.path.basename(p))
        if not m:
            continue
        t = int(m.group(1))
        mt = os.path.getmtime(p)
        if t not in by_t or mt > by_t[t][0]:
            by_t[t] = (mt, p)
    out = {}
    for t, (_, p) in by_t.items():
        txt = open(p, encoding="utf-8").read()
        out[t] = (len(txt), txt.count("\n") + 1)
    return out


def collect(subdir):
    runs = sorted(glob.glob(os.path.join(ROOT, subdir, "run_*")))
    curves = [run_curve(r) for r in runs]
    return curves


def ci(a):
    a = np.asarray(a, float)
    if len(a) < 2:
        return a.mean() if len(a) else float("nan"), float("nan")
    return a.mean(), 1.96 * a.std(ddof=1) / np.sqrt(len(a))


fig, (ax_c, ax_l) = plt.subplots(1, 2, figsize=(14, 5.5))
print("=" * 78)
print("FINAL skill.md size (t=40), mean +/- 95% CI across seeds:")
print(f"  {'rung':16s} {'n':>3s}  {'chars':>16s}  {'lines':>14s}")

for name, (subdir, color) in SYSTEMS.items():
    curves = collect(subdir)
    n = len(curves)
    # chars/lines matrices: rows=runs, cols=TS (nan if missing)
    C = np.full((n, len(TS)), np.nan)
    L = np.full((n, len(TS)), np.nan)
    for i, cur in enumerate(curves):
        for j, t in enumerate(TS):
            if t in cur:
                C[i, j], L[i, j] = cur[t]
    cm = np.nanmean(C, axis=0)
    cse = 1.96 * np.nanstd(C, axis=0, ddof=1) / np.sqrt(np.sum(~np.isnan(C), axis=0))
    lm = np.nanmean(L, axis=0)
    ax_c.plot(TS, cm, "-o", color=color, label=f"{name} (n={n})", lw=2, ms=4)
    ax_c.fill_between(TS, cm - cse, cm + cse, color=color, alpha=0.15)
    ax_l.plot(TS, lm, "-o", color=color, label=f"{name} (n={n})", lw=2, ms=4)
    fc, fch = ci(C[:, -1])
    fl, flh = ci(L[:, -1])
    print(f"  {name:16s} {n:>3d}  {fc:>8.0f} +/- {fch:<5.0f}  {fl:>6.0f} +/- {flh:<5.0f}")

ax_c.axvline(20, color="r", alpha=0.4, lw=1.2)
ax_c.set_xlabel("instance (trial t)"); ax_c.set_ylabel("skill.md characters")
ax_c.set_title("skill.md size growth (chars, mean +/- 95%CI)")
ax_c.legend(fontsize=8); ax_c.grid(alpha=0.3)
ax_l.axvline(20, color="r", alpha=0.4, lw=1.2)
ax_l.set_xlabel("instance (trial t)"); ax_l.set_ylabel("skill.md lines")
ax_l.set_title("skill.md size growth (lines)")
ax_l.legend(fontsize=8); ax_l.grid(alpha=0.3)
fig.tight_layout()
out = os.path.join(ROOT, "skill_size.png")
fig.savefig(out, dpi=130)

# growth table: chars at each t (mean)
print("=" * 78)
print("CHARS by trial t (mean across seeds):")
print(f"  {'rung':16s} " + " ".join(f"{t:>6d}" for t in TS))
for name, (subdir, color) in SYSTEMS.items():
    curves = collect(subdir)
    n = len(curves)
    row = []
    for t in TS:
        vals = [c[t][0] for c in curves if t in c]
        row.append(np.mean(vals) if vals else np.nan)
    print(f"  {name:16s} " + " ".join(f"{v:>6.0f}" for v in row))
print("=" * 78)
print("wrote", out)
