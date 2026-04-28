"""
Named presets for Martingale.
Each preset is a dict of hyperparameter overrides applied on top of defaults.
"""

PRESETS = {
    'original': {
        'base_size_value':1.0,
        'signal_mode': 'none',
        'direction_bias': 'long_only',
        'sizing_curve': 'geometric',
        'sizing_factor': 2.0,
        'max_levels': 6,
        'hedge_mode': 'fixed_pips',
        'hedge_value': 10.0,
        'tp_mode': 'fixed_pips',
        'tp_value': 20.0,
    }
}
