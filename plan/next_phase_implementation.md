# SurefireHedge V2 — Next Phase Implementation Plan

> Created: 2026-03-26
> Updated: 2026-03-26 (v2 — regime-adaptive architecture)
> Status: Pre-implementation
> Prerequisites: All 14 research scripts completed at 30:1 leverage

---

## Where We Are

### Proven (Phase 1-2 Research, Scripts 01-14)

| What | Finding | Script |
|------|---------|--------|
| Best static config | 12 levels, sqrt(2) multiplier, 0.5% base, TP=0.8*ATR, RR=2.0 | 12 |
| Production metrics | 99.7% win, 0.26% bust, PF 3.56, 14.7% return, Calmar 22.4 | 10, 13 |
| No indicator edge | EMA, RSI, MACD, ADX, SMA, all combos — all ~33% L0 win rate | 01 |
| No cooldown effect | P(loss\|prev loss) = P(loss), market is memoryless at 5m | 03 |
| No pre-entry predictor | Cohen's d < 0.1 for ALL features tested | 07, 14 |
| Session filters marginal | Best combo reduces bust rate 16% (7.53%→6.32%) — not enough | 03, 05 |
| 98.7% of busts = choppy range | Price oscillates with h < amplitude < tp | 14 |
| Busts are IID (no clustering) | P(bust\|prev bust) ≈ P(bust), clustering ratio 1.06x | 07 |
| Blind test validates | Test return 7.48% > train 2.90% — no overfitting, edge is real | 13 |
| Stress fragility | Under 2x stress: median return -1.8%, only 14.6% profitable | 11 |
| p*m is the critical quantity | sqrt(2) gives p*m=0.80 (HELPS), 2x gives p*m=1.13 (HURTS) | 12 |
| Optimal m depends on p | m* = 1/p. If p changes (regime), optimal config changes | 12 |

### What's Left to Solve

| Problem | Type | Impact | Approach |
|---------|------|--------|----------|
| P5: Entry quality | P(L0 lose) = 0.63 | HIGHEST — +12% EV if reduced to 0.50 | Non-linear classifier |
| P6: Regime detection | p is non-stationary | CRITICAL — 10% p increase → 3.1x bust rate | HMM / probabilistic |
| Choppy range vulnerability | 98.7% of busts | CORE PROBLEM — geometric kill zone | Dynamic grid + regime |
| No adaptive config | Fixed params for all conditions | m*=1/p changes when p changes | Multi-config selection |

---

## The Core Problem: The Choppy Range Kill Zone

### Why It Happens (Script 14)

```
The grid has TP distance and hedge distance h where TP = 2h.

Kill zone: when market oscillation amplitude A satisfies h < A < TP

  If A < h  → hedges never trigger → L0 wins harmlessly
  If A > TP → TP gets hit naturally → cycle wins
  If h < A < TP → EVERY hedge triggers, NO TP hits → cascade to bust

98.7% of busts fall in this kill zone.
```

### Why It's Not Unsolvable

The kill zone is defined by fixed h and TP. If we make them **dynamic**:

- **Measure current oscillation amplitude** before entry
- **Adjust TP/h so the kill zone doesn't align with current market oscillation**
- Wider TP in choppy markets → pushes kill zone ceiling above oscillation
- Or SKIP when oscillation sits exactly in [h, TP]

This requires knowing the oscillation amplitude, which requires regime detection.

### The Martingale Constraint

Even with dynamic geometry, `P(bust) > 0` always (finite capital). But we can:
- Reduce P(bust) from 0.26% toward 0.05% by avoiding the worst regimes
- Use regime-optimal configs so p*m stays well below 1.0 in all conditions
- Accept that some irreducible floor exists — the price of the strategy

---

## Architecture: Adaptive Surefire Pipeline

### Why One Config Is Wrong

Script 12 proved: optimal multiplier m* = 1/p. Script 11 proved: when p shifts +20%, bust rate goes up 8.7x. A fixed config that's optimal for p=0.566 is **wrong** when p changes.

The solution is not one config — it's **a config per regime**.

### The Four-Layer System

