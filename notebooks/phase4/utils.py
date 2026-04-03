"""
Phase 4 Research Utilities — shared helpers for all phase 4 research scripts.

Provides directory constants, candle loading, cycle simulation helpers,
statistical tests, and persistence utilities.
"""

import json
import logging
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import qengine.helpers as jh
from qengine.research import get_candles

# ---------------------------------------------------------------------------
# Directory constants (auto-created)
# ---------------------------------------------------------------------------

PHASE4_DIR = Path(__file__).resolve().parent
RESULTS_DIR = PHASE4_DIR / 'results'
PLOTS_DIR = PHASE4_DIR / 'plots'
TABLES_DIR = RESULTS_DIR / 'tables'
MODELS_DIR = RESULTS_DIR / 'models'

for _d in (RESULTS_DIR, PLOTS_DIR, TABLES_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger with console handler."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s',
                              datefmt='%H:%M:%S')
        )
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


# ---------------------------------------------------------------------------
# Candle loading
# ---------------------------------------------------------------------------

def load_candles(
    exchange: str = 'OANDA',
    symbol: str = 'EUR-USD',
    timeframe: str = '5m',
    start_date: str = '2006-01-02',
    end_date: str = '2025-12-30',
    warmup_candles_num: int = 500,
) -> Tuple[np.ndarray, np.ndarray]:
    """Load candles via qengine.research.get_candles.

    Returns:
        (warmup_candles, trading_candles) tuple. Both are 2-D numpy arrays
        with columns [timestamp, open, close, high, low, volume].
    """
    start_ts = jh.date_to_timestamp(start_date)
    end_ts = jh.date_to_timestamp(end_date)

    warmup, trading = get_candles(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        start_date_timestamp=start_ts,
        finish_date_timestamp=end_ts,
        warmup_candles_num=warmup_candles_num,
    )
    return warmup, trading


def concat_candles(warmup: np.ndarray, trading: np.ndarray) -> np.ndarray:
    """Safely concatenate warmup and trading candles.

    Handles the case where warmup may be empty (1-D array) when start_date
    is at the beginning of available data.
    """
    if warmup.ndim == 2 and len(warmup) > 0:
        return np.concatenate([warmup, trading], axis=0)
    return trading


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CycleResult:
    """Result of a single surefire cycle."""
    bust: bool
    level_reached: int
    pnl: float
    bars_held: int
    entry_idx: int
    direction: str          # 'long' or 'short'
    regime_id: Optional[int] = None
    genome_id: Optional[str] = None

    @property
    def is_win(self) -> bool:
        return not self.bust

    def to_dict(self) -> dict:
        d = asdict(self)
        d['is_win'] = self.is_win
        return d


@dataclass
class SimConfig:
    """Configuration for a surefire cycle simulation."""
    sizing_curve: str = 'geometric'     # geometric, sqrt, linear, fibonacci
    sizing_factor: float = 2.0
    base_size: float = 1.0
    max_levels: int = 6
    hedge_dist_pips: float = 20.0
    tp_pips: float = 20.0
    abort_level: int = 12
    max_bars: int = 500

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_genome(cls, genome_dict: dict) -> 'SimConfig':
        """Create SimConfig from an IslandEvolver genome dict.

        Maps genome gene names to SimConfig fields.
        """
        genes = genome_dict.get('genes', genome_dict)
        sizing_curve_val = genes.get('sizing_curve', 'geometric')
        # If int, convert via map
        if isinstance(sizing_curve_val, int):
            from qengine.framework.components.island_evolver import SIZING_CURVE_MAP
            sizing_curve_val = SIZING_CURVE_MAP.get(sizing_curve_val, 'geometric')

        return cls(
            sizing_curve=sizing_curve_val,
            sizing_factor=genes.get('sizing_factor', 2.0),
            base_size=genes.get('base_size_pct', 1.0),
            max_levels=genes.get('max_levels', 6),
            hedge_dist_pips=genes.get('hedge_distance_atr_mult', 1.0) * 20.0,
            tp_pips=genes.get('tp_distance_atr_mult', 1.0) * 20.0,
            abort_level=int(genes.get('max_levels', 6) * 2),
            max_bars=500,
        )


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------

# Fibonacci sequence cache
_FIB_CACHE = [1, 1]


def _fib(n: int) -> int:
    while len(_FIB_CACHE) <= n:
        _FIB_CACHE.append(_FIB_CACHE[-1] + _FIB_CACHE[-2])
    return _FIB_CACHE[n]


def calc_size(level: int, cfg: SimConfig) -> float:
    """Compute position size at a given hedge level.

    Args:
        level: hedge level (0 = initial entry)
        cfg: simulation config

    Returns:
        Position size as a float.
    """
    curve = cfg.sizing_curve.lower()
    f = cfg.sizing_factor
    base = cfg.base_size

    if curve == 'geometric':
        return base * (f ** level)
    elif curve == 'sqrt':
        return base * (f ** (level ** 0.5))
    elif curve == 'linear':
        return base * (1.0 + level * (f - 1.0))
    elif curve == 'fibonacci':
        return base * _fib(level)
    else:
        raise ValueError(f"Unknown sizing curve: {curve}")


# ---------------------------------------------------------------------------
# Cycle summary statistics
# ---------------------------------------------------------------------------

