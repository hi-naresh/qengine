# ARIA Pipeline — R(t) Structural Stress Integration

**Date:** 2026-04-10
**Status:** Design
**Reference:** Chen, L-Y. (2026). "Layered-averaging systems and linear reward emergence in nonlinear financial markets." *Next Research* 8, 101565. Elsevier.
**Scope:** New module `structural_stress.py` in ARIA pipeline only. No changes to IslandPilot.

---

## Motivation

ARIA's current danger score (MarketBrain L1) measures **market-feature stress** — choppiness, volatility, trend strength. It answers: "Is the market dangerous right now?"

It has **zero awareness of execution-level stress** — how deep are we, how fast are we consuming levels, how long have we been stuck, did we just come off a bust. These are the signals that explain why a visually smooth reward curve suddenly flattens or drops.

Chen (2026) formalizes this as R(t), a log-constructible deviation accumulator:

```
Reward(t) = at + b - R(t)
```

Where R(t) aggregates 6 execution-level stress components, all computable from cycle logs with zero learned parameters. This is diagnostic (explains degradation) not predictive (no overfitting risk).

**Key insight:** Market danger and execution stress are independent signals. Merging them would dilute both. R(t) runs as a parallel channel.

---

## Complete ARIA Architecture (with R(t))

```
┌─────────────────────────────────────────────────────────────────┐
│                        ARIAPipeline                             │
│                  (implements Pipeline ABC)                      │
│                                                                 │
│  ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌──────────┐ │
│  │  Market   │──→│   Cycle   │──→│    HP     │──→│   Risk   │ │
│  │  Brain    │   │   Gate    │   │  Engine   │   │  Shield  │ │
│  │  (L1)     │   │   (L2)    │   │   (L3)    │   │  (L4)    │ │
│  └───────────┘   └───────────┘   └───────────┘   └──────────┘ │
│       │               ↑                                ↑       │
│       │               │                                │       │
│  ┌────┴──────────────────────────────────────────────┐ │       │
│  │              StructuralStress (NEW)                │─┘       │
│  │         R(t) = Σ(X + C + U + F + M + V)           │         │
│  │         Log-constructible, zero parameters         │         │
│  └───────────────────────────────────────────────────┘         │
│       ↑                                                         │
│  ┌───────────┐                                                  │
│  │ Observer  │──→ enriched session logs                         │
│  │  (L5)     │                                                  │
│  └───────────┘                                                  │
│       │                                                         │
│       ↓                                                         │
│  ┌───────────┐                                                  │
│  │   Meta-   │                                                  │
│  │ Evaluator │                                                  │
│  │  (L6)     │                                                  │
│  └───────────┘                                                  │
│       │                                                         │
│       ↓                                                         │
│  ┌───────────┐                                                  │
│  │  Shadow   │  (counterfactual tracking)                       │
│  │ Tracker   │                                                  │
│  └───────────┘                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Hook Mapping

| Pipeline Hook | Layers Active | R(t) Role |
|---|---|---|
| `on_before(strategy)` | L1 updates MarketState | StructuralStress updates live cycle timing (U_i, F_i) |
| `gate_entry(strategy)` | L2 classifies allow/block | R(t) magnitude + M_i fed as gate features |
| `filter_order(strategy, intent)` | L3 injects HPs | No R(t) involvement |
| `suggest_exit(strategy)` | L4 checks kill conditions | R(t) feeds independent abort threshold |
| `on_open_position(strategy)` | L5 captures entry snapshot | StructuralStress records cycle start |
| `on_cycle_end(pnl, strategy)` | L5/L2/L3/L6 update | StructuralStress finalises all 6 components |

---

## Layer-by-Layer Specification

### Layer 1 — MarketBrain (unchanged)

**Purpose:** What is the market doing right now?

**Method:** 6-feature Welford-normalised danger score + incremental k-means regime clustering.

**Features:**
| Feature | Weight | Direction | Source |
|---|---|---|---|
| `range_atr` | 0.25 | Inverted (low = danger) | bar_range / ATR(14) |
| `chop` | 0.20 | Direct (high = danger) | Choppiness Index(14) |
| `adx` | 0.15 | Inverted (low = danger) | ADX(14) |
| `hurst` | 0.15 | Inverted (~0.5 = danger) | R/S over 100 bars |
| `atr_ratio` | 0.15 | Direct (high = danger) | ATR(14) / ATR(50) |
| `ema_slope_mag` | 0.10 | Inverted (flat = danger) | combined EMA(8,21) slopes |

**Danger formula:**
```
z_i = WelfordNormalize(feature_i)  // online z-score, O(1)
if inverted: z_i = -z_i
danger = sigmoid(Σ(weight_i × z_i) / Σ(weight_i))
```

**Output:** `MarketState{danger, trend_strength, volatility, efficiency, regime_id, regime_confidence, features}`

**Tunable parameters:**
| Parameter | Default | What it controls |
|---|---|---|
| `brain_warmup` | 50 | Candles before danger/regime outputs trusted |
| `brain_k_max` | 5 | Maximum regime clusters |

**Measurement:** Feature distributions should be roughly Gaussian after Welford. Monitor z-score ranges. Regime count should stabilise after ~200 candles.

---

### Layer 2 — CycleGate (modified: +3 R(t) features)

**Purpose:** Should a new cycle start?

**Method:** Online logistic regression with SGD. Binary target: 1 = profitable cycle, 0 = bust/abort.

**Feature vector (20 dimensions, was 17):**
```
[0:4]    — 4 continuous market features (danger, trend_strength, volatility, efficiency)
[4:9]    — 5 regime one-hot
[9:12]   — 3 account features (drawdown%, consecutive_busts, cycles_since_bust)
[12:16]  — 4 session one-hot (asian/london/overlap/new_york)
[16:19]  — 3 NEW: R(t) features (normalised_Rt, inter_cycle_gap_ratio, recent_stress_rate)
[19]     — 1 bias term
```

**New features from StructuralStress:**
| Index | Feature | Formula | Interpretation |
|---|---|---|---|
| 16 | `normalised_Rt` | `R(t) / max(n_cycles, 1)`, clipped [0, 1] | Per-cycle average structural stress |
| 17 | `inter_cycle_gap_ratio` | `last_gap / median_gap`, clipped [0, 3] / 3 | How rushed is this entry vs normal |
| 18 | `recent_stress_rate` | `Σ(stress_last_10) / 10`, clipped [0, 1] | Rolling window of per-cycle stress |

**Learning:**
- SGD: `w += lr × (y - p) × x - lr × l2 × w`
- Learning rate: 0.01 (config: `gate_learning_rate`)
- L2 regularisation: 0.001
- Warmup: 30 cycles (gate allows all, still collects features)
- Adaptive threshold: ramps from 0.0 to 0.5 max over cycles

**Tunable parameters:**
| Parameter | Default | What it controls |
|---|---|---|
| `gate_enabled` | True | Master switch |
| `gate_warmup_cycles` | 5 | Cycles before gating starts |
| `gate_learning_rate` | 0.05 | SGD step size |

**Measurement:** Track gate accuracy (% of blocked entries that would have busted, via ShadowTracker). Target: >60% of blocks are correct after 50 cycles. Monitor feature weight magnitudes — R(t) features should develop nonzero weights if informative.

---

### Layer 3 — HPEngine (unchanged)

**Purpose:** What parameters should this cycle run with?

**Method:** Thompson Sampling contextual bandits per HP group per regime.

**Arms:** Constructed from strategy's `hyperparameters()` schema. Per-group: default + single-param variations + multi-param combos. Capped at 15 arms per group (config: `hp_max_arms_per_group`).

**Safety bounds (hard limits applied post-selection):**
| Parameter | Min | Max |
|---|---|---|
| `max_levels` | 2 | 10 |
| `base_size_value` | 0.1% | 3.0% |
| `max_daily_loss_pct` | 0 | 5.0 |
| `max_exposure_pct` | 0 | 80 |

**Tunable parameters:**
| Parameter | Default | What it controls |
|---|---|---|
| `hp_engine_enabled` | True | Master switch |
| `hp_warmup_cycles` | 5 | Cycles using strategy defaults |
| `hp_max_arms_per_group` | 15 | Arm cap per group |

**Measurement:** Arm convergence — after 100 cycles, top arm should accumulate >50% of selections per group. Track regret: `(best_arm_reward - selected_arm_reward)` rolling mean.

---

### NEW: StructuralStress Module

**Purpose:** Quantify execution-level structural stress R(t) from cycle logs. Zero learned parameters.

**File:** `pipelines/_shared/ARIA/structural_stress.py`

**Class:** `StructuralStress`

#### The 6 Components (from Chen 2026, Appendix A)

##### X_i — Excess Depth (coverage breach)

```
D_mkt,i = levels_reached / max_levels          // how deep we went [0, 1]
D_max   = designed_coverage_ratio               // e.g., 0.7 for comfortable range
X_i     = max(0, D_mkt,i - D_max)              // excess beyond design
```

**Interpretation:** X_i > 0 means market moved beyond what our level/spacing configuration was designed to absorb. Directly maps to our `levels` field in session records.

**Data source:** `session['levels']`, strategy config `max_levels`

##### C_i — Exposure Concentration (deep-state loading)

```
With sqrt(2) multiplier and K levels:
  total_exposure = Σ(base × sqrt(2)^k) for k=0..K
  deep_exposure  = Σ(base × sqrt(2)^k) for k=K*0.7..K    // top 30% of levels
  C_i = deep_exposure / total_exposure
