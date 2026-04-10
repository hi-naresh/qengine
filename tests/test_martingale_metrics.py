import math
import numpy as np
import pytest

from qengine.services.metrics import _calculate_martingale_metrics


def _make_session(pnl, legs, max_level, exit_reason='tp', holding_seconds=300,
                  leg_levels=None, leg_holdings=None):
    if leg_levels is None:
        leg_levels = list(range(max_level + 1))[:legs]
        if len(leg_levels) < legs:
            leg_levels += [max_level] * (legs - len(leg_levels))
    if leg_holdings is None:
        leg_holdings = [holding_seconds / max(legs, 1)] * legs
    return {
        'pnl': pnl, 'legs': legs, 'max_level': max_level,
        'exit_reason': exit_reason, 'holding_seconds': holding_seconds,
        'leg_levels': leg_levels, 'leg_holdings': leg_holdings,
    }


class TestSessionProfitFactor:
    def test_basic(self):
        sessions = [
            _make_session(100, 1, 0),
            _make_session(50, 1, 0),
            _make_session(-30, 2, 1, exit_reason='bust'),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        # sum(wins) = 150, abs(sum(losses)) = 30
        assert result['session_profit_factor'] == pytest.approx(5.0)

    def test_no_losses(self):
        sessions = [_make_session(100, 1, 0)]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['session_profit_factor'] == float('inf')

    def test_no_wins(self):
        sessions = [_make_session(-50, 2, 1, exit_reason='bust')]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['session_profit_factor'] == 0.0


class TestMedianSessionPnl:
    def test_odd_count(self):
        sessions = [
            _make_session(100, 1, 0),
            _make_session(50, 1, 0),
            _make_session(-30, 2, 1, exit_reason='bust'),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['median_session_pnl'] == pytest.approx(50.0)

    def test_even_count(self):
        sessions = [
            _make_session(100, 1, 0),
            _make_session(50, 1, 0),
            _make_session(20, 1, 0),
            _make_session(-30, 2, 1, exit_reason='bust'),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['median_session_pnl'] == pytest.approx(35.0)


class TestBustRate:
    def test_basic(self):
        sessions = [
            _make_session(100, 1, 0),
            _make_session(50, 1, 0),
            _make_session(-200, 5, 4, exit_reason='bust'),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['bust_rate'] == pytest.approx(1 / 3)
        assert result['bust_count'] == 1

    def test_max_levels_counts_as_bust(self):
        sessions = [
            _make_session(100, 1, 0),
            _make_session(-200, 5, 4, exit_reason='max_levels'),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['bust_count'] == 1

    def test_margin_call_counts_as_bust(self):
        sessions = [
            _make_session(-500, 3, 2, exit_reason='margin_call'),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['bust_count'] == 1

    def test_liquidation_counts_as_bust(self):
        sessions = [
            _make_session(-500, 3, 2, exit_reason='liquidation'),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['bust_count'] == 1

    def test_no_busts(self):
        sessions = [_make_session(100, 1, 0), _make_session(50, 1, 0)]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['bust_rate'] == 0.0
        assert result['bust_count'] == 0


class TestWinsToRecover:
    def test_basic(self):
        sessions = [
            _make_session(100, 1, 0),
            _make_session(50, 1, 0),
            _make_session(-300, 5, 4, exit_reason='bust'),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        # avg_bust_loss = -300, avg_session_win = 75
        assert result['wins_to_recover'] == pytest.approx(4.0)

    def test_no_busts(self):
        sessions = [_make_session(100, 1, 0)]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['wins_to_recover'] == 0.0


class TestGeometricGrowthRate:
    def test_positive(self):
        sessions = [
            _make_session(100, 1, 0),   # ln(1 + 100/10000) = ln(1.01)
            _make_session(200, 1, 0),   # ln(1 + 200/10100) = ln(1.0198...)
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        g1 = math.log(1 + 100 / 10000)
        g2 = math.log(1 + 200 / 10100)
        expected = (g1 + g2) / 2
        assert result['geometric_growth_rate'] == pytest.approx(expected, rel=1e-6)

    def test_with_bust(self):
        sessions = [
            _make_session(100, 1, 0),     # balance 10000 -> 10100
            _make_session(-500, 5, 4, exit_reason='bust'),  # balance 10100 -> 9600
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        g1 = math.log(1 + 100 / 10000)
        g2 = math.log(1 + (-500) / 10100)
        expected = (g1 + g2) / 2
        assert result['geometric_growth_rate'] == pytest.approx(expected, rel=1e-6)


class TestSurvival:
    def test_with_busts(self):
        sessions = [
            _make_session(100, 1, 0),
            _make_session(-200, 5, 4, exit_reason='bust'),
            _make_session(50, 1, 0),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        bust_rate = 1 / 3
        assert result['survival_100'] == pytest.approx((1 - bust_rate) ** 100, rel=1e-6)
        assert result['survival_500'] == pytest.approx((1 - bust_rate) ** 500, rel=1e-6)
        expected_hl = math.log(0.5) / math.log(1 - bust_rate)
        assert result['survival_half_life'] == pytest.approx(expected_hl, rel=1e-6)

    def test_no_busts_infinite_half_life(self):
        sessions = [_make_session(100, 1, 0), _make_session(50, 1, 0)]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['survival_100'] == 1.0
        assert result['survival_500'] == 1.0
        assert result['survival_half_life'] == float('inf')


class TestBustLossStats:
    def test_avg_bust_loss(self):
        sessions = [
            _make_session(100, 1, 0),
            _make_session(-200, 5, 4, exit_reason='bust'),
            _make_session(-400, 5, 4, exit_reason='bust'),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['avg_bust_loss'] == pytest.approx(-300.0)

    def test_bust_severity_std(self):
        sessions = [
            _make_session(100, 1, 0),
            _make_session(-200, 5, 4, exit_reason='bust'),
            _make_session(-400, 5, 4, exit_reason='bust'),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        expected_std = np.std([-200, -400], ddof=1)
        assert result['bust_severity_std'] == pytest.approx(expected_std, rel=1e-6)

    def test_single_bust_std_zero(self):
        sessions = [
            _make_session(100, 1, 0),
            _make_session(-200, 5, 4, exit_reason='bust'),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['bust_severity_std'] == 0.0

    def test_no_busts(self):
        sessions = [_make_session(100, 1, 0)]
        result = _calculate_martingale_metrics(sessions, 10000)
        assert result['avg_bust_loss'] == 0.0
        assert result['bust_severity_std'] == 0.0


class TestLevelTransitions:
    def test_three_sessions(self):
        """
        Session 1: L0 win (max_level=0, pnl>0) -> L0 entry, L0 win
        Session 2: L0->L1->L2 win (max_level=2, pnl>0) -> L0 entry+escalate, L1 entry+escalate, L2 entry+win
        Session 3: L0->L1 bust (max_level=1, pnl<0) -> L0 entry+escalate, L1 entry (no win, no escalate)
        """
        sessions = [
            _make_session(100, 1, 0),
            _make_session(50, 3, 2, leg_levels=[0, 1, 2]),
            _make_session(-200, 2, 1, exit_reason='bust', leg_levels=[0, 1]),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        transitions = {t['level']: t for t in result['level_transitions']}

        # L0: 3 entries, 1 win (session 1), 2 escalations (sessions 2 & 3)
        assert transitions[0]['entries'] == 3
        assert transitions[0]['wins'] == 1
        assert transitions[0]['escalations'] == 2
        assert transitions[0]['p_win'] == pytest.approx(1 / 3)
        assert transitions[0]['p_escalate'] == pytest.approx(2 / 3)

        # L1: 2 entries (sessions 2 & 3), 0 wins at L1 terminal, 1 escalation (session 2)
        assert transitions[1]['entries'] == 2
        assert transitions[1]['wins'] == 0
        assert transitions[1]['escalations'] == 1

        # L2: 1 entry (session 2), 1 win (pnl > 0), 0 escalations
        assert transitions[2]['entries'] == 1
        assert transitions[2]['wins'] == 1
        assert transitions[2]['escalations'] == 0


class TestEvByDepth:
    def test_basic(self):
        sessions = [
            _make_session(100, 1, 0),
            _make_session(50, 1, 0),
            _make_session(-200, 3, 2, exit_reason='bust'),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        ev = result['ev_by_depth']

        assert ev[0]['count'] == 2
        assert ev[0]['total_pnl'] == pytest.approx(150.0)
        assert ev[0]['avg_pnl'] == pytest.approx(75.0)
        assert ev[0]['wins'] == 2
        assert ev[0]['win_rate'] == pytest.approx(1.0)

        assert ev[2]['count'] == 1
        assert ev[2]['total_pnl'] == pytest.approx(-200.0)
        assert ev[2]['avg_pnl'] == pytest.approx(-200.0)
        assert ev[2]['wins'] == 0
        assert ev[2]['win_rate'] == pytest.approx(0.0)


class TestTimeAtDepth:
    def test_basic(self):
        sessions = [
            _make_session(100, 1, 0, holding_seconds=300, leg_levels=[0], leg_holdings=[300]),
            _make_session(50, 2, 1, holding_seconds=600, leg_levels=[0, 1], leg_holdings=[200, 400]),
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        tad = result['time_at_depth']
        # L0: 300 + 200 = 500
        assert tad[0] == pytest.approx(500.0)
        # L1: 400
        assert tad[1] == pytest.approx(400.0)


class TestL0WinRate:
    def test_basic(self):
        sessions = [
            _make_session(100, 1, 0),   # L0 win
            _make_session(50, 1, 0),    # L0 win
            _make_session(30, 3, 2),    # NOT L0 win (escalated)
            _make_session(-200, 5, 4, exit_reason='bust'),  # bust
        ]
        result = _calculate_martingale_metrics(sessions, 10000)
        # 2 L0 wins out of 4 sessions
        assert result['l0_win_rate'] == pytest.approx(0.5)


class TestCostDragPct:
    def test_basic(self):
        sessions = [_make_session(100, 1, 0)]
        result = _calculate_martingale_metrics(
            sessions, 10000,
            total_fees=5.0, total_spread=10.0, total_swap=5.0,
            gross_profit=500.0,
        )
        # (5 + 10 + 5) / 500 * 100 = 4.0
        assert result['cost_drag_pct'] == pytest.approx(4.0)

    def test_zero_gross_profit(self):
        sessions = [_make_session(-100, 2, 1, exit_reason='bust')]
        result = _calculate_martingale_metrics(
            sessions, 10000,
            total_fees=5.0, gross_profit=0.0,
        )
        assert result['cost_drag_pct'] == 0.0


class TestEmptySessions:
    def test_empty_returns_empty(self):
        result = _calculate_martingale_metrics([], 10000)
        assert result == {}
