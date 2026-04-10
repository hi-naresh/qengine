# Martingale-Native Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace generic trade-level backtest metrics with a martingale-native framework that uses sessions as the atomic unit, adds survival/ruin analysis and structural diagnostics, and hides misleading normal-distribution metrics.

**Architecture:** Backend detects martingale mode via `has_sessions` flag (already exists). When true, `_calculate_martingale_metrics()` computes session-centric metrics and the `trades()` function skips Sharpe/Sortino/etc. Frontend conditionally renders 4 new metric groups instead of the current 5 when `metrics.is_martingale` is true.

**Tech Stack:** Python (numpy), Vue 3 (Composition API), Markdown guides

---

## File Structure

| File | Role | Action |
|------|------|--------|
| `qengine/services/metrics.py` | All metric computation | Modify: add `_calculate_martingale_metrics()`, modify `trades()` to branch |
| `tests/test_martingale_metrics.py` | Unit tests for new metrics | Create |
| `frontend/src/views/Backtest.vue` | Results display | Modify: conditional metric groups, new key arrays, collapsible raw trades |
| `frontend/src/guides/martingale.md` | Tooltip descriptions for new metrics | Create |
| `frontend/src/guides/index.js` | Guide registry | Modify: import martingale guide |

---

### Task 1: Backend — `_calculate_martingale_metrics()` function

**Files:**
- Modify: `qengine/services/metrics.py:364-467` (after `_calculate_hedge_session_metrics`)
- Create: `tests/test_martingale_metrics.py`

This task adds the new function that computes all martingale-specific metrics. It builds on the session data already parsed by `_calculate_hedge_session_metrics` — we refactor to share the parsed session structures.

- [ ] **Step 1: Write failing tests for the new martingale metrics**

Create `tests/test_martingale_metrics.py`:

```python
import math
import numpy as np
import pytest
from qengine.services.metrics import _calculate_martingale_metrics


def _make_session(pnl, legs, max_level, exit_reason='tp', holding_seconds=300):
    """Build a session dict matching the shape produced by _parse_sessions()."""
    return {
        'pnl': pnl,
        'legs': legs,
        'max_level': max_level,
        'exit_reason': exit_reason,
        'holding_seconds': holding_seconds,
        'leg_levels': list(range(max_level + 1))[:legs],
        'leg_holdings': [holding_seconds / legs] * legs,
    }


class TestSessionPerformance:
    def test_session_profit_factor(self):
        sessions = [
            _make_session(10, 1, 0),
            _make_session(10, 1, 0),
            _make_session(-100, 6, 5, 'bust'),
        ]
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        # PF = 20 / 100 = 0.2
        assert result['session_profit_factor'] == pytest.approx(0.2, abs=0.01)

    def test_median_session_pnl(self):
        sessions = [
            _make_session(10, 1, 0),
            _make_session(12, 1, 0),
            _make_session(-500, 8, 7, 'bust'),
        ]
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        assert result['median_session_pnl'] == 10.0  # median of [10, 12, -500]


class TestSurvivalAndRuin:
    def test_bust_rate(self):
        sessions = [_make_session(10, 1, 0)] * 99 + [_make_session(-500, 8, 7, 'bust')]
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        assert result['bust_rate'] == pytest.approx(0.01, abs=0.001)

    def test_wins_to_recover(self):
        sessions = [
            _make_session(10, 1, 0),
            _make_session(10, 1, 0),
            _make_session(-200, 6, 5, 'bust'),
        ]
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        # WTR = abs(-200) / avg_win(10) = 20
        assert result['wins_to_recover'] == pytest.approx(20.0, abs=0.1)

    def test_geometric_growth_rate_positive(self):
        # 10 wins of $10 on $10k balance each
        sessions = [_make_session(10, 1, 0)] * 10
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        # g = mean(ln(1 + 10/balance_i)) — all positive, g > 0
        assert result['geometric_growth_rate'] > 0

    def test_geometric_growth_rate_negative_with_bust(self):
        # 2 wins of $10, then bust of -$5000 on a $10k account
        sessions = [
            _make_session(10, 1, 0),
            _make_session(10, 1, 0),
            _make_session(-5000, 8, 7, 'bust'),
        ]
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        # ln(1 + (-5000/10020)) is hugely negative, dominates
        assert result['geometric_growth_rate'] < 0

    def test_survival_probabilities(self):
        # 1% bust rate
        sessions = [_make_session(10, 1, 0)] * 99 + [_make_session(-500, 8, 7, 'bust')]
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        bust_rate = result['bust_rate']
        assert result['survival_100'] == pytest.approx((1 - bust_rate) ** 100, abs=0.01)
        assert result['survival_500'] == pytest.approx((1 - bust_rate) ** 500, abs=0.01)

    def test_survival_half_life(self):
        sessions = [_make_session(10, 1, 0)] * 99 + [_make_session(-500, 8, 7, 'bust')]
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        bust_rate = result['bust_rate']
        expected = math.log(0.5) / math.log(1 - bust_rate)
        assert result['survival_half_life'] == pytest.approx(expected, rel=0.01)

    def test_survival_half_life_no_busts(self):
        sessions = [_make_session(10, 1, 0)] * 50
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        assert result['survival_half_life'] == float('inf')

    def test_avg_bust_loss_and_severity(self):
        sessions = [
            _make_session(10, 1, 0),
            _make_session(-200, 6, 5, 'bust'),
            _make_session(-300, 8, 7, 'bust'),
        ]
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        assert result['avg_bust_loss'] == pytest.approx(-250.0, abs=0.1)
        assert result['bust_severity_std'] > 0  # not zero since -200 != -300


class TestStructuralDiagnostics:
    def test_level_transitions(self):
        # 3 sessions: one wins at L0, one escalates L0->L1->win, one escalates L0->L1->L2->bust
        sessions = [
            _make_session(10, 1, 0, 'tp', leg_levels=[0], leg_holdings=[300]),
            _make_session(15, 2, 1, 'tp', leg_levels=[0, 1], leg_holdings=[150, 150]),
            _make_session(-200, 3, 2, 'bust', leg_levels=[0, 1, 2], leg_holdings=[100, 100, 100]),
        ]
        # Override the default _make_session leg_levels
        sessions[0]['leg_levels'] = [0]
        sessions[1]['leg_levels'] = [0, 1]
        sessions[2]['leg_levels'] = [0, 1, 2]
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        transitions = result['level_transitions']
        # L0: 3 sessions entered, 1 won at L0, 2 escalated => P(win@L0)=1/3, P(esc)=2/3
        assert transitions[0]['entries'] == 3
        assert transitions[0]['wins'] == 1
        assert transitions[0]['escalations'] == 2
        # L1: 2 entered, 1 won, 1 escalated
        assert transitions[1]['entries'] == 2
        assert transitions[1]['wins'] == 1
        assert transitions[1]['escalations'] == 1

    def test_ev_by_depth(self):
        sessions = [
            _make_session(10, 1, 0),   # max_depth 0
            _make_session(15, 2, 1),   # max_depth 1
            _make_session(-200, 3, 2, 'bust'),  # max_depth 2
        ]
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        ev_depth = result['ev_by_depth']
        # depth 0: 1 session, total pnl 10
        assert ev_depth[0]['count'] == 1
        assert ev_depth[0]['total_pnl'] == pytest.approx(10.0)
        # depth 2: 1 session, total pnl -200
        assert ev_depth[2]['count'] == 1
        assert ev_depth[2]['total_pnl'] == pytest.approx(-200.0)

    def test_time_at_depth(self):
        sessions = [
            _make_session(10, 1, 0, holding_seconds=300),
            _make_session(-200, 3, 2, 'bust', holding_seconds=900),
        ]
        sessions[0]['leg_levels'] = [0]
        sessions[0]['leg_holdings'] = [300.0]
        sessions[1]['leg_levels'] = [0, 1, 2]
        sessions[1]['leg_holdings'] = [300.0, 300.0, 300.0]
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        tad = result['time_at_depth']
        # L0: 300 (session1) + 300 (session2 leg0) = 600
        assert tad[0] == pytest.approx(600.0)
        assert tad[1] == pytest.approx(300.0)
        assert tad[2] == pytest.approx(300.0)

    def test_l0_win_rate(self):
        sessions = [
            _make_session(10, 1, 0),  # won at L0
            _make_session(10, 1, 0),  # won at L0
            _make_session(15, 2, 1),  # won at L1 (not L0)
            _make_session(-200, 3, 2, 'bust'),
        ]
        result = _calculate_martingale_metrics(sessions, starting_balance=10000)
        # 2 out of 4 sessions won at L0
        assert result['l0_win_rate'] == pytest.approx(0.5, abs=0.01)


class TestCapitalAndCosts:
    def test_cost_drag_pct(self):
        result = _calculate_martingale_metrics(
            [_make_session(10, 1, 0)] * 10,
            starting_balance=10000,
            total_fees=5.0, total_spread=3.0, total_swap=2.0,
            gross_profit=100.0,
        )
        # drag = (5+3+2)/100 * 100 = 10%
        assert result['cost_drag_pct'] == pytest.approx(10.0, abs=0.1)


def _make_session(pnl, legs, max_level, exit_reason='tp', holding_seconds=300,
                  leg_levels=None, leg_holdings=None):
    """Build a session dict matching the shape produced by _parse_sessions()."""
    if leg_levels is None:
        leg_levels = list(range(max_level + 1))[:legs]
        if len(leg_levels) < legs:
            leg_levels += [max_level] * (legs - len(leg_levels))
    if leg_holdings is None:
        leg_holdings = [holding_seconds / max(legs, 1)] * legs
    return {
        'pnl': pnl,
        'legs': legs,
        'max_level': max_level,
        'exit_reason': exit_reason,
        'holding_seconds': holding_seconds,
        'leg_levels': leg_levels,
        'leg_holdings': leg_holdings,
    }
```

