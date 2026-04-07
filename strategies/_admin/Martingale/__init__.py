"""
Martingale — A fully configurable grid/hedged martingale strategy.

Every aspect is modular and pluggable:
  - Direction/Entry: random, any indicator, composite, ML model
  - Sizing: geometric, sqrt, linear, fibonacci, anti-martingale, custom
  - Grid/Hedge: fixed pips, ATR-based, percentage, fibonacci levels
  - Take Profit: fixed pips, ATR, bucket %, risk-reward, trailing, per-level
  - Filters: session, volatility, trend, spread, day-of-week
  - Risk: daily/weekly loss caps, consecutive bust halt, cooldown, abort policies
  - Position: partial close, breakeven move, stop-loss hit(full-close)

Use `preset` hyperparameter to load named configurations (raw, surefire_v1,
surefire_v2, conservative, aggressive, fibonacci, scalper) or set 'custom'
to configure every parameter individually.
"""
import math
import numpy as np
import qengine.helpers as jh
import qengine.indicators as ta
from qengine.strategies import Strategy

# Fibonacci sequence (precomputed for sizing)
_FIB = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765]

# Custom sizing sequences (multipliers relative to base size)
_CUSTOM_SEQUENCES = {
    '1_1_2_3_5_8': [1, 1, 2, 3, 5, 8, 13, 21, 34, 55],
    '1_2_4_8_16': [1, 2, 4, 8, 16, 32, 64, 128, 256, 512],
    '1_1_2_4_7_11': [1, 1, 2, 4, 7, 11, 18, 29, 47, 76],
    '1_2_3_5_8_13_21': [1, 2, 3, 5, 8, 13, 21, 34, 55, 89],
    '1_3_6_12_24': [1, 3, 6, 12, 24, 48, 96, 192, 384, 768],
}


