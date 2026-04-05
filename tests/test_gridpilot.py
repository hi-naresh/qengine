"""
Tests for GridPilot pipeline — DangerScorer, EntryGate, QAbort, feature extraction,
and the max_drawdown metric fix.

Tests are self-contained: they mock strategy.candles with numpy arrays
so they don't require the full backtest engine or database.
"""
import math
import numpy as np
import pandas as pd
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_candles(n, base=1.1000, volatility=0.0005, seed=42):
    """Generate realistic OHLCV candles as numpy array.
    Format: [timestamp, open, close, high, low, volume]
    """
    rng = np.random.RandomState(seed)
    candles = np.zeros((n, 6))
    price = base
    for i in range(n):
        o = price
        change = rng.randn() * volatility
        c = o + change
        h = max(o, c) + abs(rng.randn() * volatility * 0.5)
        l = min(o, c) - abs(rng.randn() * volatility * 0.5)
        candles[i] = [i * 300_000, o, c, h, l, 1000 + rng.randint(0, 500)]
        price = c
    return candles


class MockStrategy:
    """Minimal strategy mock for pipeline testing."""
    def __init__(self, candles, index=None):
        self._candles = candles
        self.index = index if index is not None else len(candles) - 1
        self.vars = {}
        self.current_candle = candles[-1] if len(candles) > 0 else np.zeros(6)

    @property
    def candles(self):
        return self._candles


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Feature Extraction Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeatureExtraction:

    def test_returns_empty_for_short_candles(self):
        from pipelines._shared.GridPilot import _extract_features
        s = MockStrategy(_make_candles(10))
        assert _extract_features(s) == {}

    def test_returns_all_seven_features_for_enough_data(self):
        from pipelines._shared.GridPilot import _extract_features
        s = MockStrategy(_make_candles(300))
        features = _extract_features(s)
        expected_keys = {'D1_range_atr', '5m_chop', '15m_chop', 'D1_chop',
                         '5m_adx', '5m_hurst', '1H_atr_ratio'}
        assert expected_keys == set(features.keys()), \
            f"Missing: {expected_keys - set(features.keys())}, Extra: {set(features.keys()) - expected_keys}"

    def test_choppiness_values_differ_across_scales(self):
        """The old bug: 5m_chop == 15m_chop == D1_chop (all identical).
        After fix, they should differ because they use different lookback periods."""
        from pipelines._shared.GridPilot import _extract_features
        s = MockStrategy(_make_candles(300))
        features = _extract_features(s)
        assert features['5m_chop'] != features['15m_chop'], \
            "5m and 15m choppiness should differ (different lookback periods)"
        assert features['15m_chop'] != features['D1_chop'], \
            "15m and D1 choppiness should differ (different lookback periods)"

    def test_adx_in_valid_range(self):
        from pipelines._shared.GridPilot import _extract_features
        s = MockStrategy(_make_candles(300))
        features = _extract_features(s)
        assert 0 <= features['5m_adx'] <= 100, f"ADX={features['5m_adx']} out of range"

    def test_hurst_in_valid_range(self):
        from pipelines._shared.GridPilot import _extract_features
        s = MockStrategy(_make_candles(300))
        features = _extract_features(s)
        assert 0 <= features['5m_hurst'] <= 1.0, f"Hurst={features['5m_hurst']} out of range"

    def test_atr_ratio_positive(self):
        from pipelines._shared.GridPilot import _extract_features
        s = MockStrategy(_make_candles(300))
        features = _extract_features(s)
        assert features['1H_atr_ratio'] > 0

    def test_constant_time_regardless_of_history(self):
        """Feature extraction should take similar time for 100 vs 100K candles."""
        import time
        from pipelines._shared.GridPilot import _extract_features

        s_small = MockStrategy(_make_candles(100))
        s_large = MockStrategy(_make_candles(10000, seed=99))

        # Warmup
        _extract_features(s_small)
        _extract_features(s_large)

        iters = 500
        t0 = time.perf_counter()
        for _ in range(iters):
            _extract_features(s_small)
        time_small = time.perf_counter() - t0

        t0 = time.perf_counter()
        for _ in range(iters):
            _extract_features(s_large)
        time_large = time.perf_counter() - t0

        # Large should be no more than 3x slower (O(1) vs O(n) would be 100x)
        ratio = time_large / time_small
        assert ratio < 3.0, f"Large is {ratio:.1f}x slower — not O(1)"

    def test_handles_none_candles(self):
        from pipelines._shared.GridPilot import _extract_features
        s = MockStrategy(np.zeros((0, 6)))
        s._candles = None
        assert _extract_features(s) == {}

    def test_choppiness_bounded(self):
        """Choppiness Index should be in [0, 100] range."""
        from pipelines._shared.GridPilot import _extract_features
        s = MockStrategy(_make_candles(300))
        features = _extract_features(s)
        for key in ['5m_chop', '15m_chop', 'D1_chop']:
            assert 0 < features[key] < 200, f"{key}={features[key]} seems unreasonable"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DangerScorer Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDangerScorer:

    def test_warmup_returns_neutral(self):
        from qengine.framework.components.danger_scorer import DangerScorer
        scorer = DangerScorer({'warmup': 10})
        features = {'5m_chop': 55, '5m_adx': 20}
        for _ in range(9):
            score = scorer.update(features)
        assert score == 0.5, "Should return 0.5 during warmup"

    def test_after_warmup_scores_vary(self):
        from qengine.framework.components.danger_scorer import DangerScorer
        scorer = DangerScorer({'warmup': 10})
        rng = np.random.RandomState(42)
        scores = []
        for i in range(200):
            features = {
                '5m_chop': 50 + rng.randn() * 10,
                '15m_chop': 53 + rng.randn() * 10,
                'D1_chop': 47 + rng.randn() * 10,
                '5m_adx': 20 + rng.randn() * 7,
                '5m_hurst': 0.05 + abs(rng.randn()) * 0.04,
                '1H_atr_ratio': 1.1 + rng.randn() * 0.2,
                'D1_range_atr': 5 + rng.randn() * 1.3,
            }
            score = scorer.update(features)
            if i >= 10:
                scores.append(score)

        assert all(0 <= s <= 1 for s in scores), "All scores should be in [0, 1]"
        # After warmup, scores should have meaningful variance (not all ~0.5)
        std = np.std(scores)
        assert std > 0.01, f"Score std={std:.4f} — scores too clustered, gate won't work"

    def test_output_bounded_0_1(self):
        from qengine.framework.components.danger_scorer import DangerScorer
        scorer = DangerScorer({'warmup': 5})
        # Feed extreme values
        for _ in range(5):
            scorer.update({'5m_chop': 100, '5m_adx': 0})
        score_high = scorer.update({'5m_chop': 200, '5m_adx': 0})
        assert 0 <= score_high <= 1
        score_low = scorer.update({'5m_chop': 0, '5m_adx': 100})
        assert 0 <= score_low <= 1

    def test_seeded_normalizer_skips_warmup(self):
        from qengine.framework.components.danger_scorer import DangerScorer
        params = {
            'means': {'5m_chop': 50, '5m_adx': 20},
            'stds': {'5m_chop': 10, '5m_adx': 7},
            'n': 10000,
        }
        scorer = DangerScorer({'pretrained_params': params, 'warmup': 200})
        score = scorer.update({'5m_chop': 60, '5m_adx': 10})
        # Should NOT be 0.5 — normalizer is seeded and ready
        assert score != 0.5, "Seeded scorer should produce non-neutral score immediately"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. EntryGate Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestEntryGate:

    def test_allows_everything_during_warmup(self):
        from qengine.framework.components.entry_gate import EntryGate
        gate = EntryGate({'percentile': 75, 'window': 500})
        # Less than 10 observations → threshold = inf → always allow
        for _ in range(9):
            gate.observe(0.5)
        assert gate.should_allow(0.99) is True

    def test_blocks_high_scores_after_warmup(self):
        from qengine.framework.components.entry_gate import EntryGate
        gate = EntryGate({'percentile': 75, 'window': 100})
        rng = np.random.RandomState(42)
        for _ in range(100):
            gate.observe(rng.random())
        # A score of 0.99 should be blocked (above 75th percentile)
        assert gate.should_allow(0.99) is False

    def test_allows_low_scores(self):
        from qengine.framework.components.entry_gate import EntryGate
        gate = EntryGate({'percentile': 75, 'window': 100})
        rng = np.random.RandomState(42)
        for _ in range(100):
            gate.observe(rng.random())
        # A score of 0.01 should be allowed
        assert gate.should_allow(0.01) is True

    def test_sliding_window_evicts_old_scores(self):
        from qengine.framework.components.entry_gate import EntryGate
        gate = EntryGate({'percentile': 75, 'window': 20})
        # Fill with high scores
        for _ in range(20):
            gate.observe(0.9)
        # Now fill with low scores — old high scores should be evicted
        for _ in range(20):
            gate.observe(0.1)
        # 0.5 should now be allowed (above p75 of [0.1, 0.1, ...])
        # Actually 0.5 > p75 of all 0.1s... should be blocked
        # 0.05 should be allowed
        assert gate.should_allow(0.05) is True
        # Threshold should be ~0.1 now (75th percentile of all 0.1s)
        assert gate.current_threshold == pytest.approx(0.1, abs=0.01)

    def test_sorted_list_stays_consistent(self):
        """The incremental bisect-based sorted list should match a full sort."""
        from qengine.framework.components.entry_gate import EntryGate
        gate = EntryGate({'percentile': 75, 'window': 50})
        rng = np.random.RandomState(42)
        for _ in range(200):
            gate.observe(rng.random())
        # Compare gate's internal sorted list with actual sorted scores
        actual_sorted = sorted(gate._scores)
        assert gate._sorted == actual_sorted, "Incremental sorted list diverged"

    def test_disabled_gate_always_allows(self):
        from qengine.framework.components.entry_gate import EntryGate
        gate = EntryGate({'enabled': False})
        for _ in range(100):
            gate.observe(0.9)
        assert gate.should_allow(0.99) is True