Note: the duplicate `_make_session` at the bottom is the real one — remove the stub at the top. The final file should have only the bottom version at module scope, used by all test classes.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/test_martingale_metrics.py -v 2>&1 | head -40
```

Expected: ImportError — `_calculate_martingale_metrics` does not exist yet.

- [ ] **Step 3: Implement `_parse_sessions()` helper**

This refactors the session-parsing logic out of `_calculate_hedge_session_metrics` into a reusable function. Both the old function and the new martingale metrics will call it.

Add to `qengine/services/metrics.py` **before** `_calculate_hedge_session_metrics` (around line 364):

```python
def _parse_sessions(trades_list: List[ClosedTrade]) -> list:
    """
    Parse trades into session-level structures.
    Returns a list of session dicts:
      { pnl, legs, max_level, exit_reason, holding_seconds, leg_levels, leg_holdings }
    """
    sessions_map = {}      # session_num -> { pnl, legs, max_level, exit_reason, leg_levels, leg_holdings }
    trade_order = {}       # session_num -> list of trades (to preserve ordering)

    for t in trades_list:
        meta = getattr(t, 'meta', {})
        session_num = meta.get('session')
        if session_num is None:
            session_num = f'standalone-{id(t)}'

        if session_num not in sessions_map:
            sessions_map[session_num] = {
                'pnl': 0.0, 'legs': 0, 'max_level': 0,
                'exit_reason': None,
                'holding_seconds': 0.0,
                'leg_levels': [],
                'leg_holdings': [],
            }
            trade_order[session_num] = []

        s = sessions_map[session_num]
        s['pnl'] += t.pnl
        s['legs'] += 1

        level = meta.get('level', 0)
        if isinstance(level, (int, float)):
            level = int(level)
            if level > s['max_level']:
                s['max_level'] = level
        else:
            level = 0
        s['leg_levels'].append(level)

        hp = t.holding_period
        hold_sec = hp if hp is not None else 0.0
        s['leg_holdings'].append(hold_sec)
        s['holding_seconds'] += hold_sec

        reason = meta.get('session_exit_reason', meta.get('exit_reason'))
        if reason:
            s['exit_reason'] = reason

        trade_order[session_num].append(t)

    # Return in insertion order (Python 3.7+ dict guarantees this)
    return list(sessions_map.values())
