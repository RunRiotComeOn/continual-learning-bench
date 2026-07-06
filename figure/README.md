# db / cohort reward curves

Self-contained figure package (portable — no dependency on the results/ run dirs).

```
figure/
  data/
    db_reward_per_instance.csv       # 40 instances
    cohort_reward_per_instance.csv   # 20 instances
  plot_curves.py                     # reads the CSVs → cumulative-mean-reward curves
  db_reward_curves.{pdf,png}
  cohort_reward_curves.{pdf,png}
```

**CSV columns** (each = per-instance reward, already averaged over 2 seeds):
`instance, gpt5_icl, gpt5_tt, mm_icl, mm_tt, k26_icl, k26_tt`
- `gpt5_*`, `mm_*` = the 4 MEASURED configs (gpt-5-mini / MiniMax-M3, ICL / tri-track).
- `k26_icl`, `k26_tt` = k2.6 **PROXIES**, precomputed as the per-instance average of
  gpt-5-mini and MiniMax. They are NOT measured k2.6 runs.

**Plot:** curves = running cumulative mean reward (endpoint == the run's mean score).
Edit the CONFIG/SERIES block at the top of `plot_curves.py` to restyle
(`SMOOTH_WINDOW=0` = no smoothing, colors, linestyles, figsize). Run:

```
python3 plot_curves.py
```
