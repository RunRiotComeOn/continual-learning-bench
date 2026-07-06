"""Migration-split analysis of the db schema-drift retention test (4 rungs x 8 seeds).

Default schedule = Schema Drift: instances 0-19 pre-migration, 20-39 post-migration
(old-schema facts go stale after the migration). run_mode=permute keeps the
migration boundary fixed and pairs run_index i across rungs. We test whether a
system that FORGETS stale facts (full+decay) adapts better post-migration than a
hoarder (naive).

Reports, per rung, mean +/- 95% CI over 8 seeds for:
  - baseline (order-independent -> sanity that rungs share the same control)
  - whole-run reward
  - PRE (0-19) and POST (20-39) reward
  - POST - PRE within-rung drop (the migration hit)
plus paired Delta(rung - r0_naive) on the POST segment (positive = beats naive
after the schema changes; ** = 95% CI clears 0).
"""
from __future__ import annotations

import glob
import gzip
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# completion-ordered artifact groups -> rung
GROUPS = {
    "L0 stateless":   "2026-06-10T03-38-50.490073Z",
    "R0 naive":       "2026-06-11T03-48-25.465582Z",  # 16 seeds (variance-reduction pass)
    "R6 full":        "2026-06-10T04-56-37.695111Z",
    "R6 full+decay":  "2026-06-10T05-58-05.985466Z",
    "R6 full thr2":   "2026-06-10T12-43-34.743936Z",
    "R2 passthru":    "2026-06-10T17-09-09.713157Z",
    "R3 canon thr5":  "2026-06-10T17-56-19.185766Z",
    "R6 full+ground": "2026-06-11T04-54-14.060887Z",  # 16 seeds (variance-reduction pass)
    "R6 ground concise": "2026-06-11T10-22-07.607694Z",  # 16 seeds, terse-prompt refine
}
ART = "results/database_exploration/viewer_artifact_{g}_*.json.gz"
MIG = 20  # migration boundary: [0,20) pre, [20,40) post


def rewards(trace):
    outs = trace.get("instance_outcomes") or trace["result"]["instance_outcomes"]
    outs = sorted(outs, key=lambda o: o["instance_index"])
    return np.array([float(o["reward"]) for o in outs])


def load(g):
    d = json.load(gzip.open(sorted(glob.glob(ART.format(g=g)))[0]))
    runs = np.stack([rewards(rt["trace"]) for rt in d["run_traces"]])  # (8,40)
    base = rewards(d["baseline_trace"]) if d.get("baseline_trace") else None
    return runs, base


data = {n: load(g) for n, g in GROUPS.items()}


def ci(a):
    a = np.asarray(a, float)
    return a.mean(), 1.96 * a.std(ddof=1) / np.sqrt(len(a))


def line(label, a):
    m, h = ci(a)
    return f"  {label:16s} {m:+.4f} +/- {h:.4f}"


print("=" * 72)
print("BASELINE mean reward per rung (single baseline trace -> should be ~equal):")
for n, (runs, b) in data.items():
    print(f"  {n:16s} {b.mean():+.4f}" if b is not None else f"  {n}: none")

print("=" * 72)
print("WHOLE-RUN mean reward: mean +/- 95%CI over 8 seeds")
for n, (runs, b) in data.items():
    print(line(n, runs.mean(axis=1)))

print("=" * 72)
print("PRE-migration (idx 0-19) mean reward:")
for n, (runs, b) in data.items():
    print(line(n, runs[:, :MIG].mean(axis=1)))

print("=" * 72)
print("POST-migration (idx 20-39) mean reward  <- the decisive segment:")
for n, (runs, b) in data.items():
    print(line(n, runs[:, MIG:].mean(axis=1)))

print("=" * 72)
print("MIGRATION DROP  POST - PRE  (more negative = hurt more by stale facts):")
for n, (runs, b) in data.items():
    print(line(n, runs[:, MIG:].mean(axis=1) - runs[:, :MIG].mean(axis=1)))

print("=" * 72)
print("PAIRED  Delta(rung - R0 naive)  on POST segment (per-seed, ** = CI clears 0)")
naive = data["R0 naive"][0]
for n, (runs, b) in data.items():
    if n == "R0 naive":
        continue
    # run_index i is the same ordering across rungs -> pair on the first min(n)
    # seeds (8-seed rungs vs naive[:8]; 16-seed ground vs naive[:16]).
    nn = min(len(runs), len(naive))
    d = runs[:nn, MIG:].mean(axis=1) - naive[:nn, MIG:].mean(axis=1)
    m, h = ci(d)
    star = "  **" if abs(m) > h else ""
    print(f"  {n:16s} {m:+.4f} +/- {h:.4f}{star}")

# ---- plot: per-instance mean reward (smoothed) + migration line ----
cmap = {"L0 stateless": "grey", "R0 naive": "tab:orange",
        "R6 full": "tab:blue", "R6 full+decay": "black",
        "R6 full thr2": "tab:green", "R2 passthru": "tab:red",
        "R3 canon thr5": "tab:purple", "R6 full+ground": "tab:cyan",
        "R6 ground concise": "limegreen"}
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
x = np.arange(40)
w = 5  # moving-average window
for n, (runs, b) in data.items():
    m = runs.mean(axis=0)
    ma = np.convolve(m, np.ones(w) / w, mode="same")
    lw = 3 if "decay" in n else 2
    ls = "--" if n == "L0 stateless" else "-"
    ax1.plot(x, ma, label=n, color=cmap[n], lw=lw, ls=ls)
ax1.axvline(MIG, color="r", alpha=0.5, lw=1.5)
ax1.text(MIG, ax1.get_ylim()[1] * 0.98, " migration", color="r", va="top", fontsize=8)
ax1.set_xlabel("instance index"); ax1.set_ylabel(f"mean reward ({w}-MA, 8 seeds)")
ax1.set_title("Schema-drift reward trajectory"); ax1.legend(fontsize=8); ax1.grid(alpha=0.3)

# bar: PRE vs POST per rung
labels = list(data); xpos = np.arange(len(labels)); bw = 0.35
pre = [data[n][0][:, :MIG].mean() for n in labels]
post = [data[n][0][:, MIG:].mean() for n in labels]
pre_e = [ci(data[n][0][:, :MIG].mean(axis=1))[1] for n in labels]
post_e = [ci(data[n][0][:, MIG:].mean(axis=1))[1] for n in labels]
ax2.bar(xpos - bw / 2, pre, bw, yerr=pre_e, label="pre (0-19)", color="silver", capsize=3)
ax2.bar(xpos + bw / 2, post, bw, yerr=post_e, label="post (20-39)", color="tab:red",
        alpha=0.8, capsize=3)
ax2.set_xticks(xpos); ax2.set_xticklabels(labels, rotation=15, fontsize=8)
ax2.set_ylabel("mean reward +/- 95%CI"); ax2.set_title("Pre vs post migration")
ax2.legend(fontsize=8); ax2.grid(alpha=0.3, axis="y")
fig.tight_layout()
out = "results/ladder_seeds/database_exploration/migration_split.png"
fig.savefig(out, dpi=130)
print("=" * 72)
print("wrote", out)