```

- [ ] **Step 4: Refactor `_calculate_hedge_session_metrics` to use `_parse_sessions`**

Replace the body of `_calculate_hedge_session_metrics` to call `_parse_sessions` and derive values from that, keeping the same return dict shape:

```python
def _calculate_hedge_session_metrics(trades_list: List[ClosedTrade]) -> dict:
    """Calculate hedge session-level metrics from trade metadata."""
    sessions = _parse_sessions(trades_list)
    if not sessions:
        return {}

    total_sessions = len(sessions)
    session_pnls = [s['pnl'] for s in sessions]
    session_legs = [s['legs'] for s in sessions]

    winning_sessions = [p for p in session_pnls if p > 0]
    losing_sessions = [p for p in session_pnls if p <= 0]

    session_win_rate = len(winning_sessions) / total_sessions if total_sessions > 0 else 0
    avg_session_win = np.mean(winning_sessions) if winning_sessions else 0.0
    avg_session_loss = np.mean(losing_sessions) if losing_sessions else 0.0
    avg_legs = np.mean(session_legs)
    max_legs = max(session_legs)
    sessions_1_leg = sum(1 for l in session_legs if l == 1)

    ev_per_session = np.mean(session_pnls)

    session_pnl_arr = np.array(session_pnls)
    wins = (session_pnl_arr > 0).astype(int)
    max_consec_wins = _max_consecutive(wins, 1)
    max_consec_losses = _max_consecutive(wins, 0)

    bust_outcomes = {'bust', 'max_levels', 'margin_call', 'liquidation'}
    bust_pnls = [s['pnl'] for s in sessions if s.get('exit_reason') in bust_outcomes]
    total_busts = len(bust_pnls)
    worst_bust_pnl = round(min(bust_pnls), 2) if bust_pnls else 0.0
    total_losing_sessions = len(losing_sessions)

    depth_stats = {}
    for s in sessions:
        depth = s['max_level']
        if depth not in depth_stats:
            depth_stats[depth] = {'count': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0}
        depth_stats[depth]['count'] += 1
        depth_stats[depth]['pnl'] += s['pnl']
        if s['pnl'] > 0:
            depth_stats[depth]['wins'] += 1
        else:
            depth_stats[depth]['losses'] += 1

    depth_breakdown = []
    for depth in sorted(depth_stats.keys()):
        d = depth_stats[depth]
        depth_breakdown.append({
            'depth': depth, 'count': d['count'],
            'wins': d['wins'], 'losses': d['losses'],
            'pnl': round(d['pnl'], 2),
        })

    return {
        'total_sessions': total_sessions,
        'session_win_rate': round(session_win_rate, 4),
        'avg_session_win': round(avg_session_win, 2),
        'avg_session_loss': round(avg_session_loss, 2),
        'ev_per_session': round(ev_per_session, 2),
        'avg_legs_per_session': round(avg_legs, 2),
        'max_legs_in_session': max_legs,
        'sessions_with_1_leg': sessions_1_leg,
        'max_consecutive_session_wins': max_consec_wins,
        'max_consecutive_session_losses': max_consec_losses,
        'total_busts': total_busts,
        'worst_bust_pnl': worst_bust_pnl,
        'total_losing_sessions': total_losing_sessions,
        'depth_breakdown': depth_breakdown,
    }
```

- [ ] **Step 5: Run existing tests to verify refactor didn't break anything**

```bash
cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/test_metrics.py -v 2>&1 | tail -20
```

Expected: All existing tests still pass.

- [ ] **Step 6: Commit refactor**

```bash
git add qengine/services/metrics.py tests/test_martingale_metrics.py
git commit -m "refactor: extract _parse_sessions() from hedge metrics for reuse"
```

- [ ] **Step 7: Implement `_calculate_martingale_metrics()`**

Add this function to `qengine/services/metrics.py` after `_calculate_hedge_session_metrics`:

```python
def _calculate_martingale_metrics(sessions: list, starting_balance: float,
                                  total_fees: float = 0.0, total_spread: float = 0.0,
                                  total_swap: float = 0.0, gross_profit: float = 0.0) -> dict:
    """
    Compute martingale-native metrics from parsed session data.

    Args:
        sessions: list of session dicts from _parse_sessions() or test helpers.
                  Each has: pnl, legs, max_level, exit_reason, holding_seconds,
                  leg_levels, leg_holdings.
        starting_balance: account starting balance.
        total_fees, total_spread, total_swap: cost components.
        gross_profit: sum of winning trade PnLs (for cost_drag_pct).
    """
    if not sessions:
        return {}

    total = len(sessions)
    session_pnls = [s['pnl'] for s in sessions]
    winning_pnls = [p for p in session_pnls if p > 0]
    losing_pnls = [p for p in session_pnls if p <= 0]

    bust_outcomes = {'bust', 'max_levels', 'margin_call', 'liquidation'}
    bust_pnls = [s['pnl'] for s in sessions if s.get('exit_reason') in bust_outcomes]

    # ── Session Performance ──
    sum_wins = sum(winning_pnls) if winning_pnls else 0.0
    sum_losses = abs(sum(losing_pnls)) if losing_pnls else 0.0
    session_profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else float('inf')
    median_session_pnl = float(np.median(session_pnls))

    # ── Survival & Ruin ──
    bust_count = len(bust_pnls)
    bust_rate = bust_count / total if total > 0 else 0.0
    avg_session_win = np.mean(winning_pnls) if winning_pnls else 0.0
    avg_bust_loss = np.mean(bust_pnls) if bust_pnls else 0.0

    if bust_pnls and avg_session_win > 0:
        wins_to_recover = abs(avg_bust_loss) / avg_session_win
    elif bust_pnls:
        wins_to_recover = float('inf')
    else:
        wins_to_recover = 0.0

    # Geometric growth rate: g = mean(ln(1 + r_i)) where r_i = session_pnl / balance_before
    balance = starting_balance
    log_returns = []
    for s in sessions:
        if balance > 0:
            r = s['pnl'] / balance
            # Clip to prevent log(0) or log(negative)
            log_returns.append(math.log(max(1 + r, 1e-10)))
        balance += s['pnl']
    geometric_growth_rate = np.mean(log_returns) if log_returns else 0.0

    # Survival probabilities
    if bust_rate > 0 and bust_rate < 1:
        survival_100 = (1 - bust_rate) ** 100
        survival_500 = (1 - bust_rate) ** 500
        survival_half_life = math.log(0.5) / math.log(1 - bust_rate)
    elif bust_rate == 0:
        survival_100 = 1.0
        survival_500 = 1.0
        survival_half_life = float('inf')
    else:
        survival_100 = 0.0
        survival_500 = 0.0
        survival_half_life = 0.0

    bust_severity_std = float(np.std(bust_pnls, ddof=1)) if len(bust_pnls) >= 2 else 0.0

    # ── Structural Diagnostics ──

    # Level transition matrix
    max_level_seen = max((s['max_level'] for s in sessions), default=0)
    transitions = {}
    for lvl in range(max_level_seen + 1):
        transitions[lvl] = {'entries': 0, 'wins': 0, 'escalations': 0}

    for s in sessions:
        levels_in_session = s.get('leg_levels', [])
        max_lvl = s['max_level']
        seen_levels = set()
        for lvl in levels_in_session:
            if lvl not in seen_levels:
                seen_levels.add(lvl)
                if lvl not in transitions:
                    transitions[lvl] = {'entries': 0, 'wins': 0, 'escalations': 0}
                transitions[lvl]['entries'] += 1
        # The session's max_level either won (if session won or is the highest) or escalated
        # For each level < max_lvl that was entered: it escalated
        # For max_lvl: it either won or busted (count as win if pnl > 0)
        for lvl in seen_levels:
            if lvl < max_lvl:
                transitions[lvl]['escalations'] += 1
            else:
                # Terminal level — won or lost here
                if s['pnl'] > 0:
                    transitions[lvl]['wins'] += 1
                # If lost (bust) at this level, it's neither a "win" nor "escalation"
                # We leave it as entry-only, which means: entries - wins - escalations = losses

    level_transitions = []
    for lvl in sorted(transitions.keys()):
        t = transitions[lvl]
        level_transitions.append({
            'level': lvl,
            'entries': t['entries'],
            'wins': t['wins'],
            'escalations': t['escalations'],
            'p_win': round(t['wins'] / t['entries'], 4) if t['entries'] > 0 else 0.0,
            'p_escalate': round(t['escalations'] / t['entries'], 4) if t['entries'] > 0 else 0.0,
        })

    # EV by depth (sessions grouped by max_level)
    ev_by_depth_map = {}
    for s in sessions:
        d = s['max_level']
        if d not in ev_by_depth_map:
            ev_by_depth_map[d] = {'count': 0, 'total_pnl': 0.0, 'wins': 0}
        ev_by_depth_map[d]['count'] += 1
        ev_by_depth_map[d]['total_pnl'] += s['pnl']
        if s['pnl'] > 0:
            ev_by_depth_map[d]['wins'] += 1
    ev_by_depth = {}
    for d in sorted(ev_by_depth_map.keys()):
        v = ev_by_depth_map[d]
        ev_by_depth[d] = {
            'count': v['count'],
            'total_pnl': round(v['total_pnl'], 2),
            'avg_pnl': round(v['total_pnl'] / v['count'], 2),
            'wins': v['wins'],
            'win_rate': round(v['wins'] / v['count'], 4) if v['count'] > 0 else 0.0,
        }

    # Time at depth (aggregate holding time per level across all sessions)
    time_at_depth = {}
    for s in sessions:
        for lvl, hold in zip(s.get('leg_levels', []), s.get('leg_holdings', [])):
            time_at_depth[lvl] = time_at_depth.get(lvl, 0.0) + hold

    # L0 win rate
    l0_wins = sum(1 for s in sessions if s['max_level'] == 0 and s['pnl'] > 0)
    l0_win_rate = l0_wins / total if total > 0 else 0.0

    # ── Capital & Costs ──
    total_costs = total_fees + total_spread + total_swap
    cost_drag_pct = (total_costs / gross_profit * 100) if gross_profit > 0 else 0.0

    return {
        # Session Performance
        'session_profit_factor': round(session_profit_factor, 2),
        'median_session_pnl': round(median_session_pnl, 2),
        # Survival & Ruin
        'bust_rate': round(bust_rate, 4),
        'bust_count': bust_count,
        'wins_to_recover': round(wins_to_recover, 1),
        'geometric_growth_rate': round(geometric_growth_rate, 6),
        'survival_100': round(survival_100, 4),
        'survival_500': round(survival_500, 4),
        'survival_half_life': round(survival_half_life, 1) if not math.isinf(survival_half_life) else float('inf'),
        'avg_bust_loss': round(avg_bust_loss, 2),
        'bust_severity_std': round(bust_severity_std, 2),
        # Structural Diagnostics
        'level_transitions': level_transitions,
        'ev_by_depth': ev_by_depth,
        'time_at_depth': {k: round(v, 1) for k, v in sorted(time_at_depth.items())},
        'l0_win_rate': round(l0_win_rate, 4),
        # Capital & Costs
        'cost_drag_pct': round(cost_drag_pct, 1),
    }