```
┌──────────────────────────────────────────────────────────┐
│                 ADAPTIVE SUREFIRE PIPELINE                │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  LAYER 1: Regime Detection (HMM / Online Bayesian)       │
│  Answers: "What kind of market am I in right now?"        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ Trending │  │  Choppy  │  │ Volatile │  │ Unclear │ │
│  │ p ≈ 0.48 │  │ p ≈ 0.72 │  │ p ≈ 0.60 │  │ p = ?   │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │
│       │              │              │              │      │
│  LAYER 2: Config Selection (per regime)                   │
│  Answers: "What parameters are optimal for this regime?"  │
│  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐  ┌────┴────┐ │
│  │ 12 lvl   │  │ SKIP or  │  │ 8 lvl    │  │Conserv- │ │
│  │ sqrt(2)  │  │ wide TP  │  │ 1.3x     │  │ative    │ │
│  │ 0.5% base│  │ few lvls │  │ 0.3% base│  │defaults │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │
│       │              │              │              │      │
│  LAYER 3: Entry Quality Gate (Classifier)                 │
│  Answers: "Should I enter THIS specific cycle?"           │
│  ┌─────┴──────────────┴──────────────┴──────────┴──┐    │
│  │ P(L0 win | features, regime) > threshold?        │    │
│  │   YES → trade with regime config                 │    │
│  │   NO  → skip this cycle                          │    │
│  └──────────────────────────┬───────────────────────┘    │
│                             │                            │
│  LAYER 4: Mid-Cycle Monitor (Runtime)                     │
│  Answers: "Has the regime changed DURING this cycle?"     │
│  ┌──────────────────────────┴───────────────────────┐    │
│  │ At each level: re-check regime state              │    │
│  │ If regime shifted to adverse → ABORT early        │    │
│  │ Controlled loss at L3 (15x base) < bust (78x)    │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

---

## The Reward Function (Tail-Risk Aware)

Standard metrics (Sharpe, Sortino) don't capture the martingale risk structure. The reward must be **strategy-aware**.

### Why Standard Objectives Fail

| Objective | Problem for Martingale |
|---|---|
| Max return | Ignores tail risk — optimizes toward aggressive configs that blow up |
| Max Sharpe | Penalizes upside variance — wrong for asymmetric payoffs |
| Max Sortino | Better, but doesn't capture the p*m exponential risk |
| Min drawdown | Too conservative — would never trade |

### The Custom Reward

```
reward = mean_return_per_cycle
       - λ₁ * max(0, bust_rate - bust_threshold)     # tail risk penalty
       - λ₂ * max(0, p_m_product - pm_threshold)      # martingale invariant penalty
       - λ₃ * max(0, -max_drawdown - dd_threshold)    # drawdown penalty
       + λ₄ * survival_bonus                           # 0 ruin = 1.5x multiplier

where:
  bust_threshold = 0.001 (0.1% target bust rate)
  pm_threshold = 0.85 (safety margin below 1.0)
  dd_threshold = 0.005 (0.5% max drawdown target)
  λ₁ = 10, λ₂ = 5, λ₃ = 2, λ₄ = 0.5 (tunable)
```

This reward:
- Maximizes return (the primary goal)
- Exponentially penalizes bust rates above threshold
- Penalizes configs where p*m approaches the critical value 1.0
- Rewards configs that achieve 0% ruin in Monte Carlo
- Is differentiable (for gradient-based optimization) and evaluable (for GA)

---

## Implementation Phases (Revised)

### Phase A: Feature Engineering (3-4 days)

**Script**: `notebooks/phase2/15_feature_engineering.py`

Build the feature matrix that all downstream models consume.

**Features (~30 per bar)**:

| Category | Features | Purpose |
|----------|----------|---------|
| Oscillation | Choppiness Index(14), Hurst exponent(20), direction changes/20 bars | Detect kill zone |
| Volatility | ATR(14), ATR(50), ATR ratio, Bollinger bandwidth, Keltner width | Regime state |
| Momentum | RSI(14), RSI slope, MACD histogram + slope, ADX(14), ROC(10) | Trend detection |
| Microstructure | Volume ratio, bar body ratio, spread estimate | Market quality |
| Temporal | Hour (sin/cos), day (sin/cos), session flag | Time context |
| Multi-timeframe | 15m ATR/RSI/ADX, 1h ATR/RSI/ADX | Larger context |

**Key new features for choppy range detection**:
- **Choppiness Index**: `100 * log(sum(ATR(1), 14)) / (highest(14) - lowest(14)) / log(14)`
  - High CI = choppy range (kill zone risk)
  - Low CI = trending (safe for the strategy)
- **Hurst Exponent** (rolling 20-bar): H < 0.5 = mean-reverting (good), H > 0.5 = trending (good for different config), H ≈ 0.5 = random walk (kill zone)
- **Oscillation Amplitude**: range of last 20 bars relative to current tp_dist — directly measures if we're in the kill zone

**Deliverables**:
- Feature matrix: 6,419 rows × 30 features (aligned to cycle entries)
- Labels: level reached (0-12), bust binary, choppy bust binary
- Feature correlation matrix + mutual information scores
- Saved as parquet

### Phase B: Regime Discovery (5-7 days) — THE CRITICAL GATE

**Script**: `notebooks/phase2/16_hmm_regime.py`

#### Step 1: Fit HMM

```python
from hmmlearn import GaussianHMM

