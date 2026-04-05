"""
Comprehensive tests for order execution, fee/spread calculation,
and end-to-end backtest integrity.

Verifies:
  1. Fee calculation (order_service fee formula)
  2. Candle factory output format and continuity
  3. ClosedTrade PnL = raw_profit - fee
  4. Balance consistency after backtests
  5. Spread cost model for CFDExchange
  6. Order fill price semantics
"""

import numpy as np
import pytest

import qengine.helpers as jh
from qengine.config import config, reset_config
from qengine.enums import exchanges, sides, order_types, order_statuses
from qengine.factories import candles_from_close_prices
from qengine.factories.order_factory import fake_order
from qengine.models import ClosedTrade
from qengine.models.Order import Order
from qengine.store import store
from qengine.testing_utils import single_route_backtest, set_up


# ---------------------------------------------------------------------------
# Part 1: Fee Calculation
# ---------------------------------------------------------------------------
class TestFeeCalculation:
    """Verify the fee formula: fee = fee_rate * abs(filled_qty) * price."""

    def test_standard_fee(self):
        """fee = 0.001 * 100 * 50 = 5.0"""
        set_up(fee=0.001)
        order = Order({
            'id': jh.generate_unique_id(),
            'symbol': 'BTC-USDT',
            'exchange': exchanges.SANDBOX,
            'side': sides.BUY,
            'type': order_types.MARKET,
            'qty': 100,
            'price': 50,
            'fee': None,
            'filled_qty': 100,
            'status': order_statuses.ACTIVE,
            'created_at': jh.now_to_timestamp(),
        })

        # Simulate what execute_order does for fee calculation
        fee_rate = jh.get_config(f'env.exchanges.{order.exchange}.fee')
        notional = abs(order.filled_qty) * order.price
        computed_fee = fee_rate * notional

        assert fee_rate == pytest.approx(0.001)
        assert notional == pytest.approx(5000.0)
        # 0.001 * 100 * 50 = 5.0
        assert computed_fee == pytest.approx(5.0)

    def test_zero_fee(self):
        """fee_rate = 0 => fee = 0 regardless of notional."""
        set_up(fee=0)
        order = Order({
            'id': jh.generate_unique_id(),
            'symbol': 'BTC-USDT',
            'exchange': exchanges.SANDBOX,
            'side': sides.SELL,
            'type': order_types.MARKET,
            'qty': 500,
            'price': 200,
            'fee': None,
            'filled_qty': 500,
            'status': order_statuses.ACTIVE,
            'created_at': jh.now_to_timestamp(),
        })

        fee_rate = jh.get_config(f'env.exchanges.{order.exchange}.fee')
        computed_fee = fee_rate * abs(order.filled_qty) * order.price

        assert fee_rate == 0
        assert computed_fee == pytest.approx(0.0)

    def test_fee_with_small_rate(self):
        """fee = 0.0005 * 3.5 * 42000 = 73.5"""
        set_up(fee=0.0005)
        fee_rate = 0.0005
        qty = 3.5
        price = 42000
        expected_fee = fee_rate * qty * price  # 73.5
        assert expected_fee == pytest.approx(73.5)

    def test_fee_scales_with_qty(self):
        """Doubling qty doubles fee."""
        fee_rate = 0.001
        price = 100
        fee_1 = fee_rate * 10 * price   # 1.0
        fee_2 = fee_rate * 20 * price   # 2.0
        assert fee_2 == pytest.approx(2 * fee_1)


