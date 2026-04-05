# Phase 3 Pipeline Specification

## What We Proved (Research Summary)

| Finding | Script | Impact | Status |
|---|---|---|---|
| High vol = fast TP, PF 3.5x | 28 | Entry timing | Validated 2024-25 |
| DM_14 gate: -44% busts, keeps 93% | 27 | Entry gate | Validated 2024-25 |
| Confidence gate (NATR+ADX+ER) >= 0.4 | 33 | Entry gate | +6% PF walk-forward |
| Fibonacci x2.0 10L best practical | 30 | Sizing | $10K: 3.1% ROI |
| 15p hedge + 15p TP optimal | 29 | Grid params | Validated |
| Mid-cycle abort: DESTRUCTIVE | 23, 31 | Exit | Do NOT use |
| N-regime switching: +17% PF | 24 | Config switch | 8 regimes found |
| 5yr training window best | 25 | Data | Gen ratio 1.06 |
| Low vol = PF 0.52 (loss) | 28 | Vol filter | Critical |

## Pipeline Architecture

Uses the existing `qengine/framework/` pipeline system. One new pipeline component: `Phase3Gate`.

```
Strategy (UniversalMartingale preset=phase3_optimized)
  │
  ├─ Pipeline: Phase3Gate
  │   ├─ gate_entry()     → DM_14 check + NATR min + confidence score
  │   ├─ adjust_size()    → capital-aware sizing (bust DD < 20%)
  │   ├─ on_before()      → update rolling NATR/ADX/ER/DM values
  │   ├─ suggest_exit()   → None (no mid-cycle exit — proven destructive)
  │   └─ on_cycle_end()   → track PF, adjust confidence threshold adaptively
  │
  └─ Pipeline: DangerScorer + EntryGate (existing, optional layer)
```

## Phase3Gate Component

### gate_entry() Logic
```python
def gate_entry(self, strategy):
    # 1. DM directional movement check
    dm = ta.dm(strategy.candles, period=14)
    if dm.plus < self.dm_threshold and dm.minus < self.dm_threshold:
        return False  # No directional movement

    # 2. NATR vol minimum (skip low-vol death zone)
    natr = ta.natr(strategy.candles, period=14)
    if natr < self.natr_min:
        return False  # Too low vol — strategy loses money here

    # 3. Confidence score composite
    score = self._compute_confidence(strategy.candles)
    if score < self.confidence_threshold:
        return False  # Not confident enough

    return True  # All gates pass
```

### adjust_size() Logic
```python
def adjust_size(self, strategy, qty, side):
    # Capital-aware: scale base lot so bust DD < max_bust_dd_pct
    max_dd = strategy.balance * self.max_bust_dd_pct
    total_exposure = self._compute_max_exposure(strategy)
    if total_exposure * abs(qty) * pip_value > max_dd:
        return max_dd / (total_exposure * pip_value)
    return qty
```

### on_cycle_end() Logic
```python
def on_cycle_end(self, pnl, strategy):
    # Track rolling PF
    self.recent_pnls.append(pnl)
    if len(self.recent_pnls) > 50:
        wins = sum(1 for p in self.recent_pnls if p > 0)
        gross_p = sum(p for p in self.recent_pnls if p > 0)
        gross_l = abs(sum(p for p in self.recent_pnls if p < 0))
        rolling_pf = gross_p / gross_l if gross_l > 0 else float('inf')

        # If PF dropping below 1.0, tighten confidence threshold
        if rolling_pf < 1.0:
            self.confidence_threshold = min(0.7, self.confidence_threshold + 0.05)
        elif rolling_pf > 1.5 and self.confidence_threshold > 0.3:
            self.confidence_threshold = max(0.3, self.confidence_threshold - 0.02)
```

## Configuration

```python
pipeline_config = {
    'name': 'Phase3Gate',
    'params': {
        'dm_period': 14,
        'dm_threshold': 0.0,           # Any directional movement
        'natr_period': 14,
        'natr_min': 0.02,              # Skip bottom ~20% vol
        'confidence_threshold': 0.4,    # Conservative (0.5 for aggressive)
        'max_bust_dd_pct': 0.20,       # Bust costs at most 20% of account
        'sizing_curve': 'fibonacci',
        'sizing_factor': 2.0,
        'max_levels': 10,
        'adaptive_threshold': True,     # Auto-tighten when PF drops
    }
}
```

## Autopilot Integration

The pipeline works with the existing autopilot loop:

1. **Brain suggests** strategy HP (hedge_value, tp_value, ema_fast/slow)
2. **Backtest runs** with Phase3Gate pipeline attached
3. **Pipeline gates entries** using DM + NATR + confidence
4. **Pipeline adjusts sizing** based on account balance
5. **Results recorded** — Brain learns which HP + gate combo works
6. **Pipeline threshold adapts** via on_cycle_end feedback

## Expected Performance

Based on walk-forward validation (script 33):

| Metric | Without Pipeline | With Phase3Gate |
|---|---|---|
| PF (2024-25) | 1.15 | 1.22 (+6%) |
| Bust rate | 0.08% | 0.08% |
| Signals kept | 100% | 62% |
| Max DD ($10K) | 15.4% | ~12% (est.) |

## What NOT to Do

1. **No mid-cycle abort** — Q-learning exit confirmed destructive (43% false abort rate)
2. **No composite chop score gating** — AUC < 0.6, too noisy
3. **No geometric sizing** — 456 wins to recover 1 bust, unusable
4. **No training on pre-2020 data** — stale patterns, hurts generalization
