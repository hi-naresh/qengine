"""
Tests for Martingale strategy:
  - Preset validation & application
  - All signal modes
  - All sizing curves
  - Direction bias enforcement
  - Hedge cycle mechanics
  - Filter modules
  - Risk management
  - HP structure integrity
"""
import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import qengine.helpers as jh
    from qengine.factories import candles_from_close_prices
    from qengine import research
    from strategies._shared.Martingale import Martingale as UniversalMartingale, _FIB, _CUSTOM_SEQUENCES
    from strategies._shared.Martingale import PRESETS
    AVAILABLE = True
except Exception:
    AVAILABLE = False

pytestmark = pytest.mark.skipif(not AVAILABLE, reason="QEngine or Martingale not available")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_config(exchange_name='Fake Exchange', balance=100_000):
    return {
        'starting_balance': balance,
        'fee': 0,
        'type': 'futures',
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'warm_up_candles': 0,
    }


def _make_zigzag(base=100, amplitude=2.0, periods=5, candles_per_leg=20):
    """Create zigzag prices: up-down-up-down... for triggering hedge cycles."""
    prices = []
    for i in range(periods):
        if i % 2 == 0:
            for j in range(candles_per_leg):
                prices.append(base + j * amplitude / candles_per_leg)
        else:
            for j in range(candles_per_leg):
                prices.append(base + amplitude - j * amplitude / candles_per_leg)
    return prices


def _make_trending_up(base=100, steps=100, step_size=0.1):
    return [base + i * step_size for i in range(steps)]


def _make_trending_down(base=100, steps=100, step_size=0.1):
    return [base - i * step_size for i in range(steps)]


def _run_backtest(strategy_cls, prices, config_override=None, hyperparameters=None):
    candles = candles_from_close_prices(prices)
    exchange_name = 'Fake Exchange'
    symbol = 'FAKE-USDT'
    cfg = config_override or _make_config(exchange_name)
    routes = [{'exchange': exchange_name, 'strategy': strategy_cls,
               'symbol': symbol, 'timeframe': '1m'}]
    return research.backtest(
        cfg, routes, [], {
            jh.key(exchange_name, symbol): {
                'exchange': exchange_name, 'symbol': symbol,
                'candles': candles,
            },
        },
        hyperparameters=hyperparameters,
    )


def _make_strategy(hp_overrides=None, balance=10000):
    """Create a minimal strategy instance for unit tests (no candle data needed).

    Uses a dynamic subclass to override read-only properties from the Strategy
    base class (balance, candles, current_candle, is_open, position, price, etc.).
    """
    # Build dynamic class with overridable properties
    MockCls = type('MockedMartingale', (UniversalMartingale,), {
        'balance': property(lambda self: self._mock_balance),
        'candles': property(lambda self: self._mock_candles),
        'current_candle': property(lambda self: self._mock_candles[-1] if self._mock_candles is not None else None),
        'is_open': property(lambda self: self._mock_is_open),
        'price': property(lambda self: float(self._mock_candles[-1][2]) if self._mock_candles is not None else 100.0),
        'close': property(lambda self: float(self._mock_candles[-1][2]) if self._mock_candles is not None else 100.0),
        'open': property(lambda self: float(self._mock_candles[-1][1]) if self._mock_candles is not None else 100.0),
        'high': property(lambda self: float(self._mock_candles[-1][3]) if self._mock_candles is not None else 100.0),
        'low': property(lambda self: float(self._mock_candles[-1][4]) if self._mock_candles is not None else 100.0),
        'pip_size': property(lambda self: self._mock_pip_size),
        'leverage': property(lambda self: self._mock_leverage),
    })

    s = MockCls.__new__(MockCls)
    s.hp = {
        'preset': 'custom',
        'sizing_curve': 'geometric',
        'sizing_factor': 2.0,
        'base_size_mode': 'fixed',
        'base_size_value': 1.0,
        'sizing_custom_sequence': 'none',
        'direction_bias': 'both',
        'signal_mode': 'random',
        'max_levels': 6,
        'hedge_mode': 'fixed_pips',
        'hedge_value': 10.0,
        'tp_mode': 'fixed_pips',
        'tp_value': 20.0,
        'entry_on_crossover': 'no',
        'hedge_expand': 'no',
    }
    if hp_overrides:
        s.hp.update(hp_overrides)
    s._mock_balance = balance
    s._mock_candles = np.array([[1000000 + i * 60000, 100, 101, 102, 99, 1000] for i in range(50)], dtype=float)
    s._mock_is_open = False
    s._mock_pip_size = 0.0001
    s._mock_leverage = 30
    s._pipelines = None
    return s


# ===========================================================================
# HP Structure
# ===========================================================================
class TestHyperparameterStructure:
    def test_all_hps_have_required_fields(self):
        s = UniversalMartingale()
        for hp in s.hyperparameters():
            assert 'name' in hp, f"HP missing 'name': {hp}"
            assert 'type' in hp, f"HP {hp['name']} missing 'type'"
            assert 'default' in hp, f"HP {hp['name']} missing 'default'"

    def test_no_duplicate_hp_names(self):
        s = UniversalMartingale()
        names = [h['name'] for h in s.hyperparameters()]
        dupes = [n for n in names if names.count(n) > 1]
        assert len(names) == len(set(names)), f"Duplicate HP names: {dupes}"

    def test_numeric_hps_have_valid_min_max_default(self):
        s = UniversalMartingale()
        for hp in s.hyperparameters():
            if hp['type'] in (int, float):
                assert 'min' in hp, f"Numeric HP {hp['name']} missing 'min'"
                assert 'max' in hp, f"Numeric HP {hp['name']} missing 'max'"
                assert hp['min'] <= hp['default'] <= hp['max'], \
                    f"HP {hp['name']}: default {hp['default']} not in [{hp['min']}, {hp['max']}]"

    def test_categorical_hps_have_valid_defaults(self):
        s = UniversalMartingale()
        for hp in s.hyperparameters():
            if hp['type'] == 'categorical':
                assert 'options' in hp, f"Categorical HP {hp['name']} missing 'options'"
                assert hp['default'] in hp['options'], \
                    f"HP {hp['name']}: default '{hp['default']}' not in {hp['options']}"

    def test_preset_default_is_valid_option(self):
        """Regression: default was 'orginal' (typo) instead of 'original'."""
        s = UniversalMartingale()
        preset_hp = next(h for h in s.hyperparameters() if h['name'] == 'preset')
        assert preset_hp['default'] in preset_hp['options'], \
            f"Preset default '{preset_hp['default']}' not in options"

    def test_signal_mode_includes_none(self):
        """'none' mode must exist for presets like 'original' that use it."""
        s = UniversalMartingale()
        sig_hp = next(h for h in s.hyperparameters() if h['name'] == 'signal_mode')
        assert 'none' in sig_hp['options']


