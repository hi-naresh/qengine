"""
DempsterJonesPilot — default configuration and merge utility.

Based on:
    Dempster, M. A. H., & Jones, C. M. (2001).
    A real-time adaptive trading system using genetic programming.
    Quantitative Finance, 1(4), 397-413.

Key idea: rolling walk-forward GA on a single population. Every ~90 trading
days, re-optimise the genome from the trailing 3-month cycle-outcome buffer
and apply the best genome to the next period.
"""

import copy
from typing import Any, Dict


# Approximate number of 30m candles in 90 trading days (24h FX).
# 30m → 48 candles/day × 90 = 4320.
_CANDLES_PER_90D_30M = 4320


DEFAULT_CONFIG: Dict[str, Any] = {
    # Walk-forward scheduling
    'retrain': {
        'interval_candles': _CANDLES_PER_90D_30M,    # re-optimise every N candles
        'warmup_candles': 1000,                       # don't retrain until we have this many cycles/candles
        'min_cycles_for_retrain': 15,                 # skip retrain if buffer too small
        'rolling_window_days': 90,                    # trailing window used for fitness
        'only_between_cycles': True,                  # never swap HP mid-cycle
    },

    # Genetic algorithm
    'ga': {
        'population_size': 20,
        'generations_per_retrain': 10,
        'tournament_k': 3,
        'crossover_rate': 0.7,
        'mutation_rate': 0.2,
        'mutation_sigma_pct': 0.05,
        'elitism_count': 2,
        'seed': 42,
    },

    # Fitness weights (same formula as IslandPilot so comparisons are fair)
    'fitness': {
        'w_pf': 0.4,
        'w_dd': 0.3,
        'w_bust': 0.2,
        'w_sessions': 0.1,
        'dd_scale': 5.0,
        'session_cap': 100,
    },

    # How the online fitness estimator weights observed cycle PnL vs genome
    # similarity. Larger radius → more cycles contribute to each genome.
    'fitness_radius': 0.25,          # relative L2 distance (over normalised genes)
    'fitness_min_similar': 3,        # minimum matched cycles before we trust a genome's score
    'initial_noise_fitness': 0.0,    # fallback fitness for unmatched offspring

    # Misc
    'warmup': 10,                    # candles before gate_entry allows entries
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def merge_config(user_config: dict) -> dict:
    if not user_config:
        return copy.deepcopy(DEFAULT_CONFIG)
    return _deep_merge(DEFAULT_CONFIG, user_config)
