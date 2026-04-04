"""
43 — Full Pipeline Backtest

Runs the complete IslandPilot pipeline on test data (2025H2):
regime classification, genome lookup, gate check, adaptive sizing,
and surefire cycle simulation with per-regime breakdown.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils import *

import json
import numpy as np
import matplotlib.pyplot as plt

import qengine.indicators as ta
from qengine.framework.components.regime_tree import RegimeTree
from qengine.framework.components.island_evolver import IslandEvolver, Genome
from qengine.framework.components.adaptive_sizer import AdaptiveSizer
from qengine.framework.components.feature_selector import FeaturePool

log = get_logger('43_full_pipeline_backtest')


# ---------------------------------------------------------------------------
# EMA crossover signal generation
# ---------------------------------------------------------------------------

def generate_signals(candles: np.ndarray, fast: int = 8, slow: int = 21) -> list:
    """Find EMA crossover entry signals.

    Returns list of (index, direction) where direction is 'long' or 'short'.
    Only fires on the bar where the crossover occurs.
    """
    ema_fast = ta.ema(candles, period=fast, sequential=True)
    ema_slow = ta.ema(candles, period=slow, sequential=True)

    signals = []
    for i in range(1, len(candles)):
        if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]):
            continue
        if np.isnan(ema_fast[i - 1]) or np.isnan(ema_slow[i - 1]):
            continue
        # Bullish crossover
        if ema_fast[i - 1] <= ema_slow[i - 1] and ema_fast[i] > ema_slow[i]:
            signals.append((i, 'long'))
        # Bearish crossover
        elif ema_fast[i - 1] >= ema_slow[i - 1] and ema_fast[i] < ema_slow[i]:
            signals.append((i, 'short'))
    return signals


# ---------------------------------------------------------------------------
# Cycle simulation
# ---------------------------------------------------------------------------

def simulate_cycle(candles: np.ndarray, entry_idx: int, direction: str,
                   cfg: SimConfig) -> CycleResult:
    """Simulate a single surefire cycle from entry_idx using cfg parameters.

    Uses candle close prices to check TP/hedge triggers level by level.
    """
    n = len(candles)
    entry_price = candles[entry_idx, 2]  # close
    pip = 0.0001  # EUR-USD pip

    # Track all open tickets: (level, direction, entry_price, size)
    tickets = [(0, direction, entry_price, calc_size(0, cfg))]
    current_level = 0
    current_dir = direction

    # TP and hedge prices
    if direction == 'long':
        tp_price = entry_price + cfg.tp_pips * pip
        hedge_price = entry_price - cfg.hedge_dist_pips * pip
    else:
        tp_price = entry_price - cfg.tp_pips * pip
        hedge_price = entry_price + cfg.hedge_dist_pips * pip

    for bar in range(entry_idx + 1, min(entry_idx + cfg.max_bars, n)):
        price = candles[bar, 2]  # close
        high = candles[bar, 3]
        low = candles[bar, 4]

        # Check TP hit
        tp_hit = False
        if current_dir == 'long' and high >= tp_price:
            tp_hit = True
        elif current_dir == 'short' and low <= tp_price:
            tp_hit = True

        if tp_hit:
            # Calculate total PnL
            total_pnl = 0.0
            for lvl, d, ep, sz in tickets:
                if d == 'long':
                    total_pnl += (tp_price - ep) * sz / pip
                else:
                    total_pnl += (ep - tp_price) * sz / pip
            return CycleResult(
                bust=False, level_reached=current_level,
                pnl=total_pnl, bars_held=bar - entry_idx,
                entry_idx=entry_idx, direction=direction,
            )

        # Check hedge trigger
        hedge_hit = False
        if current_dir == 'long' and low <= hedge_price:
            hedge_hit = True
        elif current_dir == 'short' and high >= hedge_price:
            hedge_hit = True

        if hedge_hit:
            current_level += 1
            if current_level >= cfg.max_levels:
                # Bust — close everything at current price
                total_pnl = 0.0
                for lvl, d, ep, sz in tickets:
                    if d == 'long':
                        total_pnl += (price - ep) * sz / pip
                    else:
                        total_pnl += (ep - price) * sz / pip
                return CycleResult(
                    bust=True, level_reached=current_level,
                    pnl=total_pnl, bars_held=bar - entry_idx,
                    entry_idx=entry_idx, direction=direction,
                )

            # Add hedge ticket (opposite direction)
            new_dir = 'short' if current_dir == 'long' else 'long'
            new_size = calc_size(current_level, cfg)
            tickets.append((current_level, new_dir, hedge_price, new_size))
            current_dir = new_dir

            # Set new TP and hedge from hedge_price
            if new_dir == 'long':
                tp_price = hedge_price + cfg.tp_pips * pip
                hedge_price = hedge_price - cfg.hedge_dist_pips * pip
            else:
                tp_price = hedge_price - cfg.tp_pips * pip
                hedge_price = hedge_price + cfg.hedge_dist_pips * pip

    # Ran out of bars — close at last price
    last_price = candles[min(entry_idx + cfg.max_bars - 1, n - 1), 2]
    total_pnl = 0.0
    for lvl, d, ep, sz in tickets:
        if d == 'long':
            total_pnl += (last_price - ep) * sz / pip
        else:
            total_pnl += (ep - last_price) * sz / pip

    return CycleResult(
        bust=True, level_reached=current_level,
        pnl=total_pnl, bars_held=cfg.max_bars,
        entry_idx=entry_idx, direction=direction,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # 1. Load models
    tree_path = MODELS_DIR / 'regime_tree.pkl'
    evolver_path = MODELS_DIR / 'island_genomes.json'

    if not tree_path.exists():
        log.error(f"regime_tree.pkl not found at {tree_path}. Run script 40 first.")
        return
    if not evolver_path.exists():
        log.error(f"island_genomes.json not found at {evolver_path}. Run script 41 first.")
        return

    tree = RegimeTree.load(str(tree_path))
    evolver = IslandEvolver.load(str(evolver_path))
    log.info(f"Loaded tree ({tree.n_leaves} leaves) and evolver ({len(evolver.populations)} islands)")

    # 2. Load test candles
    log.info("Loading test candles 2025-07-01 to 2025-12-30 ...")
    warmup, trading = load_candles(start_date='2025-07-01', end_date='2025-12-30')
    candles = concat_candles(warmup, trading)
    log.info(f"Candles: {len(candles)} bars")

    # 3. Compute features
    log.info("Computing features ...")
    pool = FeaturePool()
    features = pool.compute(candles)

    # 4. Generate entry signals
    signals = generate_signals(candles)
    log.info(f"Generated {len(signals)} EMA crossover signals")

    # 5. Run pipeline: classify regime -> get genome -> gate -> size -> simulate
    sizer = AdaptiveSizer()
    cycles: List[CycleResult] = []
    regime_cycles: dict = {}  # regime_id -> list of CycleResult
    gated_count = 0
    equity = 10000.0
    equity_track = [equity]

    for sig_idx, (bar_idx, direction) in enumerate(signals):
        # Skip if bar_idx too close to end
        if bar_idx + 50 > len(candles):
            continue

        # Classify regime
        fv = features[bar_idx]
        if np.any(np.isnan(fv)):
            gated_count += 1
            continue

        regime_id, confidence = tree.classify_best(fv)
        regime_key = str(regime_id)

        # Get genome for this regime
        if regime_key not in evolver.populations:
            gated_count += 1
            continue

        genome_dict = evolver.get_best_genome(regime_key)
        genes = genome_dict.get('genes', genome_dict)

        # Gate check: min confidence
        gate_conf = genes.get('gate_confidence_min', 0.3)
        if confidence < gate_conf:
            gated_count += 1
            continue

        # Build SimConfig from genome
        cfg = SimConfig.from_genome(genes)

        # Adaptive sizing
        base_qty = calc_size(0, cfg)
        adjusted_qty = sizer.compute(
            base_pct=genes.get('base_size_pct', 1.0),
            confidence=confidence,
            sensitivity=genes.get('confidence_sensitivity', 1.0),
            drawdown_pct=max_drawdown_pct([c.pnl for c in cycles[-50:]]) if cycles else 0.0,
            recovery_aggression=genes.get('recovery_aggression', 0.5),
            balance=equity,
            qty=base_qty,
        )
        # Scale cfg base_size by the adaptive ratio
        if base_qty > 0:
            cfg.base_size = adjusted_qty

        # Simulate cycle
        result = simulate_cycle(candles, bar_idx, direction, cfg)
        result.regime_id = regime_id
        result.genome_id = genome_dict.get('id', 'unknown')
        cycles.append(result)

        # Track equity
        equity += result.pnl
        equity_track.append(equity)

        # Track per-regime
        regime_cycles.setdefault(regime_key, []).append(result)

    log.info(f"Completed {len(cycles)} cycles, gated {gated_count} signals")

    # 6. Compute overall and per-regime stats
    overall = cycle_summary(cycles)
    log.info(f"Overall: PF={overall['profit_factor']:.2f}, WR={overall['win_rate']:.3f}, "
             f"busts={overall['n_busts']}, net_pnl={overall['net_pnl']:.1f}")

    per_regime = {}
    for rid, rcycles in sorted(regime_cycles.items()):
        stats = cycle_summary(rcycles)
        per_regime[rid] = stats
        log.info(f"  Regime {rid}: n={stats['n_cycles']}, PF={stats['profit_factor']:.2f}, "
                 f"WR={stats['win_rate']:.3f}, busts={stats['n_busts']}")

    # 7. Plots
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: equity curve
    ax = axes[0]
    ax.plot(equity_track, color='steelblue', linewidth=1)
    ax.axhline(10000, color='gray', linestyle='--', alpha=0.5)
    ax.set_xlabel('Cycle')
    ax.set_ylabel('Equity')
    ax.set_title(f'IslandPilot Equity Curve (PF={overall["profit_factor"]:.2f})')
    ax.grid(True, alpha=0.3)

    # Right: per-regime profit factor
    ax = axes[1]
    regime_ids = sorted(per_regime.keys())
    pfs = [min(per_regime[r]['profit_factor'], 50) for r in regime_ids]  # cap for display
    colors = ['green' if pf > 1.0 else 'red' for pf in pfs]
    ax.barh(regime_ids, pfs, color=colors, alpha=0.7)
    ax.axvline(1.0, color='gray', linestyle='--', alpha=0.5)
    ax.set_xlabel('Profit Factor')
    ax.set_ylabel('Regime ID')
    ax.set_title('Per-Regime Profit Factor')

    savefig('43_full_pipeline_backtest')
    log.info("Plot saved")

    # 8. Save results
    results = {
        'overall': overall,
        'per_regime': per_regime,
        'n_signals': len(signals),
        'n_gated': gated_count,
        'n_cycles': len(cycles),
        'sizer_stats': sizer.get_stats(),
        'cycle_details': [c.to_dict() for c in cycles],
    }
    save_results(results, '43_full_pipeline_backtest')
    log.info("Results saved")


if __name__ == '__main__':
    main()
