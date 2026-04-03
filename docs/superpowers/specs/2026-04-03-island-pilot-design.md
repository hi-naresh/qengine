# IslandPilot: Multi-Island Evolutionary Pipeline with Hierarchical Regime Inference

**Date**: 2026-04-03  
**Status**: Approved  
**Pipeline Name**: IslandPilot  
**Location**: `pipelines/_shared/IslandPilot/`

## 1. Overview

IslandPilot is a new runtime pipeline (like GridPilot) that uses a multi-island genetic algorithm to evolve regime-specific execution configs. Each "island" corresponds to a leaf node in a hierarchical regime tree. At runtime, probabilistic inference determines the current market regime, and the pipeline applies the evolved config from the matching island — controlling entry gating, position sizing, TP/hedge distances, and abort policy.

### Core Innovation

Instead of one global config, the strategy dynamically switches between regime-specific configs that were independently evolved via a genetic algorithm. A hierarchical clustering approach discovers regimes from data, and sibling islands exchange genetic material to prevent overfitting.

### Key Design Decisions

1. **Component architecture** (like GridPilot) — RegimeTree, IslandEvolver, RegimeInferencer, AdaptiveSizer
2. **Full execution config per island** — each island evolves gate, sizing, TP, hedge, abort params
3. **Hierarchical regime tree** — GMM macro-clusters → sub-clusters, data-driven feature selection
4. **Hierarchical migration** — gene exchange between sibling islands only (same macro-parent)
5. **Soft selection, hard config + hysteresis** — no blending of configs, stickiness prevents whipsaw
6. **Multi-factor adaptive sizing** — island base × confidence × drawdown factor, bounded by SafetySizing
7. **Research-grade evaluation** — 8 ablation variants, walk-forward validation, statistical tests

## 2. Component Architecture

```
IslandPilot (Pipeline)
├── RegimeTree          — hierarchical regime discovery & classification
│   ├── MacroCluster    — GMM on primary features
│   └── SubCluster[]    — per-macro refinement on secondary features
├── IslandEvolver       — GA engine, one population per leaf node
│   ├── Population[]    — each leaf regime gets a population of configs
│   └── Migrator        — hierarchical sibling migration
├── RegimeInferencer    — runtime regime classification + hysteresis
│   └── StickySelector  — soft probabilities, hard switch with margin
└── AdaptiveSizer       — multi-factor position sizing
    ├── island_base     — evolved per-regime base size
    ├── confidence      — regime inference confidence scaling
    └── drawdown_factor — recovery-aware scaling
```

### Pipeline Hook Mapping

| Hook | Component | Behavior |
|------|-----------|----------|
| `on_before(strategy)` | RegimeInferencer | Update current regime classification every candle |
| `gate_entry(strategy)` | RegimeInferencer | Block entry if regime confidence < island's threshold |
| `adjust_size(strategy, qty, side)` | AdaptiveSizer | Multi-factor sizing with SafetySizing hard cap |
| `filter_order(strategy, order_intent)` | IslandEvolver | Inject island's evolved TP/hedge/levels into order |
| `suggest_exit(strategy)` | IslandEvolver | Abort based on evolved aggressiveness threshold |
| `on_cycle_end(pnl, strategy)` | IslandEvolver | Feed outcome for fitness tracking |
| `get_stats()` | All | Research-grade analytics |
| `save_state(path)` / `load_state(path)` | All | Full pipeline persistence |

### Genome (Evolved Config Per Island)

```python
{
    "gate_confidence_min": float,        # 0.0–1.0, min regime confidence to allow entry
    "sizing_curve": str,                 # geometric/sqrt/linear/fibonacci
    "sizing_factor": float,              # 1.1–5.0, multiplier for sizing curve
    "max_levels": int,                   # 1–12, max hedge levels
    "tp_distance_atr_mult": float,       # 0.5–5.0, take-profit as ATR multiple
    "hedge_distance_atr_mult": float,    # 0.3–3.0, hedge trigger as ATR multiple
    "abort_aggressiveness": float,       # 0.0–1.0, maps to danger abort threshold
    "base_size_pct": float,              # 0.1–10.0, % of equity as base position
    "hysteresis_margin": float,          # 0.05–0.30, regime switch stickiness
    "confidence_sensitivity": float,     # 0.5–2.0, how aggressively confidence scales size
    "recovery_aggression": float,        # 0.3–1.0, how aggressively drawdown reduces size
}
```

