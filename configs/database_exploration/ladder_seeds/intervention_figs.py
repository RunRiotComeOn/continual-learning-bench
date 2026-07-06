"""Main analysis figure (2x2) for the batch-summarize result on database_exploration.

Panel A — post-migration reward (mean ± 95%CI) for the doc-construction family
  (concise / preserve / naive / batch): batch-summarize significantly beats naive
  (Δ=+0.064, p=0.018); concise & preserve stay below.
Panel B — doc composition (schema facts vs interpretation rules per doc).
Panel C — final doc size vs post-mig reward: batch breaks the reward band the
  doc-content interventions were stuck in — the lever is candidate FORMATION, not
  doc size/content.
Panel D — build-up ablation ladder (naive -> b1 batch-form -> b2 +gate -> b3
  +ground -> b4 +canary=batch-full). Non-monotonic: the bare corroboration gate
  HURTS (-0.052, starves the doc), and +canary is the dominant significant jump
  (+0.067). The win is a batch-formation × canary synergy. See BATCH_LADDER.md.
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

ART = "results/database_exploration/viewer_artifact_{g}_*.json.gz"
MIG = 20
ROOT = "results/ladder_seeds/database_exploration"

# label -> (group id, results subdir, color)
# "naive(oc)" = outcome-only weak naive (reflect sees only question+outcome). The
# full reflect-over-traces naive scores +0.105 (group 2026-06-11T03-48-25); the
# build-up ladder (Panel D) still uses THAT reflect naive as its floor.
V = {
    "concise":   ("2026-06-11T10-22-07.607694Z", "r6_full_ground_concise",  "tab:green"),
    "preserve":  ("2026-06-12T11-51-10.354271Z", "r6_ground_preserve16",    "tab:olive"),
    "naive(oc)": ("2026-06-13T07-34-45.198535Z", "r0_naive_weak",           "tab:orange"),
    "batch":     ("2026-06-12T14-13-52.388463Z", "r7_batch_summarize16",    "tab:red"),
}
ORDER = ["concise", "preserve", "naive(oc)", "batch"]
NAIVE = "naive(oc)"  # which V-key is the floor for Panel A/B/C comparisons


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


TRIAL = re.compile(r"\bTrial\b", re.I)
VS_NUM = re.compile(r"\d[\d.,]*\s*vs\.?\s*\d")
NOT_X = re.compile(r"\bnot\b", re.I)
MEANS = re.compile(r"\b(means|interpret|refers to|should use|use .* when|when .* use)\b", re.I)


def composition(sub):
    interp, schema, chars = [], [], []
    for d in sorted(glob.glob(os.path.join(ROOT, sub, "run_*"))):
        f = os.path.join(d, "skill.md")
        if not os.path.exists(f):
            continue
        i = s = 0
        for ln in open(f, encoding="utf-8"):
            t = ln.strip()
            if not t[:1] in "-*123456789":
                continue
            if (TRIAL.search(t) or VS_NUM.search(t) or MEANS.search(t)
                    or (NOT_X.search(t) and "does not exist" not in t.lower())):
                i += 1
            else:
                s += 1
        interp.append(i); schema.append(s)
        chars.append(len(open(f, encoding="utf-8").read()))
    return np.array(interp, float), np.array(schema, float), np.array(chars, float)


R = {k: load(g) for k, (g, _, _) in V.items()}

# build-up ablation ladder (Panel D): naive -> batch-full, one mechanism per rung.
from scipy import stats  # noqa: E402
LADDER = [
    ("naive(oc)",  "2026-06-13T07-34-45.198535Z", "tab:orange"),
    ("b1 raw",     "2026-06-14T08-32-05.930092Z", "tab:olive"),
    ("b2 +gate",   "2026-06-12T19-41-18.351524Z", "tab:brown"),
    ("b3 +ground", "2026-06-12T21-24-44.065798Z", "tab:green"),
    ("b4 +canary", "2026-06-12T14-13-52.388463Z", "tab:red"),
]
RL = {lbl: load(g) for lbl, g, _ in LADDER}

fig, ((axA, axB), (axC, axD)) = plt.subplots(2, 2, figsize=(15, 10))

# ── Panel A: post-mig reward bars + paired Δ vs naive ──
# Each variant is paired against naive on ALL seeds the two share (not a fixed 8),
# so a 16-seed variant uses all 16. "n.s." = paired Δ 95%CI still spans 0 at this
# n — it means the difference is unresolved, NOT that the two are equal.
xs = np.arange(len(ORDER))
for i, name in enumerate(ORDER):
    r = R[name]
    m, h = ci(r[:, MIG:].mean(1))
    axA.bar(i, m, 0.62, yerr=h, color=V[name][2], capsize=4, alpha=0.9)
    lbl = f"n={len(r)}"
    if name != NAIVE:
        nn = min(len(r), len(R[NAIVE]))
        d = r[:nn, MIG:].mean(1) - R[NAIVE][:nn, MIG:].mean(1)
        dm, dh = ci(d)
        wins = int((d > 0).sum())
        sig = "p<.05" if abs(dm) > dh else "n.s."
        lbl = f"Δ={dm:+.3f} ({sig})\nbeats {wins}/{nn}"
    axA.text(i, m + h + 0.004, lbl, ha="center", va="bottom", fontsize=7.5)
axA.axhline(ci(R[NAIVE][:, MIG:].mean(1))[0], color="tab:orange", ls="--", alpha=0.5)
axA.set_xticks(xs); axA.set_xticklabels(ORDER, rotation=15, fontsize=9)
axA.set_ylabel("post-migration reward (mean ± 95%CI)")
axA.set_title("A. vs outcome-only naive floor (+0.033): batch +0.136 (16/16).\n"
              "vs full reflect naive (+0.105): batch +0.064 (p=.018) — see note")
axA.grid(alpha=0.3, axis="y")

# ── Panel B: doc composition (interp vs schema), stacked ──
comp_order = ["concise", NAIVE, "batch"]
xb = np.arange(len(comp_order))
interp_m, schema_m = [], []
for name in comp_order:
    i, s, _ = composition(V[name][1])
    interp_m.append(i.mean()); schema_m.append(s.mean())
axB.bar(xb, schema_m, 0.55, label="schema facts", color="silver")
axB.bar(xb, interp_m, 0.55, bottom=schema_m, label="interpretation rules", color="indianred")
for i, name in enumerate(comp_order):
    axB.text(i, schema_m[i] / 2, f"{schema_m[i]:.0f}", ha="center", va="center", fontsize=9)
    axB.text(i, schema_m[i] + interp_m[i] / 2, f"{interp_m[i]:.0f}", ha="center",
             va="center", fontsize=9, color="white")
axB.set_xticks(xb); axB.set_xticklabels(comp_order, fontsize=9)
axB.set_ylabel("entries per doc (mean)")
axB.set_title("B. Document composition\n(schema facts vs interpretation rules)")
axB.legend(fontsize=8); axB.grid(alpha=0.3, axis="y")

# ── Panel C: doc size vs post-mig reward ──
for name in ORDER:
    _, _, chars = composition(V[name][1])
    r = R[name]
    fx, fxe = chars.mean(), 1.96 * chars.std(ddof=1) / np.sqrt(len(chars))
    fy, fye = ci(r[:, MIG:].mean(1))
    axC.errorbar(fx, fy, xerr=fxe, yerr=fye, fmt="o", color=V[name][2], ms=11,
                 capsize=4, lw=1.5)
    axC.annotate(name, (fx, fy), textcoords="offset points", xytext=(8, 6),
                 fontsize=9, color=V[name][2])
axC.set_xlabel("final skill.md size (chars)")
axC.set_ylabel("post-mig reward (mean ± 95%CI)")
axC.set_title("C. batch breaks the reward band —\nthe lever is how candidates are formed, not doc size")
axC.grid(alpha=0.3)

# ── Panel D: build-up ablation ladder (naive -> batch-full) ──
lpost = {lbl: RL[lbl][:, MIG:].mean(1) for lbl, _, _ in LADDER}
lo = [lbl for lbl, _, _ in LADDER]
lmeans, lerrs = [], []
for i, lbl in enumerate(lo):
    m, h = ci(lpost[lbl]); lmeans.append(m); lerrs.append(h)
    axD.bar(i, m, 0.6, yerr=h, color=dict((x[0], x[2]) for x in LADDER)[lbl],
            capsize=4, alpha=0.9)
    axD.text(i, m + h + 0.004, f"{m:+.3f}", ha="center", va="bottom", fontsize=8.5,
             fontweight="bold")
axD.axhline(lmeans[0], color="tab:orange", ls="--", alpha=0.5)
lytop = max(m + e for m, e in zip(lmeans, lerrs)) + 0.03
for i in range(1, len(lo)):
    d = lpost[lo[i]] - lpost[lo[i - 1]]
    dm, dh = ci(d); _, p = stats.ttest_rel(lpost[lo[i]], lpost[lo[i - 1]])
    sig = "p<.05" if p < 0.05 else "n.s."
    col = "green" if dm > 0 else "red"
    y = lytop + 0.012 * (i % 2)
    axD.annotate("", xy=(i, y), xytext=(i - 1, y),
                 arrowprops=dict(arrowstyle="->", color=col, lw=1.4))
    axD.text(i - 0.5, y + 0.003, f"{dm:+.3f}\n({sig})", ha="center", va="bottom",
             fontsize=7.5, color=col)
axD.set_xticks(np.arange(len(lo))); axD.set_xticklabels(lo, rotation=12, fontsize=8.5)
axD.set_ylabel("post-mig reward (mean ± 95%CI, n=16)")
axD.set_ylim(0, lytop + 0.05)
axD.set_title("D. build-up ablation: non-monotonic —\ngate alone hurts; +canary is the dominant jump")
axD.grid(alpha=0.3, axis="y")

fig.suptitle("batch-summarize beats naive on database_exploration (16 seeds): the win is a "
             "batch-formation × canary synergy, not doc content", fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.96))
out = os.path.join(ROOT, "interventions.png")
fig.savefig(out, dpi=130)
print("wrote", out)
