"""Integration tests: StructuralStress feeding into RiskShield, CycleGate, MetaEvaluator."""
import numpy as np
import pytest

from pipelines._shared.ARIA import ARIAPipeline
from pipelines._shared.ARIA.risk_shield import RiskShield
from pipelines._shared.ARIA.cycle_gate import CycleGate, _build_features
from pipelines._shared.ARIA.meta_evaluator import MetaEvaluator


class TestStressAbort:
    def _mock_strategy(self, level=3, cycle_active=True):
        candles = np.array([[1609459200000 + i*300000, 1.2+i*0.0001, 1.2001+i*0.0001,
                            1.2002+i*0.0001, 1.1999+i*0.0001, 100.0] for i in range(20)])
        class S:
            pass
        s = S()
        s.balance = 10000.0
        s.price = 1.2
        s.leverage = 30.0
        s.fee_rate = 0.00015
        s.is_open = True
        s.candles = candles
        s.hp = {'sizing_factor': 1.4142, 'base_size_value': 1.0, 'max_levels': 12,
                'tp_value': 1.0, 'tp_atr_period': 14}
        s.vars = {'level': level, 'cycle_active': cycle_active, 'session_start_bar': 0}
        return s

    def test_no_abort_low_velocity(self):
        shield = RiskShield({'stress_abort_threshold': 1.5, 'stress_abort_min_level': 2})
        result = shield.check(self._mock_strategy(level=3), {'danger': 0.3}, stress_velocity=0.1)
        assert result is None or 'structural_stress' not in result.get('reason', '')

    def test_abort_high_velocity(self):
        shield = RiskShield({'stress_abort_threshold': 1.5, 'stress_abort_min_level': 2})
        result = shield.check(self._mock_strategy(level=3), {'danger': 0.3}, stress_velocity=2.0)
        assert result is not None
        assert 'structural_stress' in result['reason']

    def test_no_abort_shallow(self):
        shield = RiskShield({'stress_abort_threshold': 1.5, 'stress_abort_min_level': 2})
        result = shield.check(self._mock_strategy(level=1), {'danger': 0.3}, stress_velocity=2.0)
        assert result is None or 'structural_stress' not in result.get('reason', '')


class TestCycleGateStressFeatures:
    def _mock_strategy(self):
        class S:
            balance = 10000.0
            vars = {'sessions': [], 'consecutive_busts': 0}
            candles = np.array([[1609459200000, 1.2, 1.201, 1.202, 1.199, 100.0]])
        return S()

    def test_feature_vector_is_20d(self):
        ms = {'danger': 0.5, 'trend_strength': 0.4, 'volatility': 0.3,
              'efficiency': 0.5, 'regime_id': 0}
        sf = {'normalised_rt': 0.1, 'inter_cycle_gap_ratio': 0.8, 'recent_stress_rate': 0.05}
        x = _build_features(ms, self._mock_strategy(), stress_features=sf)
        assert x.shape == (20,)

    def test_stress_features_in_slots(self):
        ms = {'danger': 0.5, 'trend_strength': 0.4, 'volatility': 0.3,
              'efficiency': 0.5, 'regime_id': 0}
        sf = {'normalised_rt': 0.25, 'inter_cycle_gap_ratio': 0.6, 'recent_stress_rate': 0.15}
        x = _build_features(ms, self._mock_strategy(), stress_features=sf)
        assert x[16] == pytest.approx(0.25)
        assert x[17] == pytest.approx(0.6)
        assert x[18] == pytest.approx(0.15)
        assert x[19] == 1.0  # bias

    def test_backwards_compatible(self):
        ms = {'danger': 0.5, 'trend_strength': 0.4, 'volatility': 0.3,
              'efficiency': 0.5, 'regime_id': 0}
        x = _build_features(ms, self._mock_strategy())
        assert x.shape == (20,)
        assert x[16] == 0.0
        assert x[19] == 1.0


class TestMetaStressPenalty:
    def _make_sessions(self, n=20):
        return [{'reason': 'tp_hit', 'levels': 1, 'pnl': 50.0,
                 'gate_confidence': 0.6, 'equity_at_entry': 10000}
                for _ in range(n)]

    def test_no_stress_no_penalty(self):
        meta = MetaEvaluator({'window': 20})
        score = meta.evaluate(self._make_sessions(), stress_rate=0.01, baseline_stress_rate=0.01)
        assert score > 0

    def test_high_stress_penalised(self):
        meta = MetaEvaluator({'window': 20})
        sessions = self._make_sessions()
        score_low = meta.evaluate(sessions, stress_rate=0.01, baseline_stress_rate=0.01)
        score_high = meta.evaluate(sessions, stress_rate=0.8, baseline_stress_rate=0.01)
        assert score_high < score_low


class TestPipelineStressStats:
    def test_stress_in_stats(self):
        pipe = ARIAPipeline()
        stats = pipe.get_stats()
        assert 'structural_stress' in stats
        assert stats['structural_stress']['r_t'] == 0.0
        assert stats['structural_stress']['n_cycles'] == 0

    def test_persistence_roundtrip(self):
        pipe = ARIAPipeline()
        pipe._stress.record_cycle({
            'levels': 5, 'bars': 300, 'pnl': -50.0, 'reason': 'abort',
            'max_levels': 12, 'multiplier': 1.4142, 'expected_tp': 100.0,
            'level_timestamps': [0, 20, 40, 60, 80, 100], 'gap_bars': 50,
        })
        state = pipe._stress.state_dict()
        assert state['r_t'] > 0

        pipe2 = ARIAPipeline()
        pipe2._stress.load_state_dict(state)
        assert pipe2._stress.r_t == pipe._stress.r_t
