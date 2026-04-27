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
import time as _time
from datetime import datetime
from pathlib import Path

# Module-level candles cache — set before forking workers so children inherit
# it via fork without any serialization/pickling overhead.
_WORKER_CANDLES: "np.ndarray | None" = None


def _tlog(msg: str):
    """Timestamped log — used across train() and _evolve_islands()."""
    ts = datetime.utcnow().strftime('%H:%M:%S')
    print(f'[{ts} UTC] {msg}', flush=True)


# Cached strategy spec so workers don't rebuild it on every fitness call.
_STRATEGY_HP_SPEC_CACHE: Dict[str, dict] = {}

# Must mirror _SAFE_OPTIONS in pipelines/_shared/IslandPilot/island_evolver.py.
# Only these option sets are used during training; the resolution table below
# must match the filtered order that build_gene_bounds used.
_CATEGORICAL_SAFE = {
    'signal_mode': {'random', 'ema_cross', 'rsi', 'macd', 'supertrend', 'stoch',
                    'ema_rsi', 'ema_macd', 'triple'},
    'sizing_curve': {'geometric', 'sqrt', 'linear', 'fibonacci'},
    'hedge_mode': {'fixed_pips', 'atr_based', 'percentage'},
    'tp_mode': {'fixed_pips', 'atr_based', 'bucket_pct', 'risk_reward'},
    'base_size_mode': {'pct_equity', 'capital_aware'},
}


def _resolve_categorical_genes(hp: dict, strategy_name: str) -> dict:
    """Map integer categorical gene values back to their string option.

    Training stores categorical genes as indexes 0..N-1 into a filtered option
    list (per _CATEGORICAL_SAFE / strategy spec). The strategy runtime expects
    the original string values (e.g. 'random', 'both'). Mirror the resolution
    logic from IslandPilotPipeline._apply_genome so training and inference use
    the same mapping.
    """
    spec_by_name = _STRATEGY_HP_SPEC_CACHE.get(strategy_name)
    if spec_by_name is None:
        spec_by_name = _load_strategy_hp_spec(strategy_name)
        _STRATEGY_HP_SPEC_CACHE[strategy_name] = spec_by_name or {}
    if not spec_by_name:
        return hp

    out = dict(hp)
    for name, val in hp.items():
        spec = spec_by_name.get(name)
        if not spec or spec.get('type') != 'categorical':
            continue
        opts = spec.get('options', [])
        safe = _CATEGORICAL_SAFE.get(name)
        if safe:
            opts = [o for o in opts if o in safe]
        if not opts:
            continue
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            idx = int(round(val))
            idx = max(0, min(idx, len(opts) - 1))
            out[name] = opts[idx]
        elif isinstance(val, str) and val in opts:
            out[name] = val
    return out


def _load_strategy_hp_spec(strategy_name: str) -> Optional[dict]:
    """Load the strategy's hyperparameters() spec as a name→spec dict.

    Uses the same lightweight stub approach as build_gene_bounds_from_strategy:
    avoids the qengine.strategies → DB import chain by temporarily installing a
    stub qengine.strategies module.
    """
    try:
        import types as _types
        import importlib as _il
        _repo = Path(__file__).resolve().parents[3]
        _strat_file = _repo / 'strategies' / '_admin' / strategy_name / '__init__.py'
        if not _strat_file.exists():
            _strat_file = _repo / 'strategies' / strategy_name / '__init__.py'
        if not _strat_file.exists():
            return None
        parent = str(_strat_file.parent.parent)
        inserted = parent not in sys.path
        if inserted:
            sys.path.insert(0, parent)

        stub = _types.ModuleType('qengine.strategies')
        class _LS: pass
        stub.Strategy = _LS
        stub.cached = lambda f: f
        orig = sys.modules.get('qengine.strategies')
        sys.modules['qengine.strategies'] = stub
        try:
            mod = _il.import_module(strategy_name)
            strategy_cls = getattr(mod, strategy_name, None)
            if strategy_cls is None:
                return None
            dummy = strategy_cls.__new__(strategy_cls)
            hp_list = dummy.hyperparameters()
            return {h['name']: h for h in hp_list
                    if isinstance(h, dict) and 'name' in h}
        finally:
            if orig is None:
                sys.modules.pop('qengine.strategies', None)
            else:
                sys.modules['qengine.strategies'] = orig
            if inserted and parent in sys.path:
                sys.path.remove(parent)
    except Exception:
        return None
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