## 3. Regime Tree

### Feature Selection (Automated)

Instead of hand-picking features, a feature selection stage discovers which market features best discriminate regimes.

**Candidate pool** (~30-40 features across 5 categories):

| Category | Features (examples) | Count |
|----------|-------------------|-------|
| Volatility | NATR (multiple periods), ATR ratio, Bollinger width, Keltner width, historical vol | 5–8 |
| Trend | ADX, DM+/DM-, EMA slopes (multiple), Aroon, Vortex, Supertrend state | 5–8 |
| Mean-reversion/Chop | ER (multiple periods), Hurst, Choppiness Index, fractal dimension | 5–8 |
| Momentum | RSI, MACD histogram, Stochastic, CCI, ROC | 4–6 |
| Volume/Structure | OBV slope, VWAP deviation, session-of-day encoding, day-of-week | 3–5 |

**Selection method**: Mutual information or random-forest feature importance against cycle outcome (win/bust). Top-K features selected where K is optimized by BIC during GMM fitting.

**Per-level selection**: Macro clustering and sub-clustering may use different feature subsets.

### Hierarchy Construction (Offline)

1. **Macro level**: GMM on top primary features (expected: volatility, trend strength, directional movement). BIC selects K, expected 5–10 macro-regimes.

2. **Sub level**: Within each macro-regime, GMM on remaining selected features. BIC selects K per macro, expected 3–8 sub-regimes each. Total leaf nodes: 15–80.

3. **Minimum population**: Any leaf with fewer than 200 training cycles gets merged into its closest sibling. Prevents sparse islands.

### Runtime Classification

```
1. Compute feature vector from rolling window (default 100 bars)
2. Macro GMM: P(macro_i | features) for all macro-regimes
3. If top macro probability < min_confidence (0.3): stay in current regime
4. Sub GMM: P(sub_j | features, best_macro) for sub-regimes
5. Joint: P(leaf) = P(macro) × P(sub | macro)
6. Hysteresis: switch ONLY if best_new_prob > current_prob + hysteresis_margin
7. Output: (active_regime_id, confidence, all_probabilities)
```

**Cold start**: First 100 bars = warmup, pipeline passes through (no gating, default sizing).

**Transition grace period**: When regime switches, 5-candle grace period where no new entries allowed.

## 4. Island Evolution (GA Engine)

### Population Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Population per island | 30 | Small enough for fast evolution, large enough for diversity |
| Selection | Tournament (k=3) | Every generation |
| Crossover | Uniform (50% swap per gene) | Rate: 0.7 per pair |
| Mutation | Gaussian (σ = 5% of gene range) | Rate: 0.2 per individual |
| Elitism | Top 2 survive unchanged | Every generation |
| Max generations | 100 | Configurable |
| Early stop | 15 generations without >0.5% improvement | Per-island |

### Fitness Function

```
fitness = w1 × net_profit_pct
        + w2 × (1 - bust_rate)
        + w3 × profit_factor_norm
        + w4 × (1 - max_drawdown_pct)
```

Default weights: `w1=0.3, w2=0.3, w3=0.2, w4=0.2`.

Each individual is evaluated by running backtests on cycles belonging to that island's regime (pre-sliced, not full backtest).

### Hierarchical Migration

- **Sibling migration** (every 5 generations): Best individual from island N copies to a random sibling (same macro-parent). Replaces worst individual in receiving island.

- **Cross-macro tournament** (every 20 generations): Best individual from each macro-regime competes on shared validation set. Winner's genes injected into weakest island across all macros.

### Training Flow

```
Load candles
→ Build RegimeTree (feature selection + hierarchical GMM)
→ Assign training cycles to leaf islands
→ Initialize populations (random within gene bounds)
→ For each generation:
    → Evaluate all individuals (parallel per island)
    → Selection + Crossover + Mutation
    → Elitism carry-forward
    → Migration (if generation % 5 == 0)
    → Cross-macro tournament (if generation % 20 == 0)
    → Check convergence per island
→ Extract best genome per island
→ Save as pipeline state
```