```

**Interpretation:** Higher C_i means more capital locked in deep levels. With sqrt(2) this is bounded and sub-exponential (unlike 2x doubling), but still grows meaningfully at depth 8+.

**Data source:** `session['levels']`, strategy config `sizing_factor` (multiplier)

##### U_i — Time-Under-Stress (prolonged holding)

```
H_i  = session['bars']                          // candles in cycle
H_0  = median(all_completed_bars)               // reference duration
U_i  = max(0, H_i - H_0) / H_0                 // normalised excess duration
```

**Interpretation:** Cycles lasting 3x the median are in structural stress — the TP hasn't been reached, price is lingering. U_i = 2.0 means the cycle lasted 3x normal.

**Data source:** `session['bars']`

**NEW signal — not currently tracked.**

##### F_i — Entry Clustering (rapid level consumption)

```
For a cycle with K levels and timestamps t_0..t_K:
  gaps = [t_{k+1} - t_k for k in 0..K-1]       // time between hedge triggers
  tau  = median(all_historical_level_gaps)        // reference gap
  F_i  = (1/(K-1)) × Σ 1{gap_k < tau}           // fraction of rapid entries
```

**Interpretation:** F_i = 0.8 means 80% of hedges were triggered faster than normal — price is in freefall, eating through levels. This is the "flash crash" detector.

**Data source:** Need to add per-level timestamps. Currently `session['bars']` gives total duration but not per-level timing. **Requires Observer enrichment:** record `level_timestamps: [bar_0, bar_1, ..., bar_K]` during cycle.

**NEW signal — not currently tracked. Requires minor Observer change.**

##### M_i — Inter-Cycle Overlap (insufficient cooldown)

```
gap_i       = session[i].start_bar - session[i-1].end_bar    // bars between cycles
tau_sep     = median(all_historical_gaps)                      // reference cooldown
M_i         = 1{gap_i < tau_sep × 0.5}                        // binary: rushed re-entry
```

**Interpretation:** M_i = 1 means we re-entered too quickly after the last cycle closed. Compounding exposure without recovery time. Maps to the paper's "insufficient recovery between cycles."

**Data source:** `session['bars']` + session start timestamps. **Requires Observer enrichment:** record `start_bar` per session (currently only recorded in strategy vars, not in enriched sessions).

**NEW signal — not currently tracked. Requires minor Observer change.**

##### V_i — Rebound Deficit (insufficient recovery amplitude)

```
A_i  = session['pnl'] / expected_tp_profit       // realised vs expected TP
A_0  = 1.0                                        // full TP = no deficit
V_i  = max(0, A_0 - A_i)                          // [0, 1+] shortfall
```

**Interpretation:** V_i > 0 when cycle exits before reaching full TP (e.g., abort, partial close). V_i = 0.5 means we captured only half the expected profit. For TP-hit cycles, V_i ≈ 0.

**Data source:** `session['pnl']`, `session['reason']`, strategy config `tp_value`

#### R(t) Accumulator

```python
R(t) = Σ (X_i + C_i + U_i + F_i + M_i + V_i)   for all cycles i where t_i <= t
```

**Uncalibrated, equal-weight sum.** No learned weights. The paper explicitly states: "Component weights are not calibrated in this study. The intended use is interpretability."

**Properties:**
- R(t) is monotonically non-decreasing (stress accumulates)
- R(t) growth rate indicates current structural health
- `dR/dt ≈ 0` → healthy, near-linear reward envelope
- `dR/dt >> 0` → degrading, reward flattening
- Per-cycle stress `S_i = X_i + C_i + U_i + F_i + M_i + V_i` is the instantaneous reading

**Derived signals exposed to other layers:**
| Signal | Formula | Consumer |
|---|---|---|
| `r_t` | Running R(t) sum | MetaEvaluator (L6), stats/charting |
| `stress_i` | Per-cycle total stress | Observer enrichment |
| `normalised_rt` | `R(t) / n_cycles` | CycleGate (L2) feature |
| `recent_stress_rate` | `mean(stress[-10:])` | CycleGate (L2) feature |
| `inter_cycle_gap_ratio` | `last_gap / median_gap` | CycleGate (L2) feature |
| `stress_velocity` | `mean(stress[-5:]) - mean(stress[-20:-5])` | RiskShield (L4) |

#### Integration with RiskShield (L4)

New abort condition in `RiskShield.check()`:

```python
# Existing checks (unchanged):
# 1. Duration abort: bars > max_cycle_bars
# 2. Danger abort: level >= 3 AND market_danger > 0.8
# 3. Conformal kill
# 4. Liquidity gate