class Martingale(Strategy):

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                        HYPERPARAMETERS                              ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def hyperparameters(self):
        from .presets import PRESETS

        # Signal modes that use each indicator group
        _ema_modes = ['ema_cross', 'ema_rsi', 'ema_macd', 'triple']
        _rsi_modes = ['rsi', 'ema_rsi', 'triple']
        _macd_modes = ['macd', 'ema_macd', 'triple']

        # HPs marked 'general': True are shown for ALL presets (not just custom).
        # Group names are used as section headers in the UI.
        _G = 'General'
        _E = 'Entry Signal'
        _H = 'Grid / Hedge'
        _T = 'Take Profit'
        _F = 'Filters'
        _R = 'Risk Management'
        _P = 'Position Management'

        all_hps = [
            # ── Preset ──
            {'name': 'preset', 'type': 'categorical',
             'options': ['custom'] + sorted(PRESETS.keys()),
             'default': 'original',
             'presets': PRESETS},

            # ── General (always visible) ──
            {'name': 'sizing_curve', 'type': 'categorical', 'group': _G, 'general': True,
             'options': ['geometric', 'sqrt', 'linear', 'fibonacci', 'fixed', 'anti_martingale'],
             'default': 'geometric'},
            {'name': 'sizing_factor', 'type': float, 'group': _G, 'general': True,
             'min': 1.1, 'max': 5.0, 'default': 2.0,
             'depends_on': {'sizing_curve': ['geometric', 'sqrt', 'anti_martingale']}},
            {'name': 'sizing_custom_sequence', 'type': 'categorical', 'group': _G, 'general': True,
             'options': ['none', '1_1_2_3_5_8', '1_2_4_8_16', '1_1_2_4_7_11',
                         '1_2_3_5_8_13_21', '1_3_6_12_24'],
             'default': 'none',
             'description': 'Predefined sizing sequences. Overrides sizing_curve when not none.'},
            {'name': 'base_size_mode', 'type': 'categorical', 'group': _G, 'general': True,
             'options': ['fixed', 'pct_equity', 'risk_pips', 'capital_aware'], 'default': 'pct_equity'},
            {'name': 'base_size_value', 'type': float, 'group': _G, 'general': True,
             'min': 0.01, 'max': 100.0, 'default': 1.0},
            {'name': 'max_bust_dd_pct', 'type': float, 'group': _G, 'general': True,
             'min': 5, 'max': 50, 'default': 20,
             'depends_on': {'base_size_mode': ['capital_aware']},
             'description': 'Max % of account a single bust can lose.'},
            {'name': 'max_levels', 'type': int, 'group': _G, 'general': True,
             'min': 0, 'max': 20, 'default': 6,
             'description': '0 = no hedging, N = allow up to N hedge levels'},

            # ── Entry Signal ──
            {'name': 'signal_mode', 'type': 'categorical', 'group': _E,
             'options': ['none', 'random', 'ema_cross', 'rsi', 'macd', 'supertrend', 'stoch',
                         'cci', 'adx', 'bollinger', 'ema_rsi', 'ema_macd', 'triple',
                         'indicator', 'dual_indicator', 'model'],
             'default': 'random'},
            {'name': 'direction_bias', 'type': 'categorical', 'group': _E,
             'options': ['both', 'long_only', 'short_only'], 'default': 'both'},
            {'name': 'entry_on_crossover', 'type': 'categorical', 'group': _E,
             'options': ['yes', 'no'], 'default': 'no',
             'description': 'Only enter on crossover moment (not while condition holds)'},
            {'name': 'ema_fast', 'type': int, 'group': _E,
             'min': 3, 'max': 50, 'default': 8,
             'depends_on': {'signal_mode': _ema_modes}},
            {'name': 'ema_slow', 'type': int, 'group': _E,
             'min': 10, 'max': 200, 'default': 21,
             'depends_on': {'signal_mode': _ema_modes}},
            {'name': 'rsi_period', 'type': int, 'group': _E,
             'min': 5, 'max': 30, 'default': 14,
             'depends_on': {'signal_mode': _rsi_modes}},
            {'name': 'rsi_ob', 'type': float, 'group': _E,
             'min': 60, 'max': 85, 'default': 70,
             'depends_on': {'signal_mode': _rsi_modes}},
            {'name': 'rsi_os', 'type': float, 'group': _E,
             'min': 15, 'max': 40, 'default': 30,
             'depends_on': {'signal_mode': _rsi_modes}},
            {'name': 'macd_fast', 'type': int, 'group': _E,
             'min': 5, 'max': 20, 'default': 12,
             'depends_on': {'signal_mode': _macd_modes}},
            {'name': 'macd_slow', 'type': int, 'group': _E,
             'min': 15, 'max': 40, 'default': 26,
             'depends_on': {'signal_mode': _macd_modes}},
            {'name': 'macd_signal', 'type': int, 'group': _E,
             'min': 5, 'max': 15, 'default': 9,
             'depends_on': {'signal_mode': _macd_modes}},
            {'name': 'st_period', 'type': int, 'group': _E,
             'min': 5, 'max': 20, 'default': 10,
             'depends_on': {'signal_mode': ['supertrend']}},
            {'name': 'st_factor', 'type': float, 'group': _E,
             'min': 1.0, 'max': 6.0, 'default': 3.0,
             'depends_on': {'signal_mode': ['supertrend']}},
            {'name': 'stoch_k', 'type': int, 'group': _E,
             'min': 5, 'max': 21, 'default': 14,
             'depends_on': {'signal_mode': ['stoch']}},
            {'name': 'stoch_d', 'type': int, 'group': _E,
             'min': 3, 'max': 9, 'default': 3,
             'depends_on': {'signal_mode': ['stoch']}},
            {'name': 'stoch_ob', 'type': float, 'group': _E,
             'min': 70, 'max': 90, 'default': 80,
             'depends_on': {'signal_mode': ['stoch']}},
            {'name': 'stoch_os', 'type': float, 'group': _E,
             'min': 10, 'max': 30, 'default': 20,
             'depends_on': {'signal_mode': ['stoch']}},
            {'name': 'cci_period', 'type': int, 'group': _E,
             'min': 10, 'max': 30, 'default': 20,
             'depends_on': {'signal_mode': ['cci']}},
            {'name': 'cci_ob', 'type': float, 'group': _E,
             'min': 100, 'max': 250, 'default': 100,
             'depends_on': {'signal_mode': ['cci']}},
            {'name': 'cci_os', 'type': float, 'group': _E,
             'min': -250, 'max': -100, 'default': -100,
             'depends_on': {'signal_mode': ['cci']}},
            {'name': 'adx_period', 'type': int, 'group': _E,
             'min': 10, 'max': 30, 'default': 14,
             'depends_on': {'signal_mode': ['adx']}},
            {'name': 'adx_threshold', 'type': float, 'group': _E,
             'min': 15, 'max': 40, 'default': 25,
             'depends_on': {'signal_mode': ['adx']}},
            {'name': 'bb_period', 'type': int, 'group': _E,
             'min': 10, 'max': 30, 'default': 20,
             'depends_on': {'signal_mode': ['bollinger']}},
            {'name': 'bb_std', 'type': float, 'group': _E,
             'min': 1.0, 'max': 3.5, 'default': 2.0,
             'depends_on': {'signal_mode': ['bollinger']}},
            {'name': 'ind_name', 'type': 'categorical', 'group': _E,
             'options': ['rsi', 'cci', 'mfi', 'willr', 'stc', 'fisher', 'dpo', 'cmo',
                         'tsi', 'rsx', 'lrsi', 'srsi', 'ift_rsi', 'mom', 'roc', 'ao',
                         'bop', 'eri', 'kst', 'trix', 'ppo', 'apo', 'dx', 'adxr',
                         'aroonosc', 'chop', 'fosc', 'cfo', 'pfe', 'ultosc', 'wt',
                         'zscore', 'natr', 'atr', 'cvi', 'mass', 'ui', 'chande',
                         'reflex', 'trendflex', 'ttm_squeeze', 'squeeze_momentum',
                         'linearreg_slope', 'linearreg_angle'],
             'default': 'rsi',
             'depends_on': {'signal_mode': ['indicator', 'dual_indicator']}},
            {'name': 'ind_period', 'type': int, 'group': _E,
             'min': 3, 'max': 100, 'default': 14,
             'depends_on': {'signal_mode': ['indicator', 'dual_indicator']}},
            {'name': 'ind_rule', 'type': 'categorical', 'group': _E,
             'options': ['ob_os', 'cross_zero', 'threshold', 'rising_falling'],
             'default': 'ob_os',
             'depends_on': {'signal_mode': ['indicator', 'dual_indicator']},
             'description': 'ob_os=overbought/oversold, cross_zero=above/below 0'},
            {'name': 'ind_long_threshold', 'type': float, 'group': _E,
             'min': -500, 'max': 500, 'default': 30,
             'depends_on': {'signal_mode': ['indicator', 'dual_indicator']}},
            {'name': 'ind_short_threshold', 'type': float, 'group': _E,
             'min': -500, 'max': 500, 'default': 70,
             'depends_on': {'signal_mode': ['indicator', 'dual_indicator']}},
            {'name': 'ind2_name', 'type': 'categorical', 'group': _E,
             'options': ['ema_cross', 'rsi', 'cci', 'mfi', 'willr', 'stc', 'fisher',
                         'adx', 'tsi', 'mom', 'roc', 'macd', 'supertrend', 'bollinger',
                         'stoch', 'aroonosc', 'dx', 'ppo', 'apo', 'zscore', 'trendflex'],
             'default': 'ema_cross',
             'depends_on': {'signal_mode': ['dual_indicator']},
             'description': 'Second indicator for confirmation'},
            {'name': 'ind2_period', 'type': int, 'group': _E,
             'min': 3, 'max': 100, 'default': 21,
             'depends_on': {'signal_mode': ['dual_indicator']}},
            {'name': 'ind2_rule', 'type': 'categorical', 'group': _E,
             'options': ['agree', 'filter'], 'default': 'agree',
             'depends_on': {'signal_mode': ['dual_indicator']},
             'description': 'agree=both must agree, filter=ind2 must not contradict'},
            {'name': 'model_lookback', 'type': int, 'group': _E,
             'min': 10, 'max': 500, 'default': 50,
             'depends_on': {'signal_mode': ['model']},
             'description': 'Number of candles to feed to the model'},

            # ── Grid / Hedge ──
            {'name': 'hedge_mode', 'type': 'categorical', 'group': _H,
             'options': ['fixed_pips', 'atr_based', 'percentage', 'fibonacci_levels'],
             'default': 'fixed_pips'},
            {'name': 'hedge_value', 'type': float, 'group': _H,
             'min': 0.1, 'max': 500.0, 'default': 10.0,
             'description': 'Pips (fixed), ATR mult (atr), % (pct)'},
            {'name': 'hedge_atr_period', 'type': int, 'group': _H,
             'min': 5, 'max': 30, 'default': 14,
             'depends_on': {'hedge_mode': ['atr_based']}},
            {'name': 'hedge_expand', 'type': 'categorical', 'group': _H,
             'options': ['no', 'yes'], 'default': 'no',
             'description': 'Expand hedge distance at deeper levels'},
            {'name': 'hedge_expand_factor', 'type': float, 'group': _H,
             'min': 1.0, 'max': 2.0, 'default': 1.2,
             'depends_on': {'hedge_expand': ['yes']}},

            # ── Take Profit ──
            {'name': 'tp_mode', 'type': 'categorical', 'group': _T,
             'options': ['fixed_pips', 'atr_based', 'bucket_pct', 'risk_reward', 'trailing'],
             'default': 'fixed_pips'},
            {'name': 'tp_value', 'type': float, 'group': _T,
             'min': 0.01, 'max': 500.0, 'default': 20.0,
             'description': 'Pips (fixed), ATR mult (atr), equity % (bucket), ratio (rr), pips (trail)'},
            {'name': 'tp_atr_period', 'type': int, 'group': _T,
             'min': 5, 'max': 30, 'default': 14,
             'depends_on': {'tp_mode': ['atr_based']}},

            # ── Filters ──
            {'name': 'session_filter', 'type': 'categorical', 'group': _F,
             'options': ['any', 'london', 'new_york', 'overlap', 'london_ny', 'asian'],
             'default': 'any'},
            {'name': 'day_filter', 'type': 'categorical', 'group': _F,
             'options': ['any', 'weekdays_only', 'skip_monday', 'skip_friday', 'skip_mon_fri'],
             'default': 'any'},
            {'name': 'vol_filter', 'type': 'categorical', 'group': _F,
             'options': ['none', 'atr_range', 'natr_min'], 'default': 'none'},
            {'name': 'vol_filter_period', 'type': int, 'group': _F,
             'min': 5, 'max': 30, 'default': 14,
             'depends_on': {'vol_filter': ['atr_range', 'natr_min']}},
            {'name': 'vol_filter_min', 'type': float, 'group': _F,
             'min': 0.0, 'max': 100.0, 'default': 0.5,
             'depends_on': {'vol_filter': ['atr_range', 'natr_min']}},
            {'name': 'vol_filter_max', 'type': float, 'group': _F,
             'min': 0.0, 'max': 500.0, 'default': 50.0,
             'depends_on': {'vol_filter': ['atr_range']}},
            {'name': 'trend_filter', 'type': 'categorical', 'group': _F,
             'options': ['none', 'ema_slope', 'adx_gate', 'dm_gate'], 'default': 'none'},
            {'name': 'trend_filter_period', 'type': int, 'group': _F,
             'min': 5, 'max': 50, 'default': 14,
             'depends_on': {'trend_filter': ['ema_slope', 'adx_gate', 'dm_gate']}},
            {'name': 'trend_filter_threshold', 'type': float, 'group': _F,
             'min': 0, 'max': 50, 'default': 25,
             'depends_on': {'trend_filter': ['adx_gate', 'dm_gate']}},
            {'name': 'spread_filter', 'type': 'categorical', 'group': _F,
             'options': ['none', 'max_spread'], 'default': 'none'},
            {'name': 'spread_filter_max', 'type': float, 'group': _F,
             'min': 0.1, 'max': 20.0, 'default': 3.0,
             'depends_on': {'spread_filter': ['max_spread']}},
            {'name': 'confidence_gate', 'type': 'categorical', 'group': _F,
             'options': ['none', 'enabled'], 'default': 'none',
             'description': 'Composite gate: NATR + ADX + ER. Validated on 2024-2025.'},
            {'name': 'confidence_threshold', 'type': float, 'group': _F,
             'min': 0.1, 'max': 0.9, 'default': 0.4,
             'depends_on': {'confidence_gate': ['enabled']}},

            # ── Risk Management ──
            {'name': 'max_daily_loss_pct', 'type': float, 'group': _R,
             'min': 0, 'max': 20, 'default': 0, 'description': '0 = disabled'},
            {'name': 'max_weekly_loss_pct', 'type': float, 'group': _R,
             'min': 0, 'max': 50, 'default': 0, 'description': '0 = disabled'},
            {'name': 'max_consec_busts', 'type': int, 'group': _R,
             'min': 0, 'max': 20, 'default': 0, 'description': '0 = disabled'},
            {'name': 'max_exposure_pct', 'type': float, 'group': _R,
             'min': 0, 'max': 100, 'default': 0,
             'description': 'Max margin as % of equity. 0 = disabled'},
            {'name': 'cooldown_mode', 'type': 'categorical', 'group': _R,
             'options': ['none', 'bars', 'atr_expansion'], 'default': 'none'},
            {'name': 'cooldown_value', 'type': float, 'group': _R,
             'min': 1, 'max': 100, 'default': 10,
             'depends_on': {'cooldown_mode': ['bars', 'atr_expansion']}},
            {'name': 'abort_mode', 'type': 'categorical', 'group': _R,
             'options': ['none', 'level_threshold', 'time_bars', 'pnl_pct'], 'default': 'none'},
            {'name': 'abort_level', 'type': int, 'group': _R,
             'min': 2, 'max': 20, 'default': 6,
             'depends_on': {'abort_mode': ['level_threshold']}},
            {'name': 'abort_time_bars', 'type': int, 'group': _R,
             'min': 10, 'max': 1000, 'default': 100,
             'depends_on': {'abort_mode': ['time_bars']}},
            {'name': 'abort_pnl_pct', 'type': float, 'group': _R,
             'min': -50, 'max': -1, 'default': -10,
             'depends_on': {'abort_mode': ['pnl_pct']}},
            {'name': 'equity_curve_filter', 'type': 'categorical', 'group': _R,
             'options': ['none', 'above_ema'], 'default': 'none',
             'description': 'Only trade when equity curve is above its own EMA'},
            {'name': 'equity_ema_period', 'type': int, 'group': _R,
             'min': 5, 'max': 100, 'default': 20,
             'depends_on': {'equity_curve_filter': ['above_ema']}},

            # ── Position Management ──
            {'name': 'partial_close', 'type': 'categorical', 'group': _P,
             'options': ['none', 'at_breakeven', 'oldest_at_profit'], 'default': 'none'},
            {'name': 'partial_close_pct', 'type': float, 'group': _P,
             'min': 10, 'max': 90, 'default': 50,
             'depends_on': {'partial_close': ['at_breakeven', 'oldest_at_profit']}},
            {'name': 'breakeven_mode', 'type': 'categorical', 'group': _P,
             'options': ['none', 'after_n_levels'], 'default': 'none'},
            {'name': 'breakeven_levels', 'type': int, 'group': _P,
             'min': 1, 'max': 10, 'default': 3,
             'depends_on': {'breakeven_mode': ['after_n_levels']}},
        ]

        # ── Preset-aware HP filtering ──
        # HPs with general=True are visible in ALL presets.
        # Other HPs are visible only in presets that use them.
        all_preset_names = sorted(PRESETS.keys())
        for hp_def in all_hps:
            if hp_def['name'] == 'preset':
                continue

            # General HPs: visible in every preset
            if hp_def.get('general'):
                preset_dep = ['custom'] + all_preset_names
            else:
                relevant_presets = set()
                for pname, pvals in PRESETS.items():
                    # HP is directly set by this preset
                    if hp_def['name'] in pvals:
                        relevant_presets.add(pname)
                        continue
                    # HP is a dependent whose parent condition is met by preset values
                    deps = hp_def.get('depends_on', {})
                    if deps:
                        all_met = True
                        for dep_key, dep_vals in deps.items():
                            parent_val = pvals.get(dep_key)
                            if parent_val is None or parent_val not in dep_vals:
                                all_met = False
                                break
                        if all_met:
                            relevant_presets.add(pname)
                preset_dep = ['custom'] + sorted(relevant_presets)

            existing_deps = hp_def.get('depends_on', {})
            existing_deps['preset'] = preset_dep
            hp_def['depends_on'] = existing_deps

        return all_hps

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                          LIFECYCLE                                  ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def before(self):
        if self.index == 0:
            self._init_state()

        # Daily reset for risk tracking
        if self._is_new_day():
            self.vars['day_start_balance'] = self.balance
            self.vars['daily_busts'] = 0

        # Weekly reset (Monday)
        if self._is_new_week():
            self.vars['week_start_balance'] = self.balance

        # Track equity for equity curve filter
        if self.hp.get('equity_curve_filter', 'none') != 'none':
            self.vars['equity_history'].append(self.balance)

    def _init_state(self):
        """Initialize all strategy state on first candle."""
        self.hedge_mode = True  # Allow simultaneous long+short (CFD tickets)

        # Apply preset as defaults for keys NOT already provided by the user.
        # The frontend applies preset values on load (onPresetChange), so by the
        # time we get here, user-modified HPs already have their final values.
        # We only fill in keys the frontend didn't send (invisible/filtered HPs).
        hp = self.hp
        if hp.get('preset', 'custom') != 'custom':
            from .presets import PRESETS
            preset = PRESETS.get(hp['preset'], {})
            for k, v in preset.items():
                if k not in hp:
                    hp[k] = v

        self.vars.update({
            'cycle_active': False,
            'level': 0,
            'session_dir': None,
            'legs': [],
            'tp_price': None,
            'hedge_trigger_price': None,
            'session_number': 0,
            'session_start_bar': 0,
            'session_start_balance': self.balance,
            'day_start_balance': self.balance,
            'week_start_balance': self.balance,
            'cooldown_until': 0,
            'halted': False,
            'halt_reason': '',
            'consecutive_busts': 0,
            'daily_busts': 0,
            'trailing_tp': None,
            'prev_signal': None,
            'sessions': [],
            'equity_history': [],
            'hedge_stop_order_id': None,
            'pending_hedge_level': None,
            'pending_hedge_dir': None,
        })

    def should_long(self) -> bool:
        if self.vars.get('cycle_active') or self.vars.get('halted'):
            return False
        if not self._cooldown_ok():
            return False
        if not self._filters_pass():
            return False
        if not self._risk_limits_ok():
            return False

        signal = self._get_signal()
        if signal == 'long':
            bias = self.hp.get('direction_bias', 'both')
            return bias in ('both', 'long_only')
        return False

    def should_short(self) -> bool:
        if self.vars.get('cycle_active') or self.vars.get('halted'):
            return False
        if not self._cooldown_ok():
            return False
        if not self._filters_pass():
            return False
        if not self._risk_limits_ok():
            return False

        signal = self._get_signal()
        if signal == 'short':
            bias = self.hp.get('direction_bias', 'both')
            return bias in ('both', 'short_only')
        return False

    def go_long(self):
        # Capture balance BEFORE the order fills (spread/margin haven't been deducted yet)
        self.vars['_pre_entry_balance'] = self.balance
        qty = self._calc_size(0)
        self.buy = qty, self.price

    def go_short(self):
        self.vars['_pre_entry_balance'] = self.balance
        qty = self._calc_size(0)
        self.sell = qty, self.price

    def on_open_position(self, order):
        direction = 'long' if self.is_long else 'short'
        entry = order.price

        self.vars['cycle_active'] = True
        self.vars['level'] = 0
        self.vars['session_dir'] = direction
        self.vars['session_number'] += 1
        self.vars['session_start_bar'] = self.index
        # Use pre-entry balance (captured before order fill) for accurate session PnL
        self.vars['session_start_balance'] = self.vars.pop('_pre_entry_balance', self.balance)

        leg = {
            'level': 0,
            'dir': direction,
            'qty': abs(order.qty),
            'entry': entry,
            'ticket_id': getattr(order, 'ticket_id', None),
        }
        self.vars['legs'] = [leg]

        # Compute TP and hedge trigger
        self.vars['tp_price'] = self._compute_tp(entry, direction)
        self.vars['hedge_trigger_price'] = self._compute_hedge_trigger(entry, direction, 0)
        self.vars['trailing_tp'] = None

        # Set engine-managed TP on this ticket (1m resolution)
        if self.vars['tp_price'] is not None and leg.get('ticket_id'):
            self.set_ticket_tp_sl(leg['ticket_id'], tp=self.vars['tp_price'])

        # Place STOP order for next hedge level (also 1m resolution)
        self._place_hedge_stop()

    def on_increased_position(self, order):
        """Hedge STOP order filled — add the new leg, recalculate TP, place next hedge."""
        if not self.vars.get('cycle_active'):
            return

        level = self.vars.get('pending_hedge_level')
        new_dir = self.vars.get('pending_hedge_dir')
        if level is None or new_dir is None:
            return

        self.vars['level'] = level
        entry = order.price

        ticket_id = None
        if self.position.is_cfd_mode and self.position._tickets:
            ticket_id = self.position._tickets[-1].id

        leg = {
            'level': level,
            'dir': new_dir,
            'qty': abs(order.qty),
            'entry': entry,
            'ticket_id': ticket_id,
        }
        self.vars['legs'].append(leg)

        # Clear pending state
        self.vars['hedge_stop_order_id'] = None
        self.vars['pending_hedge_level'] = None
        self.vars['pending_hedge_dir'] = None

        # Recalculate TP from new last leg
        self._recalculate_tp()

        # Compute and place next hedge trigger
        self.vars['hedge_trigger_price'] = self._compute_hedge_trigger(entry, new_dir, level)
        self._place_hedge_stop()

    def update_position(self):
        if not self.vars.get('cycle_active'):
            return

        # Check abort conditions
        if self._should_abort():
            self._cancel_hedge_stop()
            self._close_cycle('abort')
            return

        # Session-level TP modes that can't use ticket TP (bucket_pct, trailing)
        tp_mode = self.hp.get('tp_mode', 'fixed_pips')
        if tp_mode in ('bucket_pct', 'trailing'):
            if self._check_tp():
                self._cancel_hedge_stop()
                self._close_cycle('tp_hit')
                return

        # Check partial close / breakeven
        self._check_position_management()

    def on_close_position(self, order, closed_trade):
        pass  # Handled by _close_cycle

    def _find_leg_for_ticket(self, ticket):
        """Find the leg dict that matches a ticket (by ticket_id or position)."""
        legs = self.vars.get('legs', [])
        for leg in legs:
            if leg.get('ticket_id') and leg['ticket_id'] == ticket.id:
                return leg
        return None

    def _tag_last_trade_with_session(self, ticket, exit_reason):
        """Tag the most recently closed trade (engine-closed ticket) with session metadata.

        The engine's _check_ticket_tp_sl_triggers records the trigger trade BEFORE
        calling this callback, but only with exit_reason — no session number.  We
        retroactively patch it here so session grouping works.
        """
        from qengine.store import store
        if store.closed_trades.trades:
            last = store.closed_trades.trades[-1]
            if not last.meta:
                last.meta = {}
            last.meta.setdefault('session', self.vars.get('session_number', 0))
            last.meta['session_exit_reason'] = exit_reason
            # Find specific leg for this ticket to get correct level/leg_index
            leg = self._find_leg_for_ticket(ticket)
            if leg:
                last.meta['level'] = leg['level']
                last.meta['leg_index'] = leg['level']
            else:
                last.meta.setdefault('level', self.vars.get('level', 0))
                last.meta.setdefault('leg_index', self.vars.get('level', 0))

    def _close_remaining_tickets(self, fill_price, exit_reason):
        """Close remaining open tickets with per-leg metadata."""
        if not self.position._tickets:
            return
        remaining_ticket_ids = {t.id for t in self.position._tickets}
        # Build per-leg meta for remaining tickets
        legs = self.vars.get('legs', [])
        leg_by_ticket = {}
        for leg in legs:
            tid = leg.get('ticket_id')
            if tid and tid in remaining_ticket_ids:
                leg_by_ticket[tid] = leg

        # Close all tickets — the base method applies the same meta to all,
        # so we close individually for correct per-leg metadata.
        from qengine.services import closed_trade_service
        for ticket in list(self.position._tickets):
            close_result = self.position.close_ticket(ticket.id, fill_price)
            if close_result is None:
                continue
            pnl = close_result['pnl']
            if self.position.exchange:
                self.position.exchange.add_realized_pnl(pnl)
            leg = leg_by_ticket.get(ticket.id)
            meta = {
                'session': self.vars.get('session_number', 0),
                'exit_reason': exit_reason,
                'session_exit_reason': exit_reason,
                'level': leg['level'] if leg else self.vars.get('level', 0),
                'leg_index': leg['level'] if leg else self.vars.get('level', 0),
            }
            closed_trade_service.record_ticket_close(
                self.position, close_result['ticket'], fill_price, pnl, meta=meta
            )
        self.trades_count += len(remaining_ticket_ids)
        # Reset position state
        self.position.entry_price = None
        self.position.exit_price = fill_price
        import qengine.helpers as jh
        self.position.closed_at = jh.now_to_timestamp()
        self._execute_cancel()

    def on_ticket_tp_hit(self, ticket, fill_price):
        """Engine closed last leg's ticket at TP. Cancel hedge STOP, close rest, end cycle."""
        if not self.vars.get('cycle_active'):
            return
        self._cancel_hedge_stop()
        self._tag_last_trade_with_session(ticket, 'tp_hit')
        self._close_remaining_tickets(fill_price, 'tp_hit')
        self._end_cycle('tp_hit')

    def on_ticket_sl_hit(self, ticket, fill_price):
        """Engine closed a ticket at SL. Cancel hedge STOP, close rest, end cycle."""
        if not self.vars.get('cycle_active'):
            return
        self._cancel_hedge_stop()
        self._tag_last_trade_with_session(ticket, 'sl_hit')
        self._close_remaining_tickets(fill_price, 'sl_hit')
        self._end_cycle('sl_hit')

    def after(self):
        pass

    def before_terminate(self):
        if self.vars.get('cycle_active'):
            self._cancel_hedge_stop()
            self._close_cycle('terminate')

    def terminate(self):
        pass

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                        SIGNAL MODULE                                ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def _get_signal(self):
        """Returns 'long', 'short', or None based on configured signal mode."""
        mode = self.hp.get('signal_mode', 'random')
        method = getattr(self, f'_signal_{mode}', None)
        if method:
            raw = method()
        else:
            raw = self._signal_random()

        # Crossover filter: only enter on the moment of signal change
        if self.hp.get('entry_on_crossover', 'no') == 'yes':
            prev = self.vars.get('prev_signal')
            self.vars['prev_signal'] = raw
            if raw == prev:
                return None  # Signal unchanged — not a crossover

        return raw

    def _signal_none(self):
        """Always-enter mode: returns 'long' (direction_bias handles filtering)."""
        bias = self.hp.get('direction_bias', 'both')
        if bias == 'long_only':
            return 'long'
        elif bias == 'short_only':
            return 'short'
        # 'both': alternate based on bar index for even distribution
        return 'long' if self.index % 2 == 0 else 'short'

    def _signal_random(self):
        # Use candle timestamp as seed component for reproducibility across runs
        seed = int(self.current_candle[0]) % (2**31)
        rng = np.random.RandomState(seed)
        return rng.choice(['long', 'short'])

    def _signal_ema_cross(self):
        fast = ta.ema(self.candles, period=self.hp.get('ema_fast', 8))
        slow = ta.ema(self.candles, period=self.hp.get('ema_slow', 21))
        return 'long' if fast > slow else 'short'

    def _signal_rsi(self):
        val = ta.rsi(self.candles, period=self.hp.get('rsi_period', 14))
        if val <= self.hp.get('rsi_os', 30):
            return 'long'
        if val >= self.hp.get('rsi_ob', 70):
            return 'short'
        return None

    def _signal_macd(self):
        m = ta.macd(self.candles,
                    fast_period=self.hp.get('macd_fast', 12),
                    slow_period=self.hp.get('macd_slow', 26),
                    signal_period=self.hp.get('macd_signal', 9))
        return 'long' if m.macd > m.signal else 'short'

    def _signal_supertrend(self):
        st = ta.supertrend(self.candles,
                           period=self.hp.get('st_period', 10),
                           factor=self.hp.get('st_factor', 3.0))
        return 'long' if st.trend > 0 else 'short'

    def _signal_stoch(self):
        s = ta.stoch(self.candles,
                     fastk_period=self.hp.get('stoch_k', 14),
                     slowd_period=self.hp.get('stoch_d', 3))
        if s.k <= self.hp.get('stoch_os', 20):
            return 'long'
        if s.k >= self.hp.get('stoch_ob', 80):
            return 'short'
        return None

    def _signal_cci(self):
        val = ta.cci(self.candles, period=self.hp.get('cci_period', 20))
        if val <= self.hp.get('cci_os', -100):
            return 'long'
        if val >= self.hp.get('cci_ob', 100):
            return 'short'
        return None

    def _signal_adx(self):
        adx_val = ta.adx(self.candles, period=self.hp.get('adx_period', 14))
        if adx_val < self.hp.get('adx_threshold', 25):
            return None  # No trend — don't enter
        # Use +DI / -DI for direction
        plus_di = ta.plus_di(self.candles, period=self.hp.get('adx_period', 14))
        minus_di = ta.minus_di(self.candles, period=self.hp.get('adx_period', 14))
        return 'long' if plus_di > minus_di else 'short'

    def _signal_bollinger(self):
        bb = ta.bollinger_bands(self.candles,
                                period=self.hp.get('bb_period', 20),
                                devup=self.hp.get('bb_std', 2.0),
                                devdn=self.hp.get('bb_std', 2.0))
        if self.close <= bb.lowerband:
            return 'long'
        if self.close >= bb.upperband:
            return 'short'
        return None

    def _signal_ema_rsi(self):
        ema_sig = self._signal_ema_cross()
        rsi_sig = self._signal_rsi()
        if rsi_sig is None:
            return None
        return ema_sig if ema_sig == rsi_sig else None

    def _signal_ema_macd(self):
        ema_sig = self._signal_ema_cross()
        macd_sig = self._signal_macd()
        return ema_sig if ema_sig == macd_sig else None

    def _signal_triple(self):
        ema_sig = self._signal_ema_cross()
        rsi_sig = self._signal_rsi()
        macd_sig = self._signal_macd()
        if rsi_sig is None:
            return None
        if ema_sig == rsi_sig == macd_sig:
            return ema_sig
        return None

    # ── Generic Indicator Signal ──

    def _eval_indicator(self, name, period):
        """Call any ta.xxx indicator by name. Returns scalar value."""
        fn = getattr(ta, name, None)
        if fn is None:
            return None
        try:
            # Most indicators accept (candles, period=...) — try that first
            return fn(self.candles, period=period)
        except TypeError:
            try:
                return fn(self.candles)
            except Exception:
                return None

    def _apply_rule(self, value, rule, long_thresh, short_thresh):
        """Apply a signal rule to a scalar indicator value."""
        if value is None:
            return None

        # Handle named tuple results (take first numeric field)
        if hasattr(value, '_fields'):
            value = getattr(value, value._fields[0])
        if hasattr(value, '__len__') and not isinstance(value, (int, float)):
            value = float(value) if np.isscalar(value) else float(value[-1]) if len(value) else None
        if value is None:
            return None

        if rule == 'ob_os':
            if value <= long_thresh:
                return 'long'
            if value >= short_thresh:
                return 'short'
            return None
        elif rule == 'cross_zero':
            return 'long' if value > 0 else 'short'
        elif rule == 'threshold':
            if value <= long_thresh:
                return 'long'
            if value >= short_thresh:
                return 'short'
            return None
        elif rule == 'rising_falling':
            # Compare current vs previous via sequential
            fn = getattr(ta, self.hp.get('ind_name', 'rsi'), None)
            if fn:
                try:
                    seq = fn(self.candles, period=self.hp.get('ind_period', 14), sequential=True)
                    if hasattr(seq, '_fields'):
                        seq = getattr(seq, seq._fields[0])
                    if hasattr(seq, '__len__') and len(seq) >= 2:
                        return 'long' if seq[-1] > seq[-2] else 'short'
                except Exception:
                    pass
            return 'long' if value > 0 else 'short'
        return None

    def _signal_indicator(self):
        """Generic single-indicator signal using any ta.xxx function."""
        name = self.hp.get('ind_name', 'rsi')
        period = self.hp.get('ind_period', 14)
        rule = self.hp.get('ind_rule', 'ob_os')
        long_t = self.hp.get('ind_long_threshold', 30)
        short_t = self.hp.get('ind_short_threshold', 70)

        value = self._eval_indicator(name, period)
        return self._apply_rule(value, rule, long_t, short_t)

    def _signal_dual_indicator(self):
        """Two-indicator confirmation signal."""
        # Primary indicator
        sig1 = self._signal_indicator()

        # Secondary indicator
        ind2_name = self.hp.get('ind2_name', 'ema_cross')
        ind2_period = self.hp.get('ind2_period', 21)

        # If ind2 is a built-in signal mode, use that method directly
        sig2_method = getattr(self, f'_signal_{ind2_name}', None)
        if sig2_method:
            sig2 = sig2_method()
        else:
            val2 = self._eval_indicator(ind2_name, ind2_period)
            sig2 = self._apply_rule(val2, 'cross_zero', 0, 0)

        combine = self.hp.get('ind2_rule', 'agree')
        if combine == 'agree':
            # Both must give same non-None signal
            if sig1 is not None and sig1 == sig2:
                return sig1
            return None
        elif combine == 'filter':
            # Primary signal stands unless ind2 contradicts
            if sig1 is None:
                return None
            if sig2 is not None and sig2 != sig1:
                return None  # Contradiction — skip
            return sig1
        return sig1

    def _signal_model(self):
        """ML model signal. Override this or set self.signal_fn before running.
        signal_fn(candles, hp) -> 'long' | 'short' | None
        """
        fn = getattr(self, 'signal_fn', None)
        if fn is None:
            return self._signal_random()  # Fallback if no model attached
        lookback = self.hp.get('model_lookback', 50)
        candles = self.candles[-lookback:] if len(self.candles) > lookback else self.candles
        try:
            result = fn(candles, self.hp)
            if result in ('long', 'short'):
                return result
            return None
        except Exception:
            return None

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                         SIZING MODULE                               ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def _margin_to_qty(self, margin_dollars):
        """Convert a margin amount (dollars) to position qty (units).

        qty = margin * leverage / price
        This matches the exposure table formula exactly.
        """
        price = self.price if self.price > 0 else 1.0
        lev = self.leverage if hasattr(self, 'leverage') else 1
        return margin_dollars * lev / price

    def _base_size(self):
        """Calculate base position size in UNITS (level 0)."""
        mode = self.hp.get('base_size_mode', 'pct_equity')
        val = self.hp.get('base_size_value', 1.0)

        if mode == 'fixed':
            return val
        elif mode == 'pct_equity':
            # val% of equity as margin, converted to units
            margin = self.balance * (val / 100.0)
            return self._margin_to_qty(margin)
        elif mode == 'risk_pips':
            # Size such that hedge_distance pips = val% of equity risk
            hedge_dist = self._hedge_distance_pips()
            if hedge_dist <= 0:
                return self._margin_to_qty(self.balance * 0.01)
            pip_val = self.pip_size if hasattr(self, 'pip_size') else 0.0001
            return self.balance * (val / 100.0) / (hedge_dist * pip_val)
        elif mode == 'capital_aware':
            return self._capital_aware_base_size()
        return val

    def _capital_aware_base_size(self):
        """Compute base lot so a full bust loses at most max_bust_dd_pct of account.

        Simulates actual hedged-grid bust loss by computing net PnL of all
        alternating tickets at the worst-case price (price runs past final level).
        """
        max_dd_pct = self.hp.get('max_bust_dd_pct', 20) / 100.0
        max_dd_dollars = self.balance * max_dd_pct
        max_levels = self.hp.get('max_levels', 6)
        curve = self.hp.get('sizing_curve', 'fibonacci')
        factor = self.hp.get('sizing_factor', 2.0)

        # Compute multiplier at each level (relative to base=1)
        multipliers = []
        for lvl in range(max_levels):
            if curve == 'geometric':
                multipliers.append(factor ** lvl)
            elif curve == 'sqrt':
                multipliers.append((factor ** 0.5) ** lvl)
            elif curve == 'fibonacci':
                multipliers.append(_FIB[min(lvl, len(_FIB) - 1)])
            elif curve == 'linear':
                multipliers.append(1 + lvl)
            else:
                multipliers.append(1.0)

        # Simulate worst-case: price runs one more hedge distance past the last level.
        # Build alternating legs with base=1 and compute net PnL at bust price.
        hedge_dist_pips = [self._hedge_distance_pips(lvl) for lvl in range(max_levels)]
        # Simulated entries relative to 0 (in pips)
        entries_pips = [0.0]
        directions = ['long']  # initial direction
        for lvl in range(1, max_levels):
            prev_entry = entries_pips[-1]
            prev_dir = directions[-1]
            if prev_dir == 'long':
                entries_pips.append(prev_entry - hedge_dist_pips[lvl - 1])
                directions.append('short')
            else:
                entries_pips.append(prev_entry + hedge_dist_pips[lvl - 1])
                directions.append('long')

        # Bust price: one more hedge distance past the last entry against last leg
        last_dir = directions[-1]
        last_entry = entries_pips[-1]
        if last_dir == 'long':
            bust_price_pips = last_entry - hedge_dist_pips[-1]
        else:
            bust_price_pips = last_entry + hedge_dist_pips[-1]

        # Compute net loss per base unit at bust price
        total_loss_per_base = 0
        for lvl in range(max_levels):
            size = multipliers[lvl]
            if directions[lvl] == 'long':
                pnl = size * (bust_price_pips - entries_pips[lvl])
            else:
                pnl = size * (entries_pips[lvl] - bust_price_pips)
            total_loss_per_base += pnl

        total_loss_per_base = abs(total_loss_per_base)
        if total_loss_per_base <= 0:
            return self.balance * 0.001

        # pip_value = pip_size * contract_size (e.g., 0.0001 * 100000 = $10/pip/lot)
        pip_val = self.pip_size * getattr(self, 'contract_size', 100000)
        if pip_val <= 0:
            pip_val = 10.0  # default for standard forex

        base = max_dd_dollars / (total_loss_per_base * pip_val)
        return max(base, 0.001)

    def _calc_size(self, level):
        """Calculate position size for a given hedge level."""
        # Custom sequence overrides curve
        seq_key = self.hp.get('sizing_custom_sequence', 'none')
        if seq_key != 'none':
            seq = _CUSTOM_SEQUENCES.get(seq_key, None)
            if seq:
                base = self._base_size()
                idx = min(level, len(seq) - 1)
                return base * seq[idx]

        base = self._base_size()
        curve = self.hp.get('sizing_curve', 'geometric')
        m = self.hp.get('sizing_factor', 2.0)

        if curve == 'geometric':
            return base * (m ** level)
        elif curve == 'sqrt':
            return base * (m ** 0.5) ** level
        elif curve == 'linear':
            return base * (1 + level)
        elif curve == 'fibonacci':
            idx = min(level, len(_FIB) - 1)
            return base * _FIB[idx]
        elif curve == 'fixed':
            return base  # Same size every level
        elif curve == 'anti_martingale':
            # Reduce size at deeper levels (opposite of martingale)
            return base / (m ** level) if level > 0 else base
        return base

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                    GRID / HEDGE MODULE                              ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def _hedge_distance_pips(self, level=0):
        """Raw hedge distance in pips for a given level."""
        mode = self.hp.get('hedge_mode', 'fixed_pips')
        val = self.hp.get('hedge_value', 10.0)

        if mode == 'fixed_pips':
            dist = val
        elif mode == 'atr_based':
            period = self.hp.get('hedge_atr_period', 14)
            atr = ta.atr(self.candles, period=period)
            dist = self.price_to_pips(atr * val) if hasattr(self, 'price_to_pips') else val
        elif mode == 'percentage':
            dist = self.price_to_pips(self.price * val / 100.0) if hasattr(self, 'price_to_pips') else val
        elif mode == 'fibonacci_levels':
            fib_distances = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]
            idx = min(level, len(fib_distances) - 1)
            dist = val * fib_distances[idx]  # val is the base unit in pips
        else:
            dist = val

        # Expanding hedge distance at deeper levels
        if self.hp.get('hedge_expand', 'no') == 'yes':
            factor = self.hp.get('hedge_expand_factor', 1.2)
            dist *= factor ** level

        return max(dist, 0.1)

    def _compute_hedge_trigger(self, entry_price, direction, level):
        """Compute the price at which the next hedge should trigger."""
        dist_pips = self._hedge_distance_pips(level)
        dist_price = self.pips_to_price(dist_pips) if hasattr(self, 'pips_to_price') else dist_pips * 0.0001

        if direction == 'long':
            return entry_price - dist_price  # Price drops → hedge with short
        else:
            return entry_price + dist_price  # Price rises → hedge with long

    def _place_hedge_stop(self):
        """Place a STOP order for the next hedge level via the engine order system.
        This runs at 1m resolution in _simulate_price_change_effect, matching
        ticket TP resolution — so both TP and hedge race fairly.
        """
        trigger = self.vars.get('hedge_trigger_price')
        if trigger is None:
            return

        level = self.vars['level'] + 1
        max_levels = self.hp.get('max_levels', 6)
        if level > max_levels:
            return

        last_leg = self.vars['legs'][-1]
        new_dir = 'short' if last_leg['dir'] == 'long' else 'long'
        qty = self._calc_size(level)
        side = 'buy' if new_dir == 'long' else 'sell'

        order = self.broker.api.stop_order(
            self.exchange, self.symbol, abs(qty), trigger, side, reduce_only=False
        )
        if order:
            self.vars['hedge_stop_order_id'] = order.id
            self.vars['pending_hedge_level'] = level
            self.vars['pending_hedge_dir'] = new_dir

    def _cancel_hedge_stop(self):
        """Cancel the pending hedge STOP order if it exists."""
        order_id = self.vars.get('hedge_stop_order_id')
        if order_id:
            self.broker.cancel_order(order_id)
            self.vars['hedge_stop_order_id'] = None
            self.vars['pending_hedge_level'] = None
            self.vars['pending_hedge_dir'] = None

    def _compute_tp(self, entry_price, direction):
        """Compute take-profit price (or None for bucket/trailing modes)."""
        mode = self.hp.get('tp_mode', 'fixed_pips')

        if mode == 'bucket_pct' or mode == 'trailing':
            return None  # Checked dynamically in _check_tp

        if mode == 'fixed_pips':
            dist = self.pips_to_price(self.hp.get('tp_value', 20.0)) if hasattr(self, 'pips_to_price') else self.hp.get('tp_value', 20.0) * 0.0001
        elif mode == 'atr_based':
            period = self.hp.get('tp_atr_period', 14)
            atr = ta.atr(self.candles, period=period)
            dist = atr * self.hp.get('tp_value', 2.0)
        elif mode == 'risk_reward':
            hedge_dist = self.pips_to_price(self._hedge_distance_pips(0)) if hasattr(self, 'pips_to_price') else self._hedge_distance_pips(0) * 0.0001
            dist = hedge_dist * self.hp.get('tp_value', 2.0)
        else:
            dist = self.pips_to_price(self.hp.get('tp_value', 20.0)) if hasattr(self, 'pips_to_price') else self.hp.get('tp_value', 20.0) * 0.0001

        if direction == 'long':
            return entry_price + dist
        else:
            return entry_price - dist

    def _check_tp(self):
        """Check if take-profit condition is met.

        For price-based modes (fixed_pips, atr_based, risk_reward), the engine
        handles TP via ticket triggers — this method only checks session-level
        modes (bucket_pct, trailing).
        """
        mode = self.hp.get('tp_mode', 'fixed_pips')

        if mode == 'bucket_pct':
            pnl_pct = self._session_pnl_pct()
            target = self.hp.get('tp_value', 0.1)
            return pnl_pct >= target

        if mode == 'trailing':
            return self._check_trailing_tp()

        # Price-based modes (fixed_pips, atr_based, risk_reward) are handled
        # by the engine via on_ticket_tp_hit callback. No manual check needed.
        return False

    def _check_trailing_tp(self):
        """Trailing TP: activate after reaching profit, then trail back."""
        trail_dist = self.pips_to_price(self.hp.get('tp_value', 10.0)) if hasattr(self, 'pips_to_price') else self.hp.get('tp_value', 10.0) * 0.0001
        direction = self.vars['session_dir']
        pnl = self._session_pnl()
        trailing = self.vars.get('trailing_tp')

        if pnl > 0:
            # In profit — update trailing stop
            if direction == 'long':
                new_trail = self.price - trail_dist
                if trailing is None or new_trail > trailing:
                    self.vars['trailing_tp'] = new_trail
                    trailing = new_trail
                return self.low <= trailing
            else:
                new_trail = self.price + trail_dist
                if trailing is None or new_trail < trailing:
                    self.vars['trailing_tp'] = new_trail
                    trailing = new_trail
                return self.high >= trailing
        return False

    def _recalculate_tp(self):
        """Recalculate TP price after adding a new hedge level.
        Clears TP on all other tickets, sets TP only on last leg's ticket."""
        if self.hp.get('tp_mode') in ('bucket_pct', 'trailing'):
            return

        last_leg = self.vars['legs'][-1]
        self.vars['tp_price'] = self._compute_tp(last_leg['entry'], last_leg['dir'])

        if self.vars['tp_price'] is not None:
            self.set_all_tickets_tp_sl(tp=None)
            if last_leg.get('ticket_id'):
                self.set_ticket_tp_sl(last_leg['ticket_id'], tp=self.vars['tp_price'])

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                        FILTER MODULE                                ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def _filters_pass(self):
        """Check all configured filters. Returns True if all pass."""
        return (self._session_filter_ok() and
                self._day_filter_ok() and
                self._vol_filter_ok() and
                self._trend_filter_ok() and
                self._spread_filter_ok() and
                self._confidence_gate_ok())

    def _session_filter_ok(self):
        f = self.hp.get('session_filter', 'any')
        if f == 'any':
            return True
        session = getattr(self, 'session', None)
        if session is None:
            return True

        if f == 'london':
            return session == 'london'
        if f == 'new_york':
            return session == 'new_york'
        if f == 'overlap':
            return session == 'overlap'
        if f == 'london_ny':
            return session in ('london', 'new_york', 'overlap')
        if f == 'asian':
            return session == 'asian'
        return True

    def _day_filter_ok(self):
        f = self.hp.get('day_filter', 'any')
        if f == 'any':
            return True
        try:
            dow = jh.timestamp_to_arrow(self.current_candle[0]).weekday()  # 0=Mon, 6=Sun
        except Exception:
            return True
        if f == 'weekdays_only':
            return dow < 5
        if f == 'skip_monday':
            return dow != 0
        if f == 'skip_friday':
            return dow != 4
        if f == 'skip_mon_fri':
            return dow not in (0, 4)
        return True

    def _vol_filter_ok(self):
        f = self.hp.get('vol_filter', 'none')
        if f == 'none':
            return True
        if f == 'atr_range':
            period = self.hp.get('vol_filter_period', 14)
            atr = ta.atr(self.candles, period=period)
            atr_pips = self.price_to_pips(atr) if hasattr(self, 'price_to_pips') else atr / 0.0001
            return self.hp.get('vol_filter_min', 0.5) <= atr_pips <= self.hp.get('vol_filter_max', 50.0)
        if f == 'natr_min':
            period = self.hp.get('vol_filter_period', 14)
            natr_val = ta.natr(self.candles, period=period)
            return natr_val >= self.hp.get('vol_filter_min', 0.02)
        return True

    def _trend_filter_ok(self):
        """Trend filter gates entry — only enter in direction of trend."""
        f = self.hp.get('trend_filter', 'none')
        if f == 'none':
            return True
        if f == 'adx_gate':
            period = self.hp.get('trend_filter_period', 20)
            adx_val = ta.adx(self.candles, period=period)
            return adx_val >= self.hp.get('trend_filter_threshold', 25)
        if f == 'ema_slope':
            period = self.hp.get('trend_filter_period', 20)
            ema = ta.ema(self.candles, period=period, sequential=True)
            if len(ema) < 3:
                return True
            slope = ema[-1] - ema[-3]
            # Require meaningful slope: at least 1 pip movement over 2 bars
            min_slope = self.pip_size if hasattr(self, 'pip_size') else 0.0001
            return abs(slope) > min_slope
        if f == 'dm_gate':
            period = self.hp.get('trend_filter_period', 14)
            dm_result = ta.dm(self.candles, period=period)
            thresh = self.hp.get('trend_filter_threshold', 0)
            # DM plus > threshold means there's directional movement
            return dm_result.plus >= thresh or dm_result.minus >= thresh
        return True

    def _spread_filter_ok(self):
        f = self.hp.get('spread_filter', 'none')
        if f == 'none':
            return True
        if f == 'max_spread':
            spread_pips = self.price_to_pips(self.spread) if hasattr(self, 'spread') and self.spread else 0
            return spread_pips <= self.hp.get('spread_filter_max', 3.0)
        return True

    def _confidence_gate_ok(self):
        """Composite confidence gate: NATR + ADX + ER. Validated on 2024-2025 walk-forward."""
        if self.hp.get('confidence_gate', 'none') == 'none':
            return True
        thresh = self.hp.get('confidence_threshold', 0.4)

        score = 0.0
        count = 0
        # NATR component: higher vol = more confident
        natr_val = ta.natr(self.candles, period=14)
        if not np.isnan(natr_val):
            score += np.clip(natr_val / 0.1, 0, 1)
            count += 1
        # ADX component: stronger trend = more confident
        adx_val = ta.adx(self.candles, period=14)
        if not np.isnan(adx_val):
            score += np.clip((adx_val - 15) / 30, 0, 1)
            count += 1
        # ER component: higher efficiency = more confident
        er_val = ta.er(self.candles, period=100)
        if not np.isnan(er_val):
            score += np.clip(er_val / 0.4, 0, 1)
            count += 1

        confidence = score / count if count > 0 else 0.5
        return confidence >= thresh

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                     RISK MANAGEMENT MODULE                          ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def _risk_limits_ok(self):
        """Check global risk limits before allowing new entry."""
        # Daily loss limit
        max_daily = self.hp.get('max_daily_loss_pct', 0)
        if max_daily > 0:
            day_start = self.vars.get('day_start_balance', self.balance)
            if day_start > 0:
                daily_loss_pct = (day_start - self.balance) / day_start * 100
                if daily_loss_pct >= max_daily:
                    return False

        # Consecutive bust limit
        max_consec = self.hp.get('max_consec_busts', 0)
        if max_consec > 0:
            if self.vars.get('consecutive_busts', 0) >= max_consec:
                return False

        # Max exposure limit (checked here for pre-entry and in _check_hedge_trigger for mid-cycle)
        if not self._exposure_ok():
            return False

        # Weekly loss limit
        max_weekly = self.hp.get('max_weekly_loss_pct', 0)
        if max_weekly > 0:
            week_start = self.vars.get('week_start_balance', self.balance)
            if week_start > 0:
                weekly_loss_pct = (week_start - self.balance) / week_start * 100
                if weekly_loss_pct >= max_weekly:
                    return False

        # Equity curve filter
        if self.hp.get('equity_curve_filter', 'none') == 'above_ema':
            hist = self.vars.get('equity_history', [])
            period = self.hp.get('equity_ema_period', 20)
            if len(hist) >= period:
                ema = self._simple_ema(hist, period)
                if self.balance < ema:
                    return False  # Equity below its EMA — pause trading

        return True

    def _exposure_ok(self):
        """Check max exposure limit using actual position tickets, not legs list."""
        max_exp = self.hp.get('max_exposure_pct', 0)
        if max_exp <= 0 or self.balance <= 0:
            return True
        # Use actual position gross exposure if available, else compute from legs
        if hasattr(self, 'position') and self.position.is_open and self.position.is_cfd_mode:
            total_qty = self.position.gross_exposure
        else:
            total_qty = sum(abs(leg['qty']) for leg in self.vars.get('legs', []))
        if total_qty <= 0:
            return True
        exposure_pct = (total_qty * self.price) / self.balance * 100
        return exposure_pct < max_exp

    def _cooldown_ok(self):
        mode = self.hp.get('cooldown_mode', 'none')
        if mode == 'none':
            return True
        return self.index >= self.vars.get('cooldown_until', 0)

    def _should_abort(self):
        """Check if the current cycle should be force-closed."""
        mode = self.hp.get('abort_mode', 'none')
        if mode == 'none':
            return False

        if mode == 'level_threshold':
            return self.vars['level'] >= self.hp.get('abort_level', 6)

        if mode == 'time_bars':
            bars_in = self.index - self.vars.get('session_start_bar', 0)
            return bars_in >= self.hp.get('abort_time_bars', 100)

        if mode == 'pnl_pct':
            pnl_pct = self._session_pnl_pct()
            return pnl_pct <= self.hp.get('abort_pnl_pct', -10)

        return False

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                   POSITION MANAGEMENT MODULE                        ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def _compute_breakeven_price(self):
        """Find the price where net PnL of all tickets is zero.

        For alternating long/short legs, solve: sum(qty_i * dir_i * (P - entry_i)) = 0
        where dir_i = +1 for long, -1 for short.
        Solution: P = sum(qty_i * dir_i * entry_i) / sum(qty_i * dir_i)
        """
        legs = self.vars.get('legs', [])
        if not legs:
            return None
        weighted_sum = 0.0
        net_signed_qty = 0.0
        for leg in legs:
            sign = 1.0 if leg['dir'] == 'long' else -1.0
            weighted_sum += leg['qty'] * sign * leg['entry']
            net_signed_qty += leg['qty'] * sign
        if abs(net_signed_qty) < 1e-10:
            return None  # perfectly hedged — no breakeven price exists
        return weighted_sum / net_signed_qty

    def _check_position_management(self):
        """Mid-session adjustments: partial close, breakeven move."""
        bm = self.hp.get('breakeven_mode', 'none')
        if bm == 'after_n_levels':
            be_levels = self.hp.get('breakeven_levels', 3)
            if self.vars['level'] >= be_levels and self.vars.get('tp_price') is not None:
                be_price = self._compute_breakeven_price()
                if be_price is not None:
                    self.vars['tp_price'] = be_price
                    self.set_all_tickets_tp_sl(tp=None)
                    last_leg = self.vars['legs'][-1] if self.vars.get('legs') else None
                    if last_leg and last_leg.get('ticket_id'):
                        self.set_ticket_tp_sl(last_leg['ticket_id'], tp=be_price)

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                     EXECUTION ENGINE                                ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def _close_cycle(self, reason):
        """Close all tickets/positions and reset for next cycle.
        Called from update_position() for manual exits (abort, bucket_pct, trailing, terminate).
        Works in both CFD mode (_close_remaining_tickets) and futures mode (liquidate).
        """
        self._cancel_hedge_stop()

        # Use exact TP price for TP exits, candle close for everything else
        if reason == 'tp_hit' and self.vars.get('tp_price') is not None:
            exit_price = self.vars['tp_price']
        else:
            exit_price = self.price

        # Close all positions
        if self.is_open:
            is_cfd = getattr(self.position, 'is_cfd_mode', False)
            if is_cfd:
                self._close_remaining_tickets(exit_price, reason)
            else:
                # Futures/spot mode: use broker to close at the exact price
                self.broker.reduce_position_at(
                    self.position.qty, exit_price, self.price
                )
                # Tag the resulting trade with session metadata
                from qengine.store import store
                if store.closed_trades.trades:
                    last_trade = store.closed_trades.trades[-1]
                    if not last_trade.meta:
                        last_trade.meta = {}
                    last_trade.meta.update({
                        'session': self.vars.get('session_number', 0),
                        'exit_reason': reason,
                        'level': 0,
                        'leg_index': 0,
                    })

        self._end_cycle(reason)

    def _end_cycle(self, reason):
        """Record session, update bust tracking, set cooldown, reset state.
        Called by _close_cycle (manual exit) and on_ticket_tp_hit/on_ticket_sl_hit (engine exit).
        """
        is_bust = reason in ('abort', 'terminate', 'max_level_sl', 'sl_hit')
        level = self.vars.get('level', 0)

        # Record session
        pnl = self.balance - self.vars.get('session_start_balance', self.balance)
        session_record = {
            'number': self.vars.get('session_number', 0),
            'direction': self.vars.get('session_dir'),
            'levels': level,
            'legs': len(self.vars.get('legs', [])),
            'pnl': round(pnl, 2),
            'reason': reason,
            'bars': self.index - self.vars.get('session_start_bar', 0),
        }
        self.vars['sessions'].append(session_record)

        # Update bust tracking
        if is_bust:
            self.vars['consecutive_busts'] = self.vars.get('consecutive_busts', 0) + 1
            self.vars['daily_busts'] = self.vars.get('daily_busts', 0) + 1
        else:
            self.vars['consecutive_busts'] = 0

        # Set cooldown
        mode = self.hp.get('cooldown_mode', 'none')
        if mode == 'bars':
            self.vars['cooldown_until'] = self.index + int(self.hp.get('cooldown_value', 10))
        elif mode == 'atr_expansion':
            atr = ta.atr(self.candles, period=14)
            avg_atr = ta.atr(self.candles, period=50)
            if atr > avg_atr * self.hp.get('cooldown_value', 2.0):
                self.vars['cooldown_until'] = self.index + 50
            else:
                self.vars['cooldown_until'] = self.index + 5

        # Reset cycle state
        self.vars['cycle_active'] = False
        self.vars['level'] = 0
        self.vars['legs'] = []
        self.vars['tp_price'] = None
        self.vars['hedge_trigger_price'] = None
        self.vars['trailing_tp'] = None
        self.vars['hedge_stop_order_id'] = None
        self.vars['pending_hedge_level'] = None
        self.vars['pending_hedge_dir'] = None

    # ╔═══════════════════════════════════════════════════════════════════════╗
    # ║                         UTILITIES                                   ║
    # ╚═══════════════════════════════════════════════════════════════════════╝

    def _session_pnl(self):
        """Net PnL of the current session including costs already paid.

        Uses balance delta (which captures spread, swap, fees) rather than
        just floating ticket PnL (which misses entry costs).
        """
        start_bal = self.vars.get('session_start_balance', self.balance)
        # Balance delta = realized costs. position.pnl = unrealized ticket PnL.
        # Total session PnL = (current_balance - start_balance) + floating_pnl
        floating = self.position.pnl if self.is_open else 0
        realized_delta = self.balance - start_bal
        return realized_delta + floating

    def _session_pnl_pct(self):
        """Session PnL as % of session start balance."""
        start_bal = self.vars.get('session_start_balance', self.balance)
        if start_bal <= 0:
            return 0
        return (self._session_pnl() / start_bal) * 100

    def _is_new_day(self):
        """Detect day boundary from candle timestamps."""
        if self.index < 1:
            return True
        try:
            prev_day = jh.timestamp_to_arrow(self.candles[-2][0]).day
            curr_day = jh.timestamp_to_arrow(self.candles[-1][0]).day
            return curr_day != prev_day
        except Exception:
            return False

    def _is_new_week(self):
        """Detect week boundary (Monday)."""
        if self.index < 1:
            return True
        try:
            prev = jh.timestamp_to_arrow(self.candles[-2][0])
            curr = jh.timestamp_to_arrow(self.candles[-1][0])
            return curr.isocalendar()[1] != prev.isocalendar()[1]
        except Exception:
            return False

    @staticmethod
    def _simple_ema(data, period):
        """Calculate EMA of a list of values (for equity curve filter)."""
        if len(data) < period:
            return data[-1]
        alpha = 2 / (period + 1)
        ema = data[0]
        for v in data[1:]:
            ema = alpha * v + (1 - alpha) * ema
        return ema