## 5. Regime Inference + Hysteresis

### StickySelector

The inferencer uses soft probabilities but hard config switching with hysteresis:

- Compute `P(leaf)` for all leaves every candle
- Only switch regime if: `P(new_best) > P(current) + hysteresis_margin`
- `hysteresis_margin` is evolved per-island (0.05–0.30)
- High-volatility regimes get tighter margins (regime shifts matter more)
- Ranging regimes get wider margins (false switches are costly)

### Confidence Calibration

Track whether predictions match reality:
- If pipeline says 80% confidence in regime X, do 80% of those cycles actually belong to regime X?
- Logged for research output (calibration plot)

## 6. Adaptive Sizing Operator

### Three Multiplicative Factors

```
final_size = island_base × confidence_scale × drawdown_factor
final_size = min(final_size, SafetySizing.max_safe_initial_size(...))
```

**Factor 1 — Island base** (`base_size_pct`):
- Evolved per island as % of equity
- Regime-appropriate: trending islands evolve larger, choppy islands smaller

**Factor 2 — Confidence scale**:
```
confidence_scale = max(0.2, regime_confidence ^ sensitivity)
```
- `sensitivity` evolved per island (0.5–2.0)
- `min_scale` = 0.2 (never below 20% of base)

**Factor 3 — Drawdown recovery**:
```
if current_drawdown_pct < 5%:
    drawdown_factor = 1.0
else:
    depth = (current_drawdown_pct - 5%) / max_drawdown_limit
    drawdown_factor = max(0.1, 1.0 - depth × recovery_aggression)
```
- `recovery_aggression` evolved per island (0.3–1.0)
- At max drawdown → factor = 0.1 (survival mode)

**Anti-ruin guarantee**: `SafetySizing.can_afford_cycle()` checked after all scaling. If unaffordable, size reduced or entry blocked.

## 7. Pipeline Class

```python
class IslandPilot(Pipeline):
    def __init__(self, config: dict):
        self.regime_tree = RegimeTree(config.get('regime', {}))
        self.evolver = IslandEvolver(config.get('evolution', {}))
        self.inferencer = RegimeInferencer(self.regime_tree, config.get('inference', {}))
        self.sizer = AdaptiveSizer(config.get('sizing', {}))
        self.active_regime_id = None
        self.active_genome = None
        self.regime_confidence = 0.0
        self.warmup_remaining = config.get('warmup', 100)

    def on_before(self, strategy):
        if self.warmup_remaining > 0:
            self.warmup_remaining -= 1
            return
        regime_id, confidence, probs = self.inferencer.classify(strategy)
        if regime_id != self.active_regime_id:
            self.active_regime_id = regime_id
            self.active_genome = self.evolver.get_best_genome(regime_id)
        self.regime_confidence = confidence
        self._apply_genome(strategy, self.active_genome)

    def gate_entry(self, strategy) -> bool:
        if self.active_genome is None:
            return False
        if self.regime_confidence < self.active_genome['gate_confidence_min']:
            return False
        return True

    def adjust_size(self, strategy, qty, side) -> float:
        return self.sizer.compute(
            base_pct=self.active_genome['base_size_pct'],
            confidence=self.regime_confidence,
            sensitivity=self.active_genome.get('confidence_sensitivity', 1.0),
            drawdown_pct=self._get_drawdown_pct(strategy),
            recovery_aggression=self.active_genome.get('recovery_aggression', 0.5),
            balance=strategy.balance,
            strategy=strategy,
            qty=qty
        )

    def filter_order(self, strategy, order_intent) -> dict:
        if self.active_genome:
            order_intent['tp_atr_mult'] = self.active_genome['tp_distance_atr_mult']
            order_intent['hedge_atr_mult'] = self.active_genome['hedge_distance_atr_mult']
            order_intent['max_levels'] = self.active_genome['max_levels']
            order_intent['sizing_curve'] = self.active_genome['sizing_curve']
            order_intent['sizing_factor'] = self.active_genome['sizing_factor']
        return order_intent

    def suggest_exit(self, strategy) -> dict:
        if self.active_genome is None:
            return {'action': 'hold'}
        aggressiveness = self.active_genome['abort_aggressiveness']
        danger = self._compute_danger(strategy)
        if danger > (1.0 - aggressiveness):
            return {'action': 'abort', 'reason': 'island_abort_threshold'}
        return {'action': 'hold'}

    def on_cycle_end(self, pnl, strategy):
        if self.active_regime_id is not None:
            self.evolver.record_outcome(
                regime_id=self.active_regime_id,
                genome_id=self.active_genome['id'],
                pnl=pnl,
                metrics=self._extract_cycle_metrics(strategy)
            )

    def get_stats(self) -> dict:
        return {
            'regime_distribution': self.inferencer.get_regime_counts(),
            'regime_transitions': self.inferencer.get_transition_log(),
            'island_fitness': self.evolver.get_fitness_summary(),
            'migration_events': self.evolver.get_migration_log(),
            'sizing_stats': self.sizer.get_stats(),
            'confidence_calibration': self.inferencer.get_calibration_data(),
            'active_regime': self.active_regime_id,
            'population_diversity': self.evolver.get_diversity_stats(),
        }

    def save_state(self, path):
        self.regime_tree.save(path / 'regime_tree.pkl')
        self.evolver.save(path / 'island_genomes.json')
        self.inferencer.save(path / 'inferencer_state.json')
        self.sizer.save(path / 'sizer_state.json')

    def load_state(self, path):
        self.regime_tree.load(path / 'regime_tree.pkl')
        self.evolver.load(path / 'island_genomes.json')
        self.inferencer.load(path / 'inferencer_state.json')
        self.sizer.load(path / 'sizer_state.json')
```

