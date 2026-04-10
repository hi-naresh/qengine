"""Tests for ARIA StructuralStress R(t) module."""
import math
import pytest
from pipelines._shared.ARIA.structural_stress import StructuralStress


class TestExcessDepth:
    def test_within_range_returns_zero(self):
        ss = StructuralStress()
        assert ss._compute_X(levels=5, max_levels=12) == 0.0

    def test_exceeds_returns_positive(self):
        ss = StructuralStress()
        result = ss._compute_X(levels=11, max_levels=12)
        assert result > 0.0

    def test_at_max_returns_0_3(self):
        ss = StructuralStress()
        result = ss._compute_X(levels=12, max_levels=12)
        assert abs(result - 0.3) < 1e-6

    def test_zero_levels_returns_zero(self):
        ss = StructuralStress()
        assert ss._compute_X(levels=0, max_levels=12) == 0.0


class TestExposureConcentration:
    def test_shallow_returns_zero(self):
        ss = StructuralStress()
        assert ss._compute_C(levels=1, multiplier=1.414) == 0.0

    def test_deep_above_0_4(self):
        ss = StructuralStress()
        result = ss._compute_C(levels=10, multiplier=2.0)
        assert result > 0.4

    def test_2x_greater_than_sqrt2(self):
        ss = StructuralStress()
        c_2x = ss._compute_C(levels=8, multiplier=2.0)
        c_sqrt2 = ss._compute_C(levels=8, multiplier=math.sqrt(2))
        assert c_2x > c_sqrt2


class TestTimeUnderStress:
    def test_short_returns_zero(self):
        ss = StructuralStress()
        ss._all_bars = [100, 200, 150, 120, 180]
        result = ss._compute_U(bars=100)
        assert result == 0.0

    def test_long_returns_positive(self):
        ss = StructuralStress()
        ss._all_bars = [100, 100, 100, 100, 100]
        result = ss._compute_U(bars=300)
        assert result == 2.0

    def test_no_history_returns_zero(self):
        ss = StructuralStress()
        result = ss._compute_U(bars=500)
        assert result == 0.0


class TestReboundDeficit:
    def test_full_tp_returns_zero(self):
        ss = StructuralStress()
        result = ss._compute_V(pnl=100.0, expected_tp=100.0, reason='tp')
        assert result == 0.0

    def test_partial_returns_0_5(self):
        ss = StructuralStress()
        result = ss._compute_V(pnl=50.0, expected_tp=100.0, reason='tp')
        assert abs(result - 0.5) < 1e-6

    def test_bust_returns_1(self):
        ss = StructuralStress()
        result = ss._compute_V(pnl=-200.0, expected_tp=100.0, reason='bust')
        assert result == 1.0

    def test_zero_expected_returns_zero(self):
        ss = StructuralStress()
        result = ss._compute_V(pnl=50.0, expected_tp=0.0, reason='tp')
        assert result == 0.0


class TestEntryClustering:
    def test_normal_gaps_returns_zero(self):
        ss = StructuralStress()
        # History with small median gap
        ss._all_level_gaps = [10.0, 20.0, 30.0, 40.0, 50.0]
        # All gaps above median (30) -> fraction below = 0
        result = ss._compute_F([0, 100, 200, 300])
        assert result == 0.0

    def test_rapid_returns_1(self):
        ss = StructuralStress()
        ss._all_level_gaps = [100.0, 200.0, 300.0, 400.0, 500.0]
        # All gaps (1,1,1) well below median (300) -> fraction = 1.0
        result = ss._compute_F([0, 1, 2, 3])
        assert result == 1.0

    def test_mixed_returns_fraction(self):
        ss = StructuralStress()
        ss._all_level_gaps = [10.0, 10.0, 10.0]  # median = 10
        # Gaps: 5, 15, 5 -> 2 below median, 1 above -> 2/3
        result = ss._compute_F([0, 5, 20, 25])
        assert abs(result - 2.0 / 3.0) < 1e-6

    def test_single_level_returns_zero(self):
        ss = StructuralStress()
        ss._all_level_gaps = [10.0, 20.0]
        result = ss._compute_F([100])
        assert result == 0.0

    def test_no_history_returns_zero(self):
        ss = StructuralStress()
        result = ss._compute_F([0, 1, 2])
        assert result == 0.0


