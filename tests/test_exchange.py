import pytest

from qengine.store import store
from qengine.testing_utils import single_route_backtest


def test_negative_balance_validation_for_futures_market():
    """
    The initial account balance for USDT is 10_000. So trying to spend 10_001
    should throw InsufficientMargin exception.

    Since backtest_mode now catches InsufficientMargin internally and stops the
    backtest early (logging a margin call), we verify that no trades were opened
    when leverage is insufficient, and trades succeed with sufficient leverage.
    """
    # (MARKET order) — insufficient margin at 1x leverage, backtest stops early with no fills
    single_route_backtest('TestInsufficientMargin1', is_futures_trading=True, leverage=1)
    assert len(store.closed_trades.trades) == 0, \
        "Expected no trades with insufficient margin at 1x leverage"

    # but with more leverage, it should work
    single_route_backtest('TestInsufficientMargin1', is_futures_trading=True, leverage=2)

    # (LIMIT order)
    single_route_backtest('TestInsufficientMargin2', is_futures_trading=True, leverage=1)
    assert len(store.closed_trades.trades) == 0, \
        "Expected no trades with insufficient margin at 1x leverage"
    # but with more leverage, it should work
    single_route_backtest('TestInsufficientMargin2', is_futures_trading=True, leverage=2)

    # short-version (STOP order)
    single_route_backtest('TestInsufficientMargin3', is_futures_trading=True, leverage=1)
    assert len(store.closed_trades.trades) == 0, \
        "Expected no trades with insufficient margin at 1x leverage"
    # but with more leverage, it should work
    single_route_backtest('TestInsufficientMargin3', is_futures_trading=True, leverage=2)


def test_wallet_balance_and_available_margin_for_futures_market():
    """
    Works the same way as Binance Futures'es wallet balance does.
    It is only changed at commission charges and after realized PNL is added.
    """
    single_route_backtest('TestWalletBalance', is_futures_trading=True, leverage=2)


def test_available_margin_for_futures_market():
    """
    Make sure that the reduce only orders are not affecting the available_margin causing it to go negative
    """
    single_route_backtest('TestFuturesExchangeAvailableMargin', is_futures_trading=True, leverage=2)


# TODO: test_wallet_balance_and_available_margin_for_spot_market