# NEW check (inserted after danger abort):
# 5. Structural stress abort
stress_velocity = structural_stress.stress_velocity()
if level >= 2 and stress_velocity > stress_abort_threshold:
    return {'action': 'close_all', 'reason': f'structural_stress:{stress_velocity:.3f}'}
```

**Config:**
| Parameter | Default | What it controls |
|---|---|---|
| `stress_abort_threshold` | 1.5 | Stress velocity above which to abort (starts conservative) |
| `stress_abort_min_level` | 2 | Minimum depth before stress abort activates |

**Why stress_velocity not raw R(t):** R(t) always grows. The velocity (rate of recent stress accumulation vs historical) detects when things are getting worse *right now*. A high R(t) with low velocity means past stress has subsided. A rising velocity means active degradation.

#### Integration with MetaEvaluator (L6)

**Modified ARIA score (adds R(t) awareness):**

```python
score = (
    survival_efficiency × 0.35         # was 0.4
    - bust_penalty × 0.25              # was 0.3
    + cvar_95_normalised × 0.25        # was 0.3
    - stress_rate_penalty × 0.15       # NEW: penalise rising R(t)
)

where:
  stress_rate_penalty = clip(recent_stress_rate - baseline_stress_rate, 0, 1)
  baseline_stress_rate = mean stress over first 50 cycles (after warmup)