class TestInterCycleOverlap:
    def test_adequate_gap_returns_zero(self):
        ss = StructuralStress()
        ss._all_cycle_gaps = [100, 200, 300, 400, 500]
        # gap_bars=300 >= median(300)*0.5=150 -> 0
        result = ss._compute_M(gap_bars=300)
        assert result == 0.0

    def test_rushed_returns_one(self):
        ss = StructuralStress()
        ss._all_cycle_gaps = [100, 200, 300, 400, 500]
        # gap_bars=10 < median(300)*0.5=150 -> 1.0
        result = ss._compute_M(gap_bars=10)
        assert result == 1.0

    def test_no_history_returns_zero(self):
        ss = StructuralStress()
        result = ss._compute_M(gap_bars=5)
        assert result == 0.0

    def test_negative_gap_returns_zero(self):
        ss = StructuralStress()
        ss._all_cycle_gaps = [100, 200, 300]
        result = ss._compute_M(gap_bars=-1)
        assert result == 0.0


class TestRecordCycle:
    def test_shallow_tp_low_stress(self):
        ss = StructuralStress()
        session = dict(
            levels=2, bars=50, pnl=100.0, reason='tp',
            max_levels=12, multiplier=1.414, expected_tp=100.0,
            level_timestamps=[0, 30], gap_bars=200,
        )
        result = ss.record_cycle(session)
        assert result['total'] < 1.0
        assert result['X'] == 0.0

    def test_deep_bust_high_stress(self):
        ss = StructuralStress()
        # Seed some history so U/F/M can fire
        for _ in range(5):
            ss._all_bars.append(50)
            ss._all_level_gaps.extend([20.0, 20.0])
            ss._all_cycle_gaps.append(200)
        session = dict(
            levels=12, bars=500, pnl=-1000.0, reason='bust',
            max_levels=12, multiplier=2.0, expected_tp=100.0,
            level_timestamps=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
            gap_bars=5,
        )
        result = ss.record_cycle(session)
        assert result['total'] > 2.0
        assert result['V'] == 1.0

    def test_rt_accumulates(self):
        ss = StructuralStress()
        session = dict(
            levels=6, bars=100, pnl=80.0, reason='tp',
            max_levels=12, multiplier=1.414, expected_tp=100.0,
            level_timestamps=[0, 50, 100, 150, 200, 250], gap_bars=300,
        )
        ss.record_cycle(session)
        r1 = ss.r_t
        ss.record_cycle(session)
        r2 = ss.r_t
        assert r2 > r1


class TestDerivedSignals:
    def _make_ss_with_cycles(self, n=25):
        ss = StructuralStress()
        for i in range(n):
            session = dict(
                levels=3 + (i % 5), bars=50 + i * 10, pnl=80.0, reason='tp',
                max_levels=12, multiplier=1.414, expected_tp=100.0,
                level_timestamps=[0, 20, 40], gap_bars=100 + i,
            )
            ss.record_cycle(session)
        return ss

    def test_normalised_rt_in_range(self):
        ss = self._make_ss_with_cycles(25)
        assert 0.0 <= ss.normalised_rt <= 1.0

    def test_recent_stress_rate_non_negative(self):
        ss = self._make_ss_with_cycles(15)
        assert ss.recent_stress_rate >= 0.0

    def test_stress_velocity_is_float(self):
        ss = self._make_ss_with_cycles(25)
        assert isinstance(ss.stress_velocity, float)

    def test_inter_cycle_gap_ratio_non_negative(self):
        ss = self._make_ss_with_cycles(10)
        assert ss.inter_cycle_gap_ratio(50) >= 0.0


class TestObserverEnrichment:
    def _mock_strategy(self):
        class S:
            balance = 10000.0
            hp = {'max_levels': 12, 'sizing_factor': 1.4142, 'tp_value': 1.0}
            vars = {'sessions': [{'levels': 2, 'pnl': 50.0, 'reason': 'tp_hit', 'bars': 100}]}
            candles = None
        return S()

    def test_record_level_timestamp(self):
        from pipelines._shared.ARIA.observer import Observer
        obs = Observer()
        obs.on_cycle_open(self._mock_strategy(), {'danger': 0.3, 'regime_id': 0}, start_bar=500)
        obs.record_level_timestamp(500)
        obs.record_level_timestamp(560)
        enriched = obs.on_cycle_end(self._mock_strategy(), {'danger': 0.4})
        assert enriched.get('level_timestamps') == [500, 560]
        assert enriched.get('start_bar') == 500

    def test_start_bar_in_enriched(self):
        from pipelines._shared.ARIA.observer import Observer
        obs = Observer()
        obs.on_cycle_open(self._mock_strategy(), {'danger': 0.3}, start_bar=100)
        enriched = obs.on_cycle_end(self._mock_strategy(), {'danger': 0.4})
        assert 'start_bar' in enriched
        assert 'level_timestamps' in enriched
