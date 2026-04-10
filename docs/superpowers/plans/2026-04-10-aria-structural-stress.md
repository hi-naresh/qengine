# ARIA R(t) Structural Stress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a zero-parameter R(t) structural stress accumulator to the ARIA pipeline, based on Chen (2026), that tracks 6 log-constructible execution stress components and feeds them into CycleGate (L2), RiskShield (L4), and MetaEvaluator (L6).

**Architecture:** New `StructuralStress` class in `structural_stress.py` computes R(t) = X + C + U + F + M + V from cycle logs. It runs as a parallel signal alongside MarketBrain's danger score. Observer enriches sessions with per-level timestamps and stress decomposition. RiskShield gets a stress-velocity abort. CycleGate gets 3 new features (17 -> 20 dims). MetaEvaluator gets a stress penalty term.

**Tech Stack:** Python, numpy, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-10-aria-structural-stress-design.md`

---

## File Structure

| Action | File | Responsibility |
|---|---|---|
| Create | `pipelines/_shared/ARIA/structural_stress.py` | R(t) accumulator: 6 components, derived signals |
| Modify | `pipelines/_shared/ARIA/observer.py` | Add `start_bar`, `level_timestamps`, `stress_components`, `r_t` fields |
| Modify | `pipelines/_shared/ARIA/risk_shield.py` | Add stress-velocity abort check |
| Modify | `pipelines/_shared/ARIA/cycle_gate.py` | Expand feature vector 17 -> 20 |
| Modify | `pipelines/_shared/ARIA/meta_evaluator.py` | Add stress penalty to ARIA score |
| Modify | `pipelines/_shared/ARIA/config.py` | Add 2 new config keys |
| Modify | `pipelines/_shared/ARIA/__init__.py` | Wire StructuralStress into pipeline lifecycle |
| Create | `tests/unit/test_structural_stress.py` | Unit tests for all 6 components + R(t) |
| Create | `tests/unit/test_aria_stress_integration.py` | Integration tests: stress abort, gate features, meta penalty |

---

### Task 1: StructuralStress module — core class + X_i + C_i

**Files:**
- Create: `pipelines/_shared/ARIA/structural_stress.py`
- Create: `tests/unit/test_structural_stress.py`

- [ ] **Step 1: Write failing tests for X_i (excess depth) and C_i (exposure concentration)**

```python
# tests/unit/test_structural_stress.py
"""Unit tests for ARIA StructuralStress module (Chen 2026 R(t) components)."""

import pytest
from pipelines._shared.ARIA.structural_stress import StructuralStress


class TestExcessDepth:
    """X_i: excess depth beyond designed coverage."""

    def test_within_design_range(self):
        ss = StructuralStress()
        # Level 3 of 12 max = 0.25, design coverage = 0.7 -> X = 0
        x = ss._compute_X(levels=3, max_levels=12)
        assert x == 0.0

    def test_exceeds_design_range(self):
        ss = StructuralStress()
        # Level 10 of 12 = 0.833, design coverage = 0.7 -> X = 0.133
        x = ss._compute_X(levels=10, max_levels=12)
        assert x == pytest.approx(10 / 12 - 0.7, abs=0.01)

    def test_at_max_level(self):
        ss = StructuralStress()
        # Level 12 of 12 = 1.0, design coverage = 0.7 -> X = 0.3
        x = ss._compute_X(levels=12, max_levels=12)
        assert x == pytest.approx(0.3, abs=0.01)

    def test_zero_levels(self):
        ss = StructuralStress()
        x = ss._compute_X(levels=0, max_levels=12)
        assert x == 0.0


class TestExposureConcentration:
    """C_i: fraction of exposure in deep layers."""

    def test_shallow_cycle(self):
        ss = StructuralStress()
        # Level 1 with sqrt(2) multiplier: all exposure at L0, nothing deep
        c = ss._compute_C(levels=1, multiplier=1.4142)
        assert c == 0.0  # only 1 level, no deep layers

    def test_deep_cycle(self):
        ss = StructuralStress()
        # Level 8 with sqrt(2) multiplier: top 30% is levels 6,7,8
        c = ss._compute_C(levels=8, multiplier=1.4142)
        assert 0.0 < c < 1.0
        assert c > 0.4  # deep layers should have significant exposure share

    def test_higher_multiplier_more_concentrated(self):
        ss = StructuralStress()
        c_sqrt2 = ss._compute_C(levels=8, multiplier=1.4142)
        c_2x = ss._compute_C(levels=8, multiplier=2.0)
        assert c_2x > c_sqrt2  # 2x doubling concentrates more in deep levels
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_structural_stress.py -v 2>&1 | head -30`
Expected: ImportError or ModuleNotFoundError

- [ ] **Step 3: Implement StructuralStress with X_i and C_i**

```python
# pipelines/_shared/ARIA/structural_stress.py
"""
StructuralStress — R(t) log-constructible stress accumulator.

Implements the 6-component execution-level stress framework from:
Chen, L-Y. (2026). "Layered-averaging systems and linear reward
emergence in nonlinear financial markets." Next Research 8, 101565.

    R(t) = Σ (X_i + C_i + U_i + F_i + M_i + V_i)

All components are computed from execution logs with zero learned
parameters.  R(t) is diagnostic (explains reward degradation),
not predictive (no overfitting risk).
"""

from __future__ import annotations

import math
from typing import List, Optional


# Design coverage ratio: cycles within this fraction of max_levels
# are considered "within design range" (no excess-depth stress).
_DESIGN_COVERAGE = 0.7

# Fraction of levels considered "deep" for exposure concentration.
_DEEP_FRACTION = 0.7