```

Also add `import math` at the top of `metrics.py` if not already present.

- [ ] **Step 8: Run the martingale tests**

```bash
cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/test_martingale_metrics.py -v 2>&1 | tail -30
```

Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
git add qengine/services/metrics.py tests/test_martingale_metrics.py
git commit -m "feat: add _calculate_martingale_metrics() with survival, structural, capital metrics"
```

---

### Task 2: Backend — Wire martingale metrics into `trades()` response

**Files:**
- Modify: `qengine/services/metrics.py:483-686` (the `trades()` function)

This task modifies the main `trades()` function to:
1. Call `_calculate_martingale_metrics()` when sessions are detected
2. Skip Sharpe/Sortino/Calmar/Omega/Serenity/Kelly/VaR/CVaR computation in martingale mode
3. Add `is_martingale: True` flag
4. Nest trade-level stats under `raw_trade_stats`

- [ ] **Step 1: Modify `trades()` to branch on martingale mode**

In the `trades()` function, after line 627 (`hedge_metrics = ...`), replace the return statement. The full modified section from `has_sessions` detection through the return:

Find the block starting at line 625:
```python
    # Hedge session metrics (only if trades have session metadata)
    has_sessions = any(hasattr(t, 'meta') and getattr(t, 'meta', {}).get('session') is not None for t in trades_list)
    hedge_metrics = _calculate_hedge_session_metrics(trades_list) if has_sessions else {}
```

Replace everything from line 625 through the end of the return dict (line 686) with:

