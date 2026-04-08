"""
Tests for the IslandPilot pipeline class.
"""

import os
import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from pipelines._shared.IslandPilot import IslandPilot
from pipelines._shared.IslandPilot.config import DEFAULT_CONFIG, merge_config
from qengine.framework.base import Pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_strategy(n_candles=200):
    """Create a mock strategy with candles and hp dict."""
    strategy = MagicMock()
    # Generate fake OHLCV candles: [timestamp, open, close, high, low, volume]
    rng = np.random.RandomState(42)
    timestamps = np.arange(n_candles) * 60000  # 1-min candles
    opens = 1.1000 + rng.randn(n_candles).cumsum() * 0.0001
    closes = opens + rng.randn(n_candles) * 0.0002
    highs = np.maximum(opens, closes) + abs(rng.randn(n_candles)) * 0.0001
    lows = np.minimum(opens, closes) - abs(rng.randn(n_candles)) * 0.0001
    volumes = rng.randint(100, 10000, n_candles).astype(float)

    candles = np.column_stack([timestamps, opens, closes, highs, lows, volumes])
    strategy.candles = candles
    strategy.hp = {
        'max_levels': 8,
        'tp_distance_atr_mult': 2.0,
        'hedge_distance_atr_mult': 1.0,
        'base_size_pct': 1.0,
        'sizing_curve': 'geometric',
    }
    return strategy


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIslandPilotBasics:
    """Basic construction and interface checks."""

    def test_import_and_name(self):
        pilot = IslandPilot()
        assert pilot.name == 'IslandPilot'

    def test_extends_pipeline(self):
        assert issubclass(IslandPilot, Pipeline)

    def test_default_config_returns_dict_with_required_keys(self):
        cfg = IslandPilot.default_config()
        assert isinstance(cfg, dict)
        for key in ('regime', 'evolution', 'inference', 'sizing', 'warmup'):
            assert key in cfg, f"Missing key: {key}"

    def test_architecture_returns_dict_with_layers(self):
        arch = IslandPilot.architecture()
        assert isinstance(arch, dict)
        assert 'layers' in arch
        assert len(arch['layers']) == 5
        names = {c['name'] for c in arch['layers']}
        assert 'FeaturePool' in names
        assert 'RegimeTree' in names
        assert 'IslandEvolver' in names
        # Training metadata
        assert arch['requires_training'] is True
        assert arch['training_status'] in ('trained', 'untrained')
        assert 'RegimeInferencer' in names
        assert 'AdaptiveSizer' in names


class TestGateEntry:
    """Entry gating logic."""

    def test_gate_blocks_during_warmup_no_genome(self):
        pilot = IslandPilot({'warmup': 200})
        strategy = _make_mock_strategy(n_candles=50)

        # Simulate a few candles (below warmup)
        for _ in range(10):
            pilot.on_before(strategy)

        # Should block: not enough candles for warmup AND no genome
        assert pilot.gate_entry(strategy) is False

    def test_gate_blocks_when_no_genome(self):
        pilot = IslandPilot({'warmup': 10})
        # Clear pretrained models to test "no genome" path
        pilot.regime_tree = None
        pilot.evolver = None
        pilot.inferencer = None
        strategy = _make_mock_strategy(n_candles=200)

        # Run enough candles to pass warmup, but no regime tree = no genome
        for _ in range(20):
            pilot.on_before(strategy)

        assert pilot.gate_entry(strategy) is False

    def test_gate_allows_with_genome_and_confidence(self):
        pilot = IslandPilot({'warmup': 10})
        strategy = _make_mock_strategy(n_candles=200)

        # Manually set state as if regime was classified and genome found
        pilot._candle_count = 100
        pilot._active_genome = {'gate_confidence_min': 0.2, 'base_size_pct': 1.0}
        pilot._active_confidence = 0.8
        # No inferencer, so no grace period check
        pilot.inferencer = None

        assert pilot.gate_entry(strategy) is True

    def test_gate_blocks_low_confidence(self):
        pilot = IslandPilot({'warmup': 10, 'inference': {'min_confidence': 0.5}})
        pilot._candle_count = 100
        pilot._active_genome = {'base_size_pct': 1.0}
        pilot._active_confidence = 0.2

        strategy = _make_mock_strategy()
        assert pilot.gate_entry(strategy) is False


class TestGetStats:
    """Stats reporting."""

    def test_get_stats_returns_dict_with_active_regime(self):
        pilot = IslandPilot()
        stats = pilot.get_stats()
        assert isinstance(stats, dict)
        assert 'active_regime' in stats
        assert 'candle_count' in stats
        assert 'cycle_count' in stats
        assert 'sizer' in stats

    def test_get_stats_with_components(self):
        pilot = IslandPilot()
        pilot._active_regime = 3
        pilot._active_confidence = 0.85
        pilot._candle_count = 500
        pilot._cycle_count = 25

        stats = pilot.get_stats()
        assert stats['active_regime'] == 3
        assert stats['active_confidence'] == 0.85
        assert stats['candle_count'] == 500
        assert stats['cycle_count'] == 25