class StructuralStress:
    """Accumulates R(t) from completed cycle logs.

    Zero learned parameters.  All components are computed from
    observable execution data (levels, bars, timestamps, PnL).
    """

    def __init__(self) -> None:
        # Per-cycle stress records
        self._cycle_stresses: List[dict] = []
        # Running R(t) sum
        self._r_t: float = 0.0
        # Reference statistics (computed online from cycle history)
        self._all_bars: List[int] = []           # durations for U_i median
        self._all_level_gaps: List[float] = []   # inter-level gaps for F_i median
        self._all_cycle_gaps: List[int] = []     # inter-cycle gaps for M_i median

    # ------------------------------------------------------------------
    # Individual components
    # ------------------------------------------------------------------

    def _compute_X(self, levels: int, max_levels: int) -> float:
        """X_i: excess depth beyond designed coverage.

        Parameters
        ----------
        levels : int
            Maximum level reached in the cycle (0-based count of hedge levels).
        max_levels : int
            Strategy's configured max_levels.

        Returns
        -------
        float >= 0
        """
        if max_levels <= 0:
            return 0.0
        depth_ratio = levels / max_levels
        return max(0.0, depth_ratio - _DESIGN_COVERAGE)

    def _compute_C(self, levels: int, multiplier: float) -> float:
        """C_i: exposure concentration in deep layers.

        Fraction of total deployed capital sitting in the top 30% of levels.

        Parameters
        ----------
        levels : int
            Number of levels filled (0-based: level 0 = first entry).
        multiplier : float
            Position sizing multiplier (e.g., sqrt(2) = 1.4142).

        Returns
        -------
        float in [0, 1]
        """
        if levels <= 1:
            return 0.0
        # Compute exposure at each level: base * multiplier^k
        exposures = [multiplier ** k for k in range(levels + 1)]
        total = sum(exposures)
        if total <= 0:
            return 0.0
        # Deep threshold: top 30% of levels
        deep_start = max(1, int(math.ceil(len(exposures) * _DEEP_FRACTION)))
        deep_exposure = sum(exposures[deep_start:])
        return deep_exposure / total

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def state_dict(self) -> dict:
        return {
            'cycle_stresses': self._cycle_stresses[-1000:],
            'r_t': self._r_t,
            'all_bars': self._all_bars[-1000:],
            'all_level_gaps': self._all_level_gaps[-1000:],
            'all_cycle_gaps': self._all_cycle_gaps[-1000:],
        }

    def load_state_dict(self, d: dict) -> None:
        self._cycle_stresses = d.get('cycle_stresses', [])
        self._r_t = d.get('r_t', 0.0)
        self._all_bars = d.get('all_bars', [])
        self._all_level_gaps = d.get('all_level_gaps', [])
        self._all_cycle_gaps = d.get('all_cycle_gaps', [])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_structural_stress.py -v 2>&1 | head -30`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipelines/_shared/ARIA/structural_stress.py tests/unit/test_structural_stress.py
git commit -m "feat(aria): add StructuralStress module with X_i and C_i components"
```

---

### Task 2: U_i (time-under-stress) + V_i (rebound deficit)

**Files:**
- Modify: `pipelines/_shared/ARIA/structural_stress.py`
- Modify: `tests/unit/test_structural_stress.py`

- [ ] **Step 1: Write failing tests for U_i and V_i**

Append to `tests/unit/test_structural_stress.py`:

```python
class TestTimeUnderStress:
    """U_i: prolonged holding beyond reference duration."""

    def test_short_cycle_no_stress(self):
        ss = StructuralStress()
        ss._all_bars = [100, 120, 80, 110, 90]  # median = 100
        u = ss._compute_U(bars=80)
        assert u == 0.0

    def test_long_cycle_stress(self):
        ss = StructuralStress()
        ss._all_bars = [100, 120, 80, 110, 90]  # median = 100
        u = ss._compute_U(bars=300)
        assert u == pytest.approx(2.0, abs=0.01)  # (300 - 100) / 100

    def test_no_history_returns_zero(self):
        ss = StructuralStress()
        u = ss._compute_U(bars=500)
        assert u == 0.0  # no reference yet


class TestReboundDeficit:
    """V_i: insufficient rebound amplitude (PnL vs expected TP)."""

    def test_full_tp_no_deficit(self):
        ss = StructuralStress()
        v = ss._compute_V(pnl=50.0, expected_tp=50.0, reason='tp_hit')
        assert v == 0.0

    def test_partial_capture(self):
        ss = StructuralStress()
        v = ss._compute_V(pnl=25.0, expected_tp=50.0, reason='tp_hit')
        assert v == pytest.approx(0.5, abs=0.01)

    def test_bust_full_deficit(self):
        ss = StructuralStress()
        v = ss._compute_V(pnl=-100.0, expected_tp=50.0, reason='abort')
        assert v == 1.0  # capped at 1.0

    def test_zero_expected_tp(self):
        ss = StructuralStress()
        v = ss._compute_V(pnl=10.0, expected_tp=0.0, reason='tp_hit')
        assert v == 0.0  # no expectation, no deficit
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_structural_stress.py::TestTimeUnderStress -v 2>&1 | head -20`
Expected: AttributeError: `_compute_U` not found

- [ ] **Step 3: Implement U_i and V_i**

Add to `StructuralStress` class in `structural_stress.py`, after `_compute_C`:

```python
    def _compute_U(self, bars: int) -> float:
        """U_i: time-under-stress (normalised excess holding duration).

        Parameters
        ----------
        bars : int
            Candles the cycle was open.

        Returns
        -------
        float >= 0
            0 = at or below median, 2.0 = 3x median duration, etc.
        """
        if not self._all_bars:
            return 0.0
        median_bars = float(sorted(self._all_bars)[len(self._all_bars) // 2])
        if median_bars <= 0:
            return 0.0
        return max(0.0, (bars - median_bars) / median_bars)

    def _compute_V(self, pnl: float, expected_tp: float, reason: str) -> float:
        """V_i: rebound deficit (shortfall from expected TP profit).

        Parameters
        ----------
        pnl : float
            Realised cycle PnL.
        expected_tp : float
            Expected profit if cycle had hit full TP.
        reason : str
            Exit reason (tp_hit, abort, etc.).

        Returns
        -------
        float in [0, 1]
            0 = full TP captured, 1 = total deficit (loss or zero capture).
        """
        if expected_tp <= 0:
            return 0.0
        ratio = pnl / expected_tp
        return min(1.0, max(0.0, 1.0 - ratio))
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_structural_stress.py -v 2>&1 | head -30`
Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipelines/_shared/ARIA/structural_stress.py tests/unit/test_structural_stress.py
git commit -m "feat(aria): add U_i (time-under-stress) and V_i (rebound deficit) components"
```

---

### Task 3: F_i (entry clustering) + M_i (inter-cycle overlap)

**Files:**
- Modify: `pipelines/_shared/ARIA/structural_stress.py`
- Modify: `tests/unit/test_structural_stress.py`

- [ ] **Step 1: Write failing tests for F_i and M_i**

Append to `tests/unit/test_structural_stress.py`:

```python
class TestEntryClustering:
    """F_i: rapid level consumption (flash crash detector)."""

    def test_normal_spacing(self):
        ss = StructuralStress()
        ss._all_level_gaps = [50, 60, 40, 55, 45]  # median = 50
        # Level timestamps: bars 0, 60, 120, 180 (gaps = 60, 60, 60)
        f = ss._compute_F(level_timestamps=[0, 60, 120, 180])
        assert f == 0.0  # all gaps >= median(50), no clustering

    def test_rapid_consumption(self):
        ss = StructuralStress()
        ss._all_level_gaps = [50, 60, 40, 55, 45]  # median = 50
        # Level timestamps: bars 0, 5, 10, 15 (gaps = 5, 5, 5)
        f = ss._compute_F(level_timestamps=[0, 5, 10, 15])
        assert f == 1.0  # all gaps < median, 100% rapid

    def test_mixed_gaps(self):
        ss = StructuralStress()
        ss._all_level_gaps = [50, 60, 40, 55, 45]  # median = 50
        # Level timestamps: bars 0, 10, 70, 80 (gaps = 10, 60, 10)
        f = ss._compute_F(level_timestamps=[0, 10, 70, 80])
        assert f == pytest.approx(2.0 / 3.0, abs=0.01)  # 2 of 3 gaps rapid

    def test_single_level_no_clustering(self):
        ss = StructuralStress()
        ss._all_level_gaps = [50, 60, 40]
        f = ss._compute_F(level_timestamps=[0])
        assert f == 0.0  # only 1 level, no gaps to measure

    def test_no_history_returns_zero(self):
        ss = StructuralStress()
        f = ss._compute_F(level_timestamps=[0, 5, 10])
        assert f == 0.0  # no reference gaps yet