```python
    # Hedge session metrics (only if trades have session metadata)
    has_sessions = any(hasattr(t, 'meta') and getattr(t, 'meta', {}).get('session') is not None for t in trades_list)
    hedge_metrics = _calculate_hedge_session_metrics(trades_list) if has_sessions else {}

    # ── Martingale mode: skip misleading metrics, add session-native ones ──
    if has_sessions:
        parsed_sessions = _parse_sessions(trades_list)
        martingale = _calculate_martingale_metrics(
            parsed_sessions,
            starting_balance=starting_balance,
            total_fees=safe_convert(fee),
            total_spread=safe_convert(forex_metrics.get('total_spread_cost', 0)),
            total_swap=safe_convert(forex_metrics.get('total_swap_cost', 0)),
            gross_profit=safe_convert(gross_profit),
        )
        return {
            'is_martingale': True,
            # Session Performance (from hedge_metrics + martingale)
            **hedge_metrics,
            **martingale,
            # Account-level (kept)
            'net_profit': safe_convert(net_profit),
            'net_profit_percentage': safe_convert(net_profit_percentage),
            'annual_return': safe_convert(annual_return),
            'starting_balance': safe_convert(starting_balance),
            'finishing_balance': safe_convert(current_balance),
            'gross_pnl': safe_convert(gross_pnl),
            'gross_profit': safe_convert(gross_profit),
            'gross_loss': safe_convert(gross_loss),
            # Survival (kept from current)
            'max_drawdown': safe_convert(max_dd),
            'margin_closeouts': safe_convert(margin_closeouts, int),
            'account_blown': account_blown,
            'max_consecutive_session_losses': hedge_metrics.get('max_consecutive_session_losses', 0),
            # Capital
            'worst_floating_pnl': safe_convert(worst_floating_pnl),
            'peak_margin_used': safe_convert(peak_margin_used),
            'peak_equity_usage_pct': safe_convert(peak_equity_usage_pct),
            'fee': safe_convert(fee),
            'profit_factor': safe_convert(profit_factor),
            **forex_metrics,
            # Raw trade stats (for collapsed debug section)
            'raw_trade_stats': {
                'total': safe_convert(total_completed, int),
                'total_winning_trades': safe_convert(total_winning_trades, int),
                'total_losing_trades': safe_convert(total_losing_trades, int),
                'win_rate': safe_convert(win_rate),
                'longs_count': safe_convert(longs_count, int),
                'shorts_count': safe_convert(shorts_count, int),
                'largest_winning_trade': safe_convert(largest_winning_trade),
                'largest_losing_trade': safe_convert(largest_losing_trade),
                'winning_streak': safe_convert(winning_streak, int),
                'losing_streak': safe_convert(losing_streak, int),
                'average_win': safe_convert(average_win),
                'average_loss': safe_convert(average_loss),
                'average_holding_period': safe_convert(average_holding_period),
            },
            'total_open_trades': safe_convert(total_open_trades, int),
            'open_pl': safe_convert(open_pl),
            'total': safe_convert(total_completed, int),
        }

    # ── Non-martingale: full generic metrics (existing behavior) ──
    return {
        'total': safe_convert(total_completed, int),
        'total_winning_trades': safe_convert(total_winning_trades, int),
        'total_losing_trades': safe_convert(total_losing_trades, int),
        'starting_balance': safe_convert(starting_balance),
        'finishing_balance': safe_convert(current_balance),
        'win_rate': safe_convert(win_rate),
        'win_rate_longs': safe_convert(win_rate_longs),
        'win_rate_shorts': safe_convert(win_rate_shorts),
        'ratio_avg_win_loss': safe_convert(ratio_avg_win_loss),
        'longs_count': safe_convert(longs_count, int),
        'longs_percentage': safe_convert(longs_percentage),
        'shorts_percentage': safe_convert(shorts_percentage),
        'shorts_count': safe_convert(shorts_count, int),
        'fee': safe_convert(fee),
        'gross_pnl': safe_convert(gross_pnl),
        'net_profit': safe_convert(net_profit),
        'net_profit_percentage': safe_convert(net_profit_percentage),
        'average_win': safe_convert(average_win),
        'average_loss': safe_convert(average_loss),
        'expectancy': safe_convert(expectancy),
        'expectancy_percentage': safe_convert(expectancy_percentage),
        'expected_net_profit_every_100_trades': safe_convert(expected_net_profit_every_100_trades),
        'average_holding_period': safe_convert(average_holding_period),
        'average_winning_holding_period': safe_convert(average_winning_holding_period),
        'average_losing_holding_period': safe_convert(average_losing_holding_period),
        'gross_profit': safe_convert(gross_profit),
        'gross_loss': safe_convert(gross_loss),
        'max_drawdown': safe_convert(max_dd),
        'max_underwater_period': safe_convert(max_underwater_period),
        'annual_return': safe_convert(annual_return),
        'sharpe_ratio': safe_convert(sharpe),
        'calmar_ratio': safe_convert(calmar),
        'sortino_ratio': safe_convert(sortino),
        'omega_ratio': safe_convert(omega),
        'serenity_index': safe_convert(serenity),
        'total_open_trades': safe_convert(total_open_trades, int),
        'open_pl': safe_convert(open_pl),
        'winning_streak': safe_convert(winning_streak, int),
        'losing_streak': safe_convert(losing_streak, int),
        'largest_losing_trade': safe_convert(largest_losing_trade),
        'largest_winning_trade': safe_convert(largest_winning_trade),
        'current_streak': safe_convert(current_streak[-1], int),
        'profit_factor': safe_convert(profit_factor),
        'kelly_criterion': safe_convert(kelly),
        'var_95': safe_convert(var_95),
        'var_99': safe_convert(var_99),
        'cvar_95': safe_convert(cvar_95),
        'cvar_99': safe_convert(cvar_99),
        'worst_floating_pnl': safe_convert(worst_floating_pnl),
        'peak_margin_used': safe_convert(peak_margin_used),
        'peak_equity_usage_pct': safe_convert(peak_equity_usage_pct),
        'margin_closeouts': safe_convert(margin_closeouts, int),
        'account_blown': account_blown,
        **forex_metrics,
        **hedge_metrics,
    }
```

- [ ] **Step 2: Move the Sharpe/Sortino/etc computation inside a conditional**

Currently lines 577-584 always compute these ratios. Wrap them so they only run in non-martingale mode. Find:

```python
    max_dd = np.nan if len(daily_return) < 2 else max_drawdown(daily_return).iloc[0] * 100
    max_underwater_period = np.nan if len(daily_balance) < 2 else calculate_max_underwater_period(daily_balance)
    annual_return = np.nan if len(daily_return) < 2 else cagr(daily_return, periods=periods).iloc[0] * 100
    sharpe = np.nan if len(daily_return) < 2 else sharpe_ratio(daily_return, periods=periods).iloc[0]
    calmar = np.nan if len(daily_return) < 2 else calmar_ratio(daily_return).iloc[0]
    sortino = np.nan if len(daily_return) < 2 else sortino_ratio(daily_return, periods=periods).iloc[0]
    omega = np.nan if len(daily_return) < 2 else omega_ratio(daily_return, periods=periods).iloc[0]
    serenity = np.nan if len(daily_return) < 2 else serenity_index(daily_return).iloc[0]
```

Replace with:

```python
    max_dd = np.nan if len(daily_return) < 2 else max_drawdown(daily_return).iloc[0] * 100
    annual_return = np.nan if len(daily_return) < 2 else cagr(daily_return, periods=periods).iloc[0] * 100

    # Check martingale mode early so we can skip irrelevant ratio computations
    has_sessions = any(hasattr(t, 'meta') and getattr(t, 'meta', {}).get('session') is not None for t in trades_list)

    if not has_sessions:
        max_underwater_period = np.nan if len(daily_balance) < 2 else calculate_max_underwater_period(daily_balance)
        sharpe = np.nan if len(daily_return) < 2 else sharpe_ratio(daily_return, periods=periods).iloc[0]
        calmar = np.nan if len(daily_return) < 2 else calmar_ratio(daily_return).iloc[0]
        sortino = np.nan if len(daily_return) < 2 else sortino_ratio(daily_return, periods=periods).iloc[0]
        omega = np.nan if len(daily_return) < 2 else omega_ratio(daily_return, periods=periods).iloc[0]
        serenity = np.nan if len(daily_return) < 2 else serenity_index(daily_return).iloc[0]
```