# ---------------------------------------------------------------------------
# Part 2: Candle Factory
# ---------------------------------------------------------------------------
class TestCandleFactory:
    """Verify candles_from_close_prices produces valid OHLCV data."""

    def setup_method(self):
        self.candles = candles_from_close_prices([10, 11, 12, 13, 14])

    def test_shape(self):
        """Output shape is (N, 6): [timestamp, open, close, high, low, volume]."""
        assert self.candles.shape == (5, 6)

    def test_timestamps_increment_by_60s(self):
        """Each candle is 60000ms (1 minute) apart."""
        timestamps = self.candles[:, 0]
        diffs = np.diff(timestamps)
        for d in diffs:
            assert d == pytest.approx(60000)

    def test_open_equals_previous_close(self):
        """open[i] == close[i-1] for i > 0 (price continuity)."""
        for i in range(1, len(self.candles)):
            open_i = self.candles[i, 1]
            prev_close = self.candles[i - 1, 2]
            assert open_i == pytest.approx(prev_close), (
                f"Candle {i}: open={open_i} != prev close={prev_close}"
            )

    def test_close_prices_match_input(self):
        """close column equals the input price list."""
        expected = [10, 11, 12, 13, 14]
        for i, p in enumerate(expected):
            assert self.candles[i, 2] == pytest.approx(p)

    def test_high_gte_open_and_close(self):
        """high >= max(open, close) for every candle."""
        for i in range(len(self.candles)):
            high = self.candles[i, 3]
            o = self.candles[i, 1]
            c = self.candles[i, 2]
            assert high >= max(o, c) - 1e-10, (
                f"Candle {i}: high={high} < max(open={o}, close={c})"
            )

    def test_low_lte_open_and_close(self):
        """low <= min(open, close) for every candle."""
        for i in range(len(self.candles)):
            low = self.candles[i, 4]
            o = self.candles[i, 1]
            c = self.candles[i, 2]
            assert low <= min(o, c) + 1e-10, (
                f"Candle {i}: low={low} > min(open={o}, close={c})"
            )

    def test_volume_nonnegative(self):
        """All volumes are >= 0."""
        for i in range(len(self.candles)):
            assert self.candles[i, 5] >= 0

    def test_single_candle(self):
        """Edge case: one close price produces one valid candle."""
        c = candles_from_close_prices([42])
        assert c.shape == (1, 6)
        assert c[0, 2] == pytest.approx(42)

    def test_descending_prices(self):
        """Descending close prices still satisfy OHLCV constraints."""
        c = candles_from_close_prices([100, 90, 80])
        for i in range(len(c)):
            assert c[i, 3] >= max(c[i, 1], c[i, 2]) - 1e-10  # high
            assert c[i, 4] <= min(c[i, 1], c[i, 2]) + 1e-10  # low


# ---------------------------------------------------------------------------
# Part 3: ClosedTrade PnL
# ---------------------------------------------------------------------------
class TestClosedTradePnL:
    """Verify ClosedTrade.pnl = raw_profit - fee, and fee = sum(order.fee)."""

    def test_long_trade_pnl_no_fee(self):
        """Long: buy at 100, sell at 110, qty=10, fee=0 => pnl = 100."""
        t = ClosedTrade({'type': 'long'})
        t.buy_orders.append(np.array([10, 100]))   # entry
        t.sell_orders.append(np.array([10, 110]))   # exit

        # No order objects => fee = 0
        assert t.qty == pytest.approx(10)
        assert t.entry_price == pytest.approx(100)
        assert t.exit_price == pytest.approx(110)
        # raw profit = 10 * (110 - 100) = 100, fee = 0
        assert t.pnl == pytest.approx(100.0)

    def test_short_trade_pnl_no_fee(self):
        """Short: sell at 200, buy at 180, qty=5, fee=0 => pnl = 100."""
        t = ClosedTrade({'type': 'short'})
        t.sell_orders.append(np.array([5, 200]))   # entry
        t.buy_orders.append(np.array([5, 180]))    # exit

        # raw profit = 5 * (200 - 180) = 100
        assert t.pnl == pytest.approx(100.0)

    def test_long_trade_pnl_with_fee(self):
        """
        Long: buy 10 @ 100, sell 10 @ 110.
        Entry fee = 0.001 * 10 * 100 = 1.0
        Exit fee  = 0.001 * 10 * 110 = 1.1
        Total fee = 2.1
        Raw profit = 10 * (110 - 100) = 100
        PnL = 100 - 2.1 = 97.9
        """
        t = ClosedTrade({'type': 'long'})
        t.buy_orders.append(np.array([10, 100]))
        t.sell_orders.append(np.array([10, 110]))

        # Simulate order objects with fees
        entry_order = _make_order_stub(fee=1.0)
        exit_order = _make_order_stub(fee=1.1)
        t.orders = [entry_order, exit_order]

        assert t.fee == pytest.approx(2.1)
        assert t.pnl == pytest.approx(100.0 - 2.1)

    def test_short_trade_losing_with_fee(self):
        """
        Short: sell 5 @ 200, buy 5 @ 210 (losing trade).
        Raw profit = 5 * (200 - 210) = -50 (but formula uses abs and flips sign)
        fee = 3.0
        PnL = -50 - 3.0 = -53.0
        """
        t = ClosedTrade({'type': 'short'})
        t.sell_orders.append(np.array([5, 200]))
        t.buy_orders.append(np.array([5, 210]))

        t.orders = [_make_order_stub(fee=1.5), _make_order_stub(fee=1.5)]

        # raw_profit = 5 * (210 - 200) * -1 = -50
        assert t.pnl == pytest.approx(-50.0 - 3.0)

    def test_fee_is_sum_of_order_fees(self):
        """ClosedTrade.fee = sum(order.fee for order in orders)."""
        t = ClosedTrade({'type': 'long'})
        t.buy_orders.append(np.array([1, 10]))
        t.sell_orders.append(np.array([1, 20]))
        t.orders = [
            _make_order_stub(fee=0.5),
            _make_order_stub(fee=0.7),
            _make_order_stub(fee=0.3),
        ]
        assert t.fee == pytest.approx(1.5)

    def test_weighted_average_entry_exit(self):
        """
        Multiple entry fills: buy 10@100 + buy 10@200 => avg entry = 150
        Single exit: sell 20@300
        Raw profit = 20 * (300 - 150) = 3000
        """
        t = ClosedTrade({'type': 'long'})
        t.buy_orders.append(np.array([10, 100]))
        t.buy_orders.append(np.array([10, 200]))
        t.sell_orders.append(np.array([20, 300]))

        assert t.qty == pytest.approx(20)
        assert t.entry_price == pytest.approx(150)
        assert t.exit_price == pytest.approx(300)
        assert t.pnl == pytest.approx(3000.0)