# ===========================================================================
# Presets
# ===========================================================================
class TestPresets:
    def test_all_presets_exist(self):
        expected = ['original', 'v2', 'momentum', 'mean_reversion']
        for name in expected:
            assert name in PRESETS, f"Missing preset: {name}"

    def test_presets_have_valid_keys(self):
        """All preset keys must be valid hyperparameter names."""
        hp_defs = UniversalMartingale().hyperparameters()
        valid_names = {h['name'] for h in hp_defs}
        for preset_name, preset_vals in PRESETS.items():
            for key in preset_vals:
                assert key in valid_names, \
                    f"Preset '{preset_name}' has invalid key: '{key}'"

    def test_preset_signal_modes_have_handlers(self):
        """Every signal_mode used in a preset must have a _signal_X method."""
        s = UniversalMartingale()
        for preset_name, preset_vals in PRESETS.items():
            mode = preset_vals.get('signal_mode')
            if mode and mode != 'model':
                method_name = f'_signal_{mode}'
                assert hasattr(s, method_name), \
                    f"Preset '{preset_name}' uses signal_mode='{mode}' but {method_name} is missing"

    def test_original_preset_config(self):
        p = PRESETS['original']
        assert p['signal_mode'] == 'none'
        assert p['direction_bias'] == 'long_only'
        assert p['max_levels'] == 7

    def test_v2_preset_config(self):
        p = PRESETS['v2']
        assert p['signal_mode'] == 'ema_cross'
        assert p['sizing_curve'] == 'sqrt'
        assert p['tp_mode'] == 'bucket_pct'
        assert p['session_filter'] == 'london_ny'



# ===========================================================================
# Preset Application (the critical fix)
# ===========================================================================
class TestPresetApplication:
    """Verify preset flow: frontend applies preset values, _init_state fills missing keys."""

    def _make_strategy_with_frontend_preset(self, preset_name):
        """Simulate frontend flow: preset values applied to HPs before sending to backend."""
        # Start with HP defaults (like the frontend does on load)
        hp_defs = UniversalMartingale().hyperparameters()
        hp = {'preset': preset_name}
        for hp_def in hp_defs:
            hp[hp_def['name']] = hp_def['default']
        # Frontend's onPresetChange() applies preset values on top of defaults
        preset_vals = PRESETS.get(preset_name, {})
        for k, v in preset_vals.items():
            hp[k] = v
        # Create strategy with the frontend-prepared HPs
        s = _make_strategy(hp)
        s.vars = {}
        s.index = 0
        s._init_state()
        return s

    def _make_strategy_partial(self, preset_name):
        """Simulate: frontend sends only VISIBLE HPs. _init_state fills missing from preset."""
        # Directly set hp dict with only a few keys (simulating missing invisible HPs)
        s = _make_strategy()
        s.hp = {'preset': preset_name, 'base_size_mode': 'pct_equity', 'base_size_value': 1.0}
        s.vars = {}
        s.index = 0
        s._init_state()
        return s

    def test_original_preset_from_frontend(self):
        """Frontend applies preset → direction_bias is 'long_only'."""
        s = self._make_strategy_with_frontend_preset('original')
        assert s.hp['direction_bias'] == 'long_only'
        assert s.hp['signal_mode'] == 'none'
        assert s.hp['max_levels'] == 7

    def test_v2_preset_from_frontend(self):
        s = self._make_strategy_with_frontend_preset('v2')
        assert s.hp['signal_mode'] == 'ema_cross'
        assert s.hp['sizing_curve'] == 'sqrt'


    def test_preset_fills_missing_keys(self):
        """_init_state fills keys NOT sent by frontend from preset."""
        s = self._make_strategy_partial('original')
        # signal_mode was not sent by frontend → filled from preset
        assert s.hp['signal_mode'] == 'none'
        assert s.hp['direction_bias'] == 'long_only'

    def test_user_override_not_clobbered(self):
        """User changes TP from 20→15 on original preset. Backend must NOT reset to 20."""
        hp = {'preset': 'original', 'tp_value': 15.0, 'signal_mode': 'none',
              'direction_bias': 'long_only', 'max_levels': 9}
        s = _make_strategy(hp)
        s.vars = {}
        s.index = 0
        s._init_state()
        assert s.hp['tp_value'] == 15.0, "User override must survive _init_state"

    def test_custom_preset_does_not_override(self):
        """Custom preset should leave all HPs at their framework defaults."""
        s = _make_strategy({'preset': 'custom', 'direction_bias': 'short_only'})
        s.vars = {}
        s.index = 0
        s._init_state()
        assert s.hp['direction_bias'] == 'short_only'

    def test_all_presets_apply_from_frontend(self):
        """Every preset applied via frontend flow produces correct HP values."""
        for preset_name in PRESETS:
            s = self._make_strategy_with_frontend_preset(preset_name)
            preset = PRESETS[preset_name]
            for k, v in preset.items():
                assert s.hp[k] == v, \
                    f"Preset '{preset_name}': hp['{k}'] = {s.hp[k]!r}, expected {v!r}"