## 8. Strategy Interaction

The pipeline overrides strategy hyperparameters at runtime via `_apply_genome()`. The strategy doesn't know it's being controlled — it reads from its `hp` dict which the pipeline modifies. This means IslandPilot works with **any** martingale strategy (Surefire, SurefireV2, UniversalMartingale) without strategy modifications.

## 9. Experimental Protocol

### Data Split

```
Data: EUR-USD 2006–2025 (~10.4M 1m candles)

Split:
├── Train:       2006–2018 (12yr) — regime discovery + island evolution
├── Validation:  2018–2021 (3yr)  — hyperparameter tuning, early stopping
└── Test:        2021–2025 (4yr)  — NEVER touched during training
```

### Walk-Forward Validation

```
Window 1: Train 2006-2015, Val 2015-2018, Test 2018-2020
Window 2: Train 2008-2018, Val 2018-2020, Test 2020-2022
Window 3: Train 2010-2020, Val 2020-2022, Test 2022-2025
Aggregate: mean ± std across windows
```

### Ablation Study (8 Variants)

| Variant | What it measures |
|---------|-----------------|
| Full IslandPilot | Complete system (control) |
| No migration | Value of genetic exchange |
| Flat clustering (no hierarchy) | Value of hierarchical regimes |
| Single global island | Value of regime-specificity |
| Random configs per regime | Value of evolution |
| Hard switch (no hysteresis) | Value of hysteresis |
| Uniform sizing (no adaptive) | Value of sizing operator |
| GridPilot baseline | Improvement over existing pipeline |
| No pipeline (raw strategy) | Total pipeline value |

### Statistical Rigor

- 5 random seeds per experiment (GA initialization + train/test splits)
- Paired Wilcoxon signed-rank test between full pipeline and each ablation
- Bootstrap 95% confidence intervals on all key metrics
- Cohen's d effect size for each comparison

### Output Metrics

**Table 1 — Strategy-level**: Net profit %, profit factor, bust rate, win rate, max drawdown %, Sharpe, Sortino, Calmar, Kelly fraction, avg cycles to bust recovery, VaR 95/99, CVaR

**Table 2 — Pipeline-specific**: Regime classification accuracy, regime stability, hysteresis effectiveness, migration impact, island diversity, confidence calibration, feature importance ranking

**Table 3 — Ablation results**: Each variant vs full pipeline

**Table 4 — Statistical significance**: p-values, CIs, effect sizes

### Output Artifacts

