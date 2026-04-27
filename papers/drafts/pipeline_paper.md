# Comparative Pipelines for IslandPilot Benchmarking

This document tracks the academic pipelines we are implementing as side-by-side
comparison baselines for **IslandPilot** (our regime-aware hierarchical
island-model GA pipeline). Each pipeline wraps the same grid-hedged Martingale
strategy on the same EUR-USD 30-minute data with the same OANDA CFD execution
model (2-pip spread) so results are directly comparable.

---

## Evaluation Protocol (applied to every pipeline)

| Item | Value |
|---|---|
| Instrument | EUR-USD |
| Timeframe | 30-minute |
| Training window | 2022-01-01 → 2023-12-31 |
| Out-of-sample H1 | 2024-01-01 → 2024-06-30 |
| Out-of-sample H2 | 2024-07-01 → 2024-12-31 |
| Out-of-sample Full | 2024-01-01 → 2024-12-31 |
| Strategy | `Martingale`, preset `original` |
| Exchange | OANDA CFD with 2-pip EUR-USD spread |
| Starting balance | $10,000 |
| Engine | Real `qengine.research.backtest.backtest()` (no simplified simulator) |
| Seeds | 3 random seeds per run; report mean ± std |
| Metrics | Profit Factor, Net %, Max DD %, Win Rate, Bust Rate, Sessions, Sharpe, Sortino |
| Statistical tests | Diebold-Mariano on per-session PnL; paired t-test on per-cycle bust rates |
| Output | `notebooks/phase5/5X_{pipeline}_ablation.{py,json,png}` |

Every pipeline is plugged in via the standard `Pipeline` base class at
`qengine/framework/base.py` and auto-discovered by the registry. The strategy
code is NEVER modified.

---

## Candidate Pipelines

### 1. DempsterJonesPilot — Walk-forward GA (classical baseline)

- **Paper:** Dempster, M. A. H., & Jones, C. M. (2001). *A real-time adaptive
  trading system using genetic programming.* **Quantitative Finance** 1(4),
  397–413. https://www.tandfonline.com/doi/abs/10.1088/1469-7688/1/4/301
- **Architecture:** single GA population; quarterly re-optimisation on the
  trailing 3 months of data; no regime awareness; best genome applied for the
  next quarter.
- **Why compare:** classical, simple, same domain (FX adaptive evolution).
  Isolates IslandPilot's contribution from regime structure alone —
  Dempster-Jones = "evolution without regimes".
- **Pipeline directory:** `pipelines/_shared/DempsterJonesPilot/`

### 2. IGTSPRingPilot — Ring-topology island GA, no regimes

- **Paper:** Chideme, K., Chen, C.-H., & Lin, J. C.-W. (2025). *Island genetic
  algorithm with diverse migration strategies for efficient group trading
  strategy portfolio optimization.* **Engineering Optimization**. DOI:
  10.1080/0305215X.2025.2592030. https://www.tandfonline.com/doi/full/10.1080/0305215X.2025.2592030
- **Architecture:** 4–8 island populations × 10 individuals each; ring
  migration every 5 generations; single shared fitness function across all
  islands (islands = parallel search populations, not regime-specific).
- **Why compare:** already cited in our paper §2.3 — direct ablation of the
  *regime-as-island* principle. IGTSP-Ring keeps the island machinery but
  removes the regime structure. Differences in result are attributable to
  regime-awareness alone.
- **Pipeline directory:** `pipelines/_shared/IGTSPRingPilot/`

### 3. CoEvolGPPilot — HMM regimes + per-regime populations + Shapley gating

- **Paper:** Yang, S., Xin, J., Ye, Q., & Xia, H. (2025). *A Co-evolutionary
  Genetic Programming Framework for Market-Adaptive Formulaic Alpha
  Generation.* **SSRN** 5614908.
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5614908
- **Architecture:** 3-state HMM (Gaussian mixture observations); one genetic
  population per regime; Shapley-value co-evolutionary feedback weights the
  per-regime best-genome contribution; parameters applied via posterior-
  probability-weighted aggregation.
- **Why compare:** structurally the closest published rival — also
  per-regime evolution — but uses only 3 flat HMM states vs. our 73
  hierarchical GMM leaves and evolves alpha signals rather than execution
  parameters.
- **Pipeline directory:** `pipelines/_shared/CoEvolGPPilot/`

### 4. CGAAgentPilot — Rolling-window agent-based GA

- **Paper:** *Agent-Based Genetic Algorithm for Crypto Trading Strategy
  Optimization.* **arxiv 2510.07943** (Oct 2025).
  https://arxiv.org/abs/2510.07943
- **Architecture:** rolling-window GA with 30-day re-optimisation period;
  multi-agent coordination adjusts mutation rate and crossover bias based on
  recent fitness trend; time-based adaptation, no regime structure.
- **Why compare:** modern 2025 baseline representing the "adapt on time" vs.
  our "adapt on regime" paradigm. Same evolutionary machinery, different
  adaptation trigger.
- **Pipeline directory:** `pipelines/_shared/CGAAgentPilot/`

### 5. FinRLPilot — DRL (PPO) regime-switching agent

- **Paper:** Liu, X.-Y., et al. (2020). *FinRL: A Deep Reinforcement Learning
  Library for Automated Stock Trading in Quantitative Finance.* **arxiv
  2011.09607**. https://arxiv.org/abs/2011.09607
- **Contests reference:** *FinRL Contests: Benchmarking Data-driven Financial
  Reinforcement Learning Agents.* **arxiv 2504.02281**.
  https://arxiv.org/html/2504.02281v3
- **Architecture:** PPO policy; state = feature vector from our FeaturePool
  (same 10 features as IslandPilot); action = discrete index into a small set
  of pre-defined parameter presets (e.g., conservative / moderate / aggressive
  / tight-TP); reward = cycle P&L at `on_cycle_end`.
- **Why compare:** representative of the non-evolutionary ML alternative.
  Uses open-source FinRL library, well-cited, reproducible.
- **Pipeline directory:** `pipelines/_shared/FinRLPilot/`

---

## Reporting Table (to be filled after training)

| Pipeline | Period | Sessions | Win % | Busts | PF | Net % | Max DD % | Gated | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Baseline | 2024 Full (OOS) | 608 | 90.3% | 58 | 0.870 | -32.2% | -32.6% | — | unenhanced strategy |
| **IslandPilot** | 2024 Full (OOS) | **603** | **90.5%** | **57** | **0.885** | **-30.5%** | **-30.9%** | 35/638 | ours |
| DempsterJonesPilot | 2024 Full (OOS) | — | — | — | — | — | — | — | walk-forward GA |
| IGTSPRingPilot | 2024 Full (OOS) | — | — | — | — | — | — | — | island GA no regimes |
| CoEvolGPPilot | 2024 Full (OOS) | — | — | — | — | — | — | — | HMM + per-regime pops |
| CGAAgentPilot | 2024 Full (OOS) | — | — | — | — | — | — | — | rolling 30-day GA |
| FinRLPilot | 2024 Full (OOS) | — | — | — | — | — | — | — | PPO preset-switching |

All numbers will be populated by `notebooks/phase5/5X_{pipeline}_ablation.py` runs
and aggregated into `notebooks/phase5/55_comparison_summary.py`.

---

## Paper Integration

Results will be added to `island_pilot.md` §7.5 ("Comparison with Related
Approaches") as an expanded empirical comparison, replacing the current
prose-only discussion of Chideme 2025 and Yang 2025.