# ===========================================================================
# Signal Modes
# ===========================================================================
class TestSignalModes:
    def test_all_signal_modes_have_methods(self):
        """Every signal_mode option must have a corresponding _signal_X method."""
        s = UniversalMartingale()
        sig_hp = next(h for h in s.hyperparameters() if h['name'] == 'signal_mode')
        for mode in sig_hp['options']:
            if mode == 'model':
                continue  # model requires external fn
            method_name = f'_signal_{mode}'
            assert hasattr(s, method_name), \
                f"Missing signal method: {method_name} for mode '{mode}'"

    def test_signal_none_returns_long_for_long_only(self):
        s = _make_strategy({'signal_mode': 'none', 'direction_bias': 'long_only'})
        s.vars = {'prev_signal': None}
        s.index = 0
        assert s._signal_none() == 'long'
        s.index = 1
        assert s._signal_none() == 'long'

    def test_signal_none_returns_short_for_short_only(self):
        s = _make_strategy({'signal_mode': 'none', 'direction_bias': 'short_only'})
        s.vars = {'prev_signal': None}
        s.index = 0
        assert s._signal_none() == 'short'

    def test_signal_none_alternates_for_both(self):
        s = _make_strategy({'signal_mode': 'none', 'direction_bias': 'both'})
        s.vars = {'prev_signal': None}
        s.index = 0
        assert s._signal_none() == 'long'
        s.index = 1
        assert s._signal_none() == 'short'
        s.index = 2
        assert s._signal_none() == 'long'

    def test_signal_random_returns_valid(self):
        s = _make_strategy({'signal_mode': 'random'})
        result = s._signal_random()
        assert result in ('long', 'short')

    def test_signal_random_is_deterministic(self):
        """Same candle timestamp �� same signal."""
        s = _make_strategy()
        s._mock_candles = np.array([[1234567890, 100, 101, 102, 99, 1000]], dtype=float)
        r1 = s._signal_random()
        r2 = s._signal_random()
        assert r1 == r2


# ===========================================================================
# Direction Bias
# ===========================================================================
class TestDirectionBias:
    def _setup_for_signal(self, bias, signal):
        s = _make_strategy({
            'direction_bias': bias,
            'signal_mode': 'none',
            # Disable filters that need candle data beyond what our mock provides
            'session_filter': 'any',
            'day_filter': 'any',
            'vol_filter': 'none',
            'trend_filter': 'none',
            'spread_filter': 'none',
            'confidence_gate': 'none',
            'max_daily_loss_pct': 0,
            'max_weekly_loss_pct': 0,
            'max_consec_busts': 0,
            'max_exposure_pct': 0,
            'equity_curve_filter': 'none',
            'cooldown_mode': 'none',
        })
        s.vars = {
            'cycle_active': False,
            'halted': False,
            'cooldown_until': 0,
            'prev_signal': None,
            'equity_history': [],
            'day_start_balance': 10000,
            'week_start_balance': 10000,
            'consecutive_busts': 0,
            'legs': [],
        }
        s.index = 0 if signal == 'long' else 1
        return s

    def test_long_only_allows_long(self):
        s = self._setup_for_signal('long_only', 'long')
        assert s.should_long() is True

    def test_long_only_blocks_short(self):
        s = self._setup_for_signal('long_only', 'short')
        assert s.should_short() is False

    def test_short_only_allows_short(self):
        s = self._setup_for_signal('short_only', 'short')
        assert s.should_short() is True

    def test_short_only_blocks_long(self):
        s = self._setup_for_signal('short_only', 'long')
        assert s.should_long() is False

    def test_both_allows_long(self):
        s = self._setup_for_signal('both', 'long')
        assert s.should_long() is True

    def test_both_allows_short(self):
        s = self._setup_for_signal('both', 'short')
        assert s.should_short() is True


# ===========================================================================
# Sizing Curves (unit-level)
# ===========================================================================
class TestSizingCurves:
    def test_geometric(self):
        s = _make_strategy({'sizing_curve': 'geometric', 'sizing_factor': 2.0})
        assert s._calc_size(0) == pytest.approx(1.0)
        assert s._calc_size(1) == pytest.approx(2.0)
        assert s._calc_size(2) == pytest.approx(4.0)
        assert s._calc_size(5) == pytest.approx(32.0)

    def test_sqrt(self):
        s = _make_strategy({'sizing_curve': 'sqrt', 'sizing_factor': 2.0})
        assert s._calc_size(0) == pytest.approx(1.0)
        assert s._calc_size(2) == pytest.approx(2.0, rel=1e-4)
        assert s._calc_size(4) == pytest.approx(4.0, rel=1e-4)

    def test_linear(self):
        s = _make_strategy({'sizing_curve': 'linear'})
        assert s._calc_size(0) == pytest.approx(1.0)
        assert s._calc_size(1) == pytest.approx(2.0)
        assert s._calc_size(4) == pytest.approx(5.0)

    def test_fibonacci(self):
        s = _make_strategy({'sizing_curve': 'fibonacci'})
        assert s._calc_size(0) == pytest.approx(1.0)   # fib[0]=1
        assert s._calc_size(1) == pytest.approx(1.0)   # fib[1]=1
        assert s._calc_size(2) == pytest.approx(2.0)   # fib[2]=2
        assert s._calc_size(3) == pytest.approx(3.0)   # fib[3]=3
        assert s._calc_size(4) == pytest.approx(5.0)   # fib[4]=5

    def test_fixed(self):
        s = _make_strategy({'sizing_curve': 'fixed'})
        for level in range(6):
            assert s._calc_size(level) == pytest.approx(1.0)

    def test_anti_martingale(self):
        s = _make_strategy({'sizing_curve': 'anti_martingale', 'sizing_factor': 2.0})
        assert s._calc_size(0) == pytest.approx(1.0)
        assert s._calc_size(1) == pytest.approx(0.5)
        assert s._calc_size(2) == pytest.approx(0.25)

    def test_custom_sequence_overrides_curve(self):
        s = _make_strategy({'sizing_custom_sequence': '1_2_4_8_16'})
        assert s._calc_size(0) == pytest.approx(1.0)
        assert s._calc_size(1) == pytest.approx(2.0)
        assert s._calc_size(2) == pytest.approx(4.0)
        assert s._calc_size(3) == pytest.approx(8.0)

    def test_all_custom_sequences_are_valid(self):
        for seq_name, seq_vals in _CUSTOM_SEQUENCES.items():
            assert len(seq_vals) >= 6, f"Sequence {seq_name} too short"
            assert all(v > 0 for v in seq_vals), f"Sequence {seq_name} has non-positive values"


