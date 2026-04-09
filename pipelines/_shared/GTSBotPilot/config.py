# pipelines/_shared/GTSBotPilot/config.py
"""GTSBotPilot configuration with defaults and deep-merge."""
import copy
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    'warmup': 50,
    'trend_filter': {
        'smoothing_period': 14,
        'delta_threshold': 0.00015,
        'require_direction_match': True,
        'enabled': True,
    },
    'grid_manager': {
        'x_threshold': 15,
        'y_threshold_atr_mult': 0.5,
        'max_operations': 13,
        'adaptive': True,
        'enabled': True,
    },
    'basket_manager': {
        'target_profit_atr_mult': 2.0,
        'monitor_drawdown': True,
        'emergency_dd_pct': None,
        'enabled': True,
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