class TestInterCycleOverlap:
    """M_i: insufficient cooldown between cycles."""

    def test_adequate_cooldown(self):
        ss = StructuralStress()
        ss._all_cycle_gaps = [200, 300, 250, 180, 220]  # median = 220
        m = ss._compute_M(gap_bars=200)
        assert m == 0.0  # 200 >= 220 * 0.5 = 110

    def test_rushed_reentry(self):
        ss = StructuralStress()
        ss._all_cycle_gaps = [200, 300, 250, 180, 220]  # median = 220
        m = ss._compute_M(gap_bars=50)
        assert m == 1.0  # 50 < 220 * 0.5 = 110

    def test_no_history_returns_zero(self):
        ss = StructuralStress()
        m = ss._compute_M(gap_bars=5)
        assert m == 0.0  # no reference yet

    def test_first_cycle_no_gap(self):
        ss = StructuralStress()
        ss._all_cycle_gaps = [200]
        m = ss._compute_M(gap_bars=-1)
        assert m == 0.0  # negative gap = first cycle, no overlap
```

- [ ] **Step 2: Run to verify failures**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_structural_stress.py::TestEntryClustering -v 2>&1 | head -15`
Expected: AttributeError

- [ ] **Step 3: Implement F_i and M_i**

Add to `StructuralStress` class after `_compute_V`:

```python
    def _compute_F(self, level_timestamps: list) -> float:
        """F_i: entry clustering (fraction of rapid inter-level gaps).

        Parameters
        ----------
        level_timestamps : list of int
            Bar indices when each hedge level was triggered.

        Returns
        -------
        float in [0, 1]
            0 = all gaps normal, 1 = all gaps rapid.
        """
        if len(level_timestamps) < 2 or not self._all_level_gaps:
            return 0.0
        median_gap = float(sorted(self._all_level_gaps)[len(self._all_level_gaps) // 2])
        if median_gap <= 0:
            return 0.0
        gaps = [level_timestamps[k + 1] - level_timestamps[k]
                for k in range(len(level_timestamps) - 1)]
        rapid_count = sum(1 for g in gaps if g < median_gap)
        return rapid_count / len(gaps)

    def _compute_M(self, gap_bars: int) -> float:
        """M_i: inter-cycle overlap (insufficient cooldown).

        Parameters
        ----------
        gap_bars : int
            Bars between end of previous cycle and start of this cycle.
            Negative or -1 means first cycle (no prior).

        Returns
        -------
        float: 0.0 or 1.0 (binary indicator).
        """
        if gap_bars < 0 or not self._all_cycle_gaps:
            return 0.0
        median_gap = float(sorted(self._all_cycle_gaps)[len(self._all_cycle_gaps) // 2])
        if median_gap <= 0:
            return 0.0
        return 1.0 if gap_bars < median_gap * 0.5 else 0.0
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_structural_stress.py -v 2>&1 | head -40`
Expected: All 23 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipelines/_shared/ARIA/structural_stress.py tests/unit/test_structural_stress.py
git commit -m "feat(aria): add F_i (entry clustering) and M_i (inter-cycle overlap) components"
```

---

### Task 4: R(t) accumulator + record_cycle + derived signals

**Files:**
- Modify: `pipelines/_shared/ARIA/structural_stress.py`
- Modify: `tests/unit/test_structural_stress.py`

- [ ] **Step 1: Write failing tests for record_cycle and derived signals**

Append to `tests/unit/test_structural_stress.py`:

```python
class TestRecordCycle:
    """R(t) accumulator: record_cycle finalises all 6 components."""

    def _make_session(self, levels=2, bars=100, pnl=50.0, reason='tp_hit',
                      max_levels=12, multiplier=1.4142, expected_tp=50.0,
                      level_timestamps=None, gap_bars=-1):
        return {
            'levels': levels,
            'bars': bars,
            'pnl': pnl,
            'reason': reason,
            'max_levels': max_levels,
            'multiplier': multiplier,
            'expected_tp': expected_tp,
            'level_timestamps': level_timestamps or [0],
            'gap_bars': gap_bars,
        }

    def test_shallow_tp_minimal_stress(self):
        ss = StructuralStress()
        session = self._make_session(levels=1, bars=50, pnl=50.0)
        result = ss.record_cycle(session)
        assert result['total'] == pytest.approx(0.0, abs=0.01)
        assert ss.r_t == pytest.approx(0.0, abs=0.01)

    def test_deep_bust_high_stress(self):
        ss = StructuralStress()
        # Seed some history first so medians exist
        for _ in range(10):
            ss.record_cycle(self._make_session(levels=2, bars=100, pnl=50.0))

        # Now record a deep, long, busted cycle
        session = self._make_session(
            levels=10, bars=500, pnl=-200.0, reason='abort',
            level_timestamps=[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50],
            gap_bars=10,
        )
        result = ss.record_cycle(session)
        assert result['X'] > 0       # excess depth
        assert result['C'] > 0       # deep exposure concentration
        assert result['U'] > 0       # prolonged holding
        assert result['F'] > 0       # rapid entry clustering
        assert result['M'] == 1.0    # rushed re-entry
        assert result['V'] > 0       # rebound deficit (loss)
        assert result['total'] > 1.0 # significant stress
        assert ss.r_t > 1.0

    def test_r_t_accumulates(self):
        ss = StructuralStress()
        # Seed history
        for _ in range(5):
            ss.record_cycle(self._make_session())

        r1 = ss.r_t
        ss.record_cycle(self._make_session(levels=10, bars=500, pnl=-100.0, reason='abort'))
        r2 = ss.r_t
        assert r2 > r1  # R(t) only grows


class TestDerivedSignals:
    """Derived signals: normalised_rt, recent_stress_rate, stress_velocity."""

    def _seed(self, ss, n=20):
        for _ in range(n):
            ss.record_cycle({
                'levels': 2, 'bars': 100, 'pnl': 50.0, 'reason': 'tp_hit',
                'max_levels': 12, 'multiplier': 1.4142, 'expected_tp': 50.0,
                'level_timestamps': [0, 50], 'gap_bars': 200,
            })

    def test_normalised_rt(self):
        ss = StructuralStress()
        self._seed(ss, 20)
        nrt = ss.normalised_rt
        assert 0.0 <= nrt <= 1.0  # per-cycle average, should be small

    def test_recent_stress_rate(self):
        ss = StructuralStress()
        self._seed(ss, 20)
        rate = ss.recent_stress_rate
        assert rate >= 0.0

    def test_stress_velocity(self):
        ss = StructuralStress()
        self._seed(ss, 25)
        vel = ss.stress_velocity
        assert isinstance(vel, float)

    def test_inter_cycle_gap_ratio(self):
        ss = StructuralStress()
        self._seed(ss, 10)
        ratio = ss.inter_cycle_gap_ratio(last_gap=200)
        assert ratio >= 0.0
