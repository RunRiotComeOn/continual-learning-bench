"""Analyze the deterministic (temp=0, replicate) ladder run.

- baseline-identity check: with temp=0 + order-independent baseline, every rung's
  baseline reward vector should be byte-identical -> proves the sampling noise is
  gone.
- per-rung stateful score, gain over the shared baseline.
- paired Delta(full - rung): per-instance reward diff on the identical ordering.
"""
from __future__ import annotations

import glob
import gzip
import json

import numpy as np

GROUPS = {
    "L0 stateless": "2026-06-09T08-00-59.680876Z",
    "R0 naive": "2026-06-09T09-25-46.630172Z",
    "R1 +init": "2026-06-09T08-15-00.430302Z",
    "R2 +extract": "2026-06-09T08-15-00.430401Z",
    "R3 +canon": "2026-06-09T08-35-55.574832Z",
    "R4 +gate": "2026-06-09T08-35-55.611037Z",
    "R5 +canary": "2026-06-09T09-00-38.926749Z",
    "R6 full": "2026-06-09T09-00-38.926982Z",
}
ART = "results/database_exploration/viewer_artifact_{g}_*.json.gz"


def rewards(trace):
    outs = trace.get("instance_outcomes") or trace["result"]["instance_outcomes"]
    outs = sorted(outs, key=lambda o: o["instance_index"])
    return np.array([float(o["reward"]) for o in outs])


def load(g):
    d = json.load(gzip.open(sorted(glob.glob(ART.format(g=g)))[0]))
    base = rewards(d["baseline_trace"]) if d.get("baseline_trace") else None
    run = rewards(d["run_traces"][0]["trace"])
    return run, base


data = {name: load(g) for name, g in GROUPS.items()}

# ---- baseline-identity check ----
print("=" * 64)
print("BASELINE-IDENTITY CHECK (should be identical across rungs)")
bases = {n: b for n, (r, b) in data.items() if b is not None}
ref_name, ref = next(iter(bases.items()))
print(f"  reference: {ref_name}  baseline mean={ref.mean():.4f}")
for n, b in bases.items():
    same = b.shape == ref.shape and np.allclose(b, ref)
    print(f"  {n:14s} mean={b.mean():.4f}  identical_to_ref={same}")

# ---- per-rung score + gain over shared baseline ----
print("=" * 64)
print(f"{'rung':14s} {'score':>8} {'gain_vs_base':>13}")
base_mean = ref.mean()
for n, (run, b) in data.items():
    print(f"{n:14s} {run.mean():8.4f} {run.mean()-base_mean:13.4f}")

# ---- paired Delta(full - rung), same ordering ----
print("=" * 64)
print("PAIRED  Delta(R6 full - rung)  per-instance, identical ordering")
full = data["R6 full"][0]
for n, (run, b) in data.items():
    if n == "R6 full":
        continue
    d = full - run
    wins = int((d > 0).sum())
    losses = int((d < 0).sum())
    print(
        f"  full - {n:13s} mean_delta={d.mean():+.4f}  "
        f"full_better={wins:2d}  worse={losses:2d}  ties={len(d)-wins-losses:2d}"
    )