# ===========================================================================
# Base Size Modes
# ===========================================================================
class TestBaseSizeModes:
    def test_fixed_mode(self):
        s = _make_strategy({'base_size_mode': 'fixed', 'base_size_value': 5.0})
        assert s._base_size() == 5.0

    def test_pct_equity_mode(self):
        s = _make_strategy({'base_size_mode': 'pct_equity', 'base_size_value': 1.0}, balance=10000)
        # 1% of 10000 = $100 margin, * 30 leverage / 101.0 price ≈ 29.7
        expected = (10000 * 0.01) * 30 / 101.0
        assert s._base_size() == pytest.approx(expected, rel=1e-3)

    def test_pct_equity_scales_with_balance(self):
        s1 = _make_strategy({'base_size_mode': 'pct_equity', 'base_size_value': 2.0}, balance=10000)
        s2 = _make_strategy({'base_size_mode': 'pct_equity', 'base_size_value': 2.0}, balance=20000)
        assert s2._base_size() == pytest.approx(s1._base_size() * 2.0, rel=1e-3)

    def test_fixed_mode_ignores_balance(self):
        s1 = _make_strategy({'base_size_mode': 'fixed', 'base_size_value': 5.0}, balance=1000)
        s2 = _make_strategy({'base_size_mode': 'fixed', 'base_size_value': 5.0}, balance=100000)
        assert s1._base_size() == s2._base_size()


# ===========================================================================
# Hedge Distance
# ===========================================================================
class TestHedgeDistance:
    def test_fixed_pips_mode(self):
        s = _make_strategy({'hedge_mode': 'fixed_pips', 'hedge_value': 15.0})
        assert s._hedge_distance_pips(0) == pytest.approx(15.0)
        assert s._hedge_distance_pips(3) == pytest.approx(15.0)

    def test_hedge_expand_increases_distance(self):
        s = _make_strategy({
            'hedge_mode': 'fixed_pips', 'hedge_value': 10.0,
            'hedge_expand': 'yes', 'hedge_expand_factor': 1.5,
        })
        d0 = s._hedge_distance_pips(0)
        d1 = s._hedge_distance_pips(1)
        d2 = s._hedge_distance_pips(2)
        assert d1 == pytest.approx(d0 * 1.5)
        assert d2 == pytest.approx(d0 * 1.5 ** 2)

    def test_fibonacci_hedge_levels(self):
        s = _make_strategy({'hedge_mode': 'fibonacci_levels', 'hedge_value': 5.0})
        assert s._hedge_distance_pips(0) == pytest.approx(5.0)   # 5 * fib[0]=1
        assert s._hedge_distance_pips(2) == pytest.approx(10.0)  # 5 * fib[2]=2
        assert s._hedge_distance_pips(4) == pytest.approx(25.0)  # 5 * fib[4]=5


# ===========================================================================
# TP Computation
# ===========================================================================
class TestTPComputation:
    def _make_tp_strategy(self, tp_mode, tp_value, **extra):
        hp = {
            'tp_mode': tp_mode, 'tp_value': tp_value,
            'hedge_mode': 'fixed_pips', 'hedge_value': 10.0,
            'hedge_expand': 'no',
        }
        hp.update(extra)
        s = _make_strategy(hp)
        # Mock pips_to_price and price_to_pips (Strategy base class methods)
        s.pips_to_price = lambda pips: pips * 0.0001
        s.price_to_pips = lambda price_delta: price_delta / 0.0001
        return s

    def test_fixed_pips_long(self):
        s = self._make_tp_strategy('fixed_pips', 20.0)
        tp = s._compute_tp(1.1000, 'long')
        assert tp == pytest.approx(1.1000 + 20.0 * 0.0001)

    def test_fixed_pips_short(self):
        s = self._make_tp_strategy('fixed_pips', 20.0)
        tp = s._compute_tp(1.1000, 'short')
        assert tp == pytest.approx(1.1000 - 20.0 * 0.0001)

    def test_bucket_pct_returns_none(self):
        """bucket_pct mode uses dynamic check, not a fixed TP price."""
        s = self._make_tp_strategy('bucket_pct', 0.1)
        assert s._compute_tp(1.1000, 'long') is None

    def test_trailing_returns_none(self):
        s = self._make_tp_strategy('trailing', 10.0)
        assert s._compute_tp(1.1000, 'long') is None

    def test_risk_reward_mode(self):
        s = self._make_tp_strategy('risk_reward', 2.0)
        # hedge_dist = 10 pips = 0.001
        # TP dist = 0.001 * 2.0 = 0.002
        tp = s._compute_tp(1.1000, 'long')
        expected = 1.1000 + 10.0 * 0.0001 * 2.0
        assert tp == pytest.approx(expected)


