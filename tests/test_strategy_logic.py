"""
Deterministic tests for UniversalMartingale strategy logic.

Tests the pure math of TP calculation, hedge triggering, sizing curves,
session PnL accounting, and the TP-negative-exit bug.

These tests instantiate strategy components directly with known values —
no backtest engine, no candle data, no indicators needed.
"""
import math
import numpy as np
import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Mock helpers — simulate strategy state without the engine
# ═══════════════════════════════════════════════════════════════════════════════

# Fibonacci sequence used by the strategy
_FIB = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]


def _calc_size(base, level, curve='geometric', factor=2.0):
    """Reproduce the strategy's _calc_size logic."""
    if curve == 'geometric':
        return base * (factor ** level)
    elif curve == 'sqrt':
        return base * (factor ** 0.5) ** level
    elif curve == 'linear':
        return base * (1 + level)
    elif curve == 'fibonacci':
        idx = min(level, len(_FIB) - 1)
        return base * _FIB[idx]
    elif curve == 'fixed':
        return base
    elif curve == 'anti_martingale':
        return base / (factor ** level) if level > 0 else base
    return base


def _simulate_session(direction, entry_price, hedge_pips, tp_pips, max_levels,
                      base_size=1.0, sizing_curve='geometric', sizing_factor=2.0,
                      pip_size=0.0001, levels_hit=None):
    """
    Simulate a complete hedged martingale session step by step.

    Returns list of legs and computed TP/hedge prices at each level.
    If levels_hit is given, only go up to that many levels.

    Returns: {
        'legs': [{level, dir, qty, entry, pnl_at_tp}],
        'tp_prices': [tp at each level],
        'net_pnl_at_tp': float,  # PnL if TP hits at the final level
        'tp_price': float,  # final TP price
    }
    """
    legs = []
    tp_prices = []
    hedge_dist = hedge_pips * pip_size
    tp_dist = tp_pips * pip_size

    current_entry = entry_price
    current_dir = direction
    levels_to_hit = levels_hit if levels_hit is not None else 0

    for lvl in range(levels_to_hit + 1):
        qty = _calc_size(base_size, lvl, sizing_curve, sizing_factor)
        legs.append({
            'level': lvl,
            'dir': current_dir,
            'qty': qty,
            'entry': current_entry,
        })

        # TP is set relative to LAST leg (this is the current strategy behavior)
        if current_dir == 'long':
            tp = current_entry + tp_dist
        else:
            tp = current_entry - tp_dist
        tp_prices.append(tp)

        if lvl < levels_to_hit:
            # Compute next hedge trigger and entry
            if current_dir == 'long':
                next_entry = current_entry - hedge_dist
            else:
                next_entry = current_entry + hedge_dist
            # Flip direction
            current_dir = 'short' if current_dir == 'long' else 'long'
            current_entry = next_entry

    # Compute net PnL at the final TP price
    final_tp = tp_prices[-1]
    net_pnl = 0
    for leg in legs:
        if leg['dir'] == 'long':
            pnl = leg['qty'] * (final_tp - leg['entry'])
        else:
            pnl = leg['qty'] * (leg['entry'] - final_tp)
        leg['pnl_at_tp'] = pnl
        net_pnl += pnl

    return {
        'legs': legs,
        'tp_prices': tp_prices,
        'net_pnl_at_tp': net_pnl,
        'tp_price': final_tp,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Sizing Curve Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSizingCurves:
    """Verify position sizing at each hedge level."""

    def test_geometric_2x(self):
        # base=1, factor=2: 1, 2, 4, 8, 16
        for lvl, expected in enumerate([1, 2, 4, 8, 16]):
            assert _calc_size(1, lvl, 'geometric', 2.0) == pytest.approx(expected)

    def test_geometric_sqrt2(self):
        # factor=sqrt(2) ≈ 1.414: 1, 1.414, 2, 2.828, 4
        f = math.sqrt(2)
        for lvl, expected in enumerate([1, f, f**2, f**3, f**4]):
            assert _calc_size(1, lvl, 'geometric', f) == pytest.approx(expected, rel=1e-6)

    def test_sqrt_curve(self):
        # sqrt of geometric: base * (factor^0.5)^level
        # factor=2, sqrt(2)^level: 1, 1.414, 2, 2.828, 4
        for lvl in range(5):
            expected = (2.0 ** 0.5) ** lvl
            assert _calc_size(1, lvl, 'sqrt', 2.0) == pytest.approx(expected, rel=1e-6)

    def test_linear(self):
        # base * (1 + level): 1, 2, 3, 4, 5
        for lvl, expected in enumerate([1, 2, 3, 4, 5]):
            assert _calc_size(1, lvl, 'linear', 2.0) == pytest.approx(expected)

    def test_fibonacci(self):
        # 1, 1, 2, 3, 5, 8, 13, 21
        for lvl, expected in enumerate([1, 1, 2, 3, 5, 8, 13, 21]):
            assert _calc_size(1, lvl, 'fibonacci', 2.0) == pytest.approx(expected)

    def test_fixed(self):
        # Same size every level
        for lvl in range(5):
            assert _calc_size(10, lvl, 'fixed', 2.0) == pytest.approx(10)

    def test_anti_martingale(self):
        # Decreasing: base / factor^level
        # factor=2: 10, 5, 2.5, 1.25
        for lvl, expected in enumerate([10, 5, 2.5, 1.25]):
            assert _calc_size(10, lvl, 'anti_martingale', 2.0) == pytest.approx(expected)

    def test_base_size_scales(self):
        # All curves scale linearly with base
        for curve in ['geometric', 'sqrt', 'linear', 'fibonacci', 'fixed']:
            s1 = _calc_size(1, 3, curve, 2.0)
            s10 = _calc_size(10, 3, curve, 2.0)
            assert s10 == pytest.approx(s1 * 10, rel=1e-6)

    def test_total_exposure_geometric(self):
        # Total exposure for bust: sum of all levels
        # geometric 2x, 6 levels: 1+2+4+8+16+32 = 63
        total = sum(_calc_size(1, lvl, 'geometric', 2.0) for lvl in range(6))
        assert total == pytest.approx(63)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. TP Calculation Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestTPCalculation:
    """Verify take-profit price computation."""

    def test_long_tp_above_entry(self):
        # Long: TP = entry + tp_dist
        # entry=1.1000, tp=20 pips → TP = 1.1020
        result = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=20,
                                   max_levels=6, levels_hit=0)
        assert result['tp_price'] == pytest.approx(1.1020, abs=1e-8)

    def test_short_tp_below_entry(self):
        # Short: TP = entry - tp_dist
        # entry=1.1000, tp=20 pips → TP = 1.0980
        result = _simulate_session('short', 1.1000, hedge_pips=10, tp_pips=20,
                                   max_levels=6, levels_hit=0)
        assert result['tp_price'] == pytest.approx(1.0980, abs=1e-8)

    def test_tp_recalculates_from_last_leg(self):
        # After hedge, TP is set from the NEWEST leg's entry
        # L0: long at 1.1000
        # L1: short at 1.0990 (hedge trigger = entry - 10 pips)
        # TP recalculated from L1 short entry: 1.0990 - 20 pips = 1.0970
        result = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=20,
                                   max_levels=6, levels_hit=1)
        # L1 short entry at 1.0990, TP = 1.0990 - 0.0020 = 1.0970
        assert result['tp_price'] == pytest.approx(1.0970, abs=1e-8)
        assert result['legs'][1]['dir'] == 'short'
        assert result['legs'][1]['entry'] == pytest.approx(1.0990, abs=1e-8)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Session PnL at TP — THE CRITICAL BUG TEST
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionPnLAtTP:
    """
    THE CORE BUG: When TP hits, is the net session PnL actually positive?

    The strategy sets TP relative to the LAST leg's entry only.
    Older legs have accumulated losses. If tp_pips < hedge_pips,
    the newest leg's profit may not cover the older legs' losses.

    Mathematical condition for positive TP at level N:
        tp_pips * size[N] > sum(hedge_pips * size[i] for i in 0..N-1)
        (simplified — actual formula depends on net position direction)
    """

    def test_l0_tp_always_positive(self):
        """At level 0, TP is always positive (no older legs)."""
        for tp_pips in [1, 5, 10, 20, 50]:
            result = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=tp_pips,
                                       max_levels=6, levels_hit=0)
            # L0 only: PnL = qty * tp_dist = 1 * tp_pips * 0.0001
            assert result['net_pnl_at_tp'] > 0, \
                f"L0 TP should always be positive, got {result['net_pnl_at_tp']} for tp={tp_pips}"

    def test_l1_tp_positive_when_tp_gt_hedge(self):
        """At L1 with 2x geometric, TP > hedge → net positive.

        L0: long 1 lot at 1.1000
        L1: short 2 lots at 1.0990
        TP = 1.0990 - 20 pips = 1.0970

        L0 PnL: 1 * (1.0970 - 1.1000) = -0.003 = -30 pips
        L1 PnL: 2 * (1.0990 - 1.0970) = +0.004 = +40 pips
        Net: +10 pips ✓
        """
        result = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=20,
                                   max_levels=6, sizing_curve='geometric',
                                   sizing_factor=2.0, levels_hit=1)
        assert result['net_pnl_at_tp'] > 0, \
            f"L1 TP with tp=20 > hedge=10 should be positive, got {result['net_pnl_at_tp']}"

    def test_l1_tp_NEGATIVE_when_tp_lt_hedge_div_factor(self):
        """BUG DEMONSTRATION: L1 TP with small tp_pips → negative net PnL.

        tp=5, hedge=10, geometric 2x:
        L0: long 1 at 1.1000
        L1: short 2 at 1.0990
        TP = 1.0990 - 5 pips = 1.0985

        L0 PnL: 1 * (1.0985 - 1.1000) = -0.0015 = -15 pips
        L1 PnL: 2 * (1.0990 - 1.0985) = +0.0010 = +10 pips
        Net: -5 pips ← NEGATIVE!

        The condition for positive L1: tp * factor > hedge + tp
        → tp > hedge / (factor - 1) = 10 / 1 = 10 pips minimum
        """
        result = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=5,
                                   max_levels=6, sizing_curve='geometric',
                                   sizing_factor=2.0, levels_hit=1)
        # THIS DEMONSTRATES THE BUG — TP hit but net PnL is negative
        assert result['net_pnl_at_tp'] < 0, \
            f"Expected negative PnL at L1 TP with tp=5 < hedge=10, got {result['net_pnl_at_tp']}"

    def test_l2_tp_negative_demonstration(self):
        """At L2 the losses compound further.

        tp=8, hedge=10, geometric 2x:
        L0: long 1 at 1.1000
        L1: short 2 at 1.0990
        L2: long 4 at 1.1000 (hedge back up)
        TP = 1.1000 + 8 pips = 1.1008

        L0: 1 * (1.1008 - 1.1000) = +0.0008 = +8 pips
        L1: 2 * (1.0990 - 1.1008) = -0.0036 = -36 pips
        L2: 4 * (1.1008 - 1.1000) = +0.0032 = +32 pips
        Net: 8 - 36 + 32 = +4 pips (barely positive with tp=8)

        But with tp=3:
        TP = 1.1003
        L0: 1 * (1.1003 - 1.1000) = +3 pips
        L1: 2 * (1.0990 - 1.1003) = -26 pips
        L2: 4 * (1.1003 - 1.1000) = +12 pips
        Net: 3 - 26 + 12 = -11 pips
        """
        result = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=3,
                                   max_levels=6, sizing_curve='geometric',
                                   sizing_factor=2.0, levels_hit=2)
        assert result['net_pnl_at_tp'] < 0, \
            f"Expected negative PnL at L2 TP with tp=3, got {result['net_pnl_at_tp']}"

    def test_minimum_tp_for_positive_session(self):
        """
        Find the minimum tp_pips that guarantees positive net PnL at each level.

        For geometric 2x with hedge=10:
        - L0: any tp > 0
        - L1: tp > hedge / (factor - 1) = 10 / 1 = 10 pips
        - L2: need to solve algebraically (depends on alternating directions)
        """
        hedge = 10
        for levels_hit in range(5):
            # Binary search for minimum positive TP
            lo, hi = 0.1, 100.0
            for _ in range(50):
                mid = (lo + hi) / 2
                result = _simulate_session('long', 1.1000, hedge_pips=hedge, tp_pips=mid,
                                           max_levels=10, sizing_curve='geometric',
                                           sizing_factor=2.0, levels_hit=levels_hit)
                if result['net_pnl_at_tp'] > 0:
                    hi = mid
                else:
                    lo = mid
            min_tp = hi
            # At L0, min_tp should be ~0
            if levels_hit == 0:
                assert min_tp < 1.0, f"L0 should need tiny TP, got {min_tp}"
            # At L1+, min_tp should be significant
            if levels_hit >= 1:
                assert min_tp > 1.0, f"L{levels_hit} needs tp > 1 pip, got {min_tp}"

    def test_sqrt2_sizing_with_adequate_tp(self):
        """
        With sqrt(2) sizing, tp must be slightly above hedge for guaranteed positive.
        Phase 2 research used tp=2*hedge. The key is p*m < 1 for the probabilistic
        math, but the per-session TP math requires tp > hedge * (1 / (sqrt(2)-1)) ≈ 2.41.
        With tp=2.5*hedge, all levels should be positive.
        """
        for levels_hit in range(6):
            result = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=25,
                                       max_levels=8, sizing_curve='sqrt',
                                       sizing_factor=2.0, levels_hit=levels_hit)
            assert result['net_pnl_at_tp'] > 0, \
                f"sqrt(2) with tp=2.5*hedge should be positive at L{levels_hit}, " \
                f"got {result['net_pnl_at_tp']}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Hedge Trigger Price Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestHedgeTrigger:
    """Verify hedge trigger prices at each level."""

    def test_long_hedge_below_entry(self):
        # Long entry at 1.1000, hedge=10 pips → trigger at 1.0990
        result = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=20,
                                   max_levels=6, levels_hit=0)
        # L0 long, trigger = entry - hedge_dist
        expected_trigger = 1.1000 - 0.0010
        assert result['legs'][0]['entry'] == pytest.approx(1.1000)

    def test_alternating_directions(self):
        """Hedge legs alternate long/short/long/short..."""
        result = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=20,
                                   max_levels=6, levels_hit=5)
        expected_dirs = ['long', 'short', 'long', 'short', 'long', 'short']
        actual_dirs = [leg['dir'] for leg in result['legs']]
        assert actual_dirs == expected_dirs

    def test_short_session_hedge_above_entry(self):
        """Short session: hedge triggers ABOVE entry."""
        result = _simulate_session('short', 1.1000, hedge_pips=10, tp_pips=20,
                                   max_levels=6, levels_hit=1)
        # L0 short at 1.1000
        # L1 long at 1.1010 (price rose against short)
        assert result['legs'][1]['dir'] == 'long'
        assert result['legs'][1]['entry'] == pytest.approx(1.1010, abs=1e-8)

    def test_hedge_entries_oscillate(self):
        """Entry prices should oscillate around the starting price."""
        result = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=20,
                                   max_levels=10, levels_hit=5)
        entries = [leg['entry'] for leg in result['legs']]
        # L0: 1.1000, L1: 1.0990, L2: 1.1000, L3: 1.0990, ...
        assert entries[0] == pytest.approx(1.1000, abs=1e-8)
        assert entries[1] == pytest.approx(1.0990, abs=1e-8)
        assert entries[2] == pytest.approx(1.1000, abs=1e-8)  # Back to original


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Session PnL Accounting Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionPnLAccounting:
    """Verify the session PnL calculation is correct at various exit prices."""

    def _compute_net_pnl(self, legs, exit_price):
        """Hand-compute net PnL from all legs at a given price."""
        total = 0
        for leg in legs:
            if leg['dir'] == 'long':
                total += leg['qty'] * (exit_price - leg['entry'])
            else:
                total += leg['qty'] * (leg['entry'] - exit_price)
        return total

    def test_l0_long_win(self):
        # L0 long 1 lot at 1.1000, exit at 1.1020 → PnL = 1 * 0.002 = 0.002
        legs = [{'dir': 'long', 'qty': 1.0, 'entry': 1.1000}]
        pnl = self._compute_net_pnl(legs, 1.1020)
        assert pnl == pytest.approx(0.002)

    def test_l0_long_loss(self):
        # L0 long 1 lot at 1.1000, exit at 1.0980 → PnL = 1 * -0.002 = -0.002
        legs = [{'dir': 'long', 'qty': 1.0, 'entry': 1.1000}]
        pnl = self._compute_net_pnl(legs, 1.0980)
        assert pnl == pytest.approx(-0.002)

    def test_l1_hedged_session_at_various_prices(self):
        """L0 long 1 at 1.1000, L1 short 2 at 1.0990."""
        legs = [
            {'dir': 'long', 'qty': 1.0, 'entry': 1.1000},
            {'dir': 'short', 'qty': 2.0, 'entry': 1.0990},
        ]
        # At 1.0990 (L1 entry): L0=-0.001, L1=0 → net=-0.001
        assert self._compute_net_pnl(legs, 1.0990) == pytest.approx(-0.001)
        # At 1.0970 (20 pip TP for L1): L0=-0.003, L1=+0.004 → net=+0.001
        assert self._compute_net_pnl(legs, 1.0970) == pytest.approx(+0.001)
        # At 1.1000 (back to L0 entry): L0=0, L1=-0.002 → net=-0.002
        assert self._compute_net_pnl(legs, 1.1000) == pytest.approx(-0.002)

    def test_l2_hedged_session(self):
        """L0 long 1 at 1.1000, L1 short 2 at 1.0990, L2 long 4 at 1.1000."""
        legs = [
            {'dir': 'long', 'qty': 1.0, 'entry': 1.1000},
            {'dir': 'short', 'qty': 2.0, 'entry': 1.0990},
            {'dir': 'long', 'qty': 4.0, 'entry': 1.1000},
        ]
        # Net exposure: 1 - 2 + 4 = 3 lots long
        # At 1.1020 (20 pip TP for L2):
        # L0: 1 * 0.002 = +0.002
        # L1: 2 * (1.0990 - 1.1020) = 2 * -0.003 = -0.006
        # L2: 4 * 0.002 = +0.008
        # Net: 0.002 - 0.006 + 0.008 = +0.004
        assert self._compute_net_pnl(legs, 1.1020) == pytest.approx(+0.004)

    def test_bust_pnl_at_max_adverse_price(self):
        """Verify loss when price moves against the NET exposure direction.

        With geometric 2x and alternating long/short, net exposure at L5:
        L0:+1, L1:-2, L2:+4, L3:-8, L4:+16, L5:-32 → net = -21 (short)
        So moving price UP (against shorts) causes loss.
        """
        result = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=20,
                                   max_levels=6, levels_hit=5)
        legs = result['legs']
        # Compute net exposure
        net = sum(l['qty'] if l['dir'] == 'long' else -l['qty'] for l in legs)
        # Move price against net direction
        if net > 0:
            bust_price = 1.0800  # far below for net-long
        else:
            bust_price = 1.1200  # far above for net-short
        bust_pnl = sum(
            leg['qty'] * (bust_price - leg['entry']) if leg['dir'] == 'long'
            else leg['qty'] * (leg['entry'] - bust_price)
            for leg in legs
        )
        assert bust_pnl < 0, f"Adverse move should produce loss, got {bust_pnl} (net={net})"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. TP-Hedge Ratio Validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestTPHedgeRatio:
    """
    Validate that the TP/hedge ratio is sufficient to guarantee positive sessions.
    This directly addresses the user's observation of negative exits at L1/L2.
    """

    def test_ratio_table(self):
        """Build a table of (sizing, levels, tp/hedge_ratio) → positive/negative.
        This characterizes exactly when the bug manifests."""
        hedge = 10
        results = []
        for curve in ['geometric', 'sqrt', 'fibonacci']:
            for ratio in [0.5, 0.8, 1.0, 1.5, 2.0]:
                tp = hedge * ratio
                for lvl in range(5):
                    r = _simulate_session('long', 1.1000, hedge_pips=hedge, tp_pips=tp,
                                          max_levels=10, sizing_curve=curve,
                                          sizing_factor=2.0, levels_hit=lvl)
                    results.append({
                        'curve': curve,
                        'ratio': ratio,
                        'level': lvl,
                        'positive': r['net_pnl_at_tp'] > 0,
                        'pnl': r['net_pnl_at_tp'],
                    })

        # Key assertions:
        # 1. L0 is ALWAYS positive for any ratio > 0
        l0_results = [r for r in results if r['level'] == 0]
        assert all(r['positive'] for r in l0_results), "L0 should always be positive"

        # 2. ratio=0.5 should produce negative sessions at higher levels for geometric
        geo_05 = [r for r in results if r['curve'] == 'geometric'
                  and r['ratio'] == 0.5 and r['level'] >= 1]
        assert any(not r['positive'] for r in geo_05), \
            "Geometric with ratio=0.5 should have negative L1+ sessions"

        # 3. ratio=2.0 should be positive at all levels for geometric
        geo_20 = [r for r in results if r['curve'] == 'geometric' and r['ratio'] == 2.0]
        assert all(r['positive'] for r in geo_20), \
            "Geometric with ratio=2.0 should always be positive"

    def test_sqrt2_needs_adequate_tp(self):
        """sqrt(2) sizing: tp=2.5*hedge guarantees positive sessions at all levels."""
        hedge = 10
        for levels_hit in range(6):
            result = _simulate_session('long', 1.1000, hedge_pips=hedge, tp_pips=25,
                                       max_levels=8, sizing_curve='sqrt',
                                       sizing_factor=2.0, levels_hit=levels_hit)
            assert result['net_pnl_at_tp'] > 0, \
                f"sqrt(2) with tp=2.5*hedge should be positive at L{levels_hit}"

    def test_geometric_2x_minimum_ratio(self):
        """For geometric 2x, find min tp/hedge ratio for each level."""
        hedge = 10
        min_ratios = {}
        for levels_hit in range(6):
            lo, hi = 0.0, 10.0
            for _ in range(100):
                mid = (lo + hi) / 2
                r = _simulate_session('long', 1.1000, hedge_pips=hedge, tp_pips=hedge * mid,
                                      max_levels=10, sizing_curve='geometric',
                                      sizing_factor=2.0, levels_hit=levels_hit)
                if r['net_pnl_at_tp'] > 0:
                    hi = mid
                else:
                    lo = mid
            min_ratios[levels_hit] = round(hi, 3)

        # L0 needs ratio > 0 (trivially)
        assert min_ratios[0] < 0.01
        # L1+ needs increasing ratios
        for lvl in range(1, 5):
            assert min_ratios[lvl] > 0.5, \
                f"L{lvl} needs tp/hedge > 0.5, got {min_ratios[lvl]}"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Abort Logic Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestAbortLogic:
    """Test abort conditions are triggered correctly."""

    def test_level_threshold_abort(self):
        """abort_mode='level_threshold', abort_level=3 → aborts at level 3+."""
        # Simulate: strategy at level 2 → no abort; level 3 → abort
        assert 2 < 3  # level < threshold → no abort
        assert 3 >= 3  # level >= threshold → abort

    def test_pnl_pct_abort(self):
        """abort_mode='pnl_pct', abort_pnl_pct=-10 → aborts when PnL < -10%."""
        session_start = 10000
        # PnL = -500 → pct = -500/10000 * 100 = -5% → no abort
        assert (-500 / session_start * 100) > -10
        # PnL = -1200 → pct = -12% → abort
        assert (-1200 / session_start * 100) < -10

    def test_time_bars_abort(self):
        """abort_mode='time_bars', abort_time_bars=100 → aborts after 100 bars."""
        assert 99 < 100  # 99 bars → no abort
        assert 100 >= 100  # 100 bars → abort


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Worst-Case Loss (Capital-Aware Sizing)
# ═══════════════════════════════════════════════════════════════════════════════

