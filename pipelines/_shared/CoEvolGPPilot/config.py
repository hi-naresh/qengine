"""
CoEvolGPPilot pipeline — default configuration and merge utility.

Mirrors IslandPilot's config schema so the two can be compared apples-to-apples
in the PhD dissertation. Differences are surfaced under the ``hmm`` and
``shapley`` sub-dicts which are specific to the co-evolutionary framework.
"""

import copy
from typing import Any, Dict


# Three fixed hidden states: bull / neutral / bear — the paper does not use a
# hierarchical tree, so there is no macro/sub split.
N_STATES: int = 3
STATE_IDS = [f's{i}' for i in range(N_STATES)]


DEFAULT_CONFIG: Dict[str, Any] = {
    'hmm': {
        'n_states': N_STATES,
        'n_mix': 2,                 # components in the Gaussian mixture per state
        'covariance_type': 'diag',
        'n_iter': 100,
        'tol': 1e-3,
        'top_k_features': 5,        # features picked by MI against cycle-outcome proxy
        'random_state': 42,
        'use_sklearn_fallback': False,  # auto-switch if hmmlearn missing
    },
    'evolution': {
        'population_size': 20,
        'max_generations': 5,
        'crossover_rate': 0.7,
        'mutation_rate': 0.2,
        'mutation_sigma_pct': 0.05,
        'elitism_count': 2,
        'migration_interval': 5,
        'tournament_k': 3,
    },
    'shapley': {
        'update_interval': 30,      # recompute every K cycles
        'min_samples_per_state': 5,  # need at least N credit samples to trust phi
        'pressure_min': 0.5,        # scale on tournament_k and mutation_sigma
        'pressure_max': 1.5,
    },
    'inference': {
        'min_posterior_confidence': 0.0,  # minimum max-posterior to allow entry
        'apply_between_cycles_only': True,
    },
    'warmup': 50,                   # candles before classification is trusted
    'window': 300,                  # tail window used when computing features on-line
    'fitness_weights': {            # mirror IslandPilot for direct comparison
        'pf': 0.4,
        'dd': 0.3,
        'bust': 0.2,
        'sessions': 0.1,
    },
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