And remove the duplicate `has_sessions` line that was previously at line 626 (since we moved it earlier).

Also skip VaR/CVaR and Kelly in martingale mode — wrap the VaR block (lines 598-616) and Kelly block (lines 592-596) inside `if not has_sessions:`.

- [ ] **Step 3: Run all metric tests**

```bash
cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/test_metrics.py tests/test_martingale_metrics.py -v 2>&1 | tail -30
```

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add qengine/services/metrics.py
git commit -m "feat: wire martingale metrics into trades() response, skip generic ratios in martingale mode"
```

---

### Task 3: Frontend — Martingale guide tooltips

**Files:**
- Create: `frontend/src/guides/martingale.md`
- Modify: `frontend/src/guides/index.js`

- [ ] **Step 1: Create the martingale guide file**

Create `frontend/src/guides/martingale.md`:

```markdown
## _section_guide
Martingale metrics use the **session** as the atomic unit — not the individual trade. A session is one full cycle from initial entry through resolution (TP hit or bust). Standard trade-level metrics (Sharpe, win rate per trade, etc.) are misleading for martingale systems because individual legs are structurally required, not independent bets.

## session_profit_factor
Ratio of total winning session PnL to total losing session PnL. The true profit factor for martingale systems. A value above 1.0 means winning sessions outweigh losing sessions in dollar terms. Unlike trade-level profit factor, this correctly treats each session as an atomic outcome.

## median_session_pnl
The middle value when all session PnLs are sorted. More robust than mean EV because a single bust can heavily skew the average. If median is positive but mean is negative, busts are dominating arithmetic returns.

## bust_rate
Fraction of sessions that ended in bust (max levels, margin call, liquidation). THE most important probability for martingale systems. Everything else flows from this. Even 1% bust rate compounds dangerously over hundreds of sessions.

## bust_count
Total number of sessions that ended in bust during the backtest.

## wins_to_recover
How many winning sessions it takes to recover from one average bust. Calculated as |avg_bust_loss| / avg_session_win. If WTR = 78, one bust erases 78 winning sessions. This is the most intuitive measure of bust severity.

## geometric_growth_rate
The average of ln(1 + session_return) across all sessions. If this is negative, the system is mathematically guaranteed to approach zero balance given enough sessions — even if arithmetic EV is positive. This is THE long-run survival metric. Positive geometric growth = wealth compounds. Negative = wealth erodes.

## survival_100
Probability of completing 100 sessions without a single bust. Calculated as (1 - bust_rate)^100. At 1% bust rate: 36.6%. At 2%: 13.3%.

## survival_500
Probability of completing 500 sessions without a single bust. At 1% bust rate: 0.66%. Shows the long-run fragility of even low bust rates.

## survival_half_life
Number of sessions at which there is a 50% chance of having experienced at least one bust. Calculated as ln(0.5) / ln(1 - bust_rate). At 1% bust rate: ~69 sessions. Infinite if no busts observed.

## avg_bust_loss
Average dollar loss across all bust sessions. Combined with bust_rate and avg_session_win, fully characterizes the risk/reward structure.

## bust_severity_std
Standard deviation of bust losses. Low = busts are predictable in size (structural). High = some busts are far worse than others (possible margin cascade or liquidity issues).

## level_transitions
Markov chain view of the system. For each level L: how many sessions entered L, how many won at L, how many escalated to L+1. Shows exactly where sessions go wrong. If P(escalate) at L3 is much higher than at L1, the hedge sizing or timing at that level needs work.

## ev_by_depth
Expected value decomposition by session depth. Shows which max-levels actually generate profit vs. destroy it. Healthy system: L0-L2 contribute most profit, deeper levels are rare and roughly break even.

## time_at_depth
Total time (seconds) spent at each hedge level across all sessions. Deep levels tie up more capital for longer. If time_at_depth at L5+ is high relative to total backtest duration, capital efficiency is poor.

## l0_win_rate
Fraction of all sessions that won at level 0 (initial entry correct, no hedging needed). Higher is better — it measures entry quality. If this is low, the strategy relies heavily on the hedging mechanism rather than good entries.

## cost_drag_pct
Total costs (fees + spread + swap) as a percentage of gross profit. Shows how much friction eats into returns. A drag of 30%+ means the strategy is borderline — costs are a major factor.
```

- [ ] **Step 2: Register the guide in index.js**

In `frontend/src/guides/index.js`, add the import and registration:

After line 6 (`import hedgeRaw from './hedge.md?raw'`), add:
```javascript
import martingaleRaw from './martingale.md?raw'
```

In the `guides` object (line 24-37), add after the `hedge` entry:
```javascript
  martingale: parseMdGuide(martingaleRaw),
```

In the `allGuides` merge (line 40-48), add `guides.martingale` after `guides.hedge`:
```javascript
export const allGuides = Object.assign(
  {},
  guides.performance,
  guides.trades,
  guides.risk,
  guides.forex,
  guides.hedge,
  guides.martingale,
  guides['monte-carlo'],
)
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/guides/martingale.md frontend/src/guides/index.js
git commit -m "feat: add martingale metric tooltip guides"
```

---

### Task 4: Frontend — Conditional metric groups in Backtest.vue

**Files:**
- Modify: `frontend/src/views/Backtest.vue`

This is the main frontend change. We add new key arrays for martingale mode and conditionally render the 4 new groups.

- [ ] **Step 1: Add martingale key arrays**

In `Backtest.vue`, after the existing key arrays (around line 2999, after `hedgeKeys`), add:

```javascript
// ── Martingale-mode key arrays ──
const isMartingale = computed(() => metrics.value?.is_martingale === true)

const sessionPerfKeys = [
  ['total_sessions', 'Sessions'], ['session_win_rate', 'Session Win Rate'],
  ['session_profit_factor', 'Session Profit Factor'], ['ev_per_session', 'EV / Session'],
  ['median_session_pnl', 'Median Session PnL'],
  ['net_profit', 'Net Profit'], ['net_profit_percentage', 'Net Profit %'],
  ['annual_return', 'Annual Return'], ['starting_balance', 'Starting Balance'],
  ['finishing_balance', 'Finishing Balance'],
]
const survivalKeys = [
  ['bust_rate', 'Bust Rate'], ['bust_count', 'Busts'],
  ['wins_to_recover', 'Wins to Recover'], ['geometric_growth_rate', 'Geometric Growth Rate'],
  ['survival_100', 'P(Survive 100)'], ['survival_500', 'P(Survive 500)'],
  ['survival_half_life', 'Half-Life (sessions)'],
  ['worst_bust_pnl', 'Worst Bust PnL'], ['avg_bust_loss', 'Avg Bust Loss'],
  ['bust_severity_std', 'Bust Severity Spread'],
  ['max_drawdown', 'Max Drawdown %'], ['max_consecutive_session_losses', 'Max Consec. Losses'],
  ['margin_closeouts', 'Margin Close-outs'], ['account_blown', 'Account Blown'],
]
const structuralKeys = [
  ['l0_win_rate', 'L0 Win Rate'], ['avg_legs_per_session', 'Avg Legs / Session'],
  ['max_legs_in_session', 'Max Legs in Session'], ['sessions_with_1_leg', 'L0 Wins (1-leg)'],
]
const capitalKeys = [
  ['peak_margin_used', 'Peak Margin Used'], ['peak_equity_usage_pct', 'Peak Equity Used %'],
  ['worst_floating_pnl', 'Worst Floating Loss'], ['profit_factor', 'Profit Factor'],
  ['fee', 'Total Fees'], ['total_spread_cost', 'Total Spread Cost'],
  ['total_swap_cost', 'Total Swap Cost'], ['total_pips', 'Total Pips'],
  ['avg_pips_per_trade', 'Avg Pips / Trade'], ['cost_drag_pct', 'Cost Drag %'],
]