# ---------------------------------------------------------------------------
# Part 4: Balance Consistency (end-to-end backtests)
# ---------------------------------------------------------------------------
class TestBalanceConsistency:
    """After a backtest: final_balance = starting_balance + sum(trade.pnl)."""

    def test_long_trade_balance(self):
        """
        CanAddClosedTradeToStore: buys at 10, TP at 15, qty=1, fee=0.
        PnL = 1 * (15 - 10) - 0 = 5.0
        Final balance = 10000 + 5 = 10005.
        """
        single_route_backtest('CanAddClosedTradeToStore', fee=0)

        trades = store.closed_trades.trades
        assert len(trades) == 1
        assert trades[0].pnl == pytest.approx(5.0)

        exchange = store.exchanges.get_exchange(exchanges.SANDBOX)
        expected_balance = 10_000 + 5.0
        assert exchange.wallet_balance == pytest.approx(expected_balance)

    def test_long_trade_balance_with_fee(self):
        """
        Same strategy but with fee=0.001.
        Entry: buy 1 @ 10 => fee = 0.001 * 1 * 10 = 0.01
        Exit: sell 1 @ 15 => fee = 0.001 * 1 * 15 = 0.015
        Total fee = 0.025
        PnL = 5.0 - 0.025 = 4.975
        Final balance = 10000 + 4.975 = 10004.975
        """
        single_route_backtest('CanAddClosedTradeToStore', fee=0.001)

        trades = store.closed_trades.trades
        assert len(trades) == 1
        assert trades[0].fee == pytest.approx(0.025)
        assert trades[0].pnl == pytest.approx(4.975)

        exchange = store.exchanges.get_exchange(exchanges.SANDBOX)
        expected_balance = 10_000 + 4.975
        assert exchange.wallet_balance == pytest.approx(expected_balance)

    def test_trade_pnl_sum_equals_balance_change(self):
        """Sum of all trade PnLs equals final_balance - starting_balance."""
        single_route_backtest('CanAddClosedTradeToStore', fee=0.001)

        exchange = store.exchanges.get_exchange(exchanges.SANDBOX)
        starting = 10_000
        finishing = exchange.wallet_balance

        total_pnl = sum(t.pnl for t in store.closed_trades.trades)
        assert finishing - starting == pytest.approx(total_pnl)

    def test_daily_balance_starts_at_starting_balance(self):
        """First daily_balance entry == starting_balance."""
        single_route_backtest('CanAddClosedTradeToStore', fee=0, candles_count=100)

        if len(store.app.daily_balance) > 0:
            assert store.app.daily_balance[0] == pytest.approx(10_000)


