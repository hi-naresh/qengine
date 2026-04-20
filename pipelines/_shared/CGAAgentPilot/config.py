"""
CGAAgentPilot pipeline — default configuration and merge utility.

Implements the time-based adaptation baseline from Budiharto & Prasetyo (2025)
"Agent-Based Genetic Algorithm for Crypto Trading Strategy Optimization"
(arxiv 2510.07943).

This is the *rolling-window* counterpart to IslandPilot: same evolutionary
machinery but re-optimisation is triggered by TIME (every 30 calendar days)
rather than regime change. A simple agent coordinator adjusts GA hyper-
parameters (mutation sigma, crossover rate, tournament size) based on the
recent fitness trend and market volatility regime.
"""

import copy
from typing import Any, Dict


# 30m candles per 30-day window (24h * 2 * 30) = 1440
_CANDLES_PER_30DAYS_30M = 1440

DEFAULT_CONFIG: Dict[str, Any] = {
    # Re-optimisation cadence
    'retrain_interval_candles': _CANDLES_PER_30DAYS_30M,
    'rolling_window_cycles': 120,          # outcomes used for per-genome scoring
    'rolling_window_days': 30,

    # Population (single-island GA)
    'ga': {
        'population_size': 30,
        'elitism': 2,
        # Coordinator-managed (initial values — get tuned at runtime)
        'mutation_rate': 0.2,
        'mutation_sigma': 0.05,
        'crossover_rate': 0.7,
        'tournament_k': 3,
    },

    # Agent coordinator — bounds for the three knobs it controls
    'coordinator': {
        'mutation_sigma_min': 0.02,
        'mutation_sigma_max': 0.15,
        'mutation_sigma_boost': 1.5,       # multiplier when fitness stalls
        'mutation_sigma_damp': 0.85,       # multiplier when fitness volatile
        'crossover_rate_min': 0.5,
        'crossover_rate_max': 0.9,
        'tournament_k_min': 2,
        'tournament_k_max': 5,
        'stall_retrains': 3,               # retrains without improvement → boost σ
        'stall_improvement_eps': 1e-3,     # min delta counted as improvement
        'vol_window_candles': 2000,        # trailing window for NATR quantiles
        'vol_high_quantile': 0.75,
        'vol_low_quantile': 0.25,
    },

    # Pipeline-level gene bounds (added on top of strategy-discovered HP)
    'pipeline_gene_bounds': {
        'base_size_pct':        [0.5, 5.0, 'float'],
        'abort_aggressiveness': [0.0, 0.4, 'float'],
    },

    'warmup': 50,
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def merge_config(user_config: dict) -> dict:
    """Deep merge user config over defaults."""
    if not user_config:
        return copy.deepcopy(DEFAULT_CONFIG)
    return _deep_merge(DEFAULT_CONFIG, user_config)