```

- [ ] **Step 2: Run to verify failures**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_structural_stress.py::TestRecordCycle -v 2>&1 | head -15`
Expected: AttributeError: `record_cycle` not found

- [ ] **Step 3: Implement record_cycle and derived signals**

Add to `StructuralStress` class:

```python
    # ------------------------------------------------------------------
    # Cycle recording (finalises all 6 components)
    # ------------------------------------------------------------------

    def record_cycle(self, session: dict) -> dict:
        """Compute all 6 stress components for a completed cycle.

        Parameters
        ----------
        session : dict
            Must contain: levels, bars, pnl, reason, max_levels,
            multiplier, expected_tp, level_timestamps, gap_bars.

        Returns
        -------
        dict with keys X, C, U, F, M, V, total.
        """
        levels = int(session.get('levels', 0))
        bars = int(session.get('bars', 0))
        pnl = float(session.get('pnl', 0.0))
        reason = session.get('reason', '')
        max_levels = int(session.get('max_levels', 12))
        multiplier = float(session.get('multiplier', 1.4142))
        expected_tp = float(session.get('expected_tp', 0.0))
        level_timestamps = session.get('level_timestamps', [])
        gap_bars = int(session.get('gap_bars', -1))

        X = self._compute_X(levels, max_levels)
        C = self._compute_C(levels, multiplier)
        U = self._compute_U(bars)
        F = self._compute_F(level_timestamps)
        M = self._compute_M(gap_bars)
        V = self._compute_V(pnl, expected_tp, reason)

        total = X + C + U + F + M + V

        stress = {'X': round(X, 6), 'C': round(C, 6), 'U': round(U, 6),
                  'F': round(F, 6), 'M': round(M, 6), 'V': round(V, 6),
                  'total': round(total, 6)}

        self._cycle_stresses.append(stress)
        self._r_t += total

        # Update reference statistics for future cycles
        self._all_bars.append(bars)
        if len(level_timestamps) >= 2:
            for k in range(len(level_timestamps) - 1):
                self._all_level_gaps.append(level_timestamps[k + 1] - level_timestamps[k])
        if gap_bars >= 0:
            self._all_cycle_gaps.append(gap_bars)

        # Cap history
        if len(self._all_bars) > 1000:
            self._all_bars = self._all_bars[-1000:]
        if len(self._all_level_gaps) > 1000:
            self._all_level_gaps = self._all_level_gaps[-1000:]
        if len(self._all_cycle_gaps) > 1000:
            self._all_cycle_gaps = self._all_cycle_gaps[-1000:]
        if len(self._cycle_stresses) > 1000:
            self._cycle_stresses = self._cycle_stresses[-1000:]

        return stress

    # ------------------------------------------------------------------
    # Derived signals (consumed by other ARIA layers)
    # ------------------------------------------------------------------

    @property
    def r_t(self) -> float:
        """Cumulative R(t) sum."""
        return self._r_t

    @property
    def normalised_rt(self) -> float:
        """Per-cycle average stress, clipped to [0, 1]."""
        n = len(self._cycle_stresses)
        if n == 0:
            return 0.0
        return min(1.0, self._r_t / n)

    @property
    def recent_stress_rate(self) -> float:
        """Mean per-cycle stress over last 10 cycles, clipped to [0, 1]."""
        recent = self._cycle_stresses[-10:]
        if not recent:
            return 0.0
        return min(1.0, sum(s['total'] for s in recent) / len(recent))

    @property
    def stress_velocity(self) -> float:
        """Rate of change: recent stress minus historical stress.

        Positive = stress increasing (active degradation).
        Negative = stress decreasing (recovery).
        """
        if len(self._cycle_stresses) < 20:
            return 0.0
        recent = self._cycle_stresses[-5:]
        older = self._cycle_stresses[-20:-5]
        recent_mean = sum(s['total'] for s in recent) / len(recent)
        older_mean = sum(s['total'] for s in older) / len(older)
        return recent_mean - older_mean

    def inter_cycle_gap_ratio(self, last_gap: int) -> float:
        """How rushed is the latest entry vs normal, normalised to [0, 1].

        Parameters
        ----------
        last_gap : int
            Bars since previous cycle ended.

        Returns
        -------
        float in [0, 1]: 0 = very rushed, 1 = normal or slower.
        """
        if not self._all_cycle_gaps or last_gap < 0:
            return 1.0  # no history, assume normal
        median_gap = float(sorted(self._all_cycle_gaps)[len(self._all_cycle_gaps) // 2])
        if median_gap <= 0:
            return 1.0
        ratio = last_gap / median_gap
        return min(1.0, ratio / 3.0)  # normalise: ratio 3+ maps to 1.0
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_structural_stress.py -v 2>&1 | tail -20`
Expected: All tests PASS (should be ~31 tests)

- [ ] **Step 5: Commit**

```bash
git add pipelines/_shared/ARIA/structural_stress.py tests/unit/test_structural_stress.py
git commit -m "feat(aria): add R(t) accumulator, record_cycle, and derived signals"
```

---

### Task 5: Observer enrichment — level_timestamps + start_bar + stress fields

**Files:**
- Modify: `pipelines/_shared/ARIA/observer.py`
- Modify: `tests/unit/test_structural_stress.py`

- [ ] **Step 1: Write failing test for Observer enrichment**

Append to `tests/unit/test_structural_stress.py`:

```python
from pipelines._shared.ARIA.observer import Observer


class TestObserverEnrichment:
    """Observer stores level_timestamps, start_bar, and stress decomposition."""

    def _mock_strategy(self):
        class S:
            balance = 10000.0
            hp = {'max_levels': 12, 'sizing_factor': 1.4142, 'tp_value': 1.0}
            vars = {'sessions': [{'levels': 2, 'pnl': 50.0, 'reason': 'tp_hit', 'bars': 100}]}
            candles = None
        return S()

    def test_record_level_timestamp(self):
        obs = Observer()
        obs.on_cycle_open(self._mock_strategy(), {'danger': 0.3, 'regime_id': 0}, start_bar=500)
        obs.record_level_timestamp(500)
        obs.record_level_timestamp(560)
        obs.record_level_timestamp(620)
        enriched = obs.on_cycle_end(self._mock_strategy(), {'danger': 0.4})
        assert enriched.get('level_timestamps') == [500, 560, 620]
        assert enriched.get('start_bar') == 500

    def test_stress_components_attached(self):
        obs = Observer()
        obs.on_cycle_open(self._mock_strategy(), {'danger': 0.3}, start_bar=100)
        enriched = obs.on_cycle_end(self._mock_strategy(), {'danger': 0.4})
        # stress_components will be None until StructuralStress attaches them
        # but the field should exist
        assert 'start_bar' in enriched
        assert 'level_timestamps' in enriched
```