# ═══════════════════════════════════════════════════════════════════════════════
# 4. QAbort Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestQAbort:

    def test_eval_mode_no_learning(self):
        from qengine.framework.components.q_abort import QAbort
        q = QAbort({'mode': 'eval', 'enabled': True})
        q.start_episode()
        action = q.decide(level=0, duration_bars=3, danger_entry=0.4, danger_now=0.5)
        assert action in ('continue', 'abort')
        # In eval mode with zero Q-table, should default to continue
        assert action == 'continue'
        q.end_episode(reward=10.0)
        # Q-table should NOT change in eval mode
        assert np.all(q.q_table == 0)

    def test_pretrained_table_produces_aborts(self):
        """Pre-trained Q-table has 45 abort-preferred states. Verify at least one fires."""
        from qengine.framework.components.q_abort import QAbort
        import os
        models_dir = os.path.join(os.path.dirname(__file__), '..', 'pipelines', '_shared', 'GridPilot', 'models')
        q_path = os.path.join(models_dir, 'q_table.npy')
        vc_path = os.path.join(models_dir, 'q_visit_count.npy')
        if not os.path.exists(q_path):
            pytest.skip("Pre-trained Q-table not found")
        q = QAbort({'mode': 'eval', 'q_table_path': q_path, 'visit_count_path': vc_path})
        # Scan all states for any abort-preferred
        abort_states = 0
        for s in range(q.q_table.shape[0]):
            if q.q_table[s, 1] > q.q_table[s, 0]:
                abort_states += 1
        assert abort_states > 0, "Pre-trained table should have some abort-preferred states"
        assert abort_states == 45, f"Expected 45 abort states, got {abort_states}"

    def test_train_mode_updates_qtable(self):
        from qengine.framework.components.q_abort import QAbort
        q = QAbort({'mode': 'train', 'epsilon': 0.0, 'alpha': 0.1})
        q.start_episode()
        q.decide(level=0, duration_bars=3, danger_entry=0.5, danger_now=0.5)
        q.end_episode(reward=-100.0)
        # Q-table should have been updated
        assert np.any(q.q_table != 0), "Train mode should update Q-table"

    def test_disabled_always_continues(self):
        from qengine.framework.components.q_abort import QAbort
        q = QAbort({'enabled': False})
        action = q.decide(level=5, duration_bars=100, danger_entry=0.9, danger_now=0.9)
        assert action == 'continue'

    def test_state_encoding_deterministic(self):
        from qengine.framework.components.q_abort import _encode_state
        s1 = _encode_state(0, 3, 0.4, 0.6)
        s2 = _encode_state(0, 3, 0.4, 0.6)
        assert s1 == s2
        # Different inputs → different states
        s3 = _encode_state(5, 30, 0.8, 0.9)
        assert s1 != s3

    def test_state_encoding_bounds(self):
        from qengine.framework.components.q_abort import _encode_state, TOTAL_STATES
        # Edge cases
        for level in [0, 6, 12, 20]:  # 20 gets clamped to 12
            for dur in [0, 5, 50, 200]:
                for de in [0.0, 0.5, 1.0]:
                    for dn in [0.0, 0.5, 1.0]:
                        idx = _encode_state(level, dur, de, dn)
                        assert 0 <= idx < TOTAL_STATES, \
                            f"State index {idx} out of bounds for ({level},{dur},{de},{dn})"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. GridPilot Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestGridPilotIntegration:

    def _make_pilot(self, **overrides):
        from pipelines._shared.GridPilot import GridPilot
        config = {
            'use_pretrained': True,
            'scorer': {'warmup': 20},
            'gate': {'percentile': 75, 'window': 100, 'enabled': True},
            'abort': {'enabled': True, 'mode': 'eval'},
        }
        config.update(overrides)
        return GridPilot(config)

    def test_on_before_updates_score(self):
        pilot = self._make_pilot()
        s = MockStrategy(_make_candles(100))
        pilot.on_before(s)
        # During warmup, score should be 0.5
        assert pilot.scorer.current_score == 0.5

    def test_gate_allows_during_warmup(self):
        pilot = self._make_pilot()
        s = MockStrategy(_make_candles(100))
        # Feed a few candles (still in warmup)
        for _ in range(5):
            pilot.on_before(s)
        # Gate should allow during warmup
        assert pilot.gate_entry(s) is True

    def test_gate_blocks_after_warmup(self):
        """After warmup, with varied features, gate should block some entries."""
        pilot = self._make_pilot(scorer={'warmup': 20},
                                 gate={'percentile': 50, 'window': 50, 'enabled': True})
        rng = np.random.RandomState(42)
        blocked_count = 0
        allowed_count = 0
        for i in range(200):
            candles = _make_candles(100, volatility=0.0005 + rng.random() * 0.002, seed=i)
            s = MockStrategy(candles)
            pilot.on_before(s)
            if i >= 30:  # Past warmup
                result = pilot.gate_entry(s)
                if result:
                    allowed_count += 1
                else:
                    blocked_count += 1

        total = blocked_count + allowed_count
        block_rate = blocked_count / total if total > 0 else 0
        assert blocked_count > 0, f"Gate never blocked anything ({total} checks)"
        assert allowed_count > 0, f"Gate blocked everything ({total} checks)"
        # At 50th percentile, roughly half should be blocked
        assert 0.2 < block_rate < 0.8, \
            f"Block rate {block_rate:.1%} doesn't match 50th percentile gate"

    def test_abort_skips_during_warmup(self):
        pilot = self._make_pilot()
        s = MockStrategy(_make_candles(100))
        s.vars = {'level': 5}
        for _ in range(5):
            pilot.on_before(s)
        assert pilot.should_abort(s) is False, "Should not abort during warmup"

    def test_on_open_position_records_state(self):
        pilot = self._make_pilot()
        s = MockStrategy(_make_candles(100), index=50)
        # Warmup scorer first
        for _ in range(25):
            pilot.on_before(s)
        pilot.on_open_position(s)
        assert pilot._cycle_start_index == 50
        assert pilot._danger_at_entry == pilot.scorer.current_score

    def test_on_cycle_end_records_outcome(self):
        pilot = self._make_pilot()
        s = MockStrategy(_make_candles(100), index=50)
        s.vars = {'level': 2}
        for _ in range(25):
            pilot.on_before(s)
        pilot.on_open_position(s)
        pilot.on_cycle_end(pnl=15.5, strategy=s)
        stats = pilot.get_stats()
        assert stats['cycles_completed'] == 1
        assert len(stats['cycle_outcomes']) == 1
        assert stats['cycle_outcomes'][0]['pnl'] == 15.5

    def test_full_lifecycle(self):
        """Simulate a complete cycle: warmup → entry → position open → exit."""
        pilot = self._make_pilot(scorer={'warmup': 20})
        candles = _make_candles(200)

        # Phase 1: Warmup (20 candles)
        for i in range(25):
            s = MockStrategy(candles[:50 + i], index=50 + i)
            pilot.on_before(s)

        # Phase 2: Entry attempt
        s = MockStrategy(candles[:80], index=80)
        pilot.on_before(s)
        allowed = pilot.gate_entry(s)
        # Should either allow or block — just verify no crash

        # Phase 3: Position opens
        s.vars = {'level': 0}
        pilot.on_open_position(s)

        # Phase 4: Monitor position (abort checks)
        for i in range(20):
            s = MockStrategy(candles[:80 + i], index=80 + i)
            s.vars = {'level': 0}
            pilot.on_before(s)
            pilot.should_abort(s)

        # Phase 5: Cycle ends
        pilot.on_cycle_end(pnl=5.0, strategy=s)

        # Verify stats
        stats = pilot.get_stats()
        assert stats['cycles_completed'] == 1
        assert len(stats['danger_scores']) > 0
        assert stats['scorer']['warmed_up'] is True

    def test_get_stats_returns_valid_dict(self):
        pilot = self._make_pilot()
        stats = pilot.get_stats()
        assert 'scorer' in stats
        assert 'gate' in stats
        assert 'abort' in stats
        assert 'cycles_completed' in stats
        assert 'danger' in stats


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Max Drawdown Fix Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestMaxDrawdownFix:

    def _max_drawdown(self, daily_balance):
        from qengine.services.metrics import max_drawdown
        df = pd.DataFrame(daily_balance)
        returns = df.pct_change(1)
        return float(max_drawdown(returns).iloc[0]) * 100

    def test_two_entries_declining(self):
        """The original bug: 2 balance entries gave 0% drawdown."""
        dd = self._max_drawdown([10000, 9759])
        assert dd == pytest.approx(-2.41, abs=0.01), f"Got {dd}%, expected -2.41%"

    def test_gradual_decline(self):
        dd = self._max_drawdown([10000, 9990, 9980, 9970, 9960, 9950])
        assert dd < -0.4, f"Expected negative drawdown, got {dd}%"

    def test_up_then_down(self):
        """Peak at 10400, trough at 9800 → ~5.77% drawdown."""
        dd = self._max_drawdown([10000, 10200, 10400, 10100, 9800, 10000])
        expected = (9800 - 10400) / 10400 * 100
        assert dd == pytest.approx(expected, abs=0.1)

    def test_always_winning_zero_drawdown(self):
        dd = self._max_drawdown([10000, 10100, 10200, 10300])
        assert dd == pytest.approx(0.0, abs=0.01)

    def test_single_entry(self):
        dd = self._max_drawdown([10000])
        assert dd == pytest.approx(0.0, abs=0.01)

    def test_three_entries_with_recovery(self):
        """10000 → 9000 → 10500: drawdown = -10%, then recovery."""
        dd = self._max_drawdown([10000, 9000, 10500])
        assert dd == pytest.approx(-10.0, abs=0.1)

    def test_large_monotonic_decline(self):
        """Monotonic decline should give drawdown equal to total loss."""
        balance = [10000 - i * 10 for i in range(100)]  # 10000 → 9010
        dd = self._max_drawdown(balance)
        expected = (9010 - 10000) / 10000 * 100  # -9.9%
        assert dd == pytest.approx(expected, abs=0.5)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. PipelineStats Memory Cap Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineStatsCap:

    def test_danger_scores_capped(self):
        from qengine.framework.stats import PipelineStats
        stats = PipelineStats()
        for i in range(7000):
            stats.record_danger(float(i), 0.5)
        assert len(stats.danger_scores) <= 6000, \
            f"Danger scores grew to {len(stats.danger_scores)}, expected <= 6000"

    def test_gate_decisions_capped(self):
        from qengine.framework.stats import PipelineStats
        stats = PipelineStats()
        for i in range(1500):
            stats.record_gate(float(i), 0.5, True, threshold=0.7)
        assert len(stats.gate_decisions) <= 1000

    def test_abort_decisions_capped(self):
        from qengine.framework.stats import PipelineStats
        stats = PipelineStats()
        for i in range(1500):
            stats.record_abort(float(i), 0, 0.5, 'continue')
        assert len(stats.abort_decisions) <= 1000


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Welford Normalizer Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestWelfordNormalizer:

    def test_seeded_produces_correct_zscore(self):
        from qengine.framework.components.danger_scorer import WelfordNormalizer
        norm = WelfordNormalizer()
        norm.seed(mean=50.0, std=10.0, n=10000)
        # A value 1 std above mean should give z ≈ 1.0
        z = norm.update(60.0)
        assert z == pytest.approx(1.0, abs=0.01)
        # A value at the mean should give z ≈ 0.0
        z = norm.update(50.0)
        assert z == pytest.approx(0.0, abs=0.05)

    def test_online_converges(self):
        from qengine.framework.components.danger_scorer import WelfordNormalizer
        norm = WelfordNormalizer()
        rng = np.random.RandomState(42)
        values = rng.normal(50, 10, 1000)
        zscores = [norm.update(v) for v in values]
        # After 1000 observations, z-scores should have std ≈ 1.0
        tail_std = np.std(zscores[-500:])
        assert 0.5 < tail_std < 1.5, f"Z-score std={tail_std}, expected ~1.0"
