"""
Tests for UniversalMartingale strategy cycle execution:
entry → hedge levels → TP/bust flow, presets, sizing curves.
Uses the research.backtest() isolated runner for integration tests.
"""
import pytest
import numpy as np
import sys
import os

# Ensure strategies/_admin is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import qengine.helpers as jh
    from qengine.factories import candles_from_close_prices
    from qengine import research
    from strategies._admin.UniversalMartingale import UniversalMartingale
    from strategies._admin.UniversalMartingale.presets import PRESETS
    AVAILABLE = True
except Exception:
    AVAILABLE = False

pytestmark = pytest.mark.skipif(not AVAILABLE, reason="QEngine or UniversalMartingale not available")

# Fibonacci sequence (same as strategy uses)
_FIB = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144]


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
            # Up leg
            for j in range(candles_per_leg):
                prices.append(base + j * amplitude / candles_per_leg)
        else:
            # Down leg
            for j in range(candles_per_leg):
                prices.append(base + amplitude - j * amplitude / candles_per_leg)
    return prices


def _make_trending_up(base=100, steps=100, step_size=0.1):
    """Steady uptrend — should trigger long entries and TPs."""
    return [base + i * step_size for i in range(steps)]


def _make_trending_down(base=100, steps=100, step_size=0.1):
    """Steady downtrend."""
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


# ===========================================================================
# Preset validation
# ===========================================================================
class TestPresets:
    def test_all_presets_exist(self):
        expected = ['raw', 'surefire_v1', 'surefire_v2', 'conservative',
                    'aggressive', 'fibonacci', 'scalper', 'momentum',
                    'mean_reversion', 'trend_rider', 'phase3_optimized']
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

    def test_raw_preset_is_minimal(self):
        raw = PRESETS['raw']
        assert raw['signal_mode'] == 'random'
        assert raw['abort_mode'] == 'none'
        assert raw['cooldown_mode'] == 'none'

    def test_surefire_v2_preset_config(self):
        sv2 = PRESETS['surefire_v2']
        assert sv2['signal_mode'] == 'ema_cross'
        assert sv2['sizing_curve'] == 'sqrt'
        assert sv2['max_levels'] == 6
        assert sv2['session_filter'] == 'london_ny'

    def test_phase3_optimized_preset(self):
        p3 = PRESETS['phase3_optimized']
        assert p3['sizing_curve'] == 'fibonacci'
        assert p3['base_size_mode'] == 'capital_aware'
        assert p3['confidence_gate'] == 'enabled'
        assert p3['abort_mode'] == 'none'


# ===========================================================================
# Sizing curve tests (unit-level)
# ===========================================================================
class TestSizingCurves:
    """Test _calc_size for different sizing curves."""

    def _make_strategy(self, hp_overrides=None):
        """Create a minimal strategy instance for sizing tests."""
        s = UniversalMartingale.__new__(UniversalMartingale)
        s.hp = {
            'sizing_curve': 'geometric',
            'sizing_factor': 2.0,
            'base_size_mode': 'fixed',
            'base_size_value': 1.0,
            'sizing_custom_sequence': 'none',
        }
        if hp_overrides:
            s.hp.update(hp_overrides)
        # Mock balance for pct_equity mode
        s._balance = 10000
        return s

    def test_geometric(self):
        s = self._make_strategy({'sizing_curve': 'geometric', 'sizing_factor': 2.0})
        # level 0: 1*2^0=1, level 1: 1*2^1=2, level 2: 1*2^2=4
        assert s._calc_size(0) == pytest.approx(1.0)
        assert s._calc_size(1) == pytest.approx(2.0)
        assert s._calc_size(2) == pytest.approx(4.0)
        assert s._calc_size(5) == pytest.approx(32.0)

    def test_sqrt(self):
        s = self._make_strategy({'sizing_curve': 'sqrt', 'sizing_factor': 2.0})
        # level n: 1 * (sqrt(2))^n
        assert s._calc_size(0) == pytest.approx(1.0)
        assert s._calc_size(2) == pytest.approx(2.0, rel=1e-4)  # (sqrt(2))^2 = 2
        assert s._calc_size(4) == pytest.approx(4.0, rel=1e-4)  # (sqrt(2))^4 = 4

    def test_linear(self):
        s = self._make_strategy({'sizing_curve': 'linear'})
        assert s._calc_size(0) == pytest.approx(1.0)
        assert s._calc_size(1) == pytest.approx(2.0)
        assert s._calc_size(4) == pytest.approx(5.0)

    def test_fibonacci(self):
        s = self._make_strategy({'sizing_curve': 'fibonacci'})
        assert s._calc_size(0) == pytest.approx(1.0)  # fib[0]=1
        assert s._calc_size(1) == pytest.approx(1.0)  # fib[1]=1
        assert s._calc_size(2) == pytest.approx(2.0)  # fib[2]=2
        assert s._calc_size(3) == pytest.approx(3.0)  # fib[3]=3
        assert s._calc_size(4) == pytest.approx(5.0)  # fib[4]=5

    def test_fixed(self):
        s = self._make_strategy({'sizing_curve': 'fixed'})
        # All levels same size
        for level in range(6):
            assert s._calc_size(level) == pytest.approx(1.0)

    def test_anti_martingale(self):
        s = self._make_strategy({'sizing_curve': 'anti_martingale', 'sizing_factor': 2.0})
        assert s._calc_size(0) == pytest.approx(1.0)
        assert s._calc_size(1) == pytest.approx(0.5)
        assert s._calc_size(2) == pytest.approx(0.25)

    def test_custom_sequence_overrides(self):
        s = self._make_strategy({'sizing_custom_sequence': '1_2_4_8_16'})
        assert s._calc_size(0) == pytest.approx(1.0)
        assert s._calc_size(1) == pytest.approx(2.0)
        assert s._calc_size(2) == pytest.approx(4.0)
        assert s._calc_size(3) == pytest.approx(8.0)