- [ ] **Step 2: Run to verify failures**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_structural_stress.py::TestObserverEnrichment -v 2>&1 | head -15`
Expected: TypeError (unexpected keyword `start_bar`)

- [ ] **Step 3: Modify Observer to accept and store new fields**

In `pipelines/_shared/ARIA/observer.py`, modify `on_cycle_open` (line 60) to accept `start_bar`:

```python
    def on_cycle_open(
        self,
        strategy,
        market_state: dict,
        gate_confidence: Optional[float] = None,
        aria_score: Optional[float] = None,
        start_bar: Optional[int] = None,
    ) -> None:
        """Capture entry snapshot when a new trading cycle starts."""
        self._entry_snapshot = {
            'market_state_at_entry': _copy_state(market_state),
            'hp_used': dict(getattr(strategy, 'hp', {})),
            'regime_id_at_entry': market_state.get('regime_id', 0),
            'danger_at_entry': market_state.get('danger', 0.5),
            'gate_confidence': gate_confidence,
            'equity_at_entry': getattr(strategy, 'balance', 0.0),
            'aria_score_at_entry': aria_score,
            'ruin_probs': [],
            'start_bar': start_bar,
            'level_timestamps': [],
        }
```

Add `record_level_timestamp` method after `record_ruin_prob` (line 100):

```python
    def record_level_timestamp(self, bar_index: int) -> None:
        """Record the bar index when a new hedge level is triggered.

        Called by the pipeline each time the strategy opens a new level.
        """
        if self._entry_snapshot:
            self._entry_snapshot.setdefault('level_timestamps', []).append(bar_index)
```

In `on_cycle_end` (line 134), the `**self._entry_snapshot` spread already includes the new fields, so `level_timestamps` and `start_bar` will be in the enriched dict automatically. No change needed there.

- [ ] **Step 4: Run tests**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_structural_stress.py::TestObserverEnrichment -v 2>&1 | head -15`
Expected: PASS

Also run existing Observer tests to verify no regression:
Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_aria_pipeline.py -v 2>&1 | tail -20`

- [ ] **Step 5: Commit**

```bash
git add pipelines/_shared/ARIA/observer.py tests/unit/test_structural_stress.py
git commit -m "feat(aria): Observer enrichment — level_timestamps, start_bar fields"
```

---

### Task 6: Config updates + wire StructuralStress into ARIAPipeline

**Files:**
- Modify: `pipelines/_shared/ARIA/config.py`
- Modify: `pipelines/_shared/ARIA/__init__.py`

- [ ] **Step 1: Add config keys**

In `pipelines/_shared/ARIA/config.py`, add after line 30 (`'danger_abort_threshold': 0.8,`):

```python
        'stress_abort_threshold': 1.5,    # stress velocity above which to abort
        'stress_abort_min_level': 2,      # min depth before stress abort activates
```

- [ ] **Step 2: Wire StructuralStress into ARIAPipeline.__init__**

In `pipelines/_shared/ARIA/__init__.py`, add import at line 31 (after `from .shadow_tracker import ShadowTracker`):

```python
from .structural_stress import StructuralStress
```

In `__init__` method, add after Observer init (after line 104):

```python
        # StructuralStress — R(t) accumulator (Chen 2026)
        self._stress = StructuralStress()
```

- [ ] **Step 3: Wire into on_open_position — record start_bar and first level timestamp**

In `on_open_position` (line 250), modify the `_observer.on_cycle_open` call to pass `start_bar`:

```python
    def on_open_position(self, strategy) -> None:
        """L5: Observer captures entry snapshot with gate confidence."""
        self._cycle_active = True

        # Determine current bar index
        sv = getattr(strategy, 'vars', {})
        start_bar = int(sv.get('session_start_bar', getattr(strategy, 'index', 0)))

        # Observer records entry state
        self._observer.on_cycle_open(
            strategy,
            self._market_state,
            gate_confidence=self._gate_confidence,
            aria_score=self._aria_score if self._meta_enabled else None,
            start_bar=start_bar,
        )

        # Record first level timestamp (level 0 entry)
        self._observer.record_level_timestamp(start_bar)

        # Stats
        danger = self._market_state.get('danger', 0.5)
        ts = strategy.candles[-1][0] if strategy.candles is not None and len(strategy.candles) > 0 else 0
        self._stats.start_cycle(ts, danger)
```

- [ ] **Step 4: Wire into on_cycle_end — compute stress and attach to enriched session**

In `on_cycle_end` (line 267), after the Observer builds the enriched record (line 275-278), add stress computation:

```python
        # StructuralStress: compute R(t) components for this cycle
        if enriched:
            hp = getattr(strategy, 'hp', {})
            sv = getattr(strategy, 'vars', {})

            # Compute inter-cycle gap (bars since last cycle ended)
            sessions = sv.get('sessions', [])
            if len(sessions) >= 2:
                prev_bars = sessions[-2].get('bars', 0)
                prev_start = 0  # approximate: we don't have exact end bar
                # Use start_bar difference - previous duration as proxy
                gap_bars = enriched.get('start_bar', 0) - (self._last_cycle_end_bar or 0)
            else:
                gap_bars = -1

            # Estimate expected TP profit
            expected_tp = self._estimate_expected_tp(strategy, enriched)

            stress_input = {
                'levels': enriched.get('levels', 0),
                'bars': enriched.get('bars', 0),
                'pnl': pnl,
                'reason': enriched.get('reason', ''),
                'max_levels': int(hp.get('max_levels', 12)),
                'multiplier': float(hp.get('sizing_factor', 1.4142)),
                'expected_tp': expected_tp,
                'level_timestamps': enriched.get('level_timestamps', []),
                'gap_bars': gap_bars,
            }
            stress_result = self._stress.record_cycle(stress_input)
            enriched['stress_components'] = stress_result
            enriched['r_t'] = self._stress.r_t

            self._last_cycle_end_bar = getattr(strategy, 'index', 0)
```

Add `self._last_cycle_end_bar = 0` to `__init__` (after line 131):

```python
        self._last_cycle_end_bar: int = 0
```

Add the helper method for expected TP estimation (after `_boost_exploration`):

```python
    def _estimate_expected_tp(self, strategy, enriched: dict) -> float:
        """Estimate expected TP profit for V_i computation."""
        hp = getattr(strategy, 'hp', {})
        levels = enriched.get('levels', 0)
        base_size = float(hp.get('base_size_value', 1.0))
        multiplier = float(hp.get('sizing_factor', 1.4142))
        # Total position size across all levels
        total_size = sum(base_size * multiplier ** k for k in range(levels + 1))
        # TP distance in price terms (approximate from ATR)
        atr = self._shield._estimate_atr(strategy)
        tp_mult = float(hp.get('tp_value', 1.0))
        tp_distance = atr * tp_mult
        return total_size * tp_distance
```

- [ ] **Step 5: Run existing ARIA integration tests**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_aria_pipeline.py -v 2>&1 | tail -20`
Expected: All existing tests PASS (StructuralStress is additive, no existing behaviour changes)

- [ ] **Step 6: Commit**

```bash
git add pipelines/_shared/ARIA/config.py pipelines/_shared/ARIA/__init__.py pipelines/_shared/ARIA/observer.py
git commit -m "feat(aria): wire StructuralStress into pipeline lifecycle"
```