# Features for regime detection: returns, ATR ratio, choppiness, Hurst, ADX
features = ['return_5m', 'atr_ratio', 'choppiness_index', 'hurst', 'adx']
X = feature_matrix[features].values

# Test 2, 3, 4, 5 hidden states — select by BIC
for n_states in [2, 3, 4, 5]:
    model = GaussianHMM(n_components=n_states, covariance_type='full', n_iter=200)
    model.fit(X_train)
    bic = -2 * model.score(X_train) + n_states * np.log(len(X_train))
```

#### Step 2: Label bars and cycles

```python
regimes = model.predict(X_all)  # regime label per bar
cycle_regimes = regimes[cycle_entry_indices]  # regime at each cycle entry
```

#### Step 3: Compute regime-specific p-values

```python
for regime in unique_regimes:
    mask = cycle_regimes == regime
    regime_busts = busts[mask]
    regime_wins = wins[mask]
    regime_p = regime_busts / (regime_busts + regime_wins)  # per-level p
    regime_p_m = regime_p * sqrt(2)  # p*m for current config
```

#### Step 4: The gate decision

```
IF P(bust | worst_regime) > 2x P(bust | best_regime):
    → Regime detection has signal. Proceed.
    → Each regime gets its own optimal config (Phase C).

IF P(bust | regime) uniform across regimes:
    → STOP. Busts are genuinely IID random.
    → Ship structural solution (already exceptional).
    → Future: multi-instrument diversification only.
```

#### Step 5: Validate on test period
- Train HMM on 2024-01 to 2025-02
- Validate regime stability on 2025-02 to 2026-03
- Check: do regime labels persist? Does P(bust|regime) hold?

**Data concern**: 17 busts at 12-level. Solutions:
- Use 5-level data (492 busts) for initial fitting
- Cross-validate with different level configurations
- Regime detection uses ALL bars (not just cycles) — much more data

### Phase C: Per-Regime Config Optimization (5-7 days, IF Phase B finds signal)

**Script**: `notebooks/phase2/17_regime_configs.py`

Two approaches — run both and compare:

#### Approach 1: MINLP per Regime (Fast, Exact)

For each HMM-discovered regime, run Script 12's exhaustive optimization:
```python
for regime in discovered_regimes:
    regime_p_levels = measure_p_levels(regime_data)
    regime_avg_p = np.mean(regime_p_levels)

    # Optimal config for this regime's specific p-values
    best_config = optimize_minlp(
        p_levels=regime_p_levels,
        equity=10000, leverage=30,
        variables=['N', 'm', 'base_pct', 'tp_mult', 'hedge_ratio']
    )

    # Also check: should this regime be SKIPPED entirely?
    skip_ev = 0  # EV of not trading
    if best_config.ev < skip_ev * 0.8:  # trading has negative EV in this regime
        best_config = SKIP
```

#### Approach 2: Multi-Island GA (Adaptive, Exploratory)

```python
from pymoo.algorithms.moo.nsga2 import NSGA2

# Create one island per regime
islands = {}
for regime in discovered_regimes:
    island = NSGA2(
        pop_size=200,
        # Each individual = [N, m, base_pct, tp_mult, hedge_ratio]
        # Plus: entry_threshold, abort_level, abort_conditions
    )
    islands[regime] = island

# Multi-objective fitness per island:
objectives = [
    maximize: mean_return_per_cycle,
    minimize: bust_rate,
    minimize: max_drawdown,
    minimize: CVaR_99,
]

# Custom constraint: p*m < 0.90 for all configs
constraints = [lambda config: config.avg_p * config.m < 0.90]