const mSessionPerf = computed(() => pickMetrics(sessionPerfKeys))
const mSurvival = computed(() => pickMetrics(survivalKeys))
const mStructural = computed(() => pickMetrics(structuralKeys))
const mCapital = computed(() => pickMetrics(capitalKeys))
```

- [ ] **Step 2: Update `metricColor` function**

Add color rules for the new metrics. In the `metricColor` function (around line 3918), add these cases before the final `return 'text-surface-100'`:

```javascript
  if (key === 'bust_rate') return val > 0.02 ? 'text-red-400' : val > 0 ? 'text-amber-400' : 'text-green-400'
  if (key === 'geometric_growth_rate') return val >= 0 ? 'text-green-400' : 'text-red-400'
  if (key === 'survival_100' || key === 'survival_500') return val >= 0.5 ? 'text-green-400' : val >= 0.1 ? 'text-amber-400' : 'text-red-400'
  if (key === 'wins_to_recover') return val > 100 ? 'text-red-400' : val > 50 ? 'text-amber-400' : 'text-green-400'
  if (key === 'session_profit_factor') return val >= 1 ? 'text-green-400' : 'text-red-400'
  if (key === 'median_session_pnl') return val >= 0 ? 'text-green-400' : 'text-red-400'
  if (key === 'l0_win_rate') return val >= 0.5 ? 'text-green-400' : 'text-amber-400'
  if (key === 'cost_drag_pct') return val > 30 ? 'text-red-400' : val > 15 ? 'text-amber-400' : 'text-green-400'
  if (key === 'avg_bust_loss' || key === 'worst_bust_pnl') return 'text-red-400'
  if (key === 'bust_count') return val > 0 ? 'text-red-400' : 'text-green-400'
  if (key === 'survival_half_life') return val === Infinity ? 'text-green-400' : val > 200 ? 'text-green-400' : val > 50 ? 'text-amber-400' : 'text-red-400'
```

- [ ] **Step 3: Replace the metric display template**

Find the current metrics display section (around lines 675-735). This is the section with `performanceMetrics`, `hedgeSessionMetrics`, `riskMetrics`, `tradeStatsMetrics`, `forexMetrics`.

Replace the entire block between the `<!-- Performance metrics -->` comment and the `<!-- Pipeline Intelligence -->` section with:

```html
            <!-- ═══ Martingale Mode ═══ -->
            <template v-if="isMartingale">
              <!-- Session Performance -->
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Session Performance</h3>
                <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                  <div v-for="m in mSessionPerf" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>

              <!-- Survival & Ruin -->
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-red-400/70 mb-1">Survival & Ruin</h3>
                <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                  <div v-for="m in mSurvival" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>

              <!-- Structural Diagnostics -->
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Structural Diagnostics</h3>
                <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                  <div v-for="m in mStructural" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>

                <!-- Level Transition Matrix (inline table) -->
                <div v-if="metrics.level_transitions?.length" class="mt-3">
                  <h4 class="text-[10px] text-surface-600 uppercase tracking-wider mb-1">Level Transition Matrix</h4>
                  <div class="overflow-x-auto">
                    <table class="w-full text-xs">
                      <thead>
                        <tr class="border-b border-surface-700">
                          <th class="text-left py-1 px-2 text-surface-500">Level</th>
                          <th class="text-right py-1 px-2 text-surface-500">Entries</th>
                          <th class="text-right py-1 px-2 text-surface-500">Wins</th>
                          <th class="text-right py-1 px-2 text-surface-500">Escalated</th>
                          <th class="text-right py-1 px-2 text-surface-500">P(Win)</th>
                          <th class="text-right py-1 px-2 text-surface-500">P(Esc)</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="lt in metrics.level_transitions" :key="lt.level" class="border-b border-surface-800/50">
                          <td class="py-1 px-2 font-mono text-surface-300">L{{ lt.level }}</td>
                          <td class="py-1 px-2 text-right font-mono text-surface-300">{{ lt.entries }}</td>
                          <td class="py-1 px-2 text-right font-mono text-green-400">{{ lt.wins }}</td>
                          <td class="py-1 px-2 text-right font-mono text-amber-400">{{ lt.escalations }}</td>
                          <td class="py-1 px-2 text-right font-mono" :class="lt.p_win >= 0.5 ? 'text-green-400' : 'text-red-400'">{{ (lt.p_win * 100).toFixed(1) }}%</td>
                          <td class="py-1 px-2 text-right font-mono" :class="lt.p_escalate > 0.5 ? 'text-red-400' : 'text-amber-400'">{{ (lt.p_escalate * 100).toFixed(1) }}%</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- EV by Depth -->
                <div v-if="metrics.ev_by_depth && Object.keys(metrics.ev_by_depth).length" class="mt-3">
                  <h4 class="text-[10px] text-surface-600 uppercase tracking-wider mb-1">EV Decomposition by Depth</h4>
                  <div class="overflow-x-auto">
                    <table class="w-full text-xs">
                      <thead>
                        <tr class="border-b border-surface-700">
                          <th class="text-left py-1 px-2 text-surface-500">Depth</th>
                          <th class="text-right py-1 px-2 text-surface-500">Count</th>
                          <th class="text-right py-1 px-2 text-surface-500">Win Rate</th>
                          <th class="text-right py-1 px-2 text-surface-500">Total PnL</th>
                          <th class="text-right py-1 px-2 text-surface-500">Avg PnL</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(d, depth) in metrics.ev_by_depth" :key="depth" class="border-b border-surface-800/50">
                          <td class="py-1 px-2 font-mono text-surface-300">L{{ depth }}</td>
                          <td class="py-1 px-2 text-right font-mono text-surface-300">{{ d.count }}</td>
                          <td class="py-1 px-2 text-right font-mono" :class="d.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'">{{ (d.win_rate * 100).toFixed(1) }}%</td>
                          <td class="py-1 px-2 text-right font-mono" :class="d.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMetric(d.total_pnl) }}</td>
                          <td class="py-1 px-2 text-right font-mono" :class="d.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ formatMetric(d.avg_pnl) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- Depth Distribution (horizontal bar) -->
                <div v-if="metrics.depth_breakdown?.length" class="mt-3">
                  <h4 class="text-[10px] text-surface-600 uppercase tracking-wider mb-1">Depth Distribution</h4>
                  <div class="space-y-1">
                    <div v-for="d in metrics.depth_breakdown" :key="d.depth" class="flex items-center gap-2 text-xs">
                      <span class="w-8 text-surface-500 font-mono text-right">L{{ d.depth }}</span>
                      <div class="flex-1 h-4 bg-surface-800 rounded overflow-hidden relative">
                        <div class="h-full rounded"
                          :class="d.pnl >= 0 ? 'bg-green-500/30' : 'bg-red-500/30'"
                          :style="{ width: Math.max((d.count / metrics.total_sessions) * 100, 2) + '%' }">
                        </div>
                        <span class="absolute inset-0 flex items-center px-2 font-mono text-[10px] text-surface-300">
                          {{ d.count }} ({{ ((d.count / metrics.total_sessions) * 100).toFixed(1) }}%)
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Capital & Costs -->
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Capital & Costs</h3>
                <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                  <div v-for="m in mCapital" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>

              <!-- Raw Trade Data (collapsed) -->
              <details class="mb-4">
                <summary class="text-xs text-surface-600 cursor-pointer hover:text-surface-400 select-none">
                  Raw Trade Data (debug)
                </summary>
                <div v-if="metrics.raw_trade_stats" class="mt-2 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                  <div v-for="(val, key) in metrics.raw_trade_stats" :key="key" class="p-2 bg-surface-900 rounded">
                    <div class="text-surface-600 text-xs">{{ formatKey(key) }}</div>
                    <div class="font-mono text-surface-400">{{ formatMetric(val) }}</div>
                  </div>
                </div>
              </details>
            </template>

            <!-- ═══ Generic Mode (existing) ═══ -->
            <template v-else>
              <!-- Performance metrics -->
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Performance</h3>
                <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                  <div v-for="m in performanceMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>

              <!-- Hedge Session Stats -->
              <div v-if="hedgeSessionMetrics.length" class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Hedge Session Stats</h3>
                <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                  <div v-for="m in hedgeSessionMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>

              <!-- Risk metrics -->
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Risk & Ratios</h3>
                <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                  <div v-for="m in riskMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono" :class="metricColor(m.key, m.value)">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>

              <!-- Trade Stats -->
              <div class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Trade Statistics</h3>
                <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                  <div v-for="m in tradeStatsMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono text-surface-100">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>

              <!-- Forex metrics -->
              <div v-if="forexMetrics.length" class="mb-4">
                <h3 class="text-xs font-semibold text-surface-500 mb-1">Forex</h3>
                <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                  <div v-for="m in forexMetrics" :key="m.key" class="p-2 bg-surface-800 rounded">
                    <div class="text-surface-500 text-xs"><MetricTooltip :metric-key="m.key">{{ m.label }}</MetricTooltip></div>
                    <div class="font-mono text-surface-100">{{ formatMetric(m.value) }}</div>
                  </div>
                </div>
              </div>
            </template>