```

This makes the ARIA score degrade when execution stress is rising, even if PnL is still positive (catching the "smooth Reward(t) hiding structural degradation" pattern from Chen's paper).

---

### Layer 4 — RiskShield (modified: +stress abort)

**Purpose:** Is this cycle about to destroy the account?

**Components (4, was 3):**

| Sub-component | Method | Signal |
|---|---|---|
| ConformalKill | Split conformal prediction on loss per level | `predicted_loss + bound > margin × safety` |
| LiquidityGate | Affordability + spread + ruin heuristic | `margin_required > equity` or `ruin_p > 0.5` |
| MarginSurvival | Exposure-based 3σ ruin probability | `P(ruin) = exposure × 3σ / equity` |
| **StressAbort (NEW)** | R(t) stress velocity from StructuralStress | `stress_velocity > threshold at level >= 2` |

**Tunable parameters (full list):**
| Parameter | Default | What it controls |
|---|---|---|
| `conformal_alpha` | 0.1 | Conformal quantile confidence |
| `conformal_safety` | 0.8 | Margin safety factor |
| `fallback_level` | 6 | Level-based abort before conformal calibrated |
| `max_ruin_prob` | 0.5 | Ruin probability ceiling |
| `max_cycle_bars` | 2000 | Duration abort (~7 days at 5m) |
| `danger_abort_threshold` | 0.8 | Market danger abort level |
| `stress_abort_threshold` | 1.5 | **NEW:** Stress velocity abort |
| `stress_abort_min_level` | 2 | **NEW:** Min depth for stress abort |

**Measurement:** Track false positive rate of stress abort (aborts where shadow shows cycle would have TP'd). Target: <30% false positive rate.

---

### Layer 5 — Observer (modified: +level timestamps, +start_bar, +stress)

**Purpose:** Enriched session recording.

**New fields in enriched session:**
```python
{
    # Existing fields (unchanged)
    'number', 'direction', 'levels', 'legs', 'pnl', 'reason', 'bars',
    'market_state_at_entry', 'market_state_at_exit',
    'hp_used', 'regime_id_at_entry', 'danger_at_entry', 'danger_at_exit',
    'gate_confidence', 'conformal_bound_at_kill', 'ruin_probs',
    'aria_score_at_entry',

    # NEW fields
    'start_bar': int,                    # candle index at cycle open
    'level_timestamps': list[int],       # [bar_0, bar_1, ..., bar_K] per level
    'stress_components': {               # per-cycle R(t) decomposition
        'X': float,                      # excess depth
        'C': float,                      # exposure concentration
        'U': float,                      # time under stress
        'F': float,                      # entry clustering
        'M': float,                      # inter-cycle overlap
        'V': float,                      # rebound deficit
        'total': float,                  # sum
    },
    'r_t': float,                        # cumulative R(t) at cycle end
}
```

**Requires strategy cooperation:** Strategy must call `observer.record_level_timestamp(bar_index)` when each hedge level triggers. This is a one-line addition in the Martingale strategy's hedge logic.

---

### Layer 6 — MetaEvaluator (modified: +stress penalty)

**Purpose:** Is the whole system improving?

**Modified score formula:** See StructuralStress integration section above.

**New degradation signal:** Rising R(t) velocity can trigger exploration boost independently of ARIA score, providing earlier warning.

**Tunable parameters:**
| Parameter | Default | What it controls |
|---|---|---|
| `meta_window` | 100 | Rolling window for score |
| `meta_degradation_sigma` | 1.0 | Sigma below mean to trigger boost |
| `meta_enabled` | True | Master switch |

**Measurement:** ARIA score should correlate with forward performance. Track: `corr(aria_score_at_entry, cycle_pnl)`. Target: > 0.15 after 100 cycles.

---

## What We're Tuning (Complete Parameter Table)

### Zero-parameter components (R(t) — nothing to tune)

| Component | Parameters | Notes |
|---|---|---|
| X_i (excess depth) | 0 | Directly from levels/max_levels |
| C_i (exposure concentration) | 0 | Directly from sizing multiplier |
| U_i (time under stress) | 0 | Median computed online from history |
| F_i (entry clustering) | 0 | Median gap computed online from history |
| M_i (inter-cycle overlap) | 0 | Median gap computed online from history |
| V_i (rebound deficit) | 0 | Directly from PnL vs expected TP |
| R(t) accumulator | 0 | Sum of components, equal weight |

**This is the paper's core strength: zero tunable parameters = zero overfitting risk.**

### Tunable parameters (existing ARIA layers)

| Layer | Parameter | Default | Tuned by |
|---|---|---|---|
| L1 | brain_warmup | 50 | Fixed (not tuned) |
| L1 | brain_k_max | 5 | Fixed (not tuned) |
| L2 | gate_learning_rate | 0.05 | Could be tuned by meta, currently fixed |
| L2 | gate_warmup_cycles | 5 | Fixed |
| L3 | hp_max_arms_per_group | 15 | Fixed |
| L3 | hp_warmup_cycles | 5 | Fixed |
| L4 | conformal_alpha | 0.1 | Fixed |
| L4 | conformal_safety | 0.8 | Fixed |
| L4 | fallback_level | 6 | Fixed |
| L4 | max_ruin_prob | 0.5 | Fixed |
| L4 | max_cycle_bars | 2000 | Fixed |
| L4 | danger_abort_threshold | 0.8 | Fixed |
| **L4** | **stress_abort_threshold** | **1.5** | **Fixed (NEW)** |
| **L4** | **stress_abort_min_level** | **2** | **Fixed (NEW)** |
| L6 | meta_window | 100 | Fixed |
| L6 | meta_degradation_sigma | 1.0 | Fixed |

### Self-tuning components (learn online)

| Layer | What learns | Method | Parameters learned |
|---|---|---|---|
| L1 | Feature z-scores | Welford online normalisation | Per-feature mean, variance |
| L1 | Regime structure | Incremental k-means | Cluster centroids, counts |
| L2 | Entry quality | Online logistic regression + SGD | 20 weights (was 17) |
| L3 | HP quality per regime | Thompson Sampling Beta posteriors | alpha, beta per arm per group per regime |
| L4 | Loss calibration | Split conformal prediction | Loss buckets per level |

---

## How We Measure (Evaluation Framework)

### Primary Metrics (backtest)

| Metric | Formula | Target | What it validates |
|---|---|---|---|
| **Reward linearity** | R² of linear fit to cumulative PnL curve | > 0.90 | Chen's core claim: Reward(t) ≈ at + b |
| **R(t) correlation** | corr(dR/dt, reward_deviation) | > 0.30 | R(t) explains reward flattening |
| **Stress abort accuracy** | 1 - (false_aborts / total_stress_aborts) | > 0.70 | Stress velocity is a real signal |
| **Gate improvement** | gate_accuracy_with_Rt - gate_accuracy_without_Rt | > 0 | R(t) features add value to entry gating |
| **PF improvement** | PF_with_Rt / PF_without_Rt | > 1.0 | Net positive impact on P&L |
| **Bust rate change** | busts_with_Rt / busts_without_Rt | < 1.0 | Fewer busts |

### Component-Level Diagnostics

| Component | Diagnostic | Healthy range |
|---|---|---|
| X_i | % of cycles with X_i > 0 | < 10% (most cycles within design range) |
| C_i | Mean C_i across cycles | < 0.3 (exposure not concentrated in deep levels) |
| U_i | % of cycles with U_i > 2.0 | < 5% (few cycles lasting 3x median) |
| F_i | Mean F_i for busted cycles vs TP cycles | F_i(bust) >> F_i(tp) (signal discriminates) |
| M_i | % of cycles with M_i = 1 | < 15% (not re-entering too fast) |
| V_i | Mean V_i for aborted cycles | > 0.3 (aborts capture significant rebound deficit) |

### Statistical Tests (for paper)

1. **Is R(t) informative?** Permutation test: shuffle R(t) components across cycles, compare predictive power. If shuffled R(t) performs similarly → R(t) has no signal (reject module).

2. **Are components independent?** Correlation matrix of X, C, U, F, M, V across cycles. Components should have pairwise |corr| < 0.5 (they measure different things).

3. **Does R(t) predict reward deviation?** Granger causality test: does lagged stress_velocity predict next-5-cycle PnL deviation from linear trend?

4. **Walk-forward stability:** Compute R(t) on train period, measure correlation with reward deviation on test period. Should be stable across windows.

---

## Implementation Plan

### Phase 1: StructuralStress module + Observer enrichment
- New file: `structural_stress.py` with `StructuralStress` class
- All 6 components (X, C, U, F, M, V) and R(t) accumulator
- Observer: add `start_bar`, `level_timestamps`, `stress_components`, `r_t` fields
- Strategy: add `observer.record_level_timestamp()` call in hedge logic
- Unit tests for each component formula
- **No integration with other layers yet** — just compute and record

### Phase 2: RiskShield integration (stress abort)
- Add `stress_velocity` computation to StructuralStress
- Add stress abort check in `RiskShield.check()`
- Wire `stress_abort_threshold` and `stress_abort_min_level` into config
- ShadowTracker: track stress aborts for false positive measurement

### Phase 3: CycleGate integration (+3 features)
- Extend feature vector from 17 to 20 dimensions
- Add `normalised_rt`, `inter_cycle_gap_ratio`, `recent_stress_rate`
- Verify gate weight convergence on R(t) features

### Phase 4: MetaEvaluator integration (stress penalty)
- Add `stress_rate_penalty` to ARIA score formula
- Add R(t) velocity as independent degradation trigger
- Verify ARIA score still correlates with forward performance

### Phase 5: Statistical validation + charting
- Run backtests: with vs without R(t)
- Compute all metrics from evaluation framework
- Run permutation tests, Granger causality, component independence
- Add R(t) chart to PipelineIntelligence.vue (line chart: R(t) over cycles, stacked area of components)

---

## File Structure (updated)

```
pipelines/_shared/ARIA/
├── __init__.py              # ARIAPipeline (Pipeline ABC) — modified
├── config.py                # default_config — modified (+2 stress params)
├── market_brain.py          # L1: features + clustering — unchanged
├── cycle_gate.py            # L2: online logistic regression — modified (+3 features)
├── hp_engine.py             # L3: contextual bandits — unchanged
├── risk_shield.py           # L4: conformal + liquidity + margin — modified (+stress abort)
├── observer.py              # L5: enriched sessions — modified (+3 fields)
├── structural_stress.py     # NEW: R(t) accumulator, 6 components
├── meta_evaluator.py        # L6: ARIA score — modified (+stress penalty)
└── shadow_tracker.py        # Counterfactual tracking — unchanged
```

---

## Design Decisions

1. **Parallel signal, not merged danger score** — Market features and execution stress measure fundamentally different things. Chen's paper treats R(t) as an execution-level accumulator distinct from price dynamics. Merging would dilute both signals.

2. **Zero learned parameters for R(t)** — The paper's entire value proposition is auditability. Each stress unit traces to a specific execution event. Adding weights or thresholds would introduce overfitting risk and lose interpretability.

3. **Stress velocity for abort, not raw R(t)** — R(t) is monotonically non-decreasing by design. Raw R(t) > threshold would eventually abort everything. Velocity (rate of change) detects active degradation vs historical stress that has subsided.

4. **Equal component weights** — Following the paper: "Component weights are not calibrated in this study." If future research shows one component dominates, we can weight — but the default is interpretable equal-weight sum.

5. **ARIA-only, not IslandPilot** — Each pipeline is independently explainable for publication. IslandPilot has its own regime-aware system. Cross-pollination would create entanglement.

6. **Observer enrichment over strategy modification** — Level timestamps could be tracked in the strategy or the observer. Observer is cleaner: the strategy calls one method, the observer stores the data. Keeps strategy code minimal.

---

## What's NOT In This Design

- Learned component weights (would require calibration = overfitting risk)
- Real-time R(t) updates within a cycle (R(t) finalises at cycle end)
- Multi-asset R(t) (Chen mentions cross-asset extensions as future work)
- Bayesian updating of R(t) (Chen suggests as future research)
- Integration with IslandPilot pipeline
- Frontend UI for R(t) (will follow PipelineIntelligence.vue patterns)
