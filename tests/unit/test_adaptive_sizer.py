"""Tests for the AdaptiveSizer component."""

import os
import tempfile

import numpy as np
import pytest

from qengine.framework.components.adaptive_sizer import AdaptiveSizer


class TestAdaptiveSizer:
    def test_full_confidence_no_drawdown(self):
        """Full confidence, no drawdown -> near base quantity."""
        sizer = AdaptiveSizer()
        result = sizer.compute(
            base_pct=2.0,
            confidence=1.0,
            sensitivity=1.0,
            drawdown_pct=0.0,
            recovery_aggression=0.5,
            balance=10000,
            qty=100,
        )
        # 1.0^1.0 * 1.0 = 1.0 -> qty stays at 100
        assert result == pytest.approx(100.0)

    def test_low_confidence_reduces(self):
        """Low confidence should reduce the quantity."""
        sizer = AdaptiveSizer()
        result = sizer.compute(
            base_pct=2.0,
            confidence=0.5,
            sensitivity=1.0,
            drawdown_pct=0.0,
            recovery_aggression=0.5,
            balance=10000,
            qty=100,
        )
        # 0.5^1.0 = 0.5 -> qty = 50
        assert result < 100.0
        assert result == pytest.approx(50.0)

    def test_high_sensitivity_amplifies(self):
        """Higher sensitivity amplifies the confidence effect."""
        sizer = AdaptiveSizer()
        r_low = sizer.compute(
            base_pct=2.0, confidence=0.5, sensitivity=1.0,
            drawdown_pct=0.0, recovery_aggression=0.5,
            balance=10000, qty=100,
        )
        r_high = sizer.compute(
            base_pct=2.0, confidence=0.5, sensitivity=2.0,
            drawdown_pct=0.0, recovery_aggression=0.5,
            balance=10000, qty=100,
        )
        # 0.5^2.0 = 0.25 < 0.5^1.0 = 0.5
        assert r_high < r_low

    def test_drawdown_reduces(self):
        """Drawdown beyond threshold should reduce quantity."""
        sizer = AdaptiveSizer(config={"drawdown_threshold_pct": 5.0})
        r_no_dd = sizer.compute(
            base_pct=2.0, confidence=1.0, sensitivity=1.0,
            drawdown_pct=0.0, recovery_aggression=0.5,
            balance=10000, qty=100,
        )
        r_dd = sizer.compute(
            base_pct=2.0, confidence=1.0, sensitivity=1.0,
            drawdown_pct=10.0, recovery_aggression=0.5,
            balance=10000, qty=100,
        )
        assert r_dd < r_no_dd

    def test_extreme_drawdown_hits_floor(self):
        """Extreme drawdown should hit the min_drawdown_scale floor."""
        sizer = AdaptiveSizer(config={
            "drawdown_threshold_pct": 5.0,
            "min_drawdown_scale": 0.1,
        })
        result = sizer.compute(
            base_pct=2.0, confidence=1.0, sensitivity=1.0,
            drawdown_pct=50.0, recovery_aggression=1.0,
            balance=10000, qty=100,
        )
        # Very large drawdown -> drawdown_factor = min_drawdown_scale = 0.1
        # qty * 1.0 * 0.1 = 10
        assert result == pytest.approx(10.0)

    def test_never_returns_zero(self):
        """Even with minimum everything, result should be > 0."""
        sizer = AdaptiveSizer()
        result = sizer.compute(
            base_pct=0.1, confidence=0.01, sensitivity=2.0,
            drawdown_pct=99.0, recovery_aggression=1.0,
            balance=10000, qty=100,
        )
        assert result > 0.0
        # Floor is qty * 0.01 = 1.0
        assert result >= 1.0

    def test_stats_tracking(self):
        """Stats should track calls and averages."""
        sizer = AdaptiveSizer()
        sizer.compute(
            base_pct=2.0, confidence=1.0, sensitivity=1.0,
            drawdown_pct=0.0, recovery_aggression=0.5,
            balance=10000, qty=100,
        )
        sizer.compute(
            base_pct=2.0, confidence=0.5, sensitivity=1.0,
            drawdown_pct=0.0, recovery_aggression=0.5,
            balance=10000, qty=100,
        )
        stats = sizer.get_stats()
        assert stats["calls"] == 2
        assert stats["avg_confidence_scale"] == pytest.approx(0.75)  # (1.0 + 0.5) / 2
        assert stats["avg_drawdown_factor"] == pytest.approx(1.0)

    def test_risk_cap(self):
        """Result should be capped by max_risk_per_cycle_pct of balance."""
        sizer = AdaptiveSizer(config={"max_risk_per_cycle_pct": 1.0})
        result = sizer.compute(
            base_pct=2.0, confidence=1.0, sensitivity=1.0,
            drawdown_pct=0.0, recovery_aggression=0.5,
            balance=1000, qty=100,
        )
        # max_qty = 1000 * 0.01 = 10
        assert result == pytest.approx(10.0)

    def test_save_load_roundtrip(self):
        sizer = AdaptiveSizer(config={"drawdown_threshold_pct": 3.0})
        sizer.compute(
            base_pct=2.0, confidence=0.8, sensitivity=1.0,
            drawdown_pct=0.0, recovery_aggression=0.5,
            balance=10000, qty=100,
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            sizer.save(path)
            loaded = AdaptiveSizer.load(path)
            assert loaded.drawdown_threshold_pct == 3.0
            assert loaded.get_stats()["calls"] == 1
        finally:
            os.unlink(path)