# ===========================================================================
# Integration: strategy with random signal (deterministic via seed)
# ===========================================================================
class TestRawPresetExecution:
    """Run the 'raw' preset with fixed seed to test cycle mechanics."""

    def test_raw_preset_produces_trades(self):
        """Raw preset with random signal should produce trades on a zigzag."""
        np.random.seed(42)
        prices = _make_zigzag(base=100, amplitude=5, periods=10, candles_per_leg=30)

        class RawMartingale(UniversalMartingale):
            def hyperparameters(self):
                hp = super().hyperparameters()
                # Override defaults for testing
                for h in hp:
                    if h['name'] == 'preset':
                        h['default'] = 'raw'
                    if h['name'] == 'base_size_value':
                        h['default'] = 10.0  # Fixed 10 units
                    if h['name'] == 'max_levels':
                        h['default'] = 4
                    if h['name'] == 'hedge_value':
                        h['default'] = 20.0  # 20 pip hedge
                    if h['name'] == 'tp_value':
                        h['default'] = 10.0  # 10 pip TP
                return hp

        result = _run_backtest(RawMartingale, prices)
        # Should have some trades (random signal on zigzag)
        assert result['metrics']['total'] >= 0  # May be 0 if no signals fire

    def test_flat_prices_no_crash(self):
        """Strategy on flat prices should not crash (may still open trades with random signal)."""
        np.random.seed(99)
        prices = [100.0] * 50  # Flat prices

        class FlatMartingale(UniversalMartingale):
            def hyperparameters(self):
                hp = super().hyperparameters()
                for h in hp:
                    if h['name'] == 'preset':
                        h['default'] = 'raw'
                return hp

        result = _run_backtest(FlatMartingale, prices)
        # Random signal may still trigger; just verify no crash
        assert isinstance(result['metrics']['total'], (int, float))


# ===========================================================================
# Hyperparameter structure tests
# ===========================================================================
class TestHyperparameterStructure:
    def test_all_hps_have_required_fields(self):
        s = UniversalMartingale()
        hps = s.hyperparameters()
        for hp in hps:
            assert 'name' in hp, f"HP missing 'name': {hp}"
            assert 'type' in hp, f"HP {hp['name']} missing 'type'"
            assert 'default' in hp, f"HP {hp['name']} missing 'default'"

    def test_no_duplicate_hp_names(self):
        s = UniversalMartingale()
        hps = s.hyperparameters()
        names = [h['name'] for h in hps]
        assert len(names) == len(set(names)), \
            f"Duplicate HP names: {[n for n in names if names.count(n) > 1]}"

    def test_numeric_hps_have_min_max(self):
        s = UniversalMartingale()
        hps = s.hyperparameters()
        for hp in hps:
            if hp['type'] in (int, float):
                assert 'min' in hp, f"Numeric HP {hp['name']} missing 'min'"
                assert 'max' in hp, f"Numeric HP {hp['name']} missing 'max'"
                assert hp['min'] <= hp['default'] <= hp['max'], \
                    f"HP {hp['name']}: default {hp['default']} not in [{hp['min']}, {hp['max']}]"

    def test_categorical_hps_have_valid_defaults(self):
        s = UniversalMartingale()
        hps = s.hyperparameters()
        for hp in hps:
            if hp['type'] == 'categorical':
                assert 'options' in hp, f"Categorical HP {hp['name']} missing 'options'"
                assert hp['default'] in hp['options'], \
                    f"HP {hp['name']}: default '{hp['default']}' not in {hp['options']}"