```
results/
├── tables/
│   ├── main_results.csv
│   ├── pipeline_metrics.csv
│   ├── ablation_results.csv
│   └── significance_tests.csv
├── plots/
│   ├── regime_map.png              # t-SNE/UMAP of regime clusters
│   ├── fitness_convergence.png     # Per-island fitness over generations
│   ├── migration_flow.png          # Sankey of gene flow
│   ├── regime_transitions.png      # Timeline on price chart
│   ├── equity_curves.png           # All variants overlaid
│   ├── drawdown_comparison.png     # Drawdown profiles
│   ├── confidence_calibration.png  # Calibration plot
│   ├── feature_importance.png      # Bar chart
│   └── ablation_waterfall.png      # Component contribution waterfall
├── models/
│   ├── regime_tree.pkl
│   ├── island_genomes.json
│   └── feature_selector.pkl
└── report.json
```

## 10. File Structure

### Pipeline Module

```
pipelines/_shared/IslandPilot/
├── __init__.py              # IslandPilot(Pipeline) class
├── config.py                # Default config, validation, presets
└── models/                  # Pre-trained state (populated after research)
    ├── regime_tree.pkl
    ├── island_genomes.json
    ├── feature_selector.pkl
    └── inferencer_state.json
```

### Framework Components

```
qengine/framework/components/
├── (existing files...)
├── regime_tree.py           # RegimeTree, MacroCluster, SubCluster
├── island_evolver.py        # IslandEvolver, Population, Genome, Migrator
├── regime_inferencer.py     # RegimeInferencer, StickySelector
├── adaptive_sizer.py        # AdaptiveSizer
└── feature_selector.py      # FeaturePool, automated feature selection
```

### Research Scripts

```
notebooks/phase4/
├── 40_regime_discovery.py        # Feature selection + hierarchy building
├── 41_island_evolution.py        # GA training with convergence tracking
├── 42_inference_validation.py    # Regime classification hold-out accuracy
├── 43_full_pipeline_backtest.py  # Complete pipeline test-set evaluation
├── 44_ablation_study.py          # All 8 ablation variants
├── 45_statistical_tests.py       # Significance, bootstrap CIs, effect sizes
├── 46_walk_forward.py            # 3-window walk-forward validation
├── 47_comparison_baselines.py    # vs GridPilot, published methods
├── run_pipeline.py               # Orchestrator: runs 40→47
├── utils.py                      # Shared helpers
├── results/                      # Output artifacts
└── FINDINGS.md                   # Auto-generated summary
```

### Tests

```
tests/unit/
├── test_regime_tree.py
├── test_island_evolver.py
├── test_regime_inferencer.py
├── test_adaptive_sizer.py
├── test_feature_selector.py
└── test_island_pilot.py

tests/integration/
└── test_island_pilot_backtest.py
```

## 11. Dependencies

- `scikit-learn` (GMM, feature selection) — already available
- `numpy` (GA operations) — already available
- `matplotlib` (plots) — already available
- No new heavy dependencies. GA implemented from scratch for full control.

## 12. Configuration Example

```python
pipeline_config = {
    "name": "IslandPilot",
    "regime": {
        "feature_pool_size": 35,
        "macro_features_k": "auto",     # BIC selects
        "sub_features_k": "auto",
        "min_island_cycles": 200,
        "rolling_window": 100,
    },
    "evolution": {
        "population_size": 30,
        "max_generations": 100,
        "crossover_rate": 0.7,
        "mutation_rate": 0.2,
        "mutation_sigma_pct": 0.05,
        "elitism_count": 2,
        "migration_interval": 5,
        "cross_macro_interval": 20,
        "early_stop_patience": 15,
        "early_stop_threshold": 0.005,
        "fitness_weights": {
            "net_profit": 0.3,
            "bust_rate": 0.3,
            "profit_factor": 0.2,
            "max_drawdown": 0.2,
        },
    },
    "inference": {
        "min_confidence": 0.3,
        "transition_grace_candles": 5,
    },
    "sizing": {
        "drawdown_threshold_pct": 5.0,
        "min_confidence_scale": 0.2,
        "min_drawdown_scale": 0.1,
        "max_risk_per_cycle_pct": 15.0,
    },
    "warmup": 100,
}
```
