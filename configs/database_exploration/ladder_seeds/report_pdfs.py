"""Report figures as PDF (vector) for database_exploration, 16 seeds.

Data is read from data/*.csv (see export_csv.py) via csv_io.py — no gzip artifacts.

Produces four 3-panel figures (each PNG + PDF):
  build_up_report           — ladder b1..b4, full-run reward
  build_up_report_postmig   — ladder b1..b4, POST-migration reward (cumsum reset @20)
  competitor_report         — b4(ours) vs SkillOpt-gate vs SkillClaw vs Trace2Skill, full-run
  competitor_report_postmig — same four, POST-migration reward

Panels: A reward (cumulative), B skill.md size over instances, C final size vs reward.
SkillClaw keeps a RAG skill *library* (no single-doc char count) -> reward panel only.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from csv_io import TS, MIG, load_reward, load_size

ROOT = "results/ladder_seeds/database_exploration"

# label -> (csv key, color)
LADDER = [
    ("b1 = naive(oc)", "b1_naive_oc", "tab:orange"),
    ("b2 +gate",       "b2_gate",     "tab:brown"),
    ("b3 +ground",     "b3_ground",   "tab:green"),
    ("b4 = full",      "b4_full",     "tab:red"),
]
COMPETITORS = [
    ("b4 = full (ours)", "b4_full",       "tab:red"),
    ("SkillOpt-gate",    "skillopt_gate", "tab:purple"),
    ("SkillClaw",        "skillclaw",     "tab:blue"),
    ("Trace2Skill",      "trace2skill",   "tab:cyan"),
]


def band(M):
    m = np.nanmean(M, axis=0)
    n = np.sum(~np.isnan(M), axis=0)
    sd = np.nanstd(M, axis=0, ddof=1)
    return m, 1.96 * sd / np.sqrt(np.maximum(n, 1))


def make_fig(rungs, suptitle, outstem, postmig):
    fig, (axA, axB, axC) = plt.subplots(1, 3, figsize=(17, 5.2))
    lo = MIG if postmig else 0
    x = np.arange(lo + 1, 41)
    for label, key, color in rungs:
        r = load_reward(key); n = len(r)
        cum = np.cumsum(r[:, lo:], axis=1)
        m = cum.mean(0); se = 1.96 * cum.std(0, ddof=1) / np.sqrt(n)
        axA.plot(x, m, color=color, lw=2.2, label=f"{label} (n={n})")
        axA.fill_between(x, m - se, m + se, color=color, alpha=0.12)

        M, finals = load_size(key)
        if M is None:
            continue
        # B-curve at TS=[1,5,..,40]; the x=40 point uses the final/max doc size
        sizes = np.column_stack([M[:, :-1], finals])  # replace t40 col with final
        cm, ce = band(sizes)
        axB.plot(TS, cm, "-o", color=color, lw=2.2, ms=4, label=f"{label} (n={n})")
        axB.fill_between(TS, cm - ce, cm + ce, color=color, alpha=0.12)
        ry = cum[:, -1]
        fx = np.nanmean(finals); fxe = 1.96 * np.nanstd(finals, ddof=1) / np.sqrt(n)
        fy = ry.mean(); fye = 1.96 * ry.std(ddof=1) / np.sqrt(n)
        axC.errorbar(fx, fy, xerr=fxe, yerr=fye, fmt="o", color=color, ms=10, capsize=4, lw=1.5)
        axC.annotate(label, (fx, fy), textcoords="offset points", xytext=(8, 6), fontsize=9, color=color)

    if not postmig:
        for ax in (axA, axB):
            ax.axvline(MIG, color="r", alpha=0.35, lw=1.2)
        axA.text(MIG, axA.get_ylim()[1] * 0.02, " migration", color="r", fontsize=8)
    period = "post-migration " if postmig else ""
    axA.set_xlabel("instance index")
    axA.set_ylabel(f"{period}cumulative reward (mean ± 95%CI)")
    axA.set_title(f"A. {'Post-migration reward' if postmig else 'Reward'} (cumulative)")
    axA.legend(fontsize=8, loc="upper left"); axA.grid(alpha=0.3)

    axB.set_xlabel("instance index")
    axB.set_ylabel("skill.md characters (mean ± 95%CI)")
    axB.set_title("B. Doc size over instances")
    axB.legend(fontsize=8, loc="upper left"); axB.grid(alpha=0.3)

    axC.set_xlabel("final skill.md size (chars)")
    axC.set_ylabel(f"{period}total reward (mean ± 95%CI)")
    axC.set_title(f"C. Final size vs {period}reward")
    axC.grid(alpha=0.3)

    fig.suptitle(suptitle, fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    for ext in ("png", "pdf"):
        p = f"{ROOT}/{outstem}.{ext}"
        fig.savefig(p, dpi=130)
        print("wrote", p)
    plt.close(fig)


LAD_T = "batch build-up ladder (database_exploration, 16 seeds): b1=naive(oc) → +gate → +ground → +canary=full"
CMP_T = "ours (b4=full) vs competitors (database_exploration, 16 seeds): SkillOpt-gate, SkillClaw, Trace2Skill"

make_fig(LADDER, LAD_T, "build_up_report", postmig=False)
make_fig(LADDER, LAD_T + "  —  POST-MIGRATION", "build_up_report_postmig", postmig=True)
make_fig(COMPETITORS, CMP_T, "competitor_report", postmig=False)
make_fig(COMPETITORS, CMP_T + "  —  POST-MIGRATION", "competitor_report_postmig", postmig=True)