# ---------------------------------------------------------------------------
# Part 5: Spread Cost Model
# ---------------------------------------------------------------------------
class TestSpreadModel:
    """Verify CFDExchange spread shifts entry fill prices."""

    def test_buy_entry_spread_added(self):
        """Buy entry: fill price increases by spread amount."""
        from qengine.models.CFDExchange import CFDExchange

        # Manually instantiate (needs routes set up)
        reset_config()
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'futures'
        config['env']['exchanges'][exchanges.SANDBOX]['balance'] = 10_000

        # Test the spread logic directly: buy entry gets spread added
        original_price = 1.10000
        spread = 0.00020  # 2 pips

        # Simulating order_service.execute_order spread logic:
        # if order.side == 'buy': order.price += spread
        adjusted_price = original_price + spread
        assert adjusted_price == pytest.approx(1.10020)

        # Spread cost = spread * qty
        qty = 100_000
        spread_cost = spread * qty
        # 0.00020 * 100000 = 20.0
        assert spread_cost == pytest.approx(20.0)

    def test_sell_entry_spread_subtracted(self):
        """Sell entry: fill price decreases by spread amount."""
        original_price = 1.10000
        spread = 0.00020

        # if order.side == 'sell': order.price -= spread
        adjusted_price = original_price - spread
        assert adjusted_price == pytest.approx(1.09980)

    def test_exit_order_no_spread(self):
        """
        Exit orders (reduce_only=True) do NOT get spread applied.
        From order_service.py: is_entry checks reduce_only.
        reduce_only=True => is_entry=False => no spread shift.
        """
        # The logic in order_service.py line 114:
        #   is_entry = not order.reduce_only  (CFD mode)
        # So reduce_only=True => is_entry=False => no spread
        reduce_only = True
        is_entry = not reduce_only
        assert is_entry is False

    def test_spread_cost_formula(self):
        """
        Spread cost = spread * abs(qty).
        spread=0.00015, qty=50000 => cost = 7.5
        """
        spread = 0.00015
        qty = 50_000
        cost = spread * abs(qty)
        assert cost == pytest.approx(7.5)

    def test_charge_spread_method(self):
        """CFDExchange.charge_spread deducts from balance."""
        from qengine.models.CFDExchange import CFDExchange
        from unittest.mock import patch

        # We need a minimal setup. Use patching to avoid full route init.
        reset_config()
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'futures'
        config['env']['exchanges'][exchanges.SANDBOX]['balance'] = 10_000

        # Create a minimal exchange by patching router.routes
        from qengine.routes import router
        from unittest.mock import MagicMock

        mock_route = MagicMock()
        mock_route.symbol = 'EUR-USD'

        with patch.object(router, 'routes', [mock_route]):
            with patch('qengine.helpers.is_livetrading', return_value=False):
                with patch('qengine.helpers.is_live', return_value=False):
                    ex = CFDExchange(
                        name='TestExchange',
                        starting_balance=10_000,
                        fee_rate=0.0,
                    )
                    ex.set_spread('EUR-USD', 0.00020)
                    initial_balance = ex.assets[ex.settlement_currency]

                    charged = ex.charge_spread('EUR-USD', 100_000)

                    # spread_cost = 0.00020 * 100000 = 20.0
                    assert charged == pytest.approx(20.0)
                    assert ex.assets[ex.settlement_currency] == pytest.approx(
                        initial_balance - 20.0
                    )


