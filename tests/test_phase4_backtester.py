import pytest
import numpy as np
import arrow
import pandas as pd

from qengine.config import config, reset_config
from qengine.enums import exchanges, order_types, order_statuses
from qengine.core.market_hours import MarketHours
from qengine.services import metrics as stats
from qengine.store import store
from qengine.routes import router


# ── Helper ──

def _setup_forex_env():
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['balance'] = 10_000
    config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'forex_cfd'
    config['env']['exchanges'][exchanges.SANDBOX]['futures_leverage_mode'] = 'cross'
    config['env']['exchanges'][exchanges.SANDBOX]['futures_leverage'] = 30
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'EUR-USD', 'timeframe': '1m', 'strategy': 'Test19'}
    ])


def _make_forex_exchange():
    from qengine.models.ForexCFDExchange import ForexCFDExchange
    from qengine.services.exchange_service import initialize_exchanges_state
    _setup_forex_env()
    initialize_exchanges_state()
    return store.exchanges.storage[exchanges.SANDBOX]


# ── 4.1 Market Hours in Backtest ──

def test_market_hours_rollover_detection():
    mh = MarketHours()
    # 5pm ET on a Wednesday during EST (UTC-5) = 22:00 UTC
    wed_5pm_et = arrow.get('2025-01-08T22:00:00Z').int_timestamp * 1000
    assert mh.is_rollover_time(wed_5pm_et) is True

    wed_501pm_et = arrow.get('2025-01-08T22:01:00Z').int_timestamp * 1000
    assert mh.is_rollover_time(wed_501pm_et) is False


def test_market_hours_forex_closed_on_weekend():
    mh = MarketHours()
    saturday = arrow.get('2025-01-11T12:00:00Z').int_timestamp * 1000
    assert mh.is_market_open('EUR-USD', saturday) is False


def test_market_hours_forex_open_on_weekday():
    mh = MarketHours()
    wednesday = arrow.get('2025-01-08T12:00:00Z').int_timestamp * 1000
    assert mh.is_market_open('EUR-USD', wednesday) is True


def test_market_hours_forex_closed_friday_after_5pm_et():
    mh = MarketHours()
    friday_5pm = arrow.get('2025-01-10T22:00:00Z').int_timestamp * 1000
    assert mh.is_market_open('EUR-USD', friday_5pm) is False


def test_market_hours_sunday_before_5pm_closed():
    mh = MarketHours()
    sunday_3pm = arrow.get('2025-01-12T20:00:00Z').int_timestamp * 1000
    assert mh.is_market_open('EUR-USD', sunday_3pm) is False


def test_market_hours_sunday_after_5pm_open():
    mh = MarketHours()
    sunday_6pm = arrow.get('2025-01-12T23:00:00Z').int_timestamp * 1000
    assert mh.is_market_open('EUR-USD', sunday_6pm) is True


# ── 4.2 Spread Simulation ──

def test_forex_exchange_spread_charging():
    exchange = _make_forex_exchange()
    initial_balance = exchange.assets[exchange.settlement_currency]

    exchange.set_spread('EUR-USD', 0.0002)
    cost = exchange.charge_spread('EUR-USD', 1.0)

    # spread_cost = spread * contract_size * qty = 0.0002 * 100000 * 1.0 = 20.0
    assert cost == pytest.approx(20.0, abs=0.01)
    assert exchange.assets[exchange.settlement_currency] == pytest.approx(initial_balance - 20.0, abs=0.01)


def test_forex_exchange_swap_charging():
    exchange = _make_forex_exchange()
    initial_balance = exchange.assets[exchange.settlement_currency]

    exchange.set_swap_rates('EUR-USD', -5.0, -3.0)
    cost = exchange.charge_overnight_swap('EUR-USD', 1.0, 'long')

    expected = abs(-5.0 * 100000 * 1.0 / 365)
    assert cost == pytest.approx(expected, rel=0.01)
    assert exchange._overnight_charges == pytest.approx(expected, rel=0.01)


# ── 4.3 Weekend Gap Handling ──

def test_gap_execution_buy_stop():
    from qengine.modes.backtest_mode import _apply_gap_execution_prices
    from qengine.models.Order import Order

    order = Order({
        'id': 'test-1', 'symbol': 'EUR-USD', 'exchange': 'Test',
        'side': 'buy', 'type': order_types.STOP, 'qty': 1.0, 'price': 1.1050,
    })
    order.status = order_statuses.ACTIVE

    candle = np.array([0, 1.1100, 1.1120, 1.1150, 1.1080, 100])
    _apply_gap_execution_prices([order], candle)
    assert order.price == 1.1100


def test_gap_execution_sell_stop():
    from qengine.modes.backtest_mode import _apply_gap_execution_prices
    from qengine.models.Order import Order

    order = Order({
        'id': 'test-2', 'symbol': 'EUR-USD', 'exchange': 'Test',
        'side': 'sell', 'type': order_types.STOP, 'qty': -1.0, 'price': 1.1000,
    })
    order.status = order_statuses.ACTIVE

    candle = np.array([0, 1.0950, 1.0980, 1.1020, 1.0930, 100])
    _apply_gap_execution_prices([order], candle)
    assert order.price == 1.0950