---

### Task 7: RiskShield stress-velocity abort

**Files:**
- Modify: `pipelines/_shared/ARIA/risk_shield.py`
- Modify: `pipelines/_shared/ARIA/__init__.py`
- Create: `tests/unit/test_aria_stress_integration.py`

- [ ] **Step 1: Write failing test for stress abort**

```python
# tests/unit/test_aria_stress_integration.py
"""Integration tests: StructuralStress feeding into RiskShield, CycleGate, MetaEvaluator."""

import pytest
from pipelines._shared.ARIA.risk_shield import RiskShield
from pipelines._shared.ARIA.structural_stress import StructuralStress


class TestStressAbort:
    """RiskShield aborts on high stress velocity."""

    def _mock_strategy(self, level=3, cycle_active=True):
        class S:
            balance = 10000.0
            price = 1.2000
            leverage = 30.0
            fee_rate = 0.00015
            is_open = True
            position = type('P', (), {'pnl': 0.0, 'is_cfd_mode': True})()
            hp = {'sizing_factor': 1.4142, 'base_size_value': 1.0, 'max_levels': 12,
                  'tp_value': 1.0, 'tp_atr_period': 14}
            vars = {'level': level, 'cycle_active': cycle_active, 'session_start_bar': 0}
            candles = None
        return S()

    def test_no_abort_low_velocity(self):
        shield = RiskShield({'stress_abort_threshold': 1.5, 'stress_abort_min_level': 2})
        strategy = self._mock_strategy(level=3)
        result = shield.check(strategy, {'danger': 0.3}, stress_velocity=0.1)
        # Should not abort for low stress velocity
        assert result is None or 'structural_stress' not in result.get('reason', '')

    def test_abort_high_velocity(self):
        shield = RiskShield({'stress_abort_threshold': 1.5, 'stress_abort_min_level': 2})
        strategy = self._mock_strategy(level=3)
        result = shield.check(strategy, {'danger': 0.3}, stress_velocity=2.0)
        assert result is not None
        assert 'structural_stress' in result['reason']

    def test_no_abort_shallow_level(self):
        shield = RiskShield({'stress_abort_threshold': 1.5, 'stress_abort_min_level': 2})
        strategy = self._mock_strategy(level=1)
        result = shield.check(strategy, {'danger': 0.3}, stress_velocity=2.0)
        # Level 1 < min_level 2, should not trigger stress abort
        assert result is None or 'structural_stress' not in result.get('reason', '')
```

- [ ] **Step 2: Run to verify failures**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_aria_stress_integration.py::TestStressAbort -v 2>&1 | head -15`
Expected: TypeError (unexpected keyword `stress_velocity`)

- [ ] **Step 3: Add stress_velocity parameter to RiskShield.check**

In `pipelines/_shared/ARIA/risk_shield.py`, modify `RiskShield.__init__` (line 286) to read new config:

```python
        self._stress_abort_threshold = float(cfg.get('stress_abort_threshold', 1.5))
        self._stress_abort_min_level = int(cfg.get('stress_abort_min_level', 2))
```

Modify `RiskShield.check` signature (line 308) to accept `stress_velocity`:

```python
    def check(self, strategy, market_state: Optional[dict] = None,
              stress_velocity: float = 0.0) -> Optional[dict]:
```

Add stress abort check after the danger abort block (after line 349, before line 351):

```python
        # --- Structural stress abort (Chen 2026 R(t)) ---
        if level >= self._stress_abort_min_level and stress_velocity > self._stress_abort_threshold:
            self._last_reason = 'structural_stress'
            return {'action': 'close_all', 'reason': f'structural_stress:{stress_velocity:.3f}_at_L{level}'}
```

- [ ] **Step 4: Wire stress_velocity into ARIAPipeline.suggest_exit**

In `pipelines/_shared/ARIA/__init__.py`, modify `suggest_exit` (line 208):

```python
    def suggest_exit(self, strategy) -> Optional[dict]:
        """L4: RiskShield checks conformal kill + liquidity + margin + stress."""
        if not getattr(strategy, 'is_open', False):
            return None

        result = self._shield.check(
            strategy, self._market_state,
            stress_velocity=self._stress.stress_velocity,
        )
```

- [ ] **Step 5: Run integration tests**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_aria_stress_integration.py -v 2>&1 | head -20`
Expected: All 3 tests PASS

Run existing tests for regression:
Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_aria_pipeline.py -v 2>&1 | tail -10`

- [ ] **Step 6: Commit**

```bash
git add pipelines/_shared/ARIA/risk_shield.py pipelines/_shared/ARIA/__init__.py tests/unit/test_aria_stress_integration.py
git commit -m "feat(aria): RiskShield stress-velocity abort from R(t)"
```

---

### Task 8: CycleGate — expand feature vector 17 -> 20

**Files:**
- Modify: `pipelines/_shared/ARIA/cycle_gate.py`
- Modify: `pipelines/_shared/ARIA/__init__.py`
- Modify: `tests/unit/test_aria_stress_integration.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_aria_stress_integration.py`:

```python
from pipelines._shared.ARIA.cycle_gate import CycleGate, _build_features
import numpy as np


class TestCycleGateStressFeatures:
    """CycleGate uses R(t) features for entry gating."""

    def _mock_strategy(self):
        class S:
            balance = 10000.0
            vars = {'sessions': [], 'consecutive_busts': 0}
            candles = np.array([[1609459200000, 1.2, 1.201, 1.202, 1.199, 100.0]])
        return S()

    def test_feature_vector_is_20d(self):
        ms = {'danger': 0.5, 'trend_strength': 0.4, 'volatility': 0.3,
              'efficiency': 0.5, 'regime_id': 0}
        stress_features = {'normalised_rt': 0.1, 'inter_cycle_gap_ratio': 0.8,
                           'recent_stress_rate': 0.05}
        x = _build_features(ms, self._mock_strategy(), stress_features=stress_features)
        assert x.shape == (20,)

    def test_stress_features_in_correct_slots(self):
        ms = {'danger': 0.5, 'trend_strength': 0.4, 'volatility': 0.3,
              'efficiency': 0.5, 'regime_id': 0}
        stress_features = {'normalised_rt': 0.25, 'inter_cycle_gap_ratio': 0.6,
                           'recent_stress_rate': 0.15}
        x = _build_features(ms, self._mock_strategy(), stress_features=stress_features)
        assert x[16] == pytest.approx(0.25)    # normalised_rt
        assert x[17] == pytest.approx(0.6)     # inter_cycle_gap_ratio
        assert x[18] == pytest.approx(0.15)    # recent_stress_rate
        assert x[19] == 1.0                     # bias (moved from 16 to 19)

    def test_backwards_compatible_no_stress(self):
        ms = {'danger': 0.5, 'trend_strength': 0.4, 'volatility': 0.3,
              'efficiency': 0.5, 'regime_id': 0}
        x = _build_features(ms, self._mock_strategy())
        assert x.shape == (20,)
        # Stress slots default to 0
        assert x[16] == 0.0
        assert x[17] == 0.0
        assert x[18] == 0.0
        assert x[19] == 1.0  # bias