class TestSaveLoadRoundtrip:
    """Persistence roundtrip."""

    def test_save_load_roundtrip(self, tmp_path):
        pilot = IslandPilot()
        pilot._candle_count = 42
        pilot._cycle_count = 7
        pilot._active_regime = 2
        pilot._active_confidence = 0.65
        pilot._sibling_groups = {'macro_0': ['0', '1']}

        save_dir = str(tmp_path / 'island_pilot_state')
        pilot.save_state(save_dir)

        # Verify runtime.json was written
        runtime_path = os.path.join(save_dir, 'runtime.json')
        assert os.path.exists(runtime_path)
        with open(runtime_path) as f:
            data = json.load(f)
        assert data['candle_count'] == 42
        assert data['cycle_count'] == 7

        # Load into a new instance
        pilot2 = IslandPilot()
        pilot2.load_state(save_dir)

        assert pilot2._candle_count == 42
        assert pilot2._cycle_count == 7
        assert pilot2._active_regime == 2
        assert pilot2._active_confidence == 0.65
        assert pilot2._sibling_groups == {'macro_0': ['0', '1']}

    def test_save_load_with_sizer(self, tmp_path):
        pilot = IslandPilot()
        # Trigger sizer to record some stats
        pilot.sizer.compute(
            base_pct=1.0, confidence=0.9, sensitivity=1.0,
            drawdown_pct=2.0, recovery_aggression=0.5, balance=10000, qty=100,
        )

        save_dir = str(tmp_path / 'pilot_sizer')
        pilot.save_state(save_dir)

        pilot2 = IslandPilot()
        pilot2.load_state(save_dir)

        assert pilot2.sizer._calls == 1


class TestConfigMerge:
    """Config merge utility."""

    def test_merge_empty_returns_defaults(self):
        cfg = merge_config({})
        assert cfg == DEFAULT_CONFIG

    def test_merge_partial_override(self):
        cfg = merge_config({'warmup': 200, 'sizing': {'drawdown_threshold_pct': 10.0}})
        assert cfg['warmup'] == 200
        assert cfg['sizing']['drawdown_threshold_pct'] == 10.0
        # Other sizing keys should still have defaults
        assert cfg['sizing']['min_confidence_scale'] == 0.2

    def test_merge_does_not_mutate_defaults(self):
        import copy
        original = copy.deepcopy(DEFAULT_CONFIG)
        merge_config({'warmup': 999})
        assert DEFAULT_CONFIG == original


class TestInternalHelpers:
    """Internal helper methods."""

    def test_compute_danger(self):
        pilot = IslandPilot()
        strategy = _make_mock_strategy(n_candles=50)
        danger = pilot._compute_danger(strategy)
        assert isinstance(danger, float)
        assert 0.0 <= danger <= 1.0

    def test_compute_danger_short_candles(self):
        pilot = IslandPilot()
        strategy = MagicMock()
        strategy.candles = np.zeros((5, 6))
        danger = pilot._compute_danger(strategy)
        assert danger == 0.0

    def test_apply_genome(self):
        pilot = IslandPilot()
        strategy = _make_mock_strategy()
        # Seed hp with keys the strategy would have (so _apply_genome detects them)
        strategy.hp['sizing_operator'] = 'sqrt'
        strategy.hp['hedge_distance'] = 10
        strategy.hp['tp_distance'] = 20
        genome = {
            'max_levels': 10,  # will be capped to 8
            'tp_distance_atr_mult': 3.5,
            'hedge_distance_atr_mult': 1.5,
            'sizing_curve': 0,  # int -> 'geometric'
        }
        pilot._apply_genome(strategy, genome)
        assert strategy.hp['max_levels'] == 8  # capped for safety
        # Surefire v1: tp_distance in pips (mult * 10)
        assert strategy.hp['tp_distance'] == 35.0
        assert strategy.hp['hedge_distance'] == 15.0
        # sizing_operator (not sizing_curve) for Surefire
        assert strategy.hp['sizing_operator'] == 'geometric'

    def test_apply_genome_string_sizing_curve(self):
        pilot = IslandPilot()
        strategy = _make_mock_strategy()
        strategy.hp['sizing_operator'] = 'sqrt'
        genome = {'sizing_curve': 'fibonacci'}
        pilot._apply_genome(strategy, genome)
        assert strategy.hp['sizing_operator'] == 'fibonacci'

    def test_build_sibling_groups_no_tree(self):
        pilot = IslandPilot()
        pilot.regime_tree = None  # clear pretrained
        groups = pilot._build_sibling_groups()
        assert groups == {}


class TestSuggestExit:
    """Exit suggestion logic."""

    def test_suggest_exit_no_genome(self):
        pilot = IslandPilot()
        strategy = _make_mock_strategy()
        assert pilot.suggest_exit(strategy) is None

    def test_suggest_exit_low_danger(self):
        pilot = IslandPilot()
        strategy = _make_mock_strategy(n_candles=50)
        # Set genome with high abort threshold so normal vol won't trigger
        pilot._active_genome = {'abort_aggressiveness': 0.99}
        result = pilot.suggest_exit(strategy)
        # With typical random candles, danger should be below 0.99
        assert result is None

    def test_on_cycle_end_increments_count(self):
        pilot = IslandPilot()
        strategy = _make_mock_strategy()
        pilot.on_cycle_end(100.0, strategy)
        pilot.on_cycle_end(-50.0, strategy)
        assert pilot._cycle_count == 2


class TestAdjustSize:
    """Position sizing integration."""

    def test_adjust_size_no_genome_passthrough(self):
        pilot = IslandPilot()
        strategy = _make_mock_strategy()
        result = pilot.adjust_size(strategy, 1000.0, 'long')
        assert result == 1000.0

    def test_adjust_size_with_genome(self):
        pilot = IslandPilot()
        strategy = _make_mock_strategy()
        # Set real numeric values on portfolio mock so sizer doesn't choke
        strategy.portfolio.max_drawdown = -2.0
        strategy.portfolio.equity = 10000.0
        pilot._active_genome = {
            'base_size_pct': 1.0,
            'confidence_sensitivity': 1.0,
            'recovery_aggression': 0.5,
        }
        pilot._active_confidence = 0.9
        result = pilot.adjust_size(strategy, 1000.0, 'long')
        assert isinstance(result, float)
        assert result > 0
