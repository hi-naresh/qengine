"""
Tests for financial metrics: sharpe_ratio, sortino_ratio, calmar_ratio,
autocorr_penalty, max_drawdown, cagr, omega_ratio.
Uses known inputs with hand-calculated expected outputs.
"""
import numpy as np
import pandas as pd
import pytest
from qengine.services.metrics import (
    sharpe_ratio, sortino_ratio, calmar_ratio, autocorr_penalty,
    max_drawdown, cagr, omega_ratio, _prepare_returns,
    calculate_max_underwater_period, _max_consecutive,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_returns(values, start='2024-01-01'):
    """Create a pd.Series of returns with a DatetimeIndex."""
    idx = pd.date_range(start, periods=len(values), freq='D')
    return pd.Series(values, index=idx, dtype=float)


# ===========================================================================
# _prepare_returns
# ===========================================================================
class TestPrepareReturns:
    def test_drops_nan(self):
        s = _make_returns([np.nan, 0.01, 0.02, np.nan, 0.03])
        result = _prepare_returns(s)
        assert len(result) == 3
        assert not result.isna().any()

    def test_adjusts_risk_free_rate(self):
        s = _make_returns([0.01, 0.02, 0.03])
        result = _prepare_returns(s, rf=0.365, periods=365)
        # Each return should be reduced by 0.365/365 = 0.001
        expected = np.array([0.01, 0.02, 0.03]) - 0.001
        np.testing.assert_allclose(result.values, expected, atol=1e-10)

    def test_zero_rf_no_change(self):
        s = _make_returns([0.05, -0.02])
        result = _prepare_returns(s, rf=0.0)
        np.testing.assert_allclose(result.values, [0.05, -0.02])

    def test_dataframe_input(self):
        df = pd.DataFrame({'returns': [0.01, 0.02, 0.03]},
                          index=pd.date_range('2024-01-01', periods=3, freq='D'))
        result = _prepare_returns(df)
        assert isinstance(result, pd.Series)
        assert len(result) == 3


# ===========================================================================
# sharpe_ratio
# ===========================================================================
class TestSharpeRatio:
    def test_positive_returns(self):
        # Constant positive returns → high Sharpe
        returns = _make_returns([0.01] * 100)
        result = sharpe_ratio(returns, periods=252)
        assert result.iloc[0] > 0

    def test_zero_std_returns_zero(self):
        # All identical returns → std=0 → Sharpe should be 0
        returns = _make_returns([0.0] * 10)
        result = sharpe_ratio(returns, periods=252)
        assert result.iloc[0] == 0

    def test_negative_returns(self):
        returns = _make_returns([-0.01] * 100)
        result = sharpe_ratio(returns, periods=252)
        assert result.iloc[0] < 0

    def test_known_value(self):
        # Hand-calculate: mean=0.01, std≈0.01414
        # Non-annualized: 0.01/0.01414 ≈ 0.7071
        returns = _make_returns([0.02, 0.0, 0.02, 0.0, 0.02, 0.0])
        result = sharpe_ratio(returns, periods=252, annualize=False)
        expected = np.mean([0.02, 0.0, 0.02, 0.0, 0.02, 0.0]) / np.std([0.02, 0.0, 0.02, 0.0, 0.02, 0.0], ddof=1)
        assert result.iloc[0] == pytest.approx(expected, rel=1e-4)

    def test_annualization(self):
        returns = _make_returns([0.01] * 50)
        non_ann = sharpe_ratio(returns, periods=252, annualize=False).iloc[0]
        ann = sharpe_ratio(returns, periods=252, annualize=True).iloc[0]
        assert ann == pytest.approx(non_ann * np.sqrt(252), rel=1e-4)

    def test_smart_sharpe_applies_penalty(self):
        returns = _make_returns([0.01, 0.02, 0.01, 0.02] * 25)
        normal = sharpe_ratio(returns, periods=252, smart=False).iloc[0]
        smart = sharpe_ratio(returns, periods=252, smart=True).iloc[0]
        # Smart Sharpe should be lower (penalized for autocorrelation)
        assert smart <= normal

    def test_returns_series(self):
        returns = _make_returns([0.01, -0.005, 0.008])
        result = sharpe_ratio(returns, periods=252)
        assert isinstance(result, pd.Series)


# ===========================================================================
# sortino_ratio
# ===========================================================================
class TestSortinoRatio:
    def test_all_positive_returns_inf(self):
        # No downside → sortino = inf
        returns = _make_returns([0.01, 0.02, 0.03, 0.01])
        result = sortino_ratio(returns, periods=252)
        assert np.isinf(result.iloc[0]) and result.iloc[0] > 0

    def test_all_negative_returns(self):
        returns = _make_returns([-0.01, -0.02, -0.03])
        result = sortino_ratio(returns, periods=252)
        assert result.iloc[0] < 0

    def test_mixed_returns(self):
        returns = _make_returns([0.02, -0.01, 0.03, -0.02, 0.01])
        result = sortino_ratio(returns, periods=252)
        assert result.iloc[0] > 0  # net positive

    def test_sortino_higher_than_sharpe_for_right_skewed(self):
        # Right-skewed returns (big wins, small losses) → Sortino > Sharpe
        returns = _make_returns([0.05, -0.01, 0.04, -0.01, 0.06, -0.005] * 10)
        sr = sharpe_ratio(returns, periods=252, annualize=False).iloc[0]
        so = sortino_ratio(returns, periods=252, annualize=False).iloc[0]
        assert so > sr

    def test_smart_sortino(self):
        returns = _make_returns([0.01, -0.005, 0.02, -0.01] * 25)
        normal = sortino_ratio(returns, periods=252, smart=False).iloc[0]
        smart = sortino_ratio(returns, periods=252, smart=True).iloc[0]
        assert smart <= normal


# ===========================================================================
# calmar_ratio
# ===========================================================================
class TestCalmarRatio:
    def test_positive_returns_no_drawdown_returns_zero(self):
        # Steady positive returns → no drawdown → CAGR/0 → 0
        returns = _make_returns([0.005] * 365)
        result = calmar_ratio(returns)
        assert result.iloc[0] == 0  # No drawdown means division by 0 → returns 0

    def test_zero_drawdown_returns_zero(self):
        # If no drawdown at all, it depends on implementation
        # Constant returns = no drawdown → CAGR/0 → should return 0
        returns = _make_returns([0.0] * 365)
        result = calmar_ratio(returns)
        assert result.iloc[0] == 0

    def test_known_drawdown(self):
        # Create returns with a known drawdown
        vals = [0.01] * 50 + [-0.05] * 10 + [0.01] * 305
        returns = _make_returns(vals)
        result = calmar_ratio(returns)
        assert isinstance(result, pd.Series)
        # Just verify it's a finite number
        assert np.isfinite(result.iloc[0])


# ===========================================================================
# autocorr_penalty
# ===========================================================================
class TestAutocorrPenalty:
    def test_iid_returns_penalty_near_one(self):
        np.random.seed(42)
        returns = _make_returns(np.random.normal(0, 0.01, 500))
        penalty = autocorr_penalty(returns)
        # For IID returns, penalty should be close to 1
        assert 0.8 < penalty < 1.5

    def test_highly_autocorrelated_penalty_larger(self):
        # Trending returns have high autocorrelation
        trend = np.cumsum(np.ones(100) * 0.001)
        returns = _make_returns(np.diff(trend))
        penalty = autocorr_penalty(returns)
        # Should be >= 1 (penalizes)
        assert penalty >= 1.0


# ===========================================================================
# max_drawdown
# ===========================================================================
class TestMaxDrawdown:
    def test_no_drawdown(self):
        # Monotonically increasing → 0% drawdown
        returns = _make_returns([0.01] * 10)
        result = max_drawdown(returns)
        assert result.iloc[0] == pytest.approx(0.0, abs=1e-10)

    def test_known_drawdown(self):
        # Start at 1.0, go to 1.1 (+10%), drop to 0.99 (-10% from peak)
        returns = _make_returns([0.1, -0.1])
        result = max_drawdown(returns)
        # From peak 1.1 to 0.99: dd = 0.99/1.1 - 1 = -0.1
        assert result.iloc[0] < 0

    def test_empty_returns(self):
        returns = pd.Series([], dtype=float)
        result = max_drawdown(returns)
        assert result.iloc[0] == 0.0

    def test_all_losses(self):
        returns = _make_returns([-0.05, -0.05, -0.05])
        result = max_drawdown(returns)
        assert result.iloc[0] < -0.1  # Significant drawdown


# ===========================================================================
# cagr
# ===========================================================================
class TestCAGR:
    def test_positive_cagr(self):
        # 1% daily for a year
        returns = _make_returns([0.001] * 365)
        result = cagr(returns, periods=365)
        assert result.iloc[0] > 0

    def test_negative_cagr(self):
        returns = _make_returns([-0.001] * 365)
        result = cagr(returns, periods=365)
        assert result.iloc[0] < 0

    def test_zero_returns(self):
        returns = _make_returns([0.0] * 365)
        result = cagr(returns, periods=365)
        assert result.iloc[0] == pytest.approx(0.0, abs=1e-10)


# ===========================================================================
# omega_ratio
# ===========================================================================
class TestOmegaRatio:
    def test_all_positive_returns_nan(self):
        # All positive → denominator is 0 → NaN
        returns = _make_returns([0.01, 0.02, 0.03])
        result = omega_ratio(returns, periods=365)
        assert np.isnan(result.iloc[0])

    def test_mixed_returns_above_one(self):
        # Net positive with some negatives → omega > 1
        returns = _make_returns([0.03, -0.01, 0.04, -0.005, 0.02])
        result = omega_ratio(returns, periods=365)
        assert result.iloc[0] > 1

    def test_all_negative_returns(self):
        returns = _make_returns([-0.01, -0.02, -0.03])
        result = omega_ratio(returns, periods=365)
        assert result.iloc[0] < 1


# ===========================================================================
# calculate_max_underwater_period
# ===========================================================================
class TestMaxUnderwaterPeriod:
    def test_no_drawdown(self):
        balances = [100, 101, 102, 103, 104]
        assert calculate_max_underwater_period(balances) == 0

    def test_known_underwater(self):
        # Peak at 105, then 3 days underwater before recovery
        balances = [100, 105, 103, 102, 104, 106]
        result = calculate_max_underwater_period(balances)
        assert result == 3  # days 2,3,4 underwater (indices 2-4 from peak at 1)

    def test_single_balance(self):
        assert calculate_max_underwater_period([100]) == 0

    def test_empty_balance(self):
        assert calculate_max_underwater_period([]) == 0

    def test_never_recovers(self):
        balances = [100, 90, 80, 70, 60]
        result = calculate_max_underwater_period(balances)
        assert result == 4  # all 4 days underwater


# ===========================================================================
# _max_consecutive
# ===========================================================================
class TestMaxConsecutive:
    def test_basic(self):
        arr = np.array([1, 1, 0, 1, 1, 1, 0])
        assert _max_consecutive(arr, 1) == 3
        assert _max_consecutive(arr, 0) == 1

    def test_all_same(self):
        arr = np.array([1, 1, 1, 1])
        assert _max_consecutive(arr, 1) == 4
        assert _max_consecutive(arr, 0) == 0

    def test_empty(self):
        arr = np.array([])
        assert _max_consecutive(arr, 1) == 0