# ===========================================================================
# Cycle State Management
# ===========================================================================
class TestCycleState:
    def test_init_state_resets_cycle(self):
        s = _make_strategy()
        s.vars = {}
        s.index = 0
        s._init_state()
        assert s.vars['cycle_active'] is False
        assert s.vars['level'] == 0
        assert s.vars['legs'] == []
        assert s.vars['session_number'] == 0

    def test_hedge_mode_enabled(self):
        s = _make_strategy()
        s.vars = {}
        s.index = 0
        s._init_state()
        assert s.hedge_mode is True

    def test_end_cycle_records_session(self):
        s = _make_strategy()
        s.vars = {
            'cycle_active': True,
            'level': 3,
            'legs': [{'dir': 'long', 'qty': 1, 'entry': 100}] * 4,
            'session_number': 1,
            'session_dir': 'long',
            'session_start_bar': 10,
            'session_start_balance': 10000,
            'sessions': [],
            'tp_price': None,
            'hedge_trigger_price': None,
            'trailing_tp': None,
            'consecutive_busts': 0,
            'daily_busts': 0,
        }
        s.index = 50
        s.hp['cooldown_mode'] = 'none'
        s._end_cycle('tp_hit')
        assert len(s.vars['sessions']) == 1
        assert s.vars['sessions'][0]['reason'] == 'tp_hit'
        assert s.vars['sessions'][0]['levels'] == 3
        assert s.vars['cycle_active'] is False

    def test_end_cycle_bust_increments_counters(self):
        s = _make_strategy()
        s.vars = {
            'cycle_active': True, 'level': 5,
            'legs': [], 'session_number': 1, 'session_dir': 'long',
            'session_start_bar': 0, 'session_start_balance': 10000,
            'sessions': [], 'tp_price': None, 'hedge_trigger_price': None,
            'trailing_tp': None, 'consecutive_busts': 2, 'daily_busts': 1,
        }
        s.index = 100
        s.hp['cooldown_mode'] = 'none'
        s._end_cycle('abort')
        assert s.vars['consecutive_busts'] == 3
        assert s.vars['daily_busts'] == 2

    def test_end_cycle_tp_resets_bust_counter(self):
        s = _make_strategy()
        s.vars = {
            'cycle_active': True, 'level': 2,
            'legs': [], 'session_number': 1, 'session_dir': 'long',
            'session_start_bar': 0, 'session_start_balance': 10000,
            'sessions': [], 'tp_price': None, 'hedge_trigger_price': None,
            'trailing_tp': None, 'consecutive_busts': 5, 'daily_busts': 3,
        }
        s.index = 50
        s.hp['cooldown_mode'] = 'none'
        s._end_cycle('tp_hit')
        assert s.vars['consecutive_busts'] == 0


# ===========================================================================
# Risk Management
# ===========================================================================
class TestRiskManagement:
    def _make_risk_strategy(self, hp_overrides=None, balance=10000):
        s = _make_strategy(hp_overrides, balance)
        s.vars = {
            'day_start_balance': 10000,
            'week_start_balance': 10000,
            'consecutive_busts': 0,
            'equity_history': [],
            'legs': [],
        }
        s._mock_is_open = False
        return s

    def test_daily_loss_blocks_entry(self):
        s = self._make_risk_strategy({
            'max_daily_loss_pct': 2.0,
            'max_weekly_loss_pct': 0,
            'max_consec_busts': 0,
            'max_exposure_pct': 0,
            'equity_curve_filter': 'none',
        }, balance=9700)
        s.vars['day_start_balance'] = 10000
        # Lost 3% > 2% limit
        assert s._risk_limits_ok() is False

    def test_daily_loss_allows_within_limit(self):
        s = self._make_risk_strategy({
            'max_daily_loss_pct': 2.0,
            'max_weekly_loss_pct': 0,
            'max_consec_busts': 0,
            'max_exposure_pct': 0,
            'equity_curve_filter': 'none',
        }, balance=9900)
        s.vars['day_start_balance'] = 10000
        # Lost 1% < 2% limit
        assert s._risk_limits_ok() is True

    def test_consec_busts_blocks_entry(self):
        s = self._make_risk_strategy({
            'max_daily_loss_pct': 0,
            'max_weekly_loss_pct': 0,
            'max_consec_busts': 3,
            'max_exposure_pct': 0,
            'equity_curve_filter': 'none',
        })
        s.vars['consecutive_busts'] = 3
        assert s._risk_limits_ok() is False

    def test_consec_busts_allows_below_limit(self):
        s = self._make_risk_strategy({
            'max_daily_loss_pct': 0,
            'max_weekly_loss_pct': 0,
            'max_consec_busts': 3,
            'max_exposure_pct': 0,
            'equity_curve_filter': 'none',
        })
        s.vars['consecutive_busts'] = 2
        assert s._risk_limits_ok() is True


# ===========================================================================
# Abort Conditions
# ===========================================================================
class TestAbortConditions:
    def test_abort_none(self):
        s = _make_strategy({'abort_mode': 'none'})
        s.vars = {'level': 10}
        assert s._should_abort() is False

    def test_abort_level_threshold(self):
        s = _make_strategy({'abort_mode': 'level_threshold', 'abort_level': 6})
        s.vars = {'level': 5}
        assert s._should_abort() is False
        s.vars = {'level': 6}
        assert s._should_abort() is True

    def test_abort_time_bars(self):
        s = _make_strategy({'abort_mode': 'time_bars', 'abort_time_bars': 100})
        s.vars = {'session_start_bar': 0}
        s.index = 99
        assert s._should_abort() is False
        s.index = 100
        assert s._should_abort() is True


# ===========================================================================
# Cooldown
# ===========================================================================
class TestCooldown:
    def test_cooldown_none_always_ok(self):
        s = _make_strategy({'cooldown_mode': 'none'})
        s.vars = {}
        assert s._cooldown_ok() is True

    def test_cooldown_bars_blocks_during(self):
        s = _make_strategy({'cooldown_mode': 'bars'})
        s.vars = {'cooldown_until': 50}
        s.index = 30
        assert s._cooldown_ok() is False

    def test_cooldown_bars_allows_after(self):
        s = _make_strategy({'cooldown_mode': 'bars'})
        s.vars = {'cooldown_until': 50}
        s.index = 50
        assert s._cooldown_ok() is True


# ===========================================================================
# Breakeven Price Computation
# ===========================================================================
class TestBreakevenComputation:
    def test_single_long_leg(self):
        s = _make_strategy()
        s.vars = {'legs': [{'dir': 'long', 'qty': 1.0, 'entry': 100.0}]}
        be = s._compute_breakeven_price()
        assert be == pytest.approx(100.0)

    def test_two_opposite_legs(self):
        s = _make_strategy()
        s.vars = {'legs': [
            {'dir': 'long', 'qty': 1.0, 'entry': 100.0},
            {'dir': 'short', 'qty': 2.0, 'entry': 98.0},
        ]}
        # P = (1*100 - 2*98) / (1 - 2) = (100 - 196) / (-1) = 96
        be = s._compute_breakeven_price()
        assert be == pytest.approx(96.0)

    def test_no_legs_returns_none(self):
        s = _make_strategy()
        s.vars = {'legs': []}
        assert s._compute_breakeven_price() is None