def test_no_gap_execution_when_no_gap():
    from qengine.modes.backtest_mode import _apply_gap_execution_prices
    from qengine.models.Order import Order

    original_price = 1.1050
    order = Order({
        'id': 'test-3', 'symbol': 'EUR-USD', 'exchange': 'Test',
        'side': 'buy', 'type': order_types.STOP, 'qty': 1.0, 'price': original_price,
    })
    order.status = order_statuses.ACTIVE

    candle = np.array([0, 1.1020, 1.1060, 1.1070, 1.1010, 100])
    _apply_gap_execution_prices([order], candle)
    assert order.price == original_price


def test_gap_execution_buy_limit():
    from qengine.modes.backtest_mode import _apply_gap_execution_prices
    from qengine.models.Order import Order

    order = Order({
        'id': 'test-4', 'symbol': 'EUR-USD', 'exchange': 'Test',
        'side': 'buy', 'type': order_types.LIMIT, 'qty': 1.0, 'price': 1.1050,
    })
    order.status = order_statuses.ACTIVE

    candle = np.array([0, 1.1000, 1.1030, 1.1060, 1.0990, 100])
    _apply_gap_execution_prices([order], candle)
    assert order.price == 1.1000


# ── 4.4 Metrics Annualization ──

def test_annualization_periods_function():
    from qengine.services.metrics import _get_annualization_periods
    assert callable(_get_annualization_periods)


def test_sharpe_ratio_with_252_periods():
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    returns = pd.Series(np.random.normal(0.001, 0.02, 100), index=dates)

    sharpe_365 = stats.sharpe_ratio(returns, periods=365).iloc[0]
    sharpe_252 = stats.sharpe_ratio(returns, periods=252).iloc[0]
    assert abs(sharpe_252) < abs(sharpe_365)


def test_sortino_ratio_with_252_periods():
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    returns = pd.Series(np.random.normal(0.001, 0.02, 100), index=dates)

    sortino_365 = stats.sortino_ratio(returns, periods=365).iloc[0]
    sortino_252 = stats.sortino_ratio(returns, periods=252).iloc[0]
    assert abs(sortino_252) < abs(sortino_365)


# ── 4.5 Forex-Specific Metrics ──

def test_forex_metrics_with_exchange():
    """Test forex metrics when a ForexCFDExchange is set up."""
    from qengine.services.metrics import _calculate_forex_metrics
    exchange = _make_forex_exchange()
    exchange.set_swap_rates('EUR-USD', -5.0, -3.0)
    # Simulate some overnight charges
    exchange.charge_overnight_swap('EUR-USD', 1.0, 'long')
    exchange.charge_overnight_swap('EUR-USD', 1.0, 'long')

    result = _calculate_forex_metrics([])
    assert 'total_pips' in result
    assert 'avg_pips_per_trade' in result
    assert 'total_swap_cost' in result
    assert result['total_pips'] == 0.0
    assert result['total_swap_cost'] > 0


def test_forex_metrics_empty_for_non_forex():
    """Without ForexCFDExchange, forex metrics should be empty dict."""
    from qengine.services.metrics import _calculate_forex_metrics
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'futures'
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'EUR-USD', 'timeframe': '1m', 'strategy': 'Test19'}
    ])
    from qengine.services.exchange_service import initialize_exchanges_state
    initialize_exchanges_state()

    result = _calculate_forex_metrics([])
    assert result == {}


def test_omega_ratio_with_252():
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    returns = pd.Series(np.random.normal(0.001, 0.02, 100), index=dates)

    omega_365 = stats.omega_ratio(returns, periods=365).iloc[0]
    omega_252 = stats.omega_ratio(returns, periods=252).iloc[0]
    assert omega_365 > 0
    assert omega_252 > 0


def test_cagr_with_252():
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    returns = pd.Series(np.random.normal(0.001, 0.02, 100), index=dates)

    cagr_365 = stats.cagr(returns, periods=365).iloc[0]
    cagr_252 = stats.cagr(returns, periods=252).iloc[0]
    assert isinstance(cagr_365, float)
    assert isinstance(cagr_252, float)


# ── Integration-style tests ──

def test_forex_exchange_spread_default_2_pips():
    exchange = _make_forex_exchange()
    spread = exchange.get_spread('EUR-USD')
    # EUR-USD pip_size=0.0001, default = 0.0001 * 2 = 0.0002
    assert spread == pytest.approx(0.0002, abs=1e-6)


def test_forex_exchange_custom_spread():
    exchange = _make_forex_exchange()
    exchange.set_spread('EUR-USD', 0.0005)
    assert exchange.get_spread('EUR-USD') == 0.0005


def test_forex_exchange_overnight_accumulation():
    exchange = _make_forex_exchange()
    exchange.set_swap_rates('EUR-USD', -5.0, -3.0)

    for _ in range(3):
        exchange.charge_overnight_swap('EUR-USD', 1.0, 'long')

    expected_per_night = abs(-5.0 * 100000 * 1.0 / 365)
    assert exchange._overnight_charges == pytest.approx(expected_per_night * 3, rel=0.01)


def test_market_hours_commodity_daily_break():
    mh = MarketHours()
    wed_5pm = arrow.get('2025-01-08T22:00:00Z').int_timestamp * 1000
    assert mh.is_market_open('XAU-USD', wed_5pm) is False

    wed_6pm = arrow.get('2025-01-08T23:00:00Z').int_timestamp * 1000
    assert mh.is_market_open('XAU-USD', wed_6pm) is True


def test_candles_info_exchange_type():
    assert callable(stats.candles_info)
