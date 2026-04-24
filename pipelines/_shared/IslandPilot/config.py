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
        # Conservative defaults: raised from 0.3 → 0.5 after user observed
        # -10% net over a full year of OOS trading. Pipeline now trades only
        # when regime classification confidence clearly dominates (>50% on a
        # single leaf out of ~73 leaves).
        'min_confidence': 0.5,
        'default_hysteresis': 0.30,
        'transition_grace_candles': 5,
    },
    'sizing': {
        'drawdown_threshold_pct': 5.0,
        'min_confidence_scale': 0.2,
        'min_drawdown_scale': 0.1,
        'max_risk_per_cycle_pct': 15.0,
    },
    # Online per-regime gating — blocks regimes that accumulate N cycles with
    # PF below threshold. Kicks in after min_cycles_for_gate so we give each
    # regime a fair trial. max_busts_per_regime is a softer cap now (2 busts)
    # since joint risk constraint already bounds bust size; prevents endless
    # bleed on chronically bad regimes while allowing occasional losses.
    'online_gate': {
        'enabled': True,
        'min_cycles_for_gate': 8,
        'min_regime_pf': 1.0,
        'max_busts_per_regime': 2,
    },
    # Drift detection — pause trading when recent performance drops vs lifetime.
    'drift': {
        'enabled': True,
        'recent_n': 20,
        'drop_ratio': 0.6,          # pause if recent PF < 60% of lifetime
    },
    # Safety layer. The key risk invariant is the JOINT constraint:
    #   base_size × sizing_factor^max_levels ≤ max_ticket_cap_pct (% equity)
    # This lets the GA evolve deep grids with small base_size (recovery room)
    # OR shallow grids with larger base_size (aggressive), without blowing the
    # account. max_levels_cap is left as None by default — the joint constraint
    # replaces the old hard cap. Set it to an int if you want a manual ceiling.
    #
    # Modes (tp_mode, hedge_mode, base_size_mode) are NOT locked — the GA can
    # choose bucket_pct for early profit-taking, atr_based for vol-adaptive
    # grids, etc. Mode-aware value coercion (_coerce_mode_value) ensures the
    # numeric value is scaled correctly for each mode.
    'safety': {
        'enabled': True,
        'max_levels_cap': None,               # let GA choose; joint constraint bounds risk
        'max_ticket_cap_pct': 20.0,           # deepest ticket ≤ 20% equity
        'abort_aggressiveness_floor': None,   # trust genome; set float to override
        'tp_hedge_ratio_floor': 1.5,          # enforced only when both modes = fixed_pips
        'session_loss_pct_halt': 0.08,        # emergency close at 8% float loss
        'min_genome_fitness': 55.0,           # block bottom ~25% of regimes
        'min_bust_loss_pct': 0.0005,          # bust only counts if loss > 0.05% equity
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