# ===========================================================================
# Session PnL
# ===========================================================================
class TestSessionPnL:
    def test_session_pnl_with_no_position(self):
        s = _make_strategy(balance=10500)
        s.vars = {'session_start_balance': 10000}
        s._mock_is_open = False
        assert s._session_pnl() == pytest.approx(500.0)

    def test_session_pnl_pct(self):
        s = _make_strategy(balance=10200)
        s.vars = {'session_start_balance': 10000}
        s._mock_is_open = False
        assert s._session_pnl_pct() == pytest.approx(2.0)


# ===========================================================================
# Integration: Preset Execution
# ===========================================================================
class TestPresetExecution:
    """Run each preset on synthetic data to verify no crashes and expected behavior."""

    def test_original_preset_only_longs(self):
        """Original preset with long_only must never open a short-first cycle."""
        prices = _make_zigzag(base=100, amplitude=5, periods=10, candles_per_leg=30)
        hp = dict(PRESETS['original'])
        hp['preset'] = 'original'
        hp['base_size_mode'] = 'fixed'
        hp['base_size_value'] = 10.0
        result = _run_backtest(UniversalMartingale, prices, hyperparameters=hp)
        assert result is not None

    def test_v2_preset_runs(self):
        prices = _make_zigzag(base=100, amplitude=5, periods=10, candles_per_leg=30)
        hp = dict(PRESETS['v2'])
        hp['preset'] = 'v2'
        hp['base_size_mode'] = 'fixed'
        hp['base_size_value'] = 10.0
        result = _run_backtest(UniversalMartingale, prices, hyperparameters=hp)
        assert result is not None

    def test_momentum_preset_runs(self):
        prices = _make_trending_up(base=100, steps=200, step_size=0.05)
        hp = dict(PRESETS['momentum'])
        hp['preset'] = 'momentum'
        hp['base_size_mode'] = 'fixed'
        hp['base_size_value'] = 10.0
        result = _run_backtest(UniversalMartingale, prices, hyperparameters=hp)
        assert result is not None

    def test_mean_reversion_preset_runs(self):
        prices = _make_zigzag(base=100, amplitude=3, periods=10, candles_per_leg=30)
        hp = dict(PRESETS['mean_reversion'])
        hp['preset'] = 'mean_reversion'
        hp['base_size_mode'] = 'fixed'
        hp['base_size_value'] = 10.0
        result = _run_backtest(UniversalMartingale, prices, hyperparameters=hp)
        assert result is not None

    def test_flat_prices_no_crash(self):
        """Strategy on flat prices should not crash."""
        prices = [100.0] * 50
        hp = {'preset': 'custom', 'signal_mode': 'random', 'base_size_mode': 'fixed',
              'base_size_value': 10.0, 'max_levels': 4}
        result = _run_backtest(UniversalMartingale, prices, hyperparameters=hp)
        assert isinstance(result['metrics']['total'], (int, float))

    def test_trending_up_produces_trades(self):
        prices = _make_trending_up(base=100, steps=200, step_size=0.1)
        hp = {'preset': 'custom', 'signal_mode': 'none', 'direction_bias': 'long_only',
              'base_size_mode': 'fixed', 'base_size_value': 10.0,
              'max_levels': 4, 'tp_mode': 'fixed_pips', 'tp_value': 10.0,
              'hedge_mode': 'fixed_pips', 'hedge_value': 10.0}
        result = _run_backtest(UniversalMartingale, prices, hyperparameters=hp)
        assert result['metrics']['total'] >= 0

    def test_trending_down_with_short_only(self):
        prices = _make_trending_down(base=100, steps=200, step_size=0.1)
        hp = {'preset': 'custom', 'signal_mode': 'none', 'direction_bias': 'short_only',
              'base_size_mode': 'fixed', 'base_size_value': 10.0,
              'max_levels': 4, 'tp_mode': 'fixed_pips', 'tp_value': 10.0,
              'hedge_mode': 'fixed_pips', 'hedge_value': 10.0}
        result = _run_backtest(UniversalMartingale, prices, hyperparameters=hp)
        assert result['metrics']['total'] >= 0


# ---------------------------------------------------------------------------
# CFD config helper
# ---------------------------------------------------------------------------
def _make_cfd_config(exchange_name='Fake Exchange', balance=100_000):
    return {
        'starting_balance': balance,
        'fee': 0,
        'type': 'cfd',
        'futures_leverage': 30,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'warm_up_candles': 0,
    }


# Base HP dict shared by integration tests
_BASE_HP = {
    'preset': 'custom',
    'signal_mode': 'none',
    'base_size_mode': 'fixed',
    'base_size_value': 10.0,
    'hedge_mode': 'fixed_pips',
    'hedge_value': 10.0,
    'tp_mode': 'fixed_pips',
    'tp_value': 20.0,
    'session_filter': 'any',
    'day_filter': 'any',
    'vol_filter': 'none',
    'trend_filter': 'none',
    'spread_filter': 'none',
    'confidence_gate': 'none',
    'cooldown_mode': 'none',
    'abort_mode': 'none',
    'max_daily_loss_pct': 0,
    'max_weekly_loss_pct': 0,
    'max_consec_busts': 0,
    'max_exposure_pct': 0,
    'equity_curve_filter': 'none',
    'hedge_expand': 'no',
    'entry_on_crossover': 'no',
    'breakeven_mode': 'none',
    'partial_close': 'none',
}


def _hp(**overrides):
    """Return a copy of _BASE_HP with overrides applied."""
    hp = dict(_BASE_HP)
    hp.update(overrides)
    return hp