def _write_training_config_snapshot(
    out_path: Path,
    args: dict,
    resolved_config: dict,
    tunable_groups: list,
    evolved_gene_names: list,
) -> None:
    """Write a snapshot of what governed this training run. Used by audit."""
    import json
    import datetime as _dt
    import subprocess as _sp

    try:
        out = _sp.run(["git", "rev-parse", "HEAD"], capture_output=True,
                      text=True, timeout=1)
        commit = out.stdout.strip()[:12] if out.returncode == 0 else "unknown"
    except Exception:
        commit = "unknown"

    snap = {
        "schema_version": 1,
        "qengine_commit": commit,
        "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "args": args,
        "resolved_config": resolved_config,
        "tunable_groups_snapshot": list(tunable_groups),
        "evolved_gene_names": list(evolved_gene_names),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snap, indent=2))


def _date_to_ts_ms(date_str: str) -> int:
    """Convert 'YYYY-MM-DD' to unix millisecond timestamp (UTC start-of-day).

    qengine's `get_candles()` takes `start_date_timestamp` / `finish_date_timestamp`
    as integer ms epoch values, not ISO date strings.
    """
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    epoch = datetime(1970, 1, 1)
    return int((dt - epoch).total_seconds() * 1000)


def _trim_to_contiguous_start(candles_1m: np.ndarray) -> np.ndarray:
    """Trim leading bars until candles[1][0] - candles[0][0] == 60000ms.

    The qengine backtest validator only checks the first consecutive pair.
    OANDA data sometimes starts with thin-market gaps (e.g., New Year open
    at 22:03 followed by 22:06 — a 3-minute jump). Trimming a few bars from
    the head satisfies the validator without adding any synthetic data.
    Interior gaps (weekends) are unaffected and handled fine by the engine.
    """
    while len(candles_1m) > 2 and candles_1m[1, 0] - candles_1m[0, 0] != 60_000:
        candles_1m = candles_1m[1:]
    return candles_1m


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

    from . import manifest as _manifest
    _manifest.record(
        "feature_partition",
        n_macro_feats=len(macro_indices),
        n_sub_feats=len(sub_indices),
        autocorr_threshold=persistence_threshold,
        lag=lag,
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
                    verbose: bool = True, n_workers: int = 1,
                    t_total_start: float = None):
    """Evolve per-regime genomes with fitness isolated to each island's window.

    Each island's fitness function runs a backtest over the largest contiguous
    time window where that leaf was active. Islands without a sufficiently long
    window (< min_window_days) are skipped (marked inactive). This matches the
    paper's observation (Sec 6.2) that only 10 islands were actively evolved —
    the rest were too sparse for real-engine evaluation.
    """
    from .island_evolver import IslandEvolver, build_gene_bounds_from_strategy

    # Default to now if caller didn't provide a global start timestamp
    if t_total_start is None:
        t_total_start = _time.time()

    leaf_ids = [str(lid) for lid in tree.leaf_ids]
    print(f'[train] Evolving {len(leaf_ids)} islands × {pop_size} individuals × {generations} gen...')

    # Try to load the strategy class to build proper gene bounds
    gene_bounds = None
    try:
        import importlib.util, os as _os, types as _types
        strategy_cls = None

        # Direct filesystem lookup — no DB required.
        _repo_root = _HERE.parents[2]
        _strategy_file = None
        for _c in [
            _repo_root / 'strategies' / '_admin' / strategy_name / '__init__.py',
            _repo_root / 'strategies' / strategy_name / '__init__.py',
        ]:
            if _c.exists():
                _strategy_file = str(_c)
                break

        if _strategy_file:
            # Add the strategy package directory to sys.path so importlib.import_module
            # can handle relative imports (e.g. `from .presets import PRESETS`).
            parent_dir = _os.path.dirname(_os.path.dirname(_strategy_file))
            _inserted = parent_dir not in sys.path
            if _inserted:
                sys.path.insert(0, parent_dir)

            # Stub qengine.strategies to break the DB connection chain:
            # Strategy base class imports qengine.models which calls open_connection().
            _stub_mod = _types.ModuleType('qengine.strategies')
            class _LiteStrategy: pass
            _stub_mod.Strategy = _LiteStrategy
            _stub_mod.cached = lambda f: f
            _orig_strategies = sys.modules.get('qengine.strategies')
            sys.modules['qengine.strategies'] = _stub_mod
            try:
                import importlib as _il
                # Keep strategy module in sys.modules after import so that
                # relative imports inside hyperparameters() (e.g. `from .presets
                # import PRESETS`) can resolve correctly when called later.
                mod = _il.import_module(strategy_name)
                strategy_cls = getattr(mod, strategy_name, None)
            except ImportError:
                pass
            finally:
                # Restore qengine.strategies but leave strategy module in sys.modules
                if _orig_strategies is None:
                    sys.modules.pop('qengine.strategies', None)
                else:
                    sys.modules['qengine.strategies'] = _orig_strategies
                if _inserted and parent_dir in sys.path:
                    sys.path.remove(parent_dir)

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
        'migration_interval': max(1, generations // 5),  # fire ~5 times over the run
        'seed': 42,
        'n_workers': n_workers,
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

    # Build the flat list of (lid, genes, start_ts, end_ts) tasks for parallel eval.
    # candles_1m is NOT included in the task tuple — workers access it via the
    # module-level _WORKER_CANDLES global set before forking (avoids 10 MB
    # serialization per task = 6+ GB for a full generation).
    def _make_eval_task(lid, genes):
        start, end, _ = leaf_date_ranges.get(lid, (train_start, train_end, False))
        s = _date_to_ts_ms(start)
        e = _date_to_ts_ms(end) + 86_400_000
        return (genes, exchange, symbol, timeframe, strategy_name, s, e)

    n_workers = config.get('n_workers', 1)

    global _WORKER_CANDLES
    # Set before forking so workers inherit candles without pickling (avoids
    # 10 MB serialization per task = 6+ GB for a full generation on 60 workers).
    _WORKER_CANDLES = candles_1m

    if n_workers > 1:
        # Pre-import backtest module in parent so forked workers inherit it
        # (avoids DB/service import chain inside worker subprocess)
        import qengine.research.backtest as _bt_mod  # noqa: F401
        print('[train] Backtest module pre-imported for worker fork inheritance.')

    for gen in range(generations):
        t_gen_start = _time.time()
        _tlog(f'[train] Generation {gen + 1}/{generations}...')

        if n_workers > 1:
            # Parallel evaluation: collect all (lid, individual_index, genes) tasks
            import multiprocessing as _mp
            tasks = []
            task_keys = []  # (lid, ind_idx) to map results back
            for lid, pop in evolver.populations.items():
                for idx, ind in enumerate(pop.individuals):
                    tasks.append(_make_eval_task(lid, ind.genes))
                    task_keys.append((lid, idx))

            # Force 'fork' start method so workers inherit _WORKER_CANDLES and
            # pre-imported modules via copy-on-write. macOS defaults to 'spawn'
            # (Python 3.8+) which would re-import the module and lose state.
            _ctx = _mp.get_context('fork')
            with _ctx.Pool(processes=n_workers) as pool:
                results = pool.starmap(_run_backtest_fitness, tasks)

            from . import manifest as _manifest
            for (lid, idx), result in zip(task_keys, results):
                fitness, worker_events = result
                evolver.populations[lid].individuals[idx].fitness = fitness
                _manifest.merge_worker_events(worker_events)
                # Emit summary event in parent (worker did not have aggregates)
                _manifest.record(
                    "genome_evaluated",
                    island=lid,
                    generation=gen,
                    genome_id=evolver.populations[lid].individuals[idx].id,
                    fitness=fitness,
                )
        else:
            for lid, pop in evolver.populations.items():
                start, end, _ = leaf_date_ranges.get(lid, (train_start, train_end, False))
                s = _date_to_ts_ms(start)
                e = _date_to_ts_ms(end) + 86_400_000

                from . import manifest as _manifest
                def _fn(genes, _s=s, _e=e):
                    fitness, worker_events = _run_backtest_fitness(
                        genes, exchange, symbol, timeframe, strategy_name, _s, _e)
                    _manifest.merge_worker_events(worker_events)
                    return fitness
                pop.evaluate(_fn)

        # Only produce next generation's children if there's going to be a next
        # generation that evaluates them. Without this guard, the final saved
        # population is untested children with fitness=None → 0.0 everywhere.
        is_last_gen = (gen + 1) == generations
        if not is_last_gen:
            for pop in evolver.populations.values():
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
        elapsed = _time.time() - t_gen_start
        total_elapsed = _time.time() - t_total_start
        if fitnesses:
            _tlog(f'[train]   Mean best fitness: {np.mean(fitnesses):.3f} '
                  f'(min={min(fitnesses):.3f}, max={max(fitnesses):.3f}) '
                  f'[gen {elapsed:.0f}s / total {total_elapsed/60:.1f}min]')

    return evolver, leaf_date_ranges


def _run_backtest_fitness(
    genes: dict,
    exchange: str,
    symbol: str,
    timeframe: str,
    strategy_name: str,
    start_ts_ms: int,
    end_ts_ms: int,
) -> tuple:
    """Run one backtest, return (fitness, manifest_events).

    Fitness = 0.4·(PF−1)·100 + 0.3·max(0,100−DD·5) + 0.2·(1−bust_rate)·100 + 0.1·min(sessions/100, 1)·100

    Uses the real qengine `backtest(config, routes, data_routes, candles, hyperparameters)`
    API. Candles must be at 1m resolution; the strategy route defines the execution
    timeframe (5m, 15m, 30m, ...) and the engine resamples internally.

    The 1m candle array is subsetted by timestamp range to match the per-leaf
    window being evaluated — this is how fitness isolation is implemented.

    Candles are read from the module-level `_WORKER_CANDLES` global which is set
    in the parent process before forking workers, avoiding 10 MB serialization per task.

    Forked workers reset SIGTERM/SIGINT to SIG_DFL so signals delivered to
    the worker do not invoke the parent's manifest close handler. Workers
    accumulate manifest events into a process-local buffer and return them
    alongside the fitness; the parent merges them via
    manifest.merge_worker_events() after pool.starmap returns.
    """
    import signal as _signal
    try:
        _signal.signal(_signal.SIGTERM, _signal.SIG_DFL)
        _signal.signal(_signal.SIGINT, _signal.SIG_DFL)
    except (OSError, ValueError):
        pass

    from . import manifest as _manifest
    _manifest.start_worker_buffer()

    import traceback as _tb
    try:
        from qengine.research.backtest import backtest as run_bt
        import qengine.helpers as jh

        candles_1m = _WORKER_CANDLES
        if candles_1m is None:
            print('[fitness] ERROR: _WORKER_CANDLES is None — candles not set before forking')
            return 0.0, _manifest.drain_worker_buffer()

        # Subset candles to the evaluation window, then fill gaps so the
        # backtest validator (checks candles[1][0]-candles[0][0]==60000ms) passes.
        # OANDA 1m data has weekend/thin-market gaps that would otherwise fail.
        ts_col = candles_1m[:, 0]
        mask = (ts_col >= start_ts_ms) & (ts_col <= end_ts_ms)
        subset = candles_1m[mask]
        subset = _trim_to_contiguous_start(subset)
        if len(subset) < 2000:  # less than ~1.4 days of 1m candles
            return 0.0, _manifest.drain_worker_buffer()

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

        # CRITICAL: resolve categorical gene indexes (int) to their string option
        # values. Training stores categoricals as indexes 0..N-1; the strategy
        # expects strings like 'random', 'both', 'fixed_pips' etc. Without this
        # resolution, checks like `bias in ('both', 'long_only')` fail with bias=0
        # (int), so should_long/should_short always return False → zero trades.
        # Mirrors _apply_genome in pipelines/_shared/IslandPilot/__init__.py.
        hp = _resolve_categorical_genes(hp, strategy_name)

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
        import math
        _raw_pf = metrics.get('profit_factor', 1.0)
        # Cap inf/None/NaN PF: genomes with only wins get pf=∞; NaN can appear
        # when the engine liquidation path corrupts trade state. Cap at 5.0 —
        # strategies sustaining PF 5 over the training window are top 0.1% and
        # further differentiation among them is noise.
        if _raw_pf is None:
            pf = 5.0
        elif isinstance(_raw_pf, (int, float)):
            _rp = float(_raw_pf)
            if math.isnan(_rp) or math.isinf(_rp):
                pf = 5.0
            else:
                pf = min(5.0, _rp)
        else:
            pf = 5.0
        _raw_dd = metrics.get('max_drawdown_percentage', 0.0)
        if _raw_dd is None:
            dd = 0.0
        else:
            try:
                _rd = float(_raw_dd)
                dd = 0.0 if (math.isnan(_rd) or math.isinf(_rd)) else abs(_rd)
            except (TypeError, ValueError):
                dd = 0.0

        # Net profit sanity: if it's NaN, the session state was corrupted by
        # the engine liquidation bug → treat as broken, return 0.
        _net = metrics.get('net_profit', 0.0)
        if _net is not None:
            try:
                if math.isnan(float(_net)):
                    return 0.0, _manifest.drain_worker_buffer()
            except (TypeError, ValueError):
                pass

        sessions = result.get('sessions', []) if isinstance(result, dict) else []
        # Count only proper hedge sessions (int session id)
        proper_sessions = [s for s in sessions if isinstance(s.get('session'), int)]
        n_sessions = len(proper_sessions)

        _BUST_REASONS = {
            'abort', 'terminate', 'max_level_bust', 'sl_hit',
            'margin_call', 'margin_bust', 'max_level_sl',
        }
        n_bust = sum(1 for s in proper_sessions if s.get('outcome', '') in _BUST_REASONS)
        bust_rate = (n_bust / n_sessions) if n_sessions > 0 else 1.0

        # Penalise "doesn't trade" genomes. Without this the GA converges on
        # picky signal_modes that never fire — zero sessions + default bust_rate
        # beats a marginally-losing random-entry strategy in every other term.
        # Below 10 sessions return tiny fitness scaling with activity.
        if n_sessions < 10:
            return float(n_sessions * 0.5), _manifest.drain_worker_buffer()

        # Full fitness: PF/DD/bust/session-count composite. PF-term can be
        # negative (strategies losing money), bust-term uses a cubic penalty
        # so 30% busts costs ~3x what 15% busts costs. Clamped ≥ 0 at end.
        fitness = (
            0.5 * (pf - 1.0) * 100 +                       # max ~50 at PF=2
            0.2 * max(0.0, 100.0 - dd * 5.0) +             # max 20 at DD=0
            0.2 * ((1.0 - bust_rate) ** 3) * 100 +         # cubic bust penalty
            0.1 * min(n_sessions / 100.0, 1.0) * 100       # rewards activity
        )
        return max(0.0, float(fitness)), _manifest.drain_worker_buffer()

    except Exception as e:
        print(f'[fitness] ERROR: {e}')
        print(_tb.format_exc())
        try:
            _manifest.record("worker_error", traceback=_tb.format_exc())
        except Exception:
            pass
        return 0.0, _manifest.drain_worker_buffer()


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
    n_workers: int = 1,
    candles_file: Optional[str] = None,
    output_dir: Optional[Path] = None,
    preflight_mode: bool = False,
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

    # Resolve output dir: preflight passes its tmpdir; cloud training leaves
    # output_dir=None and uses the package-level _MODELS_DIR default.
    models_dir = Path(output_dir) if output_dir is not None else _MODELS_DIR
    models_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot what governs this run so audit can interpret artifacts later.
    # Written up-front (before heavy work) so even early-exit failures retain
    # a record of what was attempted. Compute the FULL evolvable gene set
    # (strategy-discovered + baseline) so the snapshot is self-describing
    # for audit. We replicate the same lightweight stub-load that
    # _evolve_islands uses, so this works pre-evolution.
    try:
        from .island_evolver import build_gene_bounds_from_strategy
        import importlib.util as _ilu, importlib as _il, types as _types
        _repo_root = _HERE.parents[2]
        _strategy_file = None
        for _c in [
            _repo_root / 'strategies' / '_admin' / strategy_name / '__init__.py',
            _repo_root / 'strategies' / strategy_name / '__init__.py',
        ]:
            if _c.exists():
                _strategy_file = str(_c)
                break

        _full_bounds = None
        if _strategy_file:
            import os as _os
            parent_dir = _os.path.dirname(_os.path.dirname(_strategy_file))
            _inserted = parent_dir not in sys.path
            if _inserted:
                sys.path.insert(0, parent_dir)

            _stub_mod = _types.ModuleType('qengine.strategies')
            class _LiteStrategySnap: pass
            _stub_mod.Strategy = _LiteStrategySnap
            _stub_mod.cached = lambda f: f
            _orig_strategies = sys.modules.get('qengine.strategies')
            sys.modules['qengine.strategies'] = _stub_mod
            try:
                mod = _il.import_module(strategy_name)
                strategy_cls = getattr(mod, strategy_name, None)
                if strategy_cls is not None:
                    dummy = strategy_cls.__new__(strategy_cls)
                    _full_bounds = build_gene_bounds_from_strategy(dummy)
            except Exception:
                pass
            finally:
                if _orig_strategies is None:
                    sys.modules.pop('qengine.strategies', None)
                else:
                    sys.modules['qengine.strategies'] = _orig_strategies
                if _inserted and parent_dir in sys.path:
                    sys.path.remove(parent_dir)

        if _full_bounds:
            _evolved_gene_names = sorted(_full_bounds.keys())
        else:
            from .island_evolver import GENE_BOUNDS as _GENE_BOUNDS_BASE
            _evolved_gene_names = sorted(_GENE_BOUNDS_BASE.keys())
    except Exception:
        try:
            from .island_evolver import GENE_BOUNDS as _GENE_BOUNDS_BASE
            _evolved_gene_names = sorted(_GENE_BOUNDS_BASE.keys())
        except Exception:
            _evolved_gene_names = []
    # Exclude groups whose every member is in _SKIP_PARAMS (e.g. Filters
    # is intentionally all-skipped per spec OQ-1). The audit-side check E01
    # only verifies coverage of groups that actually have evolvable members.
    try:
        from .island_evolver import _GENE_TO_GROUP
        _evolvable_groups = sorted({
            _GENE_TO_GROUP[g] for g in _evolved_gene_names
            if g in _GENE_TO_GROUP
        })
    except Exception:
        _evolvable_groups = []
    # Fallback: if mapping was empty (e.g. strategy never loaded), keep the
    # documented superset so E01 has *something* to compare against.
    if not _evolvable_groups:
        _evolvable_groups = sorted([
            'General', 'Grid / Hedge', 'Take Profit',
            'Entry Signal', 'Risk Management', 'Position Management',
        ])
    _tunable_groups = _evolvable_groups
    try:
        from .config import DEFAULT_CONFIG as _DEFAULT_CONFIG
        _resolved_config = _DEFAULT_CONFIG
    except Exception:
        _resolved_config = {}

    if preflight_mode:
        # Preflight runs on a tiny 30-day slice with 24 total backtests.
        # Lower thresholds so the natural-trigger paths for online_gate
        # and proven_fitness can fire within that budget. Deep-copy so we
        # never mutate the imported DEFAULT_CONFIG (other tests / runtime
        # consumers re-read it).
        from copy import deepcopy
        _resolved_config = deepcopy(_resolved_config) if _resolved_config else {}
        _resolved_config.setdefault("online_gate", {})["min_cycles_for_gate"] = 2
        _resolved_config.setdefault("safety", {})["min_genome_fitness"] = 0.0
    _write_training_config_snapshot(
        out_path=models_dir / 'training_config.json',
        args={
            'exchange': exchange, 'symbol': symbol, 'timeframe': timeframe,
            'train_start': train_start, 'train_end': train_end,
            'strategy_name': strategy_name, 'pop_size': pop_size,
            'generations': generations, 'max_macro': max_macro,
            'max_sub': max_sub, 'min_leaf_samples': min_leaf_samples,
            'n_workers': n_workers, 'dry_run': dry_run,
        },
        resolved_config=_resolved_config,
        tunable_groups=_tunable_groups,
        evolved_gene_names=_evolved_gene_names,
    )

    tf_minutes = int(jh.timeframe_to_one_minutes(timeframe))

    import multiprocessing as _mp
    if n_workers <= 0:
        n_workers = _mp.cpu_count()
    t_total_start = _time.time()
    _t0_dt = datetime.utcnow()

    # --- System / environment info for paper ---
    import platform, sys as _sys
    try:
        import psutil as _psutil
        _ram_gb = _psutil.virtual_memory().total / 1024**3
        _ram_str = f'{_ram_gb:.0f} GB'
    except ImportError:
        try:
            _ram_bytes = int(open('/proc/meminfo').readline().split()[1]) * 1024
            _ram_str = f'{_ram_bytes / 1024**3:.0f} GB'
        except Exception:
            _ram_str = 'unknown'

    _tlog('[train] ══════════════════════════════════════════════════════════')
    _tlog('[train] IslandPilot Training Run')
    _tlog(f'[train]   Started:   {_t0_dt.strftime("%Y-%m-%d %H:%M:%S")} UTC')
    _tlog(f'[train]   Host:      {platform.node()}')
    _tlog(f'[train]   OS:        {platform.system()} {platform.release()}')
    _tlog(f'[train]   Python:    {_sys.version.split()[0]}')
    _tlog(f'[train]   CPUs:      {_mp.cpu_count()} logical  (workers: {n_workers})')
    _tlog(f'[train]   RAM:       {_ram_str}')
    _tlog(f'[train]   Exchange:  {exchange}  Symbol: {symbol}  TF: {timeframe}')
    _tlog(f'[train]   Strategy:  {strategy_name}')
    _tlog(f'[train]   Period:    {train_start} → {train_end}')
    _tlog(f'[train]   GA:        {generations} generations × pop {pop_size}')
    _tlog('[train] ══════════════════════════════════════════════════════════')

    # --- Load 1m candles ---
    # Supports loading from a pre-exported .npy file (for cloud runs without DB access)
    # or directly from PostgreSQL.
    import re

    if candles_file:
        print(f'[train] Loading candles from file: {candles_file}')
        candles_1m = np.load(candles_file)
        print(f'[train] Loaded {len(candles_1m):,} 1m candles from file.')
    else:
        from qengine.research.candles import get_candles
        from qengine.exceptions import CandleNotFoundInDatabase

        start_ts = _date_to_ts_ms(train_start)
        end_ts = _date_to_ts_ms(train_end) + 86_400_000 - 60_000

        def _load(start_ms: int, end_ms: int):
            return get_candles(exchange=exchange, symbol=symbol, timeframe='1m',
                               start_date_timestamp=start_ms, finish_date_timestamp=end_ms)

        try:
            warmup, candles_1m = _load(start_ts, end_ts)
        except CandleNotFoundInDatabase as e:
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
        if len(selected_indices) < 5:
            # Too few features → regime labels change too fast for contiguous windows.
            # Fall back to all features so the regime tree produces stable, long-lived regimes.
            print(f'[train] MI selected only {len(selected_indices)} features — '
                  f'falling back to all {clean_matrix.shape[1]} features for stable regimes.')
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
        tree_path = str(models_dir / 'regime_tree.dryrun.pkl')
    else:
        tree_path = str(models_dir / 'regime_tree.pkl')
    tree.save(tree_path)
    print(f'[train] RegimeTree saved → {tree_path}')

    # Validate regime structure before committing to evolution
    separation = _validate_regime_separation(tree, clean_matrix)
    if not separation['valid']:
        print(f'[train] WARNING: {separation["recommendation"]}')
        # Continue anyway — user may still want the models

    from . import manifest as _manifest
    _manifest.record(
        "regime_fit",
        n_macro_clusters=getattr(tree, "n_macro", None) or len(getattr(tree, "macros", []) or []) or None,
        n_sub_per_macro={},
        leaves_before_merge=getattr(tree, "leaves_before_merge", None),
        leaves_after_merge=len(tree.leaf_sample_counts),
        separation_dict=separation,
    )

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
        n_workers=n_workers,
        t_total_start=t_total_start,
    )

    evolver_path = str(models_dir / 'island_evolver.json')
    evolver.save(evolver_path)
    print(f'[train] IslandEvolver saved → {evolver_path}')

    # Also save the per-leaf date ranges for auditability
    leaf_ranges_path = str(models_dir / 'leaf_date_ranges.json')
    with open(leaf_ranges_path, 'w') as f:
        json.dump({
            lid: {'start': s, 'end': e, 'had_window': bool(hw)}
            for lid, (s, e, hw) in leaf_date_ranges.items()
        }, f, indent=2)
    print(f'[train] Leaf date ranges saved → {leaf_ranges_path}')
    elapsed_total = _time.time() - t_total_start
    _end_dt = datetime.utcnow()
    _tlog('[train] ══════════════════════════════════════════════════════════')
    _tlog('[train] Training Complete')
    _tlog(f'[train]   Finished:    {_end_dt.strftime("%Y-%m-%d %H:%M:%S")} UTC')
    _tlog(f'[train]   Started:     {_t0_dt.strftime("%Y-%m-%d %H:%M:%S")} UTC')
    _tlog(f'[train]   Total time:  {elapsed_total/3600:.2f}h ({elapsed_total:.0f}s)')
    _tlog(f'[train]   Generations: {generations}  Islands: {len(evolver.populations)}  Pop: {pop_size}')
    _tlog(f'[train]   Models dir:  {models_dir}')
    _tlog('[train] ══════════════════════════════════════════════════════════')

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
    p.add_argument('--workers', type=int, default=0,
                   help='Parallel workers for island evaluation. 0 = use all available CPUs.')
    p.add_argument('--candles-file', default=None,
                   help='Path to pre-exported .npy candles file (bypasses DB, for cloud runs).')
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
        n_workers=args.workers or __import__('multiprocessing').cpu_count(),
        candles_file=args.candles_file,
    )
