"""
Tests for SurefireHedgeV2 strategy and SafetySizing module.
"""
import pytest
import sys
import os
import math

# Import SafetySizing directly to avoid qengine __init__ (Redis dependency)
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "safety_sizing",
    os.path.join(os.path.dirname(__file__), '..', 'qengine', 'services', 'safety_sizing.py')
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SafetySizing = _mod.SafetySizing


class TestSafetySizing:

    def setup_method(self):
        self.ss = SafetySizing(max_risk_per_cycle_pct=0.15)

    # -- max_exposure_units --

    def test_max_exposure_multiplier_2_levels_5(self):
        # 1 + 2 + 4 + 8 + 16 = 31
        exposure = self.ss.max_exposure_units(1.0, 2.0, 5)
        assert exposure == pytest.approx(31.0)

    def test_max_exposure_multiplier_3_levels_4(self):
        # 1 + 3 + 9 + 27 = 40
        exposure = self.ss.max_exposure_units(1.0, 3.0, 4)
        assert exposure == pytest.approx(40.0)

    def test_max_exposure_multiplier_1(self):
        # Special case: multiplier=1, all legs same size
        exposure = self.ss.max_exposure_units(1.0, 1.0, 5)
        assert exposure == pytest.approx(5.0)

    def test_max_exposure_scales_with_initial_size(self):
        exposure_1 = self.ss.max_exposure_units(1.0, 2.0, 5)
        exposure_10 = self.ss.max_exposure_units(10.0, 2.0, 5)
        assert exposure_10 == pytest.approx(exposure_1 * 10.0)

    # -- worst_case_loss --

    def test_worst_case_loss_basic(self):
        # 5 levels, multiplier=2, hedge=10 pips, pip_value=10
        # Level 0: 1 * 10 * 10 = 100
        # Level 1: 2 * 10 * 10 = 200
        # Level 2: 4 * 10 * 10 = 400
        # Level 3: 8 * 10 * 10 = 800
        # Level 4: 16 * 10 * 10 = 1600
        # Total = 3100
        loss = self.ss.worst_case_loss(1.0, 2.0, 5, 10.0, 10.0)
        assert loss == pytest.approx(3100.0)

    def test_worst_case_loss_single_level(self):
        loss = self.ss.worst_case_loss(1.0, 2.0, 1, 10.0, 10.0)
        assert loss == pytest.approx(100.0)

    # -- max_safe_initial_size --

    def test_max_safe_size(self):
        # balance=10000, max_risk=15% → max loss allowed = 1500
        # worst_case per unit = worst_case_loss(1.0, 2.0, 5, 10.0, 10.0) = 3100
        # max_safe = 1500 / 3100 ≈ 0.4839
        max_safe = self.ss.max_safe_initial_size(10000, 2.0, 5, 10.0, 10.0)
        assert max_safe == pytest.approx(1500 / 3100, rel=1e-4)

    def test_max_safe_size_larger_balance(self):
        safe_10k = self.ss.max_safe_initial_size(10000, 2.0, 5, 10.0, 10.0)
        safe_20k = self.ss.max_safe_initial_size(20000, 2.0, 5, 10.0, 10.0)
        assert safe_20k == pytest.approx(safe_10k * 2.0, rel=1e-4)

    # -- can_afford_cycle --

    def test_can_afford_small_size(self):
        assert self.ss.can_afford_cycle(10000, 0.1, 2.0, 5, 10.0, 10.0) is True

    def test_cannot_afford_large_size(self):
        assert self.ss.can_afford_cycle(10000, 10.0, 2.0, 5, 10.0, 10.0) is False

    # -- dynamic_size --

    def test_dynamic_size_caps_to_safe(self):
        max_safe = self.ss.max_safe_initial_size(10000, 2.0, 5, 10.0, 10.0)
        # Request more than safe → capped
        result = self.ss.dynamic_size(10000, 100.0, 2.0, 5, 10.0, 10.0)
        assert result == pytest.approx(max_safe, rel=1e-4)

    def test_dynamic_size_preserves_small(self):
        # Request less than safe → kept as-is
        result = self.ss.dynamic_size(10000, 0.01, 2.0, 5, 10.0, 10.0)
        assert result == pytest.approx(0.01)

    # -- exposure_ratio --

    def test_exposure_ratio_dangerous(self):
        # 10.0 initial, multiplier 2, 5 levels → huge exposure
        ratio = self.ss.exposure_ratio(10.0, 2.0, 5, 10000, 10.0, 10.0)
        assert ratio > 1.0  # certain ruin

    def test_exposure_ratio_safe(self):
        ratio = self.ss.exposure_ratio(0.01, 2.0, 5, 10000, 10.0, 10.0)
        assert ratio < 0.01  # very safe

    # -- levels_affordable --

    def test_levels_affordable(self):
        levels = self.ss.levels_affordable(10000, 1.0, 2.0, 10.0, 10.0)
        # With 15% of 10000 = 1500 max loss
        # Level 0: 100, Level 1: 200, Level 2: 400, Level 3: 800 → cumulative 1500
        # Level 3 would push to 1500, so 3 levels affordable (0, 1, 2)
        # Actually: 0→100, 1→300, 2→700, 3→1500 (exactly at limit)
        # 4→3100 (exceeds)
        assert levels == 4  # levels 0-3 fit within budget

    # -- Edge cases --

    def test_zero_balance(self):
        assert self.ss.max_safe_initial_size(0, 2.0, 5, 10.0, 10.0) == 0.0
        assert self.ss.can_afford_cycle(0, 1.0, 2.0, 5, 10.0, 10.0) is False
        assert self.ss.exposure_ratio(1.0, 2.0, 5, 0, 10.0, 10.0) == float('inf')

    def test_zero_hedge_pips(self):
        loss = self.ss.worst_case_loss(1.0, 2.0, 5, 0, 10.0)
        assert loss == 0.0
        assert self.ss.max_safe_initial_size(10000, 2.0, 5, 0, 10.0) == 0.0

