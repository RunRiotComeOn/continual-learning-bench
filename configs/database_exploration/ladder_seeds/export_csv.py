"""Export per-system reward (and skill.md size) matrices to CSV.

One CSV per system under data/:
  data/reward_<key>.csv  -> header seed,inst_0..inst_39  (16 rows)
  data/size_<key>.csv    -> header seed,t1,t5,...,t40,final  (only systems with a
                            single skill.md; SkillClaw=RAG library, ICL=no doc)

The plotting scripts (report_pdfs.py, bars_postmig.py) read these via csv_io.py,
so figures no longer depend on the raw gzip artifacts.
"""
from __future__ import annotations

import csv
import glob
import gzip
import json
import os

import numpy as np

ART = "results/database_exploration/viewer_artifact_{g}*.json.gz"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TS = [1, 5, 10, 15, 20, 25, 30, 35, 40]

# key -> (group id, has_single_skill_doc)
SYSTEMS = {
    "b1_naive_oc":   ("2026-06-13T07-34-45.198535Z", True),
    "b2_gate":       ("2026-06-12T19-41-18.351524Z", True),
    "b3_ground":     ("2026-06-12T21-24-44.065798Z", True),
    "b4_full":       ("2026-06-12T14-13-52.388463Z", True),
    "skillopt_gate": ("2026-06-14T11-25-29.116793Z", True),
    "skillclaw":     ("2026-06-15T03-12-19.121887Z", False),
    "trace2skill":   ("2026-06-15T05-04-46.612043Z", True),
    "icl":           ("2026-06-14T13-43-01.615328Z", False),
}


def load(g):
    return json.load(gzip.open(sorted(glob.glob(ART.format(g=g)))[0]))


def rewards(tr):
    o = tr.get("instance_outcomes") or tr["result"]["instance_outcomes"]
    o = sorted(o, key=lambda x: x["instance_index"])
    return [float(x["reward"]) for x in o]


def size_rows(d):
    rows = []
    for w in d["run_traces"]:
        size = {}
        for x in w["trace"]["interactions"]:
            q = x.get("query") or {}
            rm = (x.get("response") or {}).get("metadata") or {}
            ii, sl = q.get("instance_index"), rm.get("skill_md_length")
            if ii is not None and sl is not None:
                size[ii] = sl
        fin = max(size.values()) if size else float("nan")
        rows.append([size.get(t, float("nan")) for t in TS] + [fin])
    return rows


def main():
    os.makedirs(DATA, exist_ok=True)
    for key, (g, has_size) in SYSTEMS.items():
        d = load(g)
        R = np.array([rewards(rt["trace"]) for rt in d["run_traces"]])
        rp = os.path.join(DATA, f"reward_{key}.csv")
        with open(rp, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["seed"] + [f"inst_{i}" for i in range(R.shape[1])])
            for s in range(R.shape[0]):
                w.writerow([s] + [f"{v:.6f}" for v in R[s]])
        msg = f"{key:14} reward {R.shape}  post-mig={R[:,20:].mean():.4f}"
        if has_size:
            S = size_rows(d)
            sp = os.path.join(DATA, f"size_{key}.csv")
            with open(sp, "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["seed"] + [f"t{t}" for t in TS] + ["final"])
                for s, row in enumerate(S):
                    w.writerow([s] + [("" if v != v else f"{v:.0f}") for v in row])
            msg += f"  | size rows={len(S)}"
        print("wrote", rp, "|", msg)


if __name__ == "__main__":
    main()