```

- [ ] **Step 4: Update `formatMetric` for special martingale values**

In the `formatMetric` function (around line 3807), add handling for Infinity and very small decimals:

Find:
```javascript
function formatMetric(val) {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  if (typeof val === 'number') {
    if (isNaN(val)) return '-'
    if (Number.isInteger(val)) return val.toLocaleString()
    return val.toFixed(2)
  }
  return val
}
```

Replace with:
```javascript
function formatMetric(val) {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  if (typeof val === 'number') {
    if (isNaN(val)) return '-'
    if (!isFinite(val)) return val > 0 ? '\u221E' : '-\u221E'
    if (Number.isInteger(val)) return val.toLocaleString()
    // 6 decimals for very small values (geometric growth rate)
    if (Math.abs(val) > 0 && Math.abs(val) < 0.01) return val.toFixed(6)
    return val.toFixed(2)
  }
  return val
}
```

- [ ] **Step 5: Build frontend to verify no compile errors**

```bash
cd /Users/naresh/Documents/Research/qengine/frontend && npm run build 2>&1 | tail -20
```

Expected: Build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/Backtest.vue
git commit -m "feat: conditional martingale metric groups in Backtest.vue with transition matrix and depth charts"
```

---

### Task 5: Integration smoke test

**Files:** None (manual verification)

- [ ] **Step 1: Run a surefire strategy backtest and verify the response shape**

```bash
cd /Users/naresh/Documents/Research/qengine && python -c "
from qengine.services.metrics import _parse_sessions, _calculate_martingale_metrics
import math

# Simulate: 95 wins at $12 each, 5 busts at -$250 each
sessions = []
for i in range(95):
    sessions.append({'pnl': 12.0, 'legs': 1, 'max_level': 0, 'exit_reason': 'tp',
                     'holding_seconds': 300, 'leg_levels': [0], 'leg_holdings': [300.0]})
for i in range(5):
    sessions.append({'pnl': -250.0, 'legs': 6, 'max_level': 5, 'exit_reason': 'bust',
                     'holding_seconds': 1800, 'leg_levels': [0,1,2,3,4,5], 'leg_holdings': [300]*6})

result = _calculate_martingale_metrics(sessions, starting_balance=10000)
print('Session PF:', result['session_profit_factor'])
print('Bust Rate:', result['bust_rate'])
print('WTR:', result['wins_to_recover'])
print('Geo Growth:', result['geometric_growth_rate'])
print('Survival 100:', result['survival_100'])
print('Half-life:', result['survival_half_life'])
print('L0 Win Rate:', result['l0_win_rate'])
print('Transitions:', result['level_transitions'][:3])
"
```

Expected output: meaningful values — PF ~0.91, bust_rate 0.05, WTR ~20.8, negative geo growth, survival_100 ~0.0059, etc.

- [ ] **Step 2: Run all tests**

```bash
cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/test_metrics.py tests/test_martingale_metrics.py -v 2>&1 | tail -30
```

Expected: All pass.

- [ ] **Step 3: Final commit if any fixups needed**

```bash
git add -u && git commit -m "fix: integration fixups for martingale metrics" || echo "Nothing to commit"
```
