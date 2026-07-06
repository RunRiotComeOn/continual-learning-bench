"""Post-migration reward BAR charts (PNG+PDF), database_exploration, 16 paired seeds.

Data from data/reward_*.csv (see export_csv.py) via csv_io.py — no gzip artifacts.

Two figures, batch_ladder.png style:
  batch_ladder    — build-up ladder b1=naive(oc)→+gate→+ground→+full; adjacent paired Δ.
  competitor_bar  — ours (b4=full) vs ICL, SkillOpt-gate, SkillClaw, Trace2Skill;
                    each system's paired Δ vs ours annotated.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

from csv_io import load_reward, postmig

ROOT = "results/ladder_seeds/database_exploration"

LADDER = [
    ("b1 = naive(oc)", "b1_naive_oc", "tab:orange"),
    ("b2 +gate",       "b2_gate",     "tab:brown"),
    ("b3 +ground",     "b3_ground",   "tab:green"),
    ("b4 = full",      "b4_full",     "tab:red"),
]
# competitors: ours first, then strong baseline ICL, then the three systems
COMPETITORS = [
    ("b4 = full (ours)", "b4_full",       "tab:red"),
    ("ICL",              "icl",           "tab:gray"),
    ("SkillOpt-gate",    "skillopt_gate", "tab:purple"),
    ("SkillClaw",        "skillclaw",     "tab:blue"),
    ("Trace2Skill",      "trace2skill",   "tab:cyan"),
]


def ci(a):
    a = np.asarray(a, float)
    return a.mean(), 1.96 * a.std(ddof=1) / np.sqrt(len(a))


def save(fig, stem):
    for ext in ("png", "pdf"):
        p = f"{ROOT}/{stem}.{ext}"
        fig.savefig(p, dpi=130)
        print("wrote", p)
    plt.close(fig)


def ladder_fig():
    order = [r[0] for r in LADDER]
    post = {lbl: postmig(load_reward(key)) for lbl, key, _ in LADDER}
    fig, ax = plt.subplots(figsize=(11, 6))
    means, errs = [], []
    for i, lbl in enumerate(order):
        m, h = ci(post[lbl]); means.append(m); errs.append(h)
        ax.bar(i, m, 0.6, yerr=h, color=LADDER[i][2], capsize=4, alpha=0.9)
        ax.text(i, m + h + 0.004, f"{m:+.3f}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.axhline(means[0], color="tab:orange", ls="--", alpha=0.5)
    ytop = max(m + e for m, e in zip(means, errs)) + 0.03
    for i in range(1, len(order)):
        d = post[order[i]] - post[order[i - 1]]
        dm, _ = ci(d); _, p = stats.ttest_rel(post[order[i]], post[order[i - 1]])
        sig = "p<.05" if p < 0.05 else "n.s."; col = "green" if dm > 0 else "red"
        y = ytop + 0.012 * (i % 2)
        ax.annotate("", xy=(i, y), xytext=(i - 1, y), arrowprops=dict(arrowstyle="->", color=col, lw=1.4))
        ax.text(i - 0.5, y + 0.003, f"Δ={dm:+.3f}\n({sig})", ha="center", va="bottom", fontsize=8, color=col)
    floor = order[0]; lines = []
    for lbl in order[1:]:
        d = post[lbl] - post[floor]; dm, _ = ci(d); _, p = stats.ttest_rel(post[lbl], post[floor])
        lines.append(f"{lbl} vs {floor}: {dm:+.3f} ({'p<.05' if p < 0.05 else 'n.s.'})")
    ax.text(0.015, 0.55, "\n".join(lines), transform=ax.transAxes, fontsize=7.5, va="top", ha="left",
            bbox=dict(boxstyle="round", fc="white", ec="grey", alpha=0.8))
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(order, rotation=12, fontsize=9)
    ax.set_ylabel("post-migration reward (mean ± 95%CI, n=16)")
    ax.set_ylim(0, ytop + 0.06)
    ax.set_title("Batch build-up ladder — post-migration reward (database_exploration, 16 paired seeds)\n"
                 "b1=naive(oc) → +gate → +ground → +canary=full (each rung adds a module)", fontsize=12)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    save(fig, "batch_ladder")


def competitor_fig():
    order = [r[0] for r in COMPETITORS]
    post = {lbl: postmig(load_reward(key)) for lbl, key, _ in COMPETITORS}
    ours = order[0]
    fig, ax = plt.subplots(figsize=(12, 6))
    means, errs = [], []
    for i, lbl in enumerate(order):
        m, h = ci(post[lbl]); means.append(m); errs.append(h)
        ax.bar(i, m, 0.6, yerr=h, color=COMPETITORS[i][2], capsize=4, alpha=0.9)
        ax.text(i, m + h + 0.004, f"{m:+.3f}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.axhline(means[0], color="tab:red", ls="--", alpha=0.5)
    for i in range(1, len(order)):
        d = post[ours] - post[order[i]]; dm, _ = ci(d)
        _, p = stats.ttest_rel(post[ours], post[order[i]])
        sig = "p<.05" if p < 0.05 else "n.s."
        ax.text(i, 0.006, f"ours−this\nΔ={dm:+.3f}\n({sig})", ha="center", va="bottom",
                fontsize=8, color="dimgray")
    lines = [f"{lbl} vs {ours}: {ci(post[lbl]-post[ours])[0]:+.3f} "
             f"({'p<.05' if stats.ttest_rel(post[lbl], post[ours])[1] < 0.05 else 'n.s.'})"
             for lbl in order[1:]]
    ax.text(0.985, 0.97, "\n".join(lines), transform=ax.transAxes, fontsize=7.5, va="top", ha="right",
            bbox=dict(boxstyle="round", fc="white", ec="grey", alpha=0.8))
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(order, rotation=12, fontsize=9)
    ax.set_ylabel("post-migration reward (mean ± 95%CI, n=16)")
    ax.set_ylim(0, max(m + e for m, e in zip(means, errs)) + 0.05)
    ax.set_title("Ours vs competitors — post-migration reward (database_exploration, 16 paired seeds)\n"
                 "ours (b4=full) ≈ ICL > SkillOpt-gate > SkillClaw ≈ Trace2Skill", fontsize=12)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    save(fig, "competitor_bar")


ladder_fig()
competitor_fig()
