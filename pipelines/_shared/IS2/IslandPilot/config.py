"""
IslandPilot pipeline — default configuration and merge utility.
"""

import copy
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    'regime': {
        'feature_pool_size': 35,
        'macro_features_k': 'auto',
        'sub_features_k': 'auto',
        'min_island_cycles': 200,
        'rolling_window': 100,
        'max_macro': 10,
        'max_sub': 8,
    },
    'evolution': {
        'population_size': 30,
        'max_generations': 100,
        'crossover_rate': 0.7,
        'mutation_rate': 0.2,
        'mutation_sigma_pct': 0.05,
        'elitism_count': 2,
        'migration_interval': 5,
        'cross_macro_interval': 20,
        'early_stop_patience': 15,
        'early_stop_threshold': 0.005,
        'fitness_weights': {
            'net_profit': 0.3,
            'bust_rate': 0.3,
            'profit_factor': 0.2,
            'max_drawdown': 0.2,
        },
    },
    'inference': {
        'min_confidence': 0.3,
        'default_hysteresis': 0.30,   # was 0.15 — need stronger stickiness with 73 leaves
        'transition_grace_candles': 2, # was 5 — only affects genome switching, not entry gating
    },
    'sizing': {
        'drawdown_threshold_pct': 5.0,
        'min_confidence_scale': 0.2,
        'min_drawdown_scale': 0.1,
        'max_risk_per_cycle_pct': 15.0,
    },
    # PHASE6: Online per-regime gating — blocks regimes that have accumulated
    # N cycles with PF below threshold. Defaults are LENIENT so it doesn't
    # over-block early in a run. Tighten if you want stricter risk management.
    'online_gate': {
        'enabled': True,
        'min_cycles_for_gate': 15,   # need 15+ cycles before gating kicks in (was 5)
        'min_regime_pf': 0.7,        # block regime only if PF < 0.7 (was 1.0)
    },
    # PHASE6: Drift detection — conservative defaults. Disable by setting
    # enabled=False in user config if you prefer uninterrupted trading.
    'drift': {
        'enabled': True,
        'recent_n': 30,              # larger window → less noisy (was 20)
        'drop_ratio': 0.3,           # only pause if recent PF < 30% of lifetime (was 0.5)
    },
    'warmup': 10,
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
