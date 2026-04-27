"""
FinRLPilot pipeline — default configuration and merge utility.

Configuration for the DRL-based policy that selects among discrete
parameter presets for the Martingale strategy.
"""
import copy
from typing import Any, Dict


# The 10 features we select from the shared FeaturePool.
# These mirror the set IslandPilot selected; we default to reasonable
# volatility/trend/structure features if the evolution chose others.
DEFAULT_STATE_FEATURES = [
    'natr_14',
    'natr_50',
    'atr_ratio_14_50',
    'bollinger_width_20',
    'hl_range_norm',
    'session_hour',
    'chop_14',
    'roc_10',
    'dm_diff',
    'ema_slope_21',
]


DEFAULT_CONFIG: Dict[str, Any] = {
    # Warmup before policy starts acting
    'warmup': 30,

    # State representation
    'state_features': DEFAULT_STATE_FEATURES,
    'state_dim': len(DEFAULT_STATE_FEATURES),

    # Action space size (length of presets table). Cross-check with presets.py.
    'n_actions': 4,

    # Policy: PPO-style MLP 2x64
    'policy': {
        'hidden_dim': 64,
        'n_layers': 2,
        'lr': 3e-4,
        'gamma': 0.99,
        'clip_eps': 0.2,        # PPO clip
        'entropy_coef': 0.01,
        'n_steps': 256,
        'batch_size': 64,
        'n_epochs': 4,
    },

    # Training mode vs evaluation mode
    'mode': 'eval',              # 'eval' or 'train'
    'update_every_cycles': 32,    # trigger policy update in train mode

    # Reward shaping
    'reward': {
        'drawdown_penalty_coef': 0.1,  # penalize observed drawdown during cycle
    },

    # State discretization (used by the tabular fallback learner)
    'discretize': {
        'n_bins': 3,               # 3 bins per feature
        'feature_subset': 4,       # only use the first 4 features for state
    },

    # Persistence
    'models_dir': None,           # resolved by pipeline at import time
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