# Migration: every 50 generations, top 5% of each island
# visits other islands for 10 generations
# Configs that perform well across multiple regimes = robust
```

#### Decision: MINLP vs GA

| Criteria | MINLP per Regime | Multi-Island GA |
|----------|-------------------|-----------------|
| Speed | Minutes | Hours |
| Guaranteed optimal | Yes (for fixed objectives) | No (heuristic) |
| Explores novel configs | No (limited to known search space) | Yes (can discover surprises) |
| Multi-objective | Hard to do well | Native (NSGA-II Pareto front) |
| Robustness across regimes | Must check manually | Migration handles naturally |

**Recommendation**: Start with MINLP (fast, exact baseline). Run GA as Phase C+ to see if it finds configs MINLP missed.

### Phase D: Entry Quality Classifier (5-7 days)

**Script**: `notebooks/phase2/18_entry_classifier.py`

Build a classifier that predicts P(L0 win | features, regime).

- **Target**: L0 win (1) vs L0 lose (0) — much more data than bust prediction
- **Models**: Logistic Regression → XGBoost → LightGBM → small NN
- **Features**: Top features from Phase A + regime state from Phase B
- **Evaluation**: Walk-forward CV, AUC, calibration curves
- **Entry gate**: only trade when P(L0 win) > regime-specific threshold

If classifier achieves AUC > 0.60: integrate as Layer 3.
If AUC < 0.55: L0 outcomes are genuinely unpredictable, skip this layer.

### Phase E: Mid-Cycle Abort Logic (3-4 days)

**Script**: `notebooks/phase2/19_abort_rules.py`

At each level during a live cycle:
1. Re-run HMM forward pass on latest bars
2. If regime has shifted to adverse since entry → ABORT
3. Controlled loss at current level < bust loss at max level

```
Abort at L3 (15x base loss) vs bust at L12 (78.9x base loss)
Saving: 63.9x base per abort-that-would-have-busted
Cost: losing 15x base on some aborts-that-would-have-won

Break-even: abort needs to be correct > 15/78.9 = 19% of the time
```

### Phase F: Integration + Validation (5-7 days)

**Script**: `notebooks/phase2/20_validation.py`

Full pipeline walk-forward test:
1. Features → HMM → regime label → config selection → entry gate → trade/skip
2. During cycle: regime monitoring → abort if shifted
3. Compare vs structural baseline (no ML)

**Success criteria**:

| Metric | Structural Only | Target | Stretch |
|--------|----------------|--------|---------|
| Bust rate | 0.26% | <0.10% | <0.05% |
| Win rate | 99.7% | >99.9% | >99.95% |
| PF | 3.56 | >5.0 | >8.0 |
| Max DD | -0.66% | <-0.30% | <-0.15% |
| Calmar | 22.4 | >50 | >100 |
| Survives 2x stress | 14.6% profitable | >60% | >80% |

---

## Timeline

| Phase | Duration | Depends On | Key Output |
|-------|----------|------------|------------|
| A: Feature Engineering | 3-4 days | Nothing | Feature matrix + oscillation metrics |
| B: HMM Regime Discovery | 5-7 days | A | Regime labels, P(bust\|regime) — **THE GATE** |
| C: Per-Regime Configs | 5-7 days | B | Config lookup table per regime |
| D: Entry Classifier | 5-7 days | A, B | P(L0 win) predictor |
| E: Mid-Cycle Abort | 3-4 days | B | Abort rules + break-even analysis |
| F: Validation | 5-7 days | C, D, E | Full pipeline walk-forward |

**Total**: ~5-6 weeks
**Critical path**: Phase B is the gate. Everything else depends on it.

---

## What We Are NOT Doing

| Approach | Why Not |
|----------|---------|
| More simple indicators | Proven useless (script 01) |
| Cooldown logic | Proven useless (script 03) |
| Pre-entry bust prediction (direct) | Proven impossible, Cohen's d < 0.1 (scripts 07, 14) |
| 2x multiplier | Mathematically inferior, p*m > 1 (script 12) |
| Quantum feature selection | Problem too small (~30 features), classical sufficient |
| Deep learning | Overkill for ~6,000 samples with 17 bust events |
| Changing hedge geometry (make h > TP) | Breaks the strategy's mathematical foundation |
| Single universal config | Proven suboptimal when p changes across regimes |

---

## Libraries Required

```
hmmlearn          # HMM fitting (Phase B)
scikit-learn      # Feature selection, classifiers, metrics (Phase A, D)
xgboost           # Feature importance, classification (Phase A, D)
lightgbm          # Fast gradient boosting (Phase D)
pymoo             # NSGA-II multi-objective GA (Phase C)
imbalanced-learn  # SMOTE for class imbalance (Phase D)
pyarrow           # Parquet I/O for feature matrix (Phase A)
scikit-fuzzy      # Optional: fuzzy decision layer alternative to hard thresholds
```

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| HMM finds no regime signal | Phases C-E less valuable | Ship structural solution — already exceptional |
| Too few busts (17 at 12-level) | Overfitting | Use 5-level data (492 busts) for development |
| Feature leakage | Inflated metrics | Strict walk-forward CV |
| Regime labels unstable over time | Config selection noise | Online Bayesian updating, retrain monthly |
| GA overfits per-regime configs | Works in-sample, fails out | Migration between islands + walk-forward validation |
| Mid-cycle regime shift detection lags | Abort too late | Accept 1-2 level delay — still better than bust |
| p*m changes sign across regimes | One config per regime wrong | MINLP guarantees m < 1/p for each regime |