```

- [ ] **Step 2: Run to verify failures**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_aria_stress_integration.py::TestCycleGateStressFeatures -v 2>&1 | head -15`
Expected: TypeError or shape mismatch

- [ ] **Step 3: Modify CycleGate feature vector**

In `pipelines/_shared/ARIA/cycle_gate.py`:

Change constant (line 36):
```python
_N_FEATURES = 20          # 4 market + 5 regime + 3 account + 4 session + 3 stress + 1 bias
```

Modify `_build_features` signature (line 104) to accept stress features:

```python
def _build_features(
    market_state: dict,
    strategy,
    *,
    k_max: int = _K_MAX_DEFAULT,
    peak_equity: float = 0.0,
    stress_features: Optional[dict] = None,
) -> np.ndarray:
```

Replace the bias section (lines 182-183) with stress features + bias:

```python
    # --- 3 stress features [16:19] (Chen 2026 R(t)) ---
    sf = stress_features or {}
    x[16] = min(1.0, max(0.0, float(sf.get('normalised_rt', 0.0))))
    x[17] = min(1.0, max(0.0, float(sf.get('inter_cycle_gap_ratio', 0.0))))
    x[18] = min(1.0, max(0.0, float(sf.get('recent_stress_rate', 0.0))))

    # --- 1 bias [19] ---
    x[19] = 1.0

    return x
```

Add import at top of file (after line 27):
```python
from typing import Optional, Tuple
```

(Check: `Optional` is already imported on line 27. Good.)

Modify `CycleGate.__init__` (the `_weights` initialization) to use 20:

In the `__init__` method, the weights array must match `_N_FEATURES`. Find where `self._weights` is initialized (should use `_N_FEATURES`). The constant change handles this automatically.

Modify `CycleGate.predict` to pass stress_features through:

```python
    def predict(self, market_state: dict, strategy,
                stress_features: Optional[dict] = None) -> float:
        x = _build_features(
            market_state, strategy,
            k_max=self._k_max, peak_equity=self._peak_equity,
            stress_features=stress_features,
        )
        z = float(np.dot(self._weights, x))
        return _sigmoid(z)
```

Similarly for `gate` and `update` — they need to accept and forward `stress_features`.

- [ ] **Step 4: Wire stress features from ARIAPipeline into CycleGate**

In `pipelines/_shared/ARIA/__init__.py`, modify `gate_entry` (line 176):

```python
    def gate_entry(self, strategy) -> bool:
        """L2: CycleGate predicts P(profitable) and blocks low-confidence entries."""
        if self._candle_count <= self._candle_warmup:
            return True

        danger = self._market_state.get('danger', 0.5)
        ts = strategy.candles[-1][0] if strategy.candles is not None and len(strategy.candles) > 0 else 0

        # Build stress features for CycleGate
        sv = getattr(strategy, 'vars', {})
        sessions = sv.get('sessions', [])
        last_end_bar = self._last_cycle_end_bar
        current_bar = getattr(strategy, 'index', 0)
        last_gap = current_bar - last_end_bar if last_end_bar > 0 else -1

        stress_features = {
            'normalised_rt': self._stress.normalised_rt,
            'inter_cycle_gap_ratio': self._stress.inter_cycle_gap_ratio(last_gap),
            'recent_stress_rate': self._stress.recent_stress_rate,
        }

        if self._gate_enabled:
            allowed, confidence = self._gate.gate(
                self._market_state, strategy, stress_features=stress_features)
            self._gate_confidence = confidence
            threshold = self._gate.threshold
        else:
            allowed = True
            self._gate_confidence = None
            threshold = None

        self._stats.record_gate(ts, danger, allowed=allowed, threshold=threshold)

        if not allowed:
            self._shadow.on_gate_block(
                strategy, self._market_state,
                gate_confidence=self._gate_confidence,
                hp_snapshot=self._hp_selection,
            )

        return allowed
```

Also modify the `on_cycle_end` call to `_gate.update` to pass stress features:

```python
        if self._gate_enabled:
            stress_features = {
                'normalised_rt': self._stress.normalised_rt,
                'inter_cycle_gap_ratio': self._stress.inter_cycle_gap_ratio(gap_bars),
                'recent_stress_rate': self._stress.recent_stress_rate,
            }
            self._gate.update(self._market_state, strategy, profitable,
                              stress_features=stress_features)
```

- [ ] **Step 5: Run all tests**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_aria_stress_integration.py tests/unit/test_structural_stress.py tests/unit/test_aria_pipeline.py -v 2>&1 | tail -20`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add pipelines/_shared/ARIA/cycle_gate.py pipelines/_shared/ARIA/__init__.py tests/unit/test_aria_stress_integration.py
git commit -m "feat(aria): CycleGate expanded to 20D with R(t) stress features"
```

---

### Task 9: MetaEvaluator — stress penalty in ARIA score

**Files:**
- Modify: `pipelines/_shared/ARIA/meta_evaluator.py`
- Modify: `pipelines/_shared/ARIA/__init__.py`
- Modify: `tests/unit/test_aria_stress_integration.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_aria_stress_integration.py`:

```python
from pipelines._shared.ARIA.meta_evaluator import MetaEvaluator


class TestMetaStressPenalty:
    """MetaEvaluator penalises rising structural stress in ARIA score."""

    def _make_sessions(self, n=20, stress_rate=0.05):
        return [
            {'reason': 'tp_hit', 'levels': 1, 'pnl': 50.0,
             'gate_confidence': 0.6, 'equity_at_entry': 10000,
             'stress_components': {'total': stress_rate}}
            for _ in range(n)
        ]

    def test_low_stress_no_penalty(self):
        meta = MetaEvaluator({'window': 20})
        sessions = self._make_sessions(20, stress_rate=0.01)
        score = meta.evaluate(sessions, stress_rate=0.01, baseline_stress_rate=0.01)
        # No stress penalty when rate == baseline
        assert score > 0

    def test_high_stress_penalised(self):
        meta = MetaEvaluator({'window': 20})
        sessions = self._make_sessions(20, stress_rate=0.5)
        score_low = meta.evaluate(sessions, stress_rate=0.01, baseline_stress_rate=0.01)
        score_high = meta.evaluate(sessions, stress_rate=0.8, baseline_stress_rate=0.01)
        assert score_high < score_low  # higher stress = lower score
```

- [ ] **Step 2: Run to verify failures**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_aria_stress_integration.py::TestMetaStressPenalty -v 2>&1 | head -15`
Expected: TypeError (unexpected keyword `stress_rate`)

- [ ] **Step 3: Modify MetaEvaluator.evaluate to accept stress parameters**

In `pipelines/_shared/ARIA/meta_evaluator.py`, modify `evaluate` (line 65):

```python
    def evaluate(self, enriched_sessions: list,
                 initial_capital: float = 10_000.0,
                 stress_rate: float = 0.0,
                 baseline_stress_rate: float = 0.0) -> float:
```

Replace the score formula (lines 112-116):

```python
        # 4. Stress rate penalty (Chen 2026 R(t))
        stress_penalty = min(1.0, max(0.0, stress_rate - baseline_stress_rate))

        score = (
            survival_efficiency * 0.35
            - bust_penalty * 0.25
            + cvar_normalised * 0.25
            - stress_penalty * 0.15
        )
```

- [ ] **Step 4: Wire stress into ARIAPipeline.on_cycle_end MetaEvaluator call**

In `pipelines/_shared/ARIA/__init__.py`, modify the MetaEvaluator call in `on_cycle_end` (around line 308-312):

```python
        if self._meta_enabled:
            initial_capital = self._observer.sessions[0].get('equity_at_entry', 10_000) if self._observer.sessions else 10_000

            # Compute baseline stress rate (first 50 cycles after warmup)
            stresses = self._stress._cycle_stresses
            if len(stresses) > 50:
                baseline = sum(s['total'] for s in stresses[:50]) / 50
            else:
                baseline = self._stress.recent_stress_rate

            self._aria_score = self._meta.evaluate(
                self._observer.sessions, initial_capital,
                stress_rate=self._stress.recent_stress_rate,
                baseline_stress_rate=baseline,
            )

            if self._meta.should_boost_exploration() and self._hp_engine_enabled:
                self._boost_exploration()
```

- [ ] **Step 5: Run all tests**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_aria_stress_integration.py tests/unit/test_structural_stress.py tests/unit/test_aria_pipeline.py -v 2>&1 | tail -20`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add pipelines/_shared/ARIA/meta_evaluator.py pipelines/_shared/ARIA/__init__.py tests/unit/test_aria_stress_integration.py
git commit -m "feat(aria): MetaEvaluator stress penalty in ARIA score formula"
```

---

### Task 10: Persistence + get_stats + final integration test

**Files:**
- Modify: `pipelines/_shared/ARIA/__init__.py`
- Modify: `tests/unit/test_aria_stress_integration.py`

- [ ] **Step 1: Add StructuralStress to save_state/load_state and get_stats**

In `pipelines/_shared/ARIA/__init__.py`, find `save_state` (around line 489) and add stress to the state dict:

In the method that builds the state dict for serialisation, add:
```python
            'stress': self._stress.state_dict(),
```

In `load_state`, add:
```python
        if 'stress' in state:
            self._stress.load_state_dict(state['stress'])
```

In `get_stats` (around line 336), add after the shield stats:

```python
        # ── Structural Stress (R(t)) ──
        stats['structural_stress'] = {
            'r_t': round(self._stress.r_t, 4),
            'normalised_rt': round(self._stress.normalised_rt, 4),
            'recent_stress_rate': round(self._stress.recent_stress_rate, 4),
            'stress_velocity': round(self._stress.stress_velocity, 4),
            'n_cycles': len(self._stress._cycle_stresses),
            'last_cycle_stress': self._stress._cycle_stresses[-1] if self._stress._cycle_stresses else None,
        }
```

- [ ] **Step 2: Write final integration test**

Append to `tests/unit/test_aria_stress_integration.py`:

```python
from pipelines._shared.ARIA import ARIAPipeline
import numpy as np


class TestFullPipelineIntegration:
    """End-to-end: ARIA pipeline with StructuralStress active."""

    def _make_candles(self, n=600, seed=42):
        np.random.seed(seed)
        ts = np.arange(n) * 300_000 + 1609459200000
        opens = 1.2000 + np.cumsum(np.random.randn(n) * 0.0005)
        closes = opens + np.random.randn(n) * 0.0003
        highs = np.maximum(opens, closes) + np.abs(np.random.randn(n) * 0.0002)
        lows = np.minimum(opens, closes) - np.abs(np.random.randn(n) * 0.0002)
        volume = np.random.randint(100, 1000, n).astype(float)
        return np.column_stack([ts, opens, closes, highs, lows, volume])

    def test_stress_in_stats(self):
        pipe = ARIAPipeline()
        stats = pipe.get_stats()
        assert 'structural_stress' in stats
        assert stats['structural_stress']['r_t'] == 0.0
        assert stats['structural_stress']['n_cycles'] == 0

    def test_persistence_roundtrip(self):
        pipe = ARIAPipeline()
        # Manually add some stress history
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
        assert len(pipe2._stress._cycle_stresses) == 1
```

- [ ] **Step 3: Run all tests**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_structural_stress.py tests/unit/test_aria_stress_integration.py tests/unit/test_aria_pipeline.py -v 2>&1 | tail -30`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add pipelines/_shared/ARIA/__init__.py tests/unit/test_aria_stress_integration.py
git commit -m "feat(aria): StructuralStress persistence, stats, and integration tests"
```

---

### Task 11: Observer — record_level_timestamp hook from strategy

**Files:**
- Modify: `pipelines/_shared/ARIA/__init__.py`

This is the final wiring: the pipeline needs to detect when the strategy opens a new hedge level and call `observer.record_level_timestamp()`. The strategy calls `update_position()` which triggers new hedges. The pipeline's `on_before()` runs every candle and can detect level changes.

- [ ] **Step 1: Add level tracking to on_before**

In `pipelines/_shared/ARIA/__init__.py`, add to `__init__`:

```python
        self._last_observed_level: int = 0
```

In `on_before`, after danger recording (after line 172), add:

```python
        # Track level changes for Observer level_timestamps
        if self._cycle_active:
            sv = getattr(strategy, 'vars', {})
            current_level = int(sv.get('level', 0))
            if current_level > self._last_observed_level:
                bar_index = getattr(strategy, 'index', 0)
                for lvl in range(self._last_observed_level + 1, current_level + 1):
                    self._observer.record_level_timestamp(bar_index)
                self._last_observed_level = current_level
```

In `on_open_position`, set:
```python
        self._last_observed_level = 0
```

In `on_cycle_end`, reset:
```python
        self._last_observed_level = 0
```

- [ ] **Step 2: Run all tests**

Run: `cd /Users/naresh/Documents/Research/qengine && python -m pytest tests/unit/test_structural_stress.py tests/unit/test_aria_stress_integration.py tests/unit/test_aria_pipeline.py -v 2>&1 | tail -20`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add pipelines/_shared/ARIA/__init__.py
git commit -m "feat(aria): auto-detect level changes for Observer level_timestamps"
```

---

## Summary

| Task | What it builds | Tests |
|---|---|---|
| 1 | StructuralStress + X_i + C_i | 7 unit tests |
| 2 | U_i + V_i | 7 unit tests |
| 3 | F_i + M_i | 9 unit tests |
| 4 | R(t) accumulator + record_cycle + derived signals | 8 unit tests |
| 5 | Observer enrichment | 2 unit tests |
| 6 | Config + pipeline wiring | Existing tests |
| 7 | RiskShield stress abort | 3 integration tests |
| 8 | CycleGate 17 -> 20 features | 3 integration tests |
| 9 | MetaEvaluator stress penalty | 2 integration tests |
| 10 | Persistence + stats + full integration | 2 integration tests |
| 11 | Level timestamp auto-detection | Existing tests |

**Total: ~43 new tests across 11 tasks.**