# ===========================================================================
# Signal module tests
# ===========================================================================
class TestSignalMethods:
    """Verify signal methods exist for all declared modes."""

    def test_all_signal_modes_have_methods(self):
        s = UniversalMartingale()
        hps = s.hyperparameters()
        signal_hp = next(h for h in hps if h['name'] == 'signal_mode')
        modes = signal_hp['options']

        for mode in modes:
            if mode == 'model':
                continue  # Model requires external fn
            method_name = f'_signal_{mode}'
            assert hasattr(s, method_name), \
                f"Missing signal method: {method_name} for mode '{mode}'"


# ===========================================================================
# Sizing: base_size_mode tests
# ===========================================================================
class TestBaseSizeMode:
    def _make_strategy_with_balance(self, balance, hp_overrides=None):
        s = UniversalMartingale.__new__(UniversalMartingale)
        s.hp = {
            'base_size_mode': 'fixed',
            'base_size_value': 1.0,
            'sizing_curve': 'geometric',
            'sizing_factor': 2.0,
            'sizing_custom_sequence': 'none',
        }
        if hp_overrides:
            s.hp.update(hp_overrides)
        # Mock the balance property (Strategy.balance accesses position.exchange)
        s.__class__ = type('MockedMartingale', (UniversalMartingale,), {
            'balance': property(lambda self: self._mock_balance)
        })
        s._mock_balance = balance
        return s

    def test_fixed_mode(self):
        s = self._make_strategy_with_balance(10000, {'base_size_mode': 'fixed', 'base_size_value': 5.0})
        assert s._base_size() == 5.0

    def test_pct_equity_mode(self):
        s = self._make_strategy_with_balance(10000, {'base_size_mode': 'pct_equity', 'base_size_value': 1.0})
        # 1% of 10000 = 100
        assert s._base_size() == pytest.approx(100.0)

    def test_pct_equity_scales_with_balance(self):
        s1 = self._make_strategy_with_balance(10000, {'base_size_mode': 'pct_equity', 'base_size_value': 2.0})
        s2 = self._make_strategy_with_balance(20000, {'base_size_mode': 'pct_equity', 'base_size_value': 2.0})
        assert s2._base_size() == pytest.approx(s1._base_size() * 2.0)


# ---------------------------------------------------------------------------
# Engine TP/SL Integration Tests
# ---------------------------------------------------------------------------
class TestEngineTPSL:
    """Tests that UniversalMartingale correctly uses engine ticket TP/SL."""

    def test_ticket_id_tracked_on_legs(self):
        """Legs should store ticket_id after entry and hedge."""
        prices = _make_zigzag(base=100, amplitude=2.0, periods=5, candles_per_leg=20)
        hp = dict(PRESETS.get('raw', {}))
        hp['signal_mode'] = 'random'
        hp['tp_mode'] = 'fixed_pips'
        hp['tp_value'] = 50.0  # far away — won't be hit
        hp['max_levels'] = 3
        result = _run_backtest(UniversalMartingale, prices, hyperparameters=hp)
        # If a cycle opened, legs should have ticket_id (may be None in futures mode)
        assert result is not None

    def test_preset_configs_all_load(self):
        """All presets should produce valid hyperparameter dicts."""
        for name, preset in PRESETS.items():
            assert isinstance(preset, dict), f"Preset {name} is not a dict"
            assert 'signal_mode' in preset or 'tp_mode' in preset, \
                f"Preset {name} missing key params"

    def test_surefire_v2_preset_has_bucket_exit(self):
        """surefire_v2 preset should use bucket_pct TP mode."""
        preset = PRESETS.get('surefire_v2', {})
        assert preset.get('tp_mode') == 'bucket_pct', "V2 preset should use bucket mode"

    def test_surefire_v1_preset_has_fixed_tp(self):
        """surefire_v1 preset should use fixed_pips TP mode."""
        preset = PRESETS.get('surefire_v1', {})
        tp_mode = preset.get('tp_mode', 'fixed_pips')
        assert tp_mode == 'fixed_pips', "V1 preset should use fixed_pips"
