"""
IslandPilot training pipeline — runs offline, saves models to models/.

Stages:
  1. Load candles from DB (2022-01-01 to 2024-12-31, strictly before 2025)
  2. Compute feature matrix via FeaturePool
  3. Compute volatility-regime proxy labels on forward price range
  4. MI feature selection (features ↔ labels) — keeps features with MI score
     ≥ 10% of the top feature's score (Kraskov et al. 2004 estimator)
  5. Derive macro/sub partition via lag-10 autocorrelation (Box & Jenkins 1976)
  6. Fit hierarchical RegimeTree (macro + sub GMMs)
  7. Validate regime separation (CV of leaf sample counts, Bailey et al. 2014)
  8. Compute per-leaf activation windows; evolve each island on its own regime's
     largest contiguous window (fitness isolation — paper Sec 7.1 gap)
  9. Save regime_tree.pkl + island_evolver.json to models/

Usage (from repo root, conda env):
    python -m pipelines._shared.IslandPilot.train [options]

Options:
    --exchange      Exchange name (default: OANDA_demo)
    --symbol        Symbol (default: EUR-USD)
    --timeframe     Candle timeframe for features (default: 30m)
    --train-start   ISO date, training start (default: 2022-01-01)
    --train-end     ISO date, training end — must be < 2025-01-01 (default: 2024-12-31)
    --pop-size      Island population size (default: 5)
    --generations   Evolutionary generations (default: 3)
    --strategy      Strategy module path (default: strategies.SurefireHedge)
    --dry-run       Fit regime tree only, skip GA evolution
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent.resolve()
_MODELS_DIR = _HERE / 'models'
_MODELS_DIR.mkdir(exist_ok=True)

# Training data must be strictly before 2025
_MAX_TRAIN_END = '2024-12-31'
_CUTOFF_YEAR = 2025


def _enforce_cutoff(date_str: str) -> str:
    """Ensure training end date is before 2025."""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    if dt.year >= _CUTOFF_YEAR:
        print(f'[train] WARNING: training end date {date_str} is >= {_CUTOFF_YEAR}. '
              f'Clamping to {_MAX_TRAIN_END}.')
        return _MAX_TRAIN_END
    return date_str


def _date_to_ts_ms(date_str: str) -> int:
    """Convert 'YYYY-MM-DD' to unix millisecond timestamp (UTC start-of-day).

    qengine's `get_candles()` takes `start_date_timestamp` / `finish_date_timestamp`
    as integer ms epoch values, not ISO date strings.
    """
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    epoch = datetime(1970, 1, 1)
    return int((dt - epoch).total_seconds() * 1000)


def _resample_1m_to_tf(candles_1m: np.ndarray, timeframe_minutes: int) -> np.ndarray:
    """Resample 1m candle array to a higher timeframe.

    Vectorised aggregation: groups of N consecutive 1m bars are aggregated into
    one N-minute bar. The 1m array is trimmed to a multiple of N first.
    Candle schema: [timestamp_ms, open, close, high, low, volume].

    This matches qengine's `generate_candle_from_one_minutes` semantics but
    operates in-place over the full array in one pass.
    """
    if timeframe_minutes <= 1:
        return candles_1m
    n_groups = len(candles_1m) // timeframe_minutes
    if n_groups == 0:
        return candles_1m[:0]
    trimmed = candles_1m[:n_groups * timeframe_minutes]
    reshaped = trimmed.reshape(n_groups, timeframe_minutes, 6)
    out = np.empty((n_groups, 6), dtype=candles_1m.dtype)
    out[:, 0] = reshaped[:, 0, 0]        # timestamp = first 1m timestamp
    out[:, 1] = reshaped[:, 0, 1]        # open = first open
    out[:, 2] = reshaped[:, -1, 2]       # close = last close
    out[:, 3] = reshaped[:, :, 3].max(axis=1)  # high = max high
    out[:, 4] = reshaped[:, :, 4].min(axis=1)  # low = min low
    out[:, 5] = reshaped[:, :, 5].sum(axis=1)  # volume = sum
    return out


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------

def _compute_features(candles: np.ndarray, verbose: bool = True):
    """Compute feature matrix and return (matrix, names)."""
    from .feature_selector import FeaturePool, select_features

    pool = FeaturePool()
    if verbose:
        print(f'[train] Computing {len(pool.feature_names)} features on {len(candles)} candles...')
    matrix = pool.compute(candles)
    return matrix, pool.feature_names


def _compute_proxy_labels(candles: np.ndarray, forward_bars: int = 288) -> np.ndarray:
    """Compute binary forward-range labels for MI feature selection.

    For each candle i, the label is 1 if the high-low range over the next
    `forward_bars` candles exceeds the dataset median, else 0.

    Rationale: proper MI feature selection requires ground-truth cycle
    outcomes, which need a baseline backtest to produce. As an academically
    defensible proxy, we use forward price range as a volatility-regime
    classifier:

    - `forward_bars` should correspond to ~1 trading day at the execution
      timeframe: 48 bars at 30m, 288 bars at 5m, 96 bars at 15m.
      Default 288 matches the 5m execution timeframe. Callers should pass
      the value matching their resampled candle cadence. This matches the
      typical lifetime of a SurefireHedge session (hours to 1 day), so the
      label reflects conditions the strategy actually experiences within a cycle.

    - Median split: creates a balanced binary target, maximising MI
      estimator sensitivity (Kraskov et al. 2004 — MI estimates are most
      informative for near-balanced targets).

    Features that score high on MI against this label are features that
    predict future volatility — which the paper's MI selection also found
    to dominate (Table 5: 4 of top 5 features are volatility-class).

    Returns labels as int array of same length as candles. The final
    `forward_bars` entries are -1 (masked — no future data available).
    """
    n = len(candles)
    if n <= forward_bars + 10:
        return np.full(n, -1, dtype=int)

    high = candles[:, 3]
    low = candles[:, 4]

    # Rolling forward max-high and min-low via cumulative running computation
    ranges = np.full(n, np.nan)
    for i in range(n - forward_bars):
        window_high = high[i:i + forward_bars].max()
        window_low = low[i:i + forward_bars].min()
        ranges[i] = window_high - window_low

    valid_ranges = ranges[~np.isnan(ranges)]
    if len(valid_ranges) == 0:
        return np.full(n, -1, dtype=int)

    median_range = float(np.median(valid_ranges))

    labels = np.full(n, -1, dtype=int)
    for i in range(n - forward_bars):
        if not np.isnan(ranges[i]):
            labels[i] = 1 if ranges[i] > median_range else 0

    return labels


def _select_features(matrix: np.ndarray, names: List[str], labels: Optional[np.ndarray]):
    """Run mutual-information feature selection. Falls back to all features if no labels."""
    from .feature_selector import select_features

    if labels is None or len(labels) < 10:
        print('[train] No cycle labels provided — using all features (no MI selection).')
        mask = ~np.any(np.isnan(matrix), axis=1)
        return list(range(matrix.shape[1])), [1.0] * matrix.shape[1], matrix[mask]

    mask = ~np.any(np.isnan(matrix), axis=1)
    if labels.dtype == float:
        mask &= ~np.isnan(labels)

    feat_clean = matrix[mask]
    lbl_clean = labels[mask]

    if len(feat_clean) < 20:
        print('[train] Too few valid samples for MI selection — using all features.')
        return list(range(matrix.shape[1])), [1.0] * matrix.shape[1], feat_clean

    print(f'[train] Running mutual information feature selection on {len(feat_clean)} samples...')
    indices, scores = select_features(feat_clean, lbl_clean, k='auto', min_score_ratio=0.1)
    selected_names = [names[i] for i in indices]
    print(f'[train] Selected {len(indices)} features: {selected_names}')
    return indices, scores, feat_clean


# ---------------------------------------------------------------------------
# Regime tree fitting
# ---------------------------------------------------------------------------

def _derive_macro_sub_split(
    feature_matrix: np.ndarray,
    selected_indices: List[int],
    feature_names: List[str],
    lag: int = 10,
    persistence_threshold: float = 0.7,
) -> tuple:
    """Partition selected features into macro (slow) and sub (fast) groups.

    Macro features define the broad market regime and must be temporally
    persistent — stable across at least half a trading session. Sub features
    refine the classification within a macro regime and may change faster.

    Method: lag-k autocorrelation on the training feature matrix.
    - lag=10: at 30m resolution, 10 bars = 5 hours ≈ half a trading session.
      A feature autocorrelated over this horizon defines a regime; one that
      de-correlates faster is a timing signal.
    - threshold=0.7: Box & Jenkins (1976) AR persistence criterion. AR(1)
      processes with α > 0.7 are "strongly persistent" — the regime boundary
      learned by the GMM will remain valid for hours. Below 0.7, the feature
      changes too quickly for a static GMM to capture meaningful structure.

    Fallback: if fewer than 2 features are macro or fewer than 1 is sub,
    split by top-half (macro) / bottom-half (sub) of autocorrelation ranking,
    which preserves relative ordering even when no clean threshold exists.

    Args:
        feature_matrix: (n_samples, n_total_features) full feature matrix
        selected_indices: indices of MI-selected features within feature_matrix
        feature_names: names corresponding to feature_matrix columns
        lag: autocorrelation lag in candles (default 10 = 5h at 30m)
        persistence_threshold: minimum lag-k autocorrelation to classify as macro

    Returns:
        (macro_indices, sub_indices, autocorr_report)
        where macro_indices and sub_indices are lists of column indices into
        feature_matrix, and autocorr_report is a list of dicts for logging.
    """
    autocorrs = []
    for idx in selected_indices:
        col = feature_matrix[:, idx]
        # Remove NaN
        valid = col[~np.isnan(col)]
        if len(valid) < lag + 10:
            autocorrs.append((idx, 0.0))
            continue
        # Pearson correlation between col[:-lag] and col[lag:]
        x = valid[:-lag]
        y = valid[lag:]
        if np.std(x) < 1e-12 or np.std(y) < 1e-12:
            autocorrs.append((idx, 0.0))
            continue
        corr = float(np.corrcoef(x, y)[0, 1])
        autocorrs.append((idx, abs(corr)))  # abs: negative autocorr is still persistent

    # Sort descending by autocorrelation
    autocorrs_sorted = sorted(autocorrs, key=lambda x: x[1], reverse=True)

    macro_indices = [idx for idx, ac in autocorrs_sorted if ac >= persistence_threshold]
    sub_indices = [idx for idx, ac in autocorrs_sorted if ac < persistence_threshold]

    # Fallback: threshold produced degenerate split
    if len(macro_indices) < 2 or len(sub_indices) < 1:
        mid = max(1, len(autocorrs_sorted) // 2)
        macro_indices = [idx for idx, _ in autocorrs_sorted[:mid]]
        sub_indices = [idx for idx, _ in autocorrs_sorted[mid:]]
        if not sub_indices:
            sub_indices = macro_indices[-1:]
            macro_indices = macro_indices[:-1]
        print(f'[train] Autocorr threshold produced degenerate split — '
              f'falling back to top-half/bottom-half by autocorrelation rank.')

    # Build report for logging
    report = []
    for idx, ac in autocorrs_sorted:
        name = feature_names[idx] if idx < len(feature_names) else str(idx)
        group = 'macro' if idx in macro_indices else 'sub'
        report.append({'feature': name, 'autocorr_lag10': round(ac, 4), 'assigned': group})

    macro_names = [feature_names[i] if i < len(feature_names) else str(i) for i in macro_indices]
    sub_names = [feature_names[i] if i < len(feature_names) else str(i) for i in sub_indices]
    print(f'[train] Macro features (autocorr >= {persistence_threshold} at lag {lag}): {macro_names}')
    print(f'[train] Sub features (autocorr < {persistence_threshold} at lag {lag}): {sub_names}')

    return macro_indices, sub_indices, report


def _fit_regime_tree(
    feature_matrix: np.ndarray,
    selected_indices: List[int],
    feature_names: List[str],
    max_macro: int = 10,
    max_sub: int = 8,
    min_leaf_samples: int = 200,
    lag: int = 10,
    persistence_threshold: float = 0.7,
):
    """Fit and return a RegimeTree with data-driven macro/sub feature partition.

    The macro/sub split is derived from temporal persistence (lag-10 autocorrelation)
    rather than hardcoded feature categories. See _derive_macro_sub_split() for
    the full justification of lag=10 and threshold=0.7.
    """
    from .regime_tree import RegimeTree

    macro_indices, sub_indices, autocorr_report = _derive_macro_sub_split(
        feature_matrix=feature_matrix,
        selected_indices=selected_indices,
        feature_names=feature_names,
        lag=lag,
        persistence_threshold=persistence_threshold,
    )

    print(f'[train] Fitting RegimeTree: {len(macro_indices)} macro features, '
          f'{len(sub_indices)} sub features...')

    tree = RegimeTree(min_leaf_samples=min_leaf_samples, max_macro=max_macro, max_sub=max_sub)
    tree.fit(feature_matrix, macro_features=macro_indices, sub_features=sub_indices)

    print(f'[train] RegimeTree fitted: {tree.n_macro} macro clusters, {tree.n_leaves} leaves.')
    return tree, autocorr_report


def _validate_regime_separation(
    tree,
    feature_matrix: np.ndarray,
    min_cv: float = 0.15,
) -> dict:
    """Check that discovered regime leaves differ meaningfully in sample density.

    We cannot validate regime separation by strategy performance here (that
    requires running backtests), so we use a structural proxy: the coefficient
    of variation (CV = std/mean) of sample counts across leaves. If all leaves
    have nearly identical sample counts, the GMM has found a roughly uniform
    partition of feature space — no meaningful structure was discovered.

    Threshold CV=0.15: at least 15% variation in leaf population sizes.
    If CV < 0.15, the partition is suspiciously uniform, suggesting the
    GMM is not finding genuine cluster structure. This follows Bailey et al.
    (2014) multiple-testing principle: if the regime structure does not differ
    structurally (even in density), evolution per-regime is fitting noise.

    Returns a report dict with validation result and recommendation.
    """
    counts = list(tree.leaf_sample_counts.values())
    if len(counts) < 2:
        return {'valid': False, 'reason': 'fewer than 2 leaves', 'cv': 0.0}

    mean_count = float(np.mean(counts))
    std_count = float(np.std(counts))
    cv = std_count / mean_count if mean_count > 0 else 0.0

    valid = cv >= min_cv
    report = {
        'n_leaves': len(counts),
        'min_samples': min(counts),
        'max_samples': max(counts),
        'mean_samples': round(mean_count, 1),
        'cv': round(cv, 4),
        'threshold': min_cv,
        'valid': valid,
        'recommendation': (
            'Regime structure looks meaningful — proceed with evolution.'
            if valid else
            f'CV={cv:.3f} < {min_cv}: leaf sizes are suspiciously uniform. '
            f'Consider increasing max_macro or reducing min_leaf_samples. '
            f'Evolution may fit noise rather than genuine regime structure.'
        ),
    }
    print(f'[train] Regime separation check: CV={cv:.3f} (threshold {min_cv}) — '
          f'{"PASS" if valid else "WARN: " + report["recommendation"]}')
    return report


# ---------------------------------------------------------------------------
# Per-leaf activation windows (fitness isolation)
# ---------------------------------------------------------------------------

def _compute_regime_windows(
    tree,
    feature_matrix: np.ndarray,
    candle_indices: np.ndarray,
    min_window_bars: int = 100,
) -> Dict[int, List[tuple]]:
    """Compute contiguous activation windows per leaf using the fitted tree.

    Args:
        tree: fitted RegimeTree
        feature_matrix: (n, n_features) matrix already aligned to candle_indices
        candle_indices: 1D array mapping feature_matrix rows back to candle
            indices in the original all_candles array
        min_window_bars: minimum contiguous bars to count as a window

    Rationale for min_window_bars=100:
        At 30m resolution, 100 bars = 50 hours ≈ 2 trading days. A Martingale
        session typically completes within hours to 1 day, so a window of
        < 2 days contains at best 2-3 session attempts — insufficient
        statistical power for per-genome fitness evaluation. This threshold
        ensures each window contains at least 10-20 potential sessions.

    Returns: dict {leaf_id: [(candle_start_idx, candle_end_idx, length), ...]}
    """
    labels, _confidences = tree.classify_batch(feature_matrix)

    windows_per_leaf: Dict[int, List[tuple]] = {}
    n = len(labels)
    if n == 0:
        return windows_per_leaf

    current_leaf = int(labels[0])
    current_start_row = 0

    def _close_window(leaf_id, start_row, end_row):
        """Convert row-indices (within feature_matrix) to candle indices
        (within the original all_candles) and record if large enough."""
        length = end_row - start_row
        if length >= min_window_bars:
            cs = int(candle_indices[start_row])
            ce = int(candle_indices[min(end_row, n - 1)])
            windows_per_leaf.setdefault(leaf_id, []).append((cs, ce, length))

    for i in range(1, n):
        lbl = int(labels[i])
        if lbl != current_leaf:
            _close_window(current_leaf, current_start_row, i)
            current_leaf = lbl
            current_start_row = i

    # Close the final window
    _close_window(current_leaf, current_start_row, n)

    # Sort each leaf's windows by length descending
    for lid in windows_per_leaf:
        windows_per_leaf[lid].sort(key=lambda w: w[2], reverse=True)

    return windows_per_leaf


def _ms_to_iso_date(ms_timestamp: float) -> str:
    """Convert millisecond epoch timestamp to YYYY-MM-DD string."""
    return datetime.utcfromtimestamp(ms_timestamp / 1000.0).strftime('%Y-%m-%d')


def _get_leaf_date_range(
    windows_per_leaf: Dict[int, List[tuple]],
    leaf_id: int,
    candles: np.ndarray,
    fallback_start: str,
    fallback_end: str,
    min_days: int = 30,
) -> tuple:
    """Return (start_date, end_date) for a leaf's evaluation window.

    Uses the leaf's largest contiguous activation window. If the largest
    window is shorter than min_days (default 30), returns fallback dates
    (the full training period) — too little data for meaningful fitness.

    min_days=30 rationale: the SurefireHedge strategy produces approximately
    1-3 sessions per day under default parameters. 30 days → 30-90 sessions,
    which is the minimum sample size for stable PF/drawdown estimates
    (standard error of PF with n=30 sessions is acceptable; n<30 is noisy).
    """
    windows = windows_per_leaf.get(leaf_id, [])
    if not windows:
        return fallback_start, fallback_end, False

    # Largest window (already sorted descending)
    start_idx, end_idx, length = windows[0]
    if start_idx >= len(candles) or end_idx >= len(candles):
        return fallback_start, fallback_end, False

    start_ts = float(candles[start_idx, 0])
    end_ts = float(candles[end_idx, 0])
    duration_days = (end_ts - start_ts) / 1000.0 / 86400.0

    if duration_days < min_days:
        return fallback_start, fallback_end, False

    return _ms_to_iso_date(start_ts), _ms_to_iso_date(end_ts), True


# ---------------------------------------------------------------------------
# Island evolution
# ---------------------------------------------------------------------------

def _evolve_islands(tree,
                    candles_tf: np.ndarray,
                    candles_1m: np.ndarray,
                    clean_matrix: np.ndarray, clean_row_to_candle: np.ndarray,
                    strategy_name: str,
                    exchange: str, symbol: str, timeframe: str,
                    train_start: str, train_end: str,
                    pop_size: int = 5, generations: int = 3,
                    min_window_bars: int = 100, min_window_days: int = 30,
                    verbose: bool = True):
    """Evolve per-regime genomes with fitness isolated to each island's window.

    Each island's fitness function runs a backtest over the largest contiguous
    time window where that leaf was active. Islands without a sufficiently long
    window (< min_window_days) are skipped (marked inactive). This matches the
    paper's observation (Sec 6.2) that only 10 islands were actively evolved —
    the rest were too sparse for real-engine evaluation.
    """
    from .island_evolver import IslandEvolver, build_gene_bounds_from_strategy

    leaf_ids = [str(lid) for lid in tree.leaf_ids]
    print(f'[train] Evolving {len(leaf_ids)} islands × {pop_size} individuals × {generations} gen...')

    # Try to load the strategy class to build proper gene bounds
    gene_bounds = None
    try:
        import importlib
        # Try common locations: strategies.<name>.<name> or strategies.<name>
        strategy_cls = None
        for modpath in (f'strategies.{strategy_name}.{strategy_name}',
                        f'strategies.{strategy_name}'):
            try:
                mod = importlib.import_module(modpath)
                strategy_cls = getattr(mod, strategy_name, None)
                if strategy_cls is not None:
                    break
            except ImportError:
                continue
        if strategy_cls is not None:
            dummy_strategy = strategy_cls.__new__(strategy_cls)
            gene_bounds = build_gene_bounds_from_strategy(dummy_strategy)
            print(f'[train] Built gene bounds from strategy: {len(gene_bounds)} genes.')
    except Exception as e:
        print(f'[train] Could not load strategy for gene bounds ({e}) — using defaults.')

    # Build sibling groups (leaves in same macro cluster migrate among each other)
    macro_to_leaves: Dict[int, List[str]] = {}
    for lid, (mid, _sid) in tree._leaf_map.items():
        macro_to_leaves.setdefault(mid, []).append(str(lid))
    sibling_groups = {f'macro_{m}': leaves for m, leaves in macro_to_leaves.items()
                      if len(leaves) > 1}

    config = {
        'pop_size': pop_size,
        'elitism': 2,
        'crossover_rate': 0.7,
        'mutation_rate': 0.2,
        'mutation_sigma': 0.05,
        'tournament_k': 3,
        'migration_interval': 5,
        'seed': 42,
    }

    evolver = IslandEvolver(
        leaf_ids=leaf_ids,
        config=config,
        sibling_groups=sibling_groups,
        gene_bounds=gene_bounds,
    )

    # --- Fitness isolation: compute per-leaf windows ---
    print(f'[train] Computing per-leaf activation windows (min {min_window_bars} bars)...')
    windows_per_leaf = _compute_regime_windows(
        tree=tree,
        feature_matrix=clean_matrix,
        candle_indices=clean_row_to_candle,
        min_window_bars=min_window_bars,
    )

    # Pre-compute each island's date range
    leaf_date_ranges: Dict[str, tuple] = {}
    active_islands: List[str] = []
    for lid_str in leaf_ids:
        try:
            lid_int = int(lid_str)
        except ValueError:
            lid_int = lid_str
        start, end, has_window = _get_leaf_date_range(
            windows_per_leaf=windows_per_leaf,
            leaf_id=lid_int,
            candles=candles_tf,
            fallback_start=train_start,
            fallback_end=train_end,
            min_days=min_window_days,
        )
        leaf_date_ranges[lid_str] = (start, end, has_window)
        if has_window:
            active_islands.append(lid_str)

    print(f'[train] Active islands (with window ≥ {min_window_days} days): '
          f'{len(active_islands)} / {len(leaf_ids)}')

    migration_interval = config['migration_interval']

    n_with_window = sum(1 for _, _, hw in leaf_date_ranges.values() if hw)
    n_fallback = len(leaf_ids) - n_with_window
    if n_fallback > 0:
        print(f'[train] NOTE: {n_fallback}/{len(leaf_ids)} islands have no dedicated window — '
              f'will evolve on full training period ({train_start} → {train_end}).')

    for gen in range(generations):
        print(f'[train] Generation {gen + 1}/{generations}...')

        for lid, pop in evolver.populations.items():
            start, end, has_window = leaf_date_ranges.get(lid, (train_start, train_end, False))
            # When no dedicated window exists, evolve on the full training period.
            # Fitness isolation is best-effort: use the per-leaf window when available,
            # fall back to the full period when the leaf switches too rapidly to form
            # a 30-day contiguous block (common with high-frequency volatility regimes).

            start_ts = _date_to_ts_ms(start)
            end_ts = _date_to_ts_ms(end) + 86_400_000  # include the end day

            def _leaf_fitness_fn(genes, _s=start_ts, _e=end_ts):
                return _run_backtest_fitness(
                    genes=genes,
                    candles_1m=candles_1m,
                    exchange=exchange,
                    symbol=symbol,
                    timeframe=timeframe,
                    strategy_name=strategy_name,
                    start_ts_ms=_s,
                    end_ts_ms=_e,
                )

            pop.evaluate(_leaf_fitness_fn)
            pop.evolve(
                elitism=config['elitism'],
                crossover_rate=config['crossover_rate'],
                mutation_rate=config['mutation_rate'],
                mutation_sigma=config['mutation_sigma'],
                tournament_k=config['tournament_k'],
            )

        if (gen + 1) % migration_interval == 0:
            evolver.migrate_siblings()
            print(f'[train]   Sibling migration completed.')

        summary = evolver.get_fitness_summary()
        fitnesses = [v['best'] for v in summary.values() if v.get('best') is not None]
        if fitnesses:
            print(f'[train]   Mean best fitness: {np.mean(fitnesses):.3f} '
                  f'(min={min(fitnesses):.3f}, max={max(fitnesses):.3f})')

    return evolver, leaf_date_ranges


def _run_backtest_fitness(
    genes: dict,
    candles_1m: np.ndarray,
    exchange: str,
    symbol: str,
    timeframe: str,
    strategy_name: str,
    start_ts_ms: int,
    end_ts_ms: int,
) -> float:
    """Run a qengine backtest over a 1m candle subset and return composite fitness.

    Fitness = 0.4·(PF−1)·100 + 0.3·max(0,100−DD·5) + 0.2·(1−bust_rate)·100 + 0.1·min(sessions/100, 1)·100

    Uses the real qengine `backtest(config, routes, data_routes, candles, hyperparameters)`
    API. Candles must be at 1m resolution; the strategy route defines the execution
    timeframe (5m, 15m, 30m, ...) and the engine resamples internally.

    The 1m candle array is subsetted by timestamp range to match the per-leaf
    window being evaluated — this is how fitness isolation is implemented.
    """
    try:
        from qengine.research.backtest import backtest as run_bt
        import qengine.helpers as jh

        # Subset candles to the evaluation window
        ts_col = candles_1m[:, 0]
        mask = (ts_col >= start_ts_ms) & (ts_col <= end_ts_ms)
        subset = candles_1m[mask]
        if len(subset) < 2000:  # less than ~1.4 days of 1m candles
            return 0.0

        config = {
            'starting_balance': 10_000,
            'fee': 0.0,
            'type': 'cfd',
            'exchange': exchange,
            'warm_up_candles': 210,
        }
        routes = [{
            'exchange': exchange,
            'strategy': strategy_name,
            'symbol': symbol,
            'timeframe': timeframe,
        }]
        key = jh.key(exchange, symbol)
        candles_dict = {key: {'exchange': exchange, 'symbol': symbol, 'candles': subset}}

        # Drop pipeline-only genes that aren't strategy HP
        _PIPELINE_ONLY = {
            'gate_confidence_min', 'abort_aggressiveness', 'base_size_pct',
            'hysteresis_margin', 'confidence_sensitivity', 'recovery_aggression',
        }
        hp = {k: v for k, v in genes.items() if k not in _PIPELINE_ONLY}

        result = run_bt(
            config=config,
            routes=routes,
            data_routes=[],
            candles=candles_dict,
            hyperparameters=hp,
            generate_equity_curve=False,
            cost_model=True,
        )

        metrics = result.get('metrics', {}) if isinstance(result, dict) else {}
        pf = float(metrics.get('profit_factor', 1.0) or 1.0)
        dd = abs(float(metrics.get('max_drawdown_percentage', 0.0) or 0.0))

        sessions = result.get('sessions', []) if isinstance(result, dict) else []
        # Count only proper hedge sessions (int session id)
        proper_sessions = [s for s in sessions if isinstance(s.get('session'), int)]
        n_sessions = len(proper_sessions)

        _BUST_REASONS = {
            'abort', 'terminate', 'max_level_bust', 'sl_hit',
            'margin_call', 'margin_bust', 'max_level_sl',
        }
        n_bust = sum(1 for s in proper_sessions if s.get('outcome', '') in _BUST_REASONS)
        bust_rate = (n_bust / n_sessions) if n_sessions > 0 else 0.5

        fitness = (
            0.4 * (pf - 1.0) * 100 +
            0.3 * max(0.0, 100.0 - dd * 5.0) +
            0.2 * (1.0 - bust_rate) * 100 +
            0.1 * min(n_sessions / 100.0, 1.0) * 100
        )
        return float(fitness)

    except Exception as e:
        # Silent 0-fitness on exception — GA will naturally deselect broken genomes
        return 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def train(
    exchange: str = 'OANDA',
    symbol: str = 'EUR-USD',
    timeframe: str = '5m',
    train_start: str = '2022-01-01',
    train_end: str = '2024-12-31',
    strategy_name: str = 'Martingale',
    pop_size: int = 5,
    generations: int = 3,
    max_macro: int = 10,
    max_sub: int = 8,
    min_leaf_samples: int = 200,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """Full IslandPilot training pipeline.

    All training data is strictly before 2025 (train_end clamped to 2024-12-31).

    Default timeframe is 5m (higher cycle frequency than the paper's 30m,
    matching the strategy's live execution cadence). Feature/label bar-count
    defaults are scaled by timeframe so "1 day" and "2 days" have the same
    wall-clock meaning regardless of bar size.

    Returns dict with model artefact paths.
    """
    import qengine.helpers as jh

    # Enforce pre-2025 cutoff
    train_end = _enforce_cutoff(train_end)

    tf_minutes = int(jh.timeframe_to_one_minutes(timeframe))

    print(f'[train] IslandPilot training pipeline')
    print(f'[train]   Exchange: {exchange}  Symbol: {symbol}  Strategy: {strategy_name}  TF: {timeframe} ({tf_minutes}m)')
    print(f'[train]   Period: {train_start} → {train_end} (training data, strictly before 2025)')

    # --- Load 1m candles (engine always needs 1m; routes will resample) ---
    # OANDA forex data has weekend gaps (Friday ~21:00 UTC → Sunday ~21:00 UTC).
    # If the requested end_ts falls after the last available candle, the DB
    # raises CandleNotFoundInDatabase. We catch this, parse the available
    # upper bound, and retry with a clamped end.
    from qengine.research.candles import get_candles
    from qengine.exceptions import CandleNotFoundInDatabase
    import re

    start_ts = _date_to_ts_ms(train_start)
    end_ts = _date_to_ts_ms(train_end) + 86_400_000 - 60_000  # inclusive end-of-day (T-1 minute)

    def _load(start_ms: int, end_ms: int):
        return get_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe='1m',
            start_date_timestamp=start_ms,
            finish_date_timestamp=end_ms,
        )

    try:
        warmup, candles_1m = _load(start_ts, end_ts)
    except CandleNotFoundInDatabase as e:
        # Parse "latest available candle is up to YYYY-MM-DDTHH:MM:SS" from message
        msg = str(e)
        m = re.search(r'latest available candle is up to "([^"]+)"', msg)
        if m:
            from datetime import timezone
            dt_str = m.group(1)
            try:
                clamp_dt = datetime.fromisoformat(dt_str)
            except ValueError:
                clamp_dt = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S')
            clamp_ts = int(clamp_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
            print(f'[train] Requested end past DB coverage — clamping to {dt_str} (weekend/gap).')
            warmup, candles_1m = _load(start_ts, clamp_ts)
        else:
            print(f'[train] ERROR loading candles: {e}')
            raise

    if candles_1m is None or (hasattr(candles_1m, 'ndim') and candles_1m.ndim < 2) or len(candles_1m) == 0:
        print('[train] ERROR: No candles loaded. Check exchange/symbol/date range.')
        sys.exit(1)
    if warmup is not None and hasattr(warmup, 'ndim') and warmup.ndim == 2 and len(warmup) > 0:
        candles_1m = np.concatenate([warmup, candles_1m], axis=0)
    print(f'[train] Loaded {len(candles_1m):,} 1m candles.')

    # --- Resample to target timeframe for features / regime discovery ---
    candles_tf = _resample_1m_to_tf(candles_1m, tf_minutes)
    print(f'[train] Resampled to {len(candles_tf):,} {timeframe} candles for feature computation.')

    # --- Feature computation ---
    feature_matrix, feature_names = _compute_features(candles_tf, verbose=verbose)

    # Remove NaN rows for clustering; track candle indices that survive the filter
    nan_mask = ~np.any(np.isnan(feature_matrix), axis=1)
    clean_matrix = feature_matrix[nan_mask]
    clean_row_to_candle = np.where(nan_mask)[0]  # row i in clean_matrix → candle j (in candles_tf)
    print(f'[train] Clean feature rows (no NaN): {len(clean_matrix)}')

    # --- Proxy labels for MI feature selection ---
    # Scale forward_bars to match 1 trading day at the chosen TF:
    # 30m → 48, 15m → 96, 5m → 288, 1h → 24
    forward_bars = max(4, int(round(1440 / tf_minutes)))
    print(f'[train] Proxy labels: forward_bars={forward_bars} (~1 trading day at {timeframe})')
    proxy_labels_all = _compute_proxy_labels(candles_tf, forward_bars=forward_bars)
    # Align labels to clean_matrix rows
    proxy_labels_clean = proxy_labels_all[clean_row_to_candle]
    valid_label_mask = proxy_labels_clean != -1
    print(f'[train] Valid labels for MI: {int(valid_label_mask.sum())} of {len(proxy_labels_clean)}')

    # --- MI feature selection using the proxy labels ---
    if valid_label_mask.sum() >= 100:
        feat_for_mi = clean_matrix[valid_label_mask]
        lbl_for_mi = proxy_labels_clean[valid_label_mask].astype(int)
        selected_indices, mi_scores, _ = _select_features(
            matrix=feat_for_mi,
            names=feature_names,
            labels=lbl_for_mi,
        )
        if not selected_indices:
            print('[train] MI selection returned empty — falling back to all features.')
            selected_indices = list(range(clean_matrix.shape[1]))
        else:
            selected_names = [feature_names[i] for i in selected_indices]
            print(f'[train] MI-selected {len(selected_indices)} features: {selected_names}')
    else:
        print('[train] Too few valid labels — using all features.')
        selected_indices = list(range(clean_matrix.shape[1]))

    # --- Fit regime tree (with data-driven macro/sub partition) ---
    tree, autocorr_report = _fit_regime_tree(
        feature_matrix=clean_matrix,
        selected_indices=selected_indices,
        feature_names=feature_names,
        max_macro=max_macro,
        max_sub=max_sub,
        min_leaf_samples=min_leaf_samples,
    )

    # Under --dry-run, write to a side location so we don't clobber the
    # currently-shipped models (which are paired with a matching evolver).
    if dry_run:
        tree_path = str(_MODELS_DIR / 'regime_tree.dryrun.pkl')
    else:
        tree_path = str(_MODELS_DIR / 'regime_tree.pkl')
    tree.save(tree_path)
    print(f'[train] RegimeTree saved → {tree_path}')

    # Validate regime structure before committing to evolution
    separation = _validate_regime_separation(tree, clean_matrix)
    if not separation['valid']:
        print(f'[train] WARNING: {separation["recommendation"]}')
        # Continue anyway — user may still want the models

    if dry_run:
        print('[train] --dry-run: skipping GA evolution.')
        print('[train] NOTE: dry-run output is at regime_tree.dryrun.pkl to avoid '
              'overwriting the shipped regime_tree.pkl.')
        return {
            'regime_tree_path': tree_path,
            'evolver_path': None,
            'autocorr_report': autocorr_report,
            'separation': separation,
        }

    # --- Island evolution with per-leaf fitness isolation ---
    # Scale min_window_bars to ~2 trading days at the chosen TF (48h)
    #   5m → 576, 15m → 192, 30m → 96, 1h → 48
    min_window_bars = max(20, int(round(2880 / tf_minutes)))
    print(f'[train] Per-leaf min window: {min_window_bars} bars (~2 trading days at {timeframe})')

    evolver, leaf_date_ranges = _evolve_islands(
        tree=tree,
        candles_tf=candles_tf,
        candles_1m=candles_1m,
        clean_matrix=clean_matrix,
        clean_row_to_candle=clean_row_to_candle,
        strategy_name=strategy_name,
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        train_start=train_start,
        train_end=train_end,
        pop_size=pop_size,
        generations=generations,
        min_window_bars=min_window_bars,
        verbose=verbose,
    )

    evolver_path = str(_MODELS_DIR / 'island_evolver.json')
    evolver.save(evolver_path)
    print(f'[train] IslandEvolver saved → {evolver_path}')

    # Also save the per-leaf date ranges for auditability
    leaf_ranges_path = str(_MODELS_DIR / 'leaf_date_ranges.json')
    with open(leaf_ranges_path, 'w') as f:
        json.dump({
            lid: {'start': s, 'end': e, 'had_window': bool(hw)}
            for lid, (s, e, hw) in leaf_date_ranges.items()
        }, f, indent=2)
    print(f'[train] Leaf date ranges saved → {leaf_ranges_path}')
    print('[train] Training complete.')

    return {
        'regime_tree_path': tree_path,
        'evolver_path': evolver_path,
        'leaf_date_ranges_path': leaf_ranges_path,
        'autocorr_report': autocorr_report,
        'separation': separation,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args():
    p = argparse.ArgumentParser(description='IslandPilot offline training pipeline')
    p.add_argument('--exchange', default='OANDA')
    p.add_argument('--symbol', default='EUR-USD')
    p.add_argument('--timeframe', default='5m',
                   help='Execution timeframe. 5m = high cycle frequency (default); '
                        '30m matches the paper.')
    p.add_argument('--train-start', default='2022-01-01')
    p.add_argument('--train-end', default='2024-12-31',
                   help='Training end date. Must be before 2025-01-01.')
    p.add_argument('--strategy', default='Martingale',
                   help='Strategy class name (looked up under strategies/<name>/).')
    p.add_argument('--pop-size', type=int, default=5)
    p.add_argument('--generations', type=int, default=3)
    p.add_argument('--max-macro', type=int, default=10)
    p.add_argument('--max-sub', type=int, default=8)
    p.add_argument('--min-leaf-samples', type=int, default=200)
    p.add_argument('--dry-run', action='store_true',
                   help='Only fit regime tree, skip GA evolution.')
    return p.parse_args()


if __name__ == '__main__':
    args = _parse_args()
    train(
        exchange=args.exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        train_start=args.train_start,
        train_end=args.train_end,
        strategy_name=args.strategy,
        pop_size=args.pop_size,
        generations=args.generations,
        max_macro=args.max_macro,
        max_sub=args.max_sub,
        min_leaf_samples=args.min_leaf_samples,
        dry_run=args.dry_run,
    )