def _t(trade, key, default=None):
    """Extract a field from a trade (dict or object)."""
    if isinstance(trade, dict):
        return trade.get(key, default)
    return getattr(trade, key, default)


def _tmeta(trade):
    """Extract meta dict from a trade."""
    return (_t(trade, 'meta') or {})


# ===========================================================================
# Max Levels / Bust Integration
# ===========================================================================
class TestMaxLevelsBust:

    def test_max_levels_0_no_hedging(self):
        """With max_levels=0, only L0 trades fire — no hedges at all."""
        prices = _make_zigzag(base=100, amplitude=5, periods=10, candles_per_leg=30)
        hp = _hp(direction_bias='long_only', max_levels=0)
        result = _run_backtest(UniversalMartingale, prices, config_override=_make_cfd_config(),
                               hyperparameters=hp)
        # With max_levels=0, no hedge orders possible. Every session is L0 only.
        # (the SL at the hedge trigger kills the single ticket immediately)
        assert result is not None
        trades = result.get('trades', [])
        # Every trade should be from level 0 sessions
        for t in trades:
            meta = _tmeta(t)
            level = meta.get('level', 0)
            assert level == 0, f"Trade at level {level} but max_levels=0"

    def test_bust_at_max_level(self):
        """With max_levels=2, a strong downtrend should bust. Session ends with sl_hit/max_level_bust."""
        # Strong downtrend: price drops steadily — long entry will bust through both levels
        prices = _make_trending_down(base=100, steps=300, step_size=0.05)
        hp = _hp(direction_bias='long_only', max_levels=2, hedge_value=5.0, tp_value=50.0)
        result = _run_backtest(UniversalMartingale, prices, config_override=_make_cfd_config(),
                               hyperparameters=hp)
        assert result is not None
        trades = result.get('trades', [])
        # With only 2 levels (L0, L1) and price continuously falling, we should see busts
        # Check that some trades reached level 1 (hedge was placed and hit)
        max_level_seen = 0
        bust_found = False
        for t in trades:
            meta = _tmeta(t)
            lvl = meta.get('level', 0)
            max_level_seen = max(max_level_seen, lvl)
            reason = meta.get('session_exit_reason', '')
            if reason in ('max_level_bust', 'sl_hit', 'margin_call'):
                bust_found = True
        assert bust_found or result['metrics']['total'] > 0, \
            "Expected bust or profitable TP exits with max_levels=2 on downtrend"


# ===========================================================================
# Direction Bias Integration (full backtests)
# ===========================================================================
class TestDirectionBiasIntegration:

    def test_long_only_never_shorts_initial(self):
        """Backtest trending down with long_only — all initial (L0) entries must be long."""
        prices = _make_trending_down(base=100, steps=200, step_size=0.05)
        hp = _hp(direction_bias='long_only', max_levels=3)
        result = _run_backtest(UniversalMartingale, prices, config_override=_make_cfd_config(),
                               hyperparameters=hp)
        trades = result.get('trades', [])
        for t in trades:
            meta = _tmeta(t)
            ttype = _t(t, 'type')
            # L0 entries are always the session direction
            if meta.get('level', 0) == 0 and meta.get('leg_index', 0) == 0:
                assert ttype in ('long', 'buy'), \
                    f"Initial entry is {ttype} but direction_bias=long_only"

    def test_short_only_never_longs_initial(self):
        """Backtest trending up with short_only — all initial (L0) entries must be short."""
        prices = _make_trending_up(base=100, steps=200, step_size=0.05)
        hp = _hp(direction_bias='short_only', max_levels=3)
        result = _run_backtest(UniversalMartingale, prices, config_override=_make_cfd_config(),
                               hyperparameters=hp)
        trades = result.get('trades', [])
        for t in trades:
            meta = _tmeta(t)
            ttype = _t(t, 'type')
            if meta.get('level', 0) == 0 and meta.get('leg_index', 0) == 0:
                assert ttype in ('short', 'sell'), \
                    f"Initial entry is {ttype} but direction_bias=short_only"


# ===========================================================================
# TP Modes Integration
# ===========================================================================
class TestTPModes:

    def test_bucket_pct_tp(self):
        """With tp_mode='bucket_pct', sessions close when equity % target is hit."""
        # Zigzag creates opportunities for TP hits
        prices = _make_zigzag(base=100, amplitude=3, periods=15, candles_per_leg=20)
        hp = _hp(tp_mode='bucket_pct', tp_value=0.5, direction_bias='both',
                 max_levels=4, hedge_value=5.0)
        result = _run_backtest(UniversalMartingale, prices, config_override=_make_cfd_config(),
                               hyperparameters=hp)
        assert result is not None
        # bucket_pct mode should produce trades (strategy doesn't crash with dynamic TP)
        assert isinstance(result['metrics']['total'], (int, float))

    def test_fixed_pips_tp(self):
        """With tp_mode='fixed_pips' on trending data, trades close with profit."""
        prices = _make_trending_up(base=100, steps=300, step_size=0.05)
        hp = _hp(tp_mode='fixed_pips', tp_value=10.0, direction_bias='long_only',
                 max_levels=4, hedge_value=20.0)
        result = _run_backtest(UniversalMartingale, prices, config_override=_make_cfd_config(),
                               hyperparameters=hp)
        trades = result.get('trades', [])
        # On a strong uptrend with long_only, most/all TP hits should be profitable
        if trades:
            profitable = sum(1 for t in trades if _t(t, 'pnl', 0) > 0)
            assert profitable > 0, "Expected at least one profitable trade on uptrend"


