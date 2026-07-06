"""Shared CSV loader for the database_exploration figures.

Data lives in data/reward_<key>.csv and data/size_<key>.csv (see export_csv.py).
Figures import from here so they no longer touch the raw gzip artifacts.
"""
from __future__ import annotations

import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TS = [1, 5, 10, 15, 20, 25, 30, 35, 40]
MIG = 20


def load_reward(key):
    """-> np.array [n_seeds x 40] of per-instance reward."""
    p = os.path.join(DATA, f"reward_{key}.csv")
    return np.genfromtxt(p, delimiter=",", skip_header=1)[:, 1:]


def load_size(key):
    """-> (rows[n x len(TS)], finals[n]) or (None, None) if no size CSV (e.g. ICL,
    SkillClaw). rows[:, k] = skill.md chars at instance TS[k]; finals = last col."""
    p = os.path.join(DATA, f"size_{key}.csv")
    if not os.path.exists(p):
        return None, None
    a = np.genfromtxt(p, delimiter=",", skip_header=1)[:, 1:]  # t1..t40, final
    return a[:, :-1], a[:, -1]


def postmig(R):
    return R[:, MIG:].mean(axis=1)