def cycle_summary(cycles: List[CycleResult]) -> dict:
    """Compute aggregate statistics from a list of cycle results."""
    if not cycles:
        return {
            'n_cycles': 0, 'n_wins': 0, 'n_busts': 0,
            'win_rate': 0.0, 'bust_rate': 0.0, 'net_pnl': 0.0,
            'avg_win_pnl': 0.0, 'avg_bust_pnl': 0.0,
            'profit_factor': 0.0, 'max_drawdown_pct': 0.0,
            'avg_level': 0.0, 'avg_bars': 0.0,
        }

    n = len(cycles)
    wins = [c for c in cycles if c.is_win]
    busts = [c for c in cycles if c.bust]
    pnls = [c.pnl for c in cycles]

    gross_profit = sum(c.pnl for c in wins) if wins else 0.0
    gross_loss = abs(sum(c.pnl for c in busts)) if busts else 0.0

    return {
        'n_cycles': n,
        'n_wins': len(wins),
        'n_busts': len(busts),
        'win_rate': len(wins) / n,
        'bust_rate': len(busts) / n,
        'net_pnl': sum(pnls),
        'avg_win_pnl': gross_profit / len(wins) if wins else 0.0,
        'avg_bust_pnl': -gross_loss / len(busts) if busts else 0.0,
        'profit_factor': gross_profit / gross_loss if gross_loss > 0 else float('inf'),
        'max_drawdown_pct': max_drawdown_pct(pnls),
        'avg_level': float(np.mean([c.level_reached for c in cycles])),
        'avg_bars': float(np.mean([c.bars_held for c in cycles])),
    }


# ---------------------------------------------------------------------------
# Equity and drawdown
# ---------------------------------------------------------------------------

def max_drawdown_pct(pnls: Sequence[float], initial: float = 10000.0) -> float:
    """Compute maximum drawdown percentage from a sequence of P&L values.

    Args:
        pnls: per-cycle P&L values
        initial: starting equity

    Returns:
        Max drawdown as a percentage (0-100 scale).
    """
    if not pnls:
        return 0.0

    eq = equity_curve(pnls, initial)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / (peak + 1e-12) * 100.0
    return float(np.max(dd))


def equity_curve(pnls: Sequence[float], initial: float = 10000.0) -> np.ndarray:
    """Build cumulative equity curve from P&L values.

    Returns:
        numpy array of length len(pnls) + 1 starting at initial.
    """
    pnl_arr = np.asarray(pnls, dtype=float)
    eq = np.empty(len(pnl_arr) + 1)
    eq[0] = initial
    eq[1:] = initial + np.cumsum(pnl_arr)
    return eq


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def bootstrap_ci(
    data: Sequence[float],
    stat_fn: Callable = np.mean,
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Bootstrap confidence interval for a statistic.

    Args:
        data: 1-D array-like of observations
        stat_fn: function to compute the statistic (default: np.mean)
        n_boot: number of bootstrap resamples
        ci: confidence level (e.g. 0.95 for 95% CI)
        seed: random seed

    Returns:
        (point_estimate, lower_bound, upper_bound)
    """
    data = np.asarray(data, dtype=float)
    rng = np.random.RandomState(seed)
    n = len(data)

    point = float(stat_fn(data))
    boot_stats = np.empty(n_boot)
    for i in range(n_boot):
        sample = data[rng.randint(0, n, size=n)]
        boot_stats[i] = stat_fn(sample)

    alpha = 1.0 - ci
    lower = float(np.percentile(boot_stats, 100 * alpha / 2))
    upper = float(np.percentile(boot_stats, 100 * (1 - alpha / 2)))

    return point, lower, upper


def paired_wilcoxon(
    a: Sequence[float],
    b: Sequence[float],
) -> Tuple[float, float]:
    """Wilcoxon signed-rank test for paired samples.

    Returns:
        (statistic, p_value)
    """
    from scipy.stats import wilcoxon
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    stat, pval = wilcoxon(a, b)
    return float(stat), float(pval)


def cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    """Cohen's d effect size for two independent samples.

    Returns:
        Effect size (positive means a > b).
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na, nb = len(a), len(b)
    var_a, var_b = np.var(a, ddof=1), np.var(b, ddof=1)
    pooled_std = np.sqrt(((na - 1) * var_a + (nb - 1) * var_b) / (na + nb - 2))
    if pooled_std < 1e-12:
        return 0.0
    return float((np.mean(a) - np.mean(b)) / pooled_std)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_results(data: Any, name: str, subdir: str = '') -> str:
    """Save data as JSON to RESULTS_DIR / subdir / name.json.

    Args:
        data: JSON-serializable data
        name: filename without extension
        subdir: optional subdirectory under RESULTS_DIR

    Returns:
        Absolute path of saved file.
    """
    target_dir = RESULTS_DIR / subdir if subdir else RESULTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f'{name}.json'

    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)

    return str(path)


def load_results(name: str, subdir: str = '') -> Any:
    """Load JSON data from RESULTS_DIR / subdir / name.json.

    Returns:
        Parsed JSON data.
    """
    target_dir = RESULTS_DIR / subdir if subdir else RESULTS_DIR
    path = target_dir / f'{name}.json'

    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def savefig(name: str, dpi: int = 150, tight: bool = True) -> str:
    """Save the current matplotlib figure to PLOTS_DIR / name.png.

    Args:
        name: filename without extension
        dpi: resolution
        tight: use tight_layout before saving

    Returns:
        Absolute path of saved file.
    """
    if tight:
        plt.tight_layout()
    path = PLOTS_DIR / f'{name}.png'
    plt.savefig(str(path), dpi=dpi, bbox_inches='tight')
    plt.close()
    return str(path)
