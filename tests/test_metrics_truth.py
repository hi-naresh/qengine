"""
Ground-truth tests for qengine financial metrics.

Every test uses hand-calculated expected values with comments showing the math.
No backtest engine is used -- metric functions are called directly with synthetic data.
"""

import numpy as np
import pandas as pd
import pytest

from qengine.services.metrics import (
    _prepare_returns,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
    calmar_ratio,
    cagr,
    omega_ratio,
    calculate_max_underwater_period,
    _max_consecutive,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_returns_series(returns, start="2025-01-01"):
    """Create a DatetimeIndex pd.Series from a list of daily returns."""
    idx = pd.date_range(start=start, periods=len(returns), freq="D")
    return pd.Series(returns, index=idx, dtype=float)


def _balance_to_returns(balances, start="2025-01-01"):
    """Convert a list of daily balances to a pct_change Series (first entry is NaN)."""
    idx = pd.date_range(start=start, periods=len(balances), freq="D")
    return pd.Series(balances, index=idx, dtype=float).pct_change()


# ===========================================================================
# TestPrepareReturns
# ===========================================================================

class TestPrepareReturns:
    """Verify _prepare_returns: NaN dropping and risk-free subtraction."""

    def test_drops_nan(self):
        # pct_change on [100, 110, 105] gives [NaN, 0.1, -0.04545...]
        s = pd.Series([100.0, 110.0, 105.0]).pct_change()
        result = _prepare_returns(s)
        assert len(result) == 2
        assert not result.isna().any()

    def test_rf_subtraction(self):
        # rf=0.05, periods=252 => daily_rf = 0.05/252 = 0.00019841...
        # returns = [0.01, 0.02] => adjusted = [0.01 - 0.000198, 0.02 - 0.000198]
        s = _make_returns_series([0.01, 0.02])
        daily_rf = 0.05 / 252
        result = _prepare_returns(s, rf=0.05, periods=252)
        assert result.iloc[0] == pytest.approx(0.01 - daily_rf, abs=1e-10)
        assert result.iloc[1] == pytest.approx(0.02 - daily_rf, abs=1e-10)

    def test_rf_zero_is_noop(self):
        s = _make_returns_series([0.01, -0.005])
        result = _prepare_returns(s, rf=0.0)
        assert result.iloc[0] == pytest.approx(0.01, abs=1e-10)
        assert result.iloc[1] == pytest.approx(-0.005, abs=1e-10)

    def test_dataframe_input(self):
        # If passed a DataFrame, should extract first column
        df = pd.DataFrame({"a": [0.01, 0.02], "b": [0.03, 0.04]})
        result = _prepare_returns(df)
        assert len(result) == 2
        assert result.iloc[0] == pytest.approx(0.01, abs=1e-10)


# ===========================================================================
# TestMaxDrawdown
# ===========================================================================

class TestMaxDrawdown:
    """Verify max_drawdown against hand-calculated values."""

    def test_single_decline(self):
        # Balances: [100, 110, 90, 95, 105]
        # Returns:  [NaN, 0.10, -0.18182, 0.05556, 0.10526]
        # Cumulative product of (1+r): [1.10, 0.90, 0.95, 1.05]
        # Prepend 1.0: [1.0, 1.10, 0.90, 0.95, 1.05]
        # Running max:  [1.0, 1.10, 1.10, 1.10, 1.10]
        # Ratio:        [1.0, 1.0, 0.8182, 0.8636, 0.9545]
        # Min ratio: 0.8182 => drawdown = 0.8182 - 1 = -0.18182
        returns = _balance_to_returns([100, 110, 90, 95, 105])
        result = max_drawdown(returns).iloc[0]
        # Hand: peak=110, trough=90 => dd = (90-110)/110 = -18.18%
        assert result == pytest.approx(-0.18182, abs=1e-4)

    def test_always_up(self):
        # Balances: [100, 105, 110, 120]
        # Never declines, drawdown = 0
        returns = _balance_to_returns([100, 105, 110, 120])
        result = max_drawdown(returns).iloc[0]
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_flat(self):
        # Balances: [100, 100, 100]
        # Returns: [NaN, 0.0, 0.0] => cumprod = [1.0, 1.0], prepend => [1.0, 1.0, 1.0]
        # drawdown = 0
        returns = _balance_to_returns([100, 100, 100])
        result = max_drawdown(returns).iloc[0]
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_recover_then_drop(self):
        # Balances: [100, 120, 110, 130, 100]
        # Returns: [NaN, 0.20, -0.08333, 0.18182, -0.23077]
        # Cumprod: [1.20, 1.10, 1.30, 1.00]
        # Prepend: [1.0, 1.20, 1.10, 1.30, 1.00]
        # Running max: [1.0, 1.20, 1.20, 1.30, 1.30]
        # Ratio: [1.0, 1.0, 0.9167, 1.0, 0.7692]
        # Min ratio: 0.7692 => dd = -0.23077
        # Hand: peak=130, trough=100 => dd = (100-130)/130 = -23.077%
        returns = _balance_to_returns([100, 120, 110, 130, 100])
        result = max_drawdown(returns).iloc[0]
        assert result == pytest.approx(-0.23077, abs=1e-4)

    def test_total_loss(self):
        # Balances: [100, 50, 10]
        # Returns: [NaN, -0.50, -0.80]
        # Cumprod: [0.50, 0.10], prepend: [1.0, 0.50, 0.10]
        # Max: [1.0, 1.0, 1.0], ratio: [1.0, 0.50, 0.10]
        # dd = 0.10 - 1 = -0.90
        returns = _balance_to_returns([100, 50, 10])
        result = max_drawdown(returns).iloc[0]
        assert result == pytest.approx(-0.90, abs=1e-10)

    def test_empty_returns(self):
        returns = pd.Series([], dtype=float)
        result = max_drawdown(returns).iloc[0]
        assert result == pytest.approx(0.0, abs=1e-10)


# ===========================================================================
# TestSharpeRatio
# ===========================================================================

class TestSharpeRatio:
    """Verify sharpe_ratio against hand-calculated values."""

    def test_basic(self):
        # Returns: [0.01, -0.005, 0.02, -0.01, 0.015]
        # mean = (0.01 - 0.005 + 0.02 - 0.01 + 0.015) / 5 = 0.03 / 5 = 0.006
        # std(ddof=1):
        #   deviations: [0.004, -0.011, 0.014, -0.016, 0.009]
        #   sum_sq = 0.000016 + 0.000121 + 0.000196 + 0.000256 + 0.000081 = 0.000670
        #   var = 0.000670 / 4 = 0.0001675
        #   std = sqrt(0.0001675) = 0.012942
        # daily_sharpe = 0.006 / 0.012942 = 0.46350
        # annualized (periods=365) = 0.46350 * sqrt(365) = 8.8548
        r = _make_returns_series([0.01, -0.005, 0.02, -0.01, 0.015])
        result = sharpe_ratio(r, rf=0.0, periods=365, annualize=True).iloc[0]
        mean = 0.006
        std = np.sqrt(0.000670 / 4)
        expected = (mean / std) * np.sqrt(365)
        assert result == pytest.approx(expected, abs=1e-3)

    def test_not_annualized(self):
        # Same returns, annualize=False => just mean/std
        r = _make_returns_series([0.01, -0.005, 0.02, -0.01, 0.015])
        result = sharpe_ratio(r, rf=0.0, periods=365, annualize=False).iloc[0]
        mean = 0.006
        std = np.sqrt(0.000670 / 4)
        expected = mean / std
        assert result == pytest.approx(expected, abs=1e-3)

    def test_with_risk_free(self):
        # rf=0.05, periods=365 => daily_rf = 0.05/365 = 0.000136986
        # adjusted returns = [0.01-rf, -0.005-rf, 0.02-rf, -0.01-rf, 0.015-rf]
        rf = 0.05
        periods = 365
        daily_rf = rf / periods
        raw = [0.01, -0.005, 0.02, -0.01, 0.015]
        adj = [x - daily_rf for x in raw]
        r = _make_returns_series(raw)
        result = sharpe_ratio(r, rf=rf, periods=periods, annualize=True).iloc[0]
        mean_adj = np.mean(adj)
        std_adj = np.std(adj, ddof=1)
        expected = (mean_adj / std_adj) * np.sqrt(periods)
        assert result == pytest.approx(expected, abs=1e-3)

    def test_zero_std(self):
        # All same returns => std=0 => sharpe=0
        r = _make_returns_series([0.01, 0.01, 0.01])
        result = sharpe_ratio(r, periods=365).iloc[0]
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_all_negative(self):
        # Returns: [-0.01, -0.02, -0.03]
        # mean = -0.02, std(ddof=1) = 0.01
        # daily = -0.02/0.01 = -2.0
        # annualized = -2.0 * sqrt(365)
        r = _make_returns_series([-0.01, -0.02, -0.03])
        result = sharpe_ratio(r, periods=365).iloc[0]
        mean = -0.02
        std = 0.01
        expected = (mean / std) * np.sqrt(365)
        assert result == pytest.approx(expected, abs=1e-3)


# ===========================================================================
# TestSortinoRatio
# ===========================================================================

class TestSortinoRatio:
    """Verify sortino_ratio against hand-calculated values."""

    def test_basic(self):
        # Returns: [0.01, -0.005, 0.02, -0.01, 0.015]
        # mean = 0.006
        # Negative returns: [-0.005, -0.01]
        # downside = sqrt( ((-0.005)^2 + (-0.01)^2) / 5 )
        #          = sqrt( (0.000025 + 0.0001) / 5 )
        #          = sqrt(0.000125 / 5) = sqrt(0.000025) = 0.005
        # daily sortino = 0.006 / 0.005 = 1.2
        # annualized = 1.2 * sqrt(365) = 22.913
        r = _make_returns_series([0.01, -0.005, 0.02, -0.01, 0.015])
        result = sortino_ratio(r, rf=0, periods=365, annualize=True).iloc[0]
        downside = np.sqrt(0.000125 / 5)
        expected = (0.006 / downside) * np.sqrt(365)
        assert result == pytest.approx(expected, abs=1e-2)

    def test_no_negative_returns(self):
        # Returns: [0.01, 0.02, 0.03]
        # No negatives => downside=0 => sortino=inf
        r = _make_returns_series([0.01, 0.02, 0.03])
        result = sortino_ratio(r, periods=365).iloc[0]
        assert result == np.inf

    def test_all_negative(self):
        # Returns: [-0.01, -0.02, -0.03]
        # mean = -0.02
        # downside = sqrt( (0.0001 + 0.0004 + 0.0009) / 3 ) = sqrt(0.0014/3)
        #          = sqrt(0.000466667) = 0.021602
        # daily = -0.02 / 0.021602 = -0.9258
        # annualized = -0.9258 * sqrt(365)
        r = _make_returns_series([-0.01, -0.02, -0.03])
        result = sortino_ratio(r, periods=365).iloc[0]
        downside = np.sqrt((0.0001 + 0.0004 + 0.0009) / 3)
        expected = (-0.02 / downside) * np.sqrt(365)
        assert result == pytest.approx(expected, abs=1e-2)

    def test_not_annualized(self):
        r = _make_returns_series([0.01, -0.005, 0.02, -0.01, 0.015])
        result = sortino_ratio(r, rf=0, periods=365, annualize=False).iloc[0]
        downside = np.sqrt(0.000125 / 5)
        expected = 0.006 / downside
        assert result == pytest.approx(expected, abs=1e-3)


# ===========================================================================
# TestCagr
# ===========================================================================

class TestCagr:
    """Verify CAGR against hand-calculated values."""

    def test_50pct_in_one_year(self):
        # Start at 1.0, end at 1.5 over 365 days
        # total = prod(1+r) = 1.5, years = 364/365 (date diff: last - first)
        # CAGR = 1.5^(1/years) - 1
        # Note: the code uses (index[-1] - index[0]).days for years
        n = 365
        daily_r = 1.5 ** (1 / (n - 1)) - 1  # so that prod over n-1 returns = 1.5
        # Actually construct returns so prod(1+r) = 1.5 exactly
        returns = [daily_r] * (n - 1)
        # But the code computes years = (last_date - first_date).days / 365
        # With n-1 returns and DatetimeIndex of n-1 entries, days = n-2
        r = _make_returns_series(returns)
        result = cagr(r, periods=365).iloc[0]
        # prod(1+r) = 1.5
        # days = n-2 = 363
        # years = 363/365
        prod_val = (1 + daily_r) ** (n - 1)
        years = (n - 2) / 365.0
        expected = prod_val ** (1 / years) - 1
        assert result == pytest.approx(expected, abs=1e-4)

    def test_loss_over_two_years(self):
        # Start at 1.0, end at 0.8 over ~730 days
        # CAGR = 0.8^(365/days) - 1
        n = 730
        daily_r = 0.8 ** (1 / (n - 1)) - 1
        returns = [daily_r] * (n - 1)
        r = _make_returns_series(returns)
        result = cagr(r, periods=365).iloc[0]
        prod_val = (1 + daily_r) ** (n - 1)
        days = n - 2
        years = days / 365.0
        expected = prod_val ** (1 / years) - 1
        assert result == pytest.approx(expected, abs=1e-4)

    def test_flat(self):
        # All zero returns => CAGR = 0
        r = _make_returns_series([0.0] * 100)
        result = cagr(r, periods=365).iloc[0]
        # prod = 1.0, 1.0^(1/years) - 1 = 0
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_known_doubling(self):
        # If balance doubles in 365 days:
        # prod(1+r) = 2.0, years = 364/365
        # CAGR = 2.0^(365/364) - 1 (slightly more than 100%)
        n = 365
        daily_r = 2.0 ** (1 / (n - 1)) - 1
        returns = [daily_r] * (n - 1)
        r = _make_returns_series(returns)
        result = cagr(r, periods=365).iloc[0]
        days = n - 2
        years = days / 365.0
        expected = 2.0 ** (1 / years) - 1
        assert result == pytest.approx(expected, abs=1e-4)


# ===========================================================================
# TestCalmarRatio
# ===========================================================================

class TestCalmarRatio:
    """Verify calmar_ratio = CAGR / |max_drawdown|."""

    def test_basic(self):
        # Use a longer series so CAGR is a reasonable number.
        # 100 days of mild growth with a dip in the middle.
        # Balances: start 100, dip to 90 at day 20, recover to 120 by day 100
        np.random.seed(42)
        n = 101
        balances = [100.0]
        for i in range(1, n):
            if i <= 20:
                balances.append(balances[-1] * (1 - 0.005))  # slight decline
            else:
                balances.append(balances[-1] * (1 + 0.004))  # steady growth
        returns = _balance_to_returns(balances)
        result = calmar_ratio(returns).iloc[0]

        # Manually compute CAGR and max_dd from the same returns
        clean = _prepare_returns(returns)
        prod_val = (1 + clean).prod()
        days = (clean.index[-1] - clean.index[0]).days
        years = days / 365.0
        cagr_val = np.clip(prod_val, 1e-10, 1e10) ** (1 / years) - 1

        cum = (1 + clean).cumprod()
        cum = pd.concat([pd.Series([1.0]), cum]).reset_index(drop=True)
        dd = abs((cum / cum.expanding(min_periods=1).max() - 1).min())

        expected = cagr_val / dd if dd != 0 else 0
        assert result == pytest.approx(expected, rel=1e-6)

    def test_no_drawdown(self):
        # Always up => dd=0 => calmar=0 (division guarded)
        returns = _balance_to_returns([100, 105, 110, 115, 120])
        result = calmar_ratio(returns).iloc[0]
        assert result == pytest.approx(0.0, abs=1e-10)


# ===========================================================================
# TestOmegaRatio
# ===========================================================================

class TestOmegaRatio:
    """Verify omega_ratio with hand calculations."""

    def test_basic_zero_threshold(self):
        # Returns: [0.01, -0.005, 0.02, -0.01, 0.015]
        # required_return=0.0, periods=365
        # return_threshold = (1+0)^(1/365) - 1 = 0.0
        # Since threshold = 0:
        #   returns_less_thresh = returns - 0 = returns
        #   above: [0.01, 0.02, 0.015] => sum = 0.045
        #   below (strictly < 0): [-0.005, -0.01] => *(-1) => 0.015
        # omega = 0.045 / 0.015 = 3.0
        r = _make_returns_series([0.01, -0.005, 0.02, -0.01, 0.015])
        result = omega_ratio(r, rf=0.0, required_return=0.0, periods=365).iloc[0]
        assert result == pytest.approx(3.0, abs=1e-6)

    def test_with_threshold(self):
        # required_return=0.10 (10% annual), periods=365
        # threshold = (1.10)^(1/365) - 1 = 0.0002611...
        # returns_less_thresh = returns - threshold
        # above 0: those entries where r > threshold
        # below 0: those entries where r < threshold
        r = _make_returns_series([0.01, -0.005, 0.02, -0.01, 0.015])
        threshold = (1.10) ** (1 / 365) - 1
        adj = [x - threshold for x in [0.01, -0.005, 0.02, -0.01, 0.015]]
        above = sum(x for x in adj if x > 0)
        below = -sum(x for x in adj if x < 0)
        expected = above / below
        result = omega_ratio(r, rf=0.0, required_return=0.10, periods=365).iloc[0]
        assert result == pytest.approx(expected, abs=1e-4)

    def test_all_positive(self):
        # Returns: [0.01, 0.02, 0.03], threshold=0
        # No losses below threshold => denom=0 => result=nan
        r = _make_returns_series([0.01, 0.02, 0.03])
        result = omega_ratio(r, required_return=0.0, periods=365).iloc[0]
        # Code returns nan when denom <= 0 and no returns equal threshold
        # Actually threshold = 0 exactly, and returns > 0 strictly, so
        # returns_less_thresh = returns, all > 0, denom = 0 => nan
        assert np.isnan(result)

    def test_all_negative(self):
        # Returns: [-0.01, -0.02, -0.03], threshold=0
        # All below threshold => numer=0
        # returns_less_thresh = [-0.01, -0.02, -0.03], all < 0
        # numer = 0, denom = 0.06 => omega = 0
        r = _make_returns_series([-0.01, -0.02, -0.03])
        result = omega_ratio(r, required_return=0.0, periods=365).iloc[0]
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_symmetric(self):
        # Returns: [0.01, -0.01] with threshold=0
        # above: [0.01], below: [0.01] => omega = 1.0
        r = _make_returns_series([0.01, -0.01])
        result = omega_ratio(r, required_return=0.0, periods=365).iloc[0]
        assert result == pytest.approx(1.0, abs=1e-6)


# ===========================================================================
# TestMaxUnderwaterPeriod
# ===========================================================================

class TestMaxUnderwaterPeriod:
    """Verify calculate_max_underwater_period with hand calculations."""

    def test_basic(self):
        # Balances: [100, 110, 90, 95, 100, 105, 115]
        # Peak at index 1 (110), underwater from index 2 to 5 (back to 105 < 110)
        # Actually: peak=100@0, new peak=110@1, underwater 2,3,4,5 until 115@6
        # Days underwater from peak at 1: indices 2..5 = 4 days, then recovery at 6 => 5 days
        # Wait, let me re-trace:
        #   i=0: peak=100, peak_idx=0
        #   i=1: 110>=100, peak=110, peak_idx=1
        #   i=2: 90<110, days=2-1=1, max=1
        #   i=3: 95<110, days=3-1=2, max=2
        #   i=4: 100<110, days=4-1=3, max=3
        #   i=5: 105<110, days=5-1=4, max=4
        #   i=6: 115>=110, peak=115, peak_idx=6
        # max_period = 4
        result = calculate_max_underwater_period([100, 110, 90, 95, 100, 105, 115])
        assert result == 4

    def test_no_drawdown(self):
        result = calculate_max_underwater_period([100, 105, 110, 120])
        assert result == 0

    def test_never_recovers(self):
        # Balances: [100, 90, 80, 70]
        # Peak=100@0, underwater forever
        # i=1: days=1, i=2: days=2, i=3: days=3
        result = calculate_max_underwater_period([100, 90, 80, 70])
        assert result == 3

    def test_single_element(self):
        result = calculate_max_underwater_period([100])
        assert result == 0

    def test_two_drawdowns(self):
        # [100, 90, 100, 80, 100]
        # Peak=100@0. i=1: 90<100, days=1. i=2: 100>=100, peak=100@2.
        # i=3: 80<100, days=1. i=4: 100>=100, peak=100@4.
        # max=1
        result = calculate_max_underwater_period([100, 90, 100, 80, 100])
        assert result == 1

    def test_longer_second_drawdown(self):
        # [100, 90, 100, 80, 85, 90, 100]
        # Peak=100@0. i=1: days=1. i=2: recovery, peak=100@2.
        # i=3: days=1. i=4: days=2. i=5: days=3. i=6: recovery.
        # max=3
        result = calculate_max_underwater_period([100, 90, 100, 80, 85, 90, 100])
        assert result == 3


# ===========================================================================
# TestMaxConsecutive
# ===========================================================================

class TestMaxConsecutive:
    """Verify _max_consecutive helper."""

    def test_wins(self):
        # [1, 1, 0, 1, 1, 1, 0] => max consecutive 1s = 3
        arr = np.array([1, 1, 0, 1, 1, 1, 0])
        assert _max_consecutive(arr, 1) == 3

    def test_losses(self):
        # [1, 0, 0, 0, 1, 0] => max consecutive 0s = 3
        arr = np.array([1, 0, 0, 0, 1, 0])
        assert _max_consecutive(arr, 0) == 3

    def test_all_same(self):
        arr = np.array([1, 1, 1, 1])
        assert _max_consecutive(arr, 1) == 4
        assert _max_consecutive(arr, 0) == 0

    def test_empty(self):
        arr = np.array([])
        assert _max_consecutive(arr, 1) == 0


# ===========================================================================
# Integration-style: cross-validate metrics against each other
# ===========================================================================

class TestCrossValidation:
    """Sanity checks: metrics should be consistent with each other."""

    def test_sharpe_vs_sortino_positive_returns(self):
        # With mixed returns, sortino should be >= sharpe (same mean,
        # smaller denominator since sortino only uses downside)
        r = _make_returns_series([0.01, -0.005, 0.02, -0.01, 0.015])
        s = sharpe_ratio(r, periods=365).iloc[0]
        so = sortino_ratio(r, periods=365).iloc[0]
        # Sortino uses smaller denominator (downside only) => larger ratio
        assert so > s

    def test_omega_equals_one_for_zero_mean(self):
        # If gains above threshold exactly equal losses below threshold,
        # omega = 1.0. This happens when returns are symmetric around 0.
        r = _make_returns_series([0.01, -0.01, 0.02, -0.02])
        result = omega_ratio(r, required_return=0.0, periods=365).iloc[0]
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_drawdown_bounded(self):
        # Max drawdown should be in [-1, 0]
        r = _make_returns_series([0.05, -0.10, 0.03, -0.20, 0.15])
        dd = max_drawdown(r).iloc[0]
        assert -1.0 <= dd <= 0.0

    def test_calmar_sign_matches_cagr(self):
        # If CAGR > 0 and there is a drawdown, calmar > 0
        returns = _balance_to_returns([100, 110, 95, 120])
        c = calmar_ratio(returns).iloc[0]
        cagr_val = cagr(returns, periods=365).iloc[0]
        if cagr_val > 0:
            assert c >= 0


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_single_return_drawdown(self):
        # Single negative return: balance [100, 90]
        # Returns: [NaN, -0.10]
        # cumprod: [0.90], prepend: [1.0, 0.90]
        # max: [1.0, 1.0], ratio: [1.0, 0.90]
        # dd = 0.90 - 1 = -0.10
        returns = _balance_to_returns([100, 90])
        result = max_drawdown(returns).iloc[0]
        assert result == pytest.approx(-0.10, abs=1e-10)

    def test_single_positive_return_drawdown(self):
        # Single positive return: balance [100, 110]
        # dd = 0.0
        returns = _balance_to_returns([100, 110])
        result = max_drawdown(returns).iloc[0]
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_large_returns_sharpe(self):
        # Very large returns should not cause overflow
        r = _make_returns_series([0.50, -0.30, 0.40, -0.20, 0.60])
        result = sharpe_ratio(r, periods=365).iloc[0]
        assert np.isfinite(result)

    def test_nan_in_returns_handled(self):
        # NaN values should be dropped
        s = pd.Series([np.nan, 0.01, np.nan, -0.005, 0.02])
        result = max_drawdown(s).iloc[0]
        # After dropping NaN: [0.01, -0.005, 0.02]
        # cumprod: [1.01, 1.00495, 1.02505]
        # prepend: [1.0, 1.01, 1.00495, 1.02505]
        # max:     [1.0, 1.01, 1.01, 1.02505]
        # ratio:   [1.0, 1.0, 0.9950, 1.0]
        # dd = 0.9950 - 1 = -0.0050
        assert result == pytest.approx(-0.005, abs=1e-3)

    def test_omega_with_rf(self):
        # rf shifts returns down, making omega smaller
        r = _make_returns_series([0.01, -0.005, 0.02, -0.01, 0.015])
        omega_no_rf = omega_ratio(r, rf=0.0, periods=365).iloc[0]
        omega_with_rf = omega_ratio(r, rf=0.10, periods=365).iloc[0]
        # Higher rf => lower adjusted returns => lower omega
        assert omega_with_rf < omega_no_rf
