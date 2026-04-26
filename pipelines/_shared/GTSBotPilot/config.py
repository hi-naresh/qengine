# pipelines/_shared/GTSBotPilot/config.py
"""GTSBotPilot configuration with defaults and deep-merge."""
import copy
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    'warmup': 50,
    'trend_filter': {
        'smoothing_period': 14,
        'delta_atr_mult': 0.02,          # delta = ATR * mult (adaptive to volatility)
        'confirm_bars': 2,               # require N consecutive bars confirming trend direction
        'null_tolerance': 1,             # allow N null bars within a streak before resetting
        'require_acceleration': False,   # True=paper's d2>0 check (strict), False=d1 only (practical)
        'require_direction_match': True,
        'enabled': True,
    },
    'grid_manager': {
        'x_threshold': 15,               # min candles between same-direction trades within a cycle
        'y_threshold_atr_mult': 0.5,     # min price distance as ATR multiple
        'max_operations': 13,
        'cycle_cooldown': 10,            # min candles to wait after cycle ends before new entry
        'adaptive': True,
        'enabled': True,
    },
    'basket_manager': {
        'target_profit_atr_mult': 2.0,
        'max_loss_atr_mult': 10.0,           # basket loss cutoff = ATR * mult (prevents catastrophic busts)
        'monitor_drawdown': True,
        'emergency_dd_pct': None,
        'enabled': True,
    },
    'trend_abort': {
        'enabled': True,
        'min_level': 3,                      # only abort at level >= N (let grid work at lower levels)
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning new dict."""
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


def merge_config(user_config: dict) -> dict:
    """Deep merge user config over defaults."""
    if not user_config:
        return copy.deepcopy(DEFAULT_CONFIG)
    return _deep_merge(DEFAULT_CONFIG, user_config)
