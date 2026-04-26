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
    },

    'v2': {
        'signal_mode': 'ema_cross',
        'ema_fast': 8,
        'ema_slow': 21,
        'sizing_curve': 'sqrt',
        'sizing_factor': 2.0,
        'max_levels': 6,
        'hedge_mode': 'atr_based',
        'hedge_value': 1.5,
        'hedge_atr_period': 14,
        'tp_mode': 'bucket_pct',
        'tp_value': 0.1,
        'session_filter': 'london_ny',
        'cooldown_mode': 'bars',
        'cooldown_value': 10,
        'max_daily_loss_pct': 2.0,
        'max_consec_busts': 3,
    }
}