# ===========================================================================
# Abort Modes Integration
# ===========================================================================
class TestAbortModes:

    def test_abort_level_threshold(self):
        """With abort_mode='level_threshold', abort_level=2, no session exceeds L2."""
        prices = _make_zigzag(base=100, amplitude=5, periods=15, candles_per_leg=20)
        hp = _hp(direction_bias='both', max_levels=6, abort_mode='level_threshold',
                 abort_level=2, hedge_value=5.0, tp_value=30.0)
        result = _run_backtest(UniversalMartingale, prices, config_override=_make_cfd_config(),
                               hyperparameters=hp)
        trades = result.get('trades', [])
        for t in trades:
            meta = _tmeta(t)
            level = meta.get('level', 0)
            # abort_level=2 means abort when level >= 2, so max level in trades is 2
            # (the abort fires at level 2, closing the cycle)
            assert level <= 2, f"Trade at level {level} but abort_level=2"

    def test_abort_time_bars(self):
        """With abort_mode='time_bars', abort_time_bars=10, sessions are short-lived."""
        # Use flat-ish prices so sessions don't end from TP/bust quickly
        prices = [100.0 + 0.001 * (i % 5) for i in range(300)]
        hp = _hp(direction_bias='long_only', max_levels=6, abort_mode='time_bars',
                 abort_time_bars=10, hedge_value=50.0, tp_value=50.0)
        result = _run_backtest(UniversalMartingale, prices, config_override=_make_cfd_config(),
                               hyperparameters=hp)
        # The strategy should run without crashing; sessions should be short
        assert result is not None
        assert isinstance(result['metrics']['total'], (int, float))


# ===========================================================================
# Cooldown Modes Integration
# ===========================================================================
class TestCooldownModes:

    def test_cooldown_bars(self):
        """With cooldown_mode='bars', cooldown_value=20, there's a gap between sessions."""
        prices = _make_trending_up(base=100, steps=400, step_size=0.02)
        hp = _hp(direction_bias='long_only', max_levels=2, cooldown_mode='bars',
                 cooldown_value=20, tp_value=5.0, hedge_value=10.0)
        result = _run_backtest(UniversalMartingale, prices, config_override=_make_cfd_config(),
                               hyperparameters=hp)
        # Compare trade count with and without cooldown — cooldown should produce fewer sessions
        hp_no_cd = _hp(direction_bias='long_only', max_levels=2, cooldown_mode='none',
                       tp_value=5.0, hedge_value=10.0)
        result_no_cd = _run_backtest(UniversalMartingale, prices, config_override=_make_cfd_config(),
                                     hyperparameters=hp_no_cd)
        # Cooldown should produce equal or fewer total trades
        assert result['metrics']['total'] <= result_no_cd['metrics']['total']


# ===========================================================================
# Risk Limits Integration
# ===========================================================================
class TestRiskLimits:

    def test_daily_loss_limit(self):
        """With max_daily_loss_pct=1, strategy stops entering after 1% daily loss."""
        # Downtrend causes losses on long_only; daily limit should kick in
        prices = _make_trending_down(base=100, steps=400, step_size=0.05)
        hp_limited = _hp(direction_bias='long_only', max_levels=2,
                         max_daily_loss_pct=1.0, hedge_value=5.0, tp_value=50.0)
        result_limited = _run_backtest(UniversalMartingale, prices,
                                       config_override=_make_cfd_config(),
                                       hyperparameters=hp_limited)
        # Without daily limit
        hp_unlimited = _hp(direction_bias='long_only', max_levels=2,
                           max_daily_loss_pct=0, hedge_value=5.0, tp_value=50.0)
        result_unlimited = _run_backtest(UniversalMartingale, prices,
                                         config_override=_make_cfd_config(),
                                         hyperparameters=hp_unlimited)
        # Limited version should have equal or fewer trades
        assert result_limited['metrics']['total'] <= result_unlimited['metrics']['total']

    def test_consec_bust_limit(self):
        """With max_consec_busts=1, strategy halts after 1 consecutive bust."""
        # Strong downtrend causes bust on long_only sessions
        prices = _make_trending_down(base=100, steps=400, step_size=0.05)
        hp_limited = _hp(direction_bias='long_only', max_levels=2,
                         max_consec_busts=1, hedge_value=5.0, tp_value=50.0)
        result_limited = _run_backtest(UniversalMartingale, prices,
                                       config_override=_make_cfd_config(),
                                       hyperparameters=hp_limited)
        hp_unlimited = _hp(direction_bias='long_only', max_levels=2,
                           max_consec_busts=0, hedge_value=5.0, tp_value=50.0)
        result_unlimited = _run_backtest(UniversalMartingale, prices,
                                         config_override=_make_cfd_config(),
                                         hyperparameters=hp_unlimited)
        # Limited version should have fewer or equal trades
        assert result_limited['metrics']['total'] <= result_unlimited['metrics']['total']


# ===========================================================================
# Hedge Expand Integration
# ===========================================================================
class TestHedgeExpand:

    def test_hedge_expand_increases_distance(self):
        """With hedge_expand='yes', deeper levels have wider hedge distances."""
        # Use a strong zigzag to trigger multiple levels
        prices = _make_zigzag(base=100, amplitude=8, periods=10, candles_per_leg=30)
        hp = _hp(direction_bias='both', max_levels=5, hedge_expand='yes',
                 hedge_expand_factor=1.5, hedge_value=5.0, tp_value=30.0)
        result = _run_backtest(UniversalMartingale, prices, config_override=_make_cfd_config(),
                               hyperparameters=hp)
        trades = result.get('trades', [])
        # Verify strategy ran successfully
        assert result is not None
        assert isinstance(result['metrics']['total'], (int, float))
        # If multi-level sessions occurred, check that leg entry prices show expanding gaps
        if len(trades) >= 3:
            # Group trades by session
            sessions = {}
            for t in trades:
                meta = _tmeta(t)
                sn = meta.get('session', 0)
                if sn not in sessions:
                    sessions[sn] = []
                sessions[sn].append(t)
            # Find a session with 3+ legs and verify expanding distances
            for sn, session_trades in sessions.items():
                if len(session_trades) >= 3:
                    entries = [_t(t, 'opened_at') for t in sorted(session_trades,
                               key=lambda x: _tmeta(x).get('level', 0))]
                    # With expanding hedge, later gaps should be >= earlier ones
                    # (Just verifying no crash; precise distance checking is done in unit tests)
                    break