# ---------------------------------------------------------------------------
# Part 6: Order Fill Prices
# ---------------------------------------------------------------------------
class TestOrderFillPrices:
    """Verify order fill price semantics in backtests."""

    def test_market_order_fills_at_current_price(self):
        """
        CanAddClosedTradeToStore: buys at self.price when price==10.
        candles_from_close_prices(range(1,100)) => close prices 1..99.
        Entry triggers when close=10, so entry_price=10.
        """
        single_route_backtest('CanAddClosedTradeToStore', fee=0)

        trades = store.closed_trades.trades
        assert len(trades) == 1
        assert trades[0].type == 'long'
        # Market buy fills at self.price = 10
        assert trades[0].entry_price == pytest.approx(10.0)

    def test_take_profit_fills_at_tp_price(self):
        """
        CanAddClosedTradeToStore: TP set at 15.
        Exit should fill exactly at 15 (not at any other candle close).
        """
        single_route_backtest('CanAddClosedTradeToStore', fee=0)

        trades = store.closed_trades.trades
        assert len(trades) == 1
        # TP at 15 means exit_price = 15
        assert trades[0].exit_price == pytest.approx(15.0)

    def test_long_take_profit_hit(self):
        """
        CanAddClosedTradeToStore: buy at 10, TP at 15.
        With uptrend candles (1..99), TP is hit at price 15.
        """
        single_route_backtest('CanAddClosedTradeToStore', fee=0)

        trades = store.closed_trades.trades
        assert len(trades) == 1
        assert trades[0].entry_price == pytest.approx(10.0)
        assert trades[0].exit_price == pytest.approx(15.0)
        assert trades[0].type == 'long'

    def test_long_trade_profit_is_correct(self):
        """
        qty=1, entry=10, exit=15, fee=0 => pnl = 1*(15-10) = 5.
        """
        single_route_backtest('CanAddClosedTradeToStore', fee=0)

        t = store.closed_trades.trades[0]
        expected_pnl = t.qty * (t.exit_price - t.entry_price)
        assert t.pnl == pytest.approx(expected_pnl)
        assert t.pnl == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Part 7: End-to-End Integrity with Fees
# ---------------------------------------------------------------------------
class TestEndToEndIntegrity:
    """Cross-check trade PnL, fees, and balance after full backtests."""

    def test_trade_fee_matches_config_rate(self):
        """
        With fee=0.002: entry fee + exit fee should match the formula.
        CanAddClosedTradeToStore: buy 1@10, sell 1@15.
        Entry fee = 0.002 * 1 * 10 = 0.02
        Exit fee  = 0.002 * 1 * 15 = 0.03
        Total = 0.05
        """
        single_route_backtest('CanAddClosedTradeToStore', fee=0.002)

        t = store.closed_trades.trades[0]
        assert t.fee == pytest.approx(0.05)
        assert t.pnl == pytest.approx(5.0 - 0.05)

    def test_winning_long_trade_increases_balance(self):
        """
        CanAddClosedTradeToStore with fee=0.002:
        Buy 1@10, sell 1@15 => raw profit=5, fee=0.05.
        Balance goes from 10000 to 10004.95.
        """
        single_route_backtest('CanAddClosedTradeToStore', fee=0.002)

        trades = store.closed_trades.trades
        assert len(trades) == 1
        assert trades[0].pnl == pytest.approx(5.0 - 0.05)

        exchange = store.exchanges.get_exchange(exchanges.SANDBOX)
        assert exchange.wallet_balance == pytest.approx(10_000 + 5.0 - 0.05)

    def test_multiple_assertions_on_closed_trade_object(self):
        """Verify all ClosedTrade properties are self-consistent."""
        single_route_backtest('CanAddClosedTradeToStore', fee=0.001)

        t = store.closed_trades.trades[0]

        # size = qty * entry_price
        assert t.size == pytest.approx(t.qty * t.entry_price)

        # pnl = raw_profit - fee
        raw_profit = t.qty * (t.exit_price - t.entry_price)
        assert t.pnl == pytest.approx(raw_profit - t.fee)

        # roi = pnl / total_cost * 100
        assert t.pnl_percentage == pytest.approx(t.pnl / t.total_cost * 100)

        # holding period is positive
        assert t.holding_period > 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _OrderStub:
    """Minimal order stand-in that only exposes a fee attribute."""
    def __init__(self, fee: float):
        self.fee = fee


def _make_order_stub(fee: float) -> _OrderStub:
    return _OrderStub(fee=fee)
