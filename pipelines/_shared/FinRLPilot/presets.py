"""
FinRLPilot — discrete parameter preset table.

Each preset is a concrete set of Martingale hyperparameters that the PPO
policy can select at the start of a cycle. Only HPs in the following groups
are tuned:

    {'General', 'Grid / Hedge', 'Take Profit'}

HP names below were discovered at runtime from
    strategy.hyperparameters()
on the Martingale strategy (see strategies/_admin/Martingale).

Sizing factor note:
  - `sizing_curve='geometric'` uses `sizing_factor` as the multiplier (2x).
  - `sizing_curve='sqrt'` uses `sizing_factor` as a base for sqrt growth.
  - `sizing_curve='linear'` does NOT use `sizing_factor` but we leave it set
    for consistency.
"""
from typing import List, Dict, Any


# Names must match the HP names emitted by Martingale.hyperparameters()
PRESET_NAMES: List[str] = [
    'conservative',
    'moderate',
    'aggressive',
    'tight_tp',
]


# All presets share a fixed-pips hedge distance and TP distance for simplicity;
# base_size_mode stays on pct_equity so sizing is balance-aware.
PRESETS: List[Dict[str, Any]] = [
    # 0 — Conservative: few levels, wide hedge, wide TP, gentle sizing
    {
        'name': 'conservative',
        'preset': 'custom',
        'max_levels': 4,
        'hedge_mode': 'fixed_pips',
        'hedge_value': 15.0,          # pips
        'tp_mode': 'fixed_pips',
        'tp_value': 25.0,             # pips
        'sizing_curve': 'sqrt',
        'sizing_factor': 1.5,
        'base_size_mode': 'pct_equity',
        'base_size_value': 0.8,       # % of equity
    },
    # 1 — Moderate: balanced
    {
        'name': 'moderate',
        'preset': 'custom',
        'max_levels': 6,
        'hedge_mode': 'fixed_pips',
        'hedge_value': 10.0,
        'tp_mode': 'fixed_pips',
        'tp_value': 20.0,
        'sizing_curve': 'geometric',
        'sizing_factor': 2.0,
        'base_size_mode': 'pct_equity',
        'base_size_value': 1.5,
    },
    # 2 — Aggressive: deep grid, tight hedges, full 2.5x doubling
    {
        'name': 'aggressive',
        'preset': 'custom',
        'max_levels': 8,
        'hedge_mode': 'fixed_pips',
        'hedge_value': 8.0,
        'tp_mode': 'fixed_pips',
        'tp_value': 15.0,
        'sizing_curve': 'geometric',
        'sizing_factor': 2.5,
        'base_size_mode': 'pct_equity',
        'base_size_value': 2.5,
    },
    # 3 — Tight-TP: quick scalp exits, modest grid
    {
        'name': 'tight_tp',
        'preset': 'custom',
        'max_levels': 5,
        'hedge_mode': 'fixed_pips',
        'hedge_value': 12.0,
        'tp_mode': 'fixed_pips',
        'tp_value': 8.0,              # tight TP
        'sizing_curve': 'linear',
        'sizing_factor': 1.8,
        'base_size_mode': 'pct_equity',
        'base_size_value': 1.2,
    },
]


# HP groups the pipeline is allowed to touch. Matches IslandPilot's safelist.
TUNABLE_GROUPS = {'General', 'Grid / Hedge', 'Take Profit'}


def get_preset(idx: int) -> Dict[str, Any]:
    """Return preset dict by index with bounds checking."""
    idx = max(0, min(int(idx), len(PRESETS) - 1))
    return dict(PRESETS[idx])


def apply_preset_to_hp(strategy, idx: int, hp_spec: Dict[str, dict]) -> Dict[str, Any]:
    """Apply preset `idx` to strategy.hp, validating against hp_spec.

    Returns the dict of changes actually applied.

    Args:
        strategy: strategy instance with .hp attribute
        idx: preset index
        hp_spec: {hp_name: spec_dict} discovered from strategy.hyperparameters()

    Only applies keys whose group is in TUNABLE_GROUPS and that exist on the
    strategy. Enforces declared bounds / options.
    """
    if not hasattr(strategy, 'hp') or not hp_spec:
        return {}

    preset = get_preset(idx)
    applied: Dict[str, Any] = {}

    for key, val in preset.items():
        # Always allow setting 'preset' so custom overrides are unlocked
        if key == 'preset':
            strategy.hp['preset'] = val
            applied['preset'] = val
            continue

        spec = hp_spec.get(key)
        if spec is None:
            continue

        group = spec.get('group', '')
        if group not in TUNABLE_GROUPS:
            continue

        hp_type = spec.get('type')
        if hp_type == 'categorical':
            options = spec.get('options', [])
            if val in options:
                strategy.hp[key] = val
                applied[key] = val
        elif hp_type in (int, 'int'):
            lo = spec.get('min', float('-inf'))
            hi = spec.get('max', float('inf'))
            v = int(round(max(lo, min(hi, float(val)))))
            strategy.hp[key] = v
            applied[key] = v
        elif hp_type in (float, 'float'):
            lo = spec.get('min', float('-inf'))
            hi = spec.get('max', float('inf'))
            v = float(max(lo, min(hi, float(val))))
            strategy.hp[key] = v
            applied[key] = v
        else:
            # Unknown type — set verbatim
            strategy.hp[key] = val
            applied[key] = val

    return applied