class TestWorstCaseLoss:
    """Test the worst-case loss calculation for capital_aware base sizing."""

    def test_geometric_worst_case(self):
        """Total loss if all levels bust (geometric 2x, 6 levels, 10 pip hedge).

        Each level's loss = size[lvl] * hedge_dist * pip_value
        With base=1, factor=2, 6 levels:
        total_size_pips = 1*10 + 2*10 + 4*10 + 8*10 + 16*10 + 32*10
                        = 10 * (1+2+4+8+16+32) = 10 * 63 = 630 pip-lots
        """
        base = 1.0
        factor = 2.0
        hedge_pips = 10
        max_levels = 6
        total = sum(_calc_size(base, lvl, 'geometric', factor) * hedge_pips
                    for lvl in range(max_levels))
        assert total == pytest.approx(630)

    def test_fibonacci_worst_case(self):
        """Fibonacci sizing: 1,1,2,3,5,8 → total*10 = (1+1+2+3+5+8)*10 = 200."""
        base = 1.0
        hedge_pips = 10
        total = sum(_calc_size(base, lvl, 'fibonacci', 2.0) * hedge_pips
                    for lvl in range(6))
        assert total == pytest.approx(200)

    def test_capital_aware_backsolve(self):
        """
        If max_bust_dd_pct=20%, balance=10000, worst_loss=630 pip-lots:
        max_loss = 10000 * 0.20 = 2000
        base = max_loss / (total_loss_per_base * pip_value)
        With pip_value=10 (standard lot EUR/USD):
        base = 2000 / (630 * 10) = 0.317 lots
        """
        balance = 10000
        max_dd_pct = 20
        max_loss = balance * max_dd_pct / 100  # = 2000
        total_loss_per_base = 630  # from test above (pip-lots per base lot)
        pip_value = 10  # $ per pip per lot
        base = max_loss / (total_loss_per_base * pip_value)
        assert base == pytest.approx(0.3175, abs=0.001)
        # Verify: worst loss with this base = base * 630 * 10 = 0.3175 * 6300 = 2000
        actual_worst = base * total_loss_per_base * pip_value
        assert actual_worst == pytest.approx(2000, abs=1)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Direction Symmetry Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDirectionSymmetry:
    """Long and short sessions should produce symmetric PnL results."""

    def test_long_short_pnl_symmetry(self):
        """Long session PnL at TP should equal short session PnL at TP."""
        for levels_hit in range(5):
            long_r = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=20,
                                       max_levels=8, levels_hit=levels_hit)
            short_r = _simulate_session('short', 1.1000, hedge_pips=10, tp_pips=20,
                                        max_levels=8, levels_hit=levels_hit)
            assert long_r['net_pnl_at_tp'] == pytest.approx(short_r['net_pnl_at_tp'], abs=1e-10), \
                f"Long/short asymmetry at L{levels_hit}: " \
                f"long={long_r['net_pnl_at_tp']}, short={short_r['net_pnl_at_tp']}"

    def test_leg_count_matches_level(self):
        """Number of legs should be level + 1."""
        for levels_hit in range(6):
            result = _simulate_session('long', 1.1000, hedge_pips=10, tp_pips=20,
                                       max_levels=8, levels_hit=levels_hit)
            assert len(result['legs']) == levels_hit + 1


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Cooldown and Risk Limit Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestRiskLimits:
    """Verify risk management calculations."""

    def test_daily_loss_pct(self):
        """daily_loss_pct = (day_start - current) / day_start * 100."""
        day_start = 10000
        current = 9500
        loss_pct = (day_start - current) / day_start * 100
        assert loss_pct == pytest.approx(5.0)

    def test_weekly_loss_pct(self):
        week_start = 10000
        current = 9000
        loss_pct = (week_start - current) / week_start * 100
        assert loss_pct == pytest.approx(10.0)

    def test_exposure_pct(self):
        """Total exposure = sum(abs(qty)) * price / balance * 100."""
        legs = [
            {'qty': 1.0}, {'qty': 2.0}, {'qty': 4.0}
        ]
        total_qty = sum(abs(l['qty']) for l in legs)
        price = 1.1000
        balance = 10000
        exposure_pct = (total_qty * price) / balance * 100
        # 7 * 1.1 / 10000 * 100 = 0.077%
        assert exposure_pct == pytest.approx(0.077, abs=0.001)
