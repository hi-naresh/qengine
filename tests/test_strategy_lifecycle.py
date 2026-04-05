"""
Tests for strategy execution lifecycle: the full
before() → should_long/short → go_long/short → update_position() → after()
sequence, and deterministic ordering guarantees.
"""
import numpy as np
import qengine.helpers as jh
from qengine.factories import candles_from_close_prices
from qengine.strategies import Strategy
from qengine import research


# ---------------------------------------------------------------------------
# Config helper
# ---------------------------------------------------------------------------
def _make_config(exchange_name='Fake Exchange'):
    return {
        'starting_balance': 10_000,
        'fee': 0,
        'type': 'futures',
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'warm_up_candles': 0,
    }


def _run(strategy_cls, prices=None, config_override=None):
    prices = prices or list(range(10, 60))  # 50 candles: 10,11,...,59
    candles = candles_from_close_prices(prices)
    exchange_name = 'Fake Exchange'
    symbol = 'FAKE-USDT'
    cfg = config_override or _make_config(exchange_name)
    routes = [{'exchange': exchange_name, 'strategy': strategy_cls,
               'symbol': symbol, 'timeframe': '1m'}]
    return research.backtest(cfg, routes, [], {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name, 'symbol': symbol,
            'candles': candles,
        },
    })


# ===========================================================================
# Lifecycle ordering tests
# ===========================================================================
class TestLifecycleOrdering:
    """Verify that before(), signal methods, and after() are called in the correct order."""

    def test_before_called_before_signals(self):
        call_log = []

        class LifecycleTracker(Strategy):
            def before(self):
                call_log.append(('before', self.index))

            def should_long(self):
                call_log.append(('should_long', self.index))
                return False

            def should_short(self):
                return False

            def go_long(self):
                pass

            def go_short(self):
                pass

            def should_cancel_entry(self):
                return False

        _run(LifecycleTracker, list(range(10, 20)))

        # For each candle, before should come before should_long
        for i in range(10):
            befores = [c for c in call_log if c == ('before', i)]
            signals = [c for c in call_log if c == ('should_long', i)]
            if befores and signals:
                before_idx = call_log.index(('before', i))
                signal_idx = call_log.index(('should_long', i))
                assert before_idx < signal_idx, \
                    f"before() should be called before should_long() at index {i}"

    def test_after_called_after_everything(self):
        after_calls = []
        before_calls = []

        class AfterTracker(Strategy):
            def before(self):
                before_calls.append(self.index)

            def should_long(self):
                return False

            def should_short(self):
                return False

            def go_long(self):
                pass

            def go_short(self):
                pass

            def should_cancel_entry(self):
                return False

            def after(self):
                after_calls.append(self.index)

        _run(AfterTracker, list(range(10, 25)))

        assert len(after_calls) > 0
        assert len(before_calls) == len(after_calls)
        # after() called for every candle
        for i in range(len(after_calls)):
            assert before_calls[i] == after_calls[i]

    def test_update_position_called_when_position_open(self):
        update_calls = []

        class UpdateTracker(Strategy):
            def should_long(self):
                return self.index == 2

            def should_short(self):
                return False

            def go_long(self):
                qty = 1
                self.buy = qty, self.price

            def go_short(self):
                pass

            def should_cancel_entry(self):
                return False

            def update_position(self):
                update_calls.append(self.index)
                # Close after 3 candles
                if self.index >= 5:
                    self.take_profit = self.position.qty, self.price + 5

        _run(UpdateTracker, list(range(10, 30)))

        # update_position should be called while position is open
        assert len(update_calls) > 0
        # All update_position calls should be after position was opened (index >= 3)
        for idx in update_calls:
            assert idx >= 3, f"update_position called at index {idx}, before position opened"


# ===========================================================================
# Entry/exit flow tests
# ===========================================================================
class TestEntryExitFlow:
    def test_long_entry_and_take_profit(self):
        class LongTP(Strategy):
            def should_long(self):
                return self.index == 2

            def should_short(self):
                return False

            def go_long(self):
                qty = 1
                self.buy = qty, self.price
                self.take_profit = qty, self.price + 5
                self.stop_loss = qty, self.price - 10

            def go_short(self):
                pass

            def should_cancel_entry(self):
                return False

        # Prices go up → TP should hit
        prices = list(range(10, 30))
        result = _run(LongTP, prices)
        assert result['metrics']['total'] >= 1
        assert result['metrics']['total_winning_trades'] >= 1

    def test_long_entry_and_stop_loss(self):
        class LongSL(Strategy):
            def should_long(self):
                return self.index == 5

            def should_short(self):
                return False

            def go_long(self):
                qty = 1
                self.buy = qty, self.price
                self.take_profit = qty, self.price + 100  # Won't hit
                self.stop_loss = qty, self.price - 2

            def go_short(self):
                pass

            def should_cancel_entry(self):
                return False

        # Prices go up then reverse hard
        prices = list(range(10, 25)) + list(range(24, 5, -1))
        result = _run(LongSL, prices)
        assert result['metrics']['total'] >= 1

    def test_short_entry(self):
        class ShortEntry(Strategy):
            def should_long(self):
                return False

            def should_short(self):
                return self.index == 2

            def go_long(self):
                pass

            def go_short(self):
                qty = 1
                self.sell = qty, self.price
                self.take_profit = qty, self.price - 3
                self.stop_loss = qty, self.price + 10

            def should_cancel_entry(self):
                return False

        # Prices go down → short TP should hit
        prices = list(range(30, 10, -1))
        result = _run(ShortEntry, prices)
        assert result['metrics']['total'] >= 1

    def test_should_cancel_entry_works(self):
        entry_attempts = []
        cancel_calls = []

        class CancelEntry(Strategy):
            def should_long(self):
                if self.index == 2:
                    entry_attempts.append(self.index)
                    return True
                return False

            def should_short(self):
                return False

            def go_long(self):
                # Use a limit order that won't fill immediately
                qty = 1
                self.buy = qty, self.price - 5  # Limit far below current price

            def go_short(self):
                pass

            def should_cancel_entry(self):
                if self.index > 3 and not self.position.is_open:
                    cancel_calls.append(self.index)
                    return True
                return False

        _run(CancelEntry, list(range(10, 30)))

        assert len(entry_attempts) > 0
        assert len(cancel_calls) > 0


# ===========================================================================
# Multiple trades per backtest
# ===========================================================================
class TestMultipleTrades:
    def test_can_open_after_close(self):
        """After a position is closed, a new one can be opened."""

        class ReEntryStrategy(Strategy):
            def should_long(self):
                return self.index in (2, 15) and not self.position.is_open

            def should_short(self):
                return False

            def go_long(self):
                qty = 1
                self.buy = qty, self.price
                self.take_profit = qty, self.price + 2
                self.stop_loss = qty, self.price - 10

            def go_short(self):
                pass

            def should_cancel_entry(self):
                return False

        prices = list(range(10, 50))
        result = _run(ReEntryStrategy, prices)
        # Should have completed at least 2 trades
        assert result['metrics']['total'] >= 2


# ===========================================================================
# Strategy state isolation between runs
# ===========================================================================
class TestStateIsolation:
    def test_strategy_state_does_not_leak_between_runs(self):
        """Running two backtests should not leak state."""
        trades_per_run = []

        class CountingStrategy(Strategy):
            def should_long(self):
                return self.index == 3 and not self.position.is_open

            def should_short(self):
                return False

            def go_long(self):
                qty = 1
                self.buy = qty, self.price
                self.take_profit = qty, self.price + 3
                self.stop_loss = qty, self.price - 10

            def go_short(self):
                pass

            def should_cancel_entry(self):
                return False

        prices = list(range(10, 30))

        r1 = _run(CountingStrategy, prices)
        trades_per_run.append(r1['metrics']['total'])

        r2 = _run(CountingStrategy, prices)
        trades_per_run.append(r2['metrics']['total'])

        assert trades_per_run[0] == trades_per_run[1]
        assert trades_per_run[0] > 0


# ===========================================================================
# Hyperparameter injection
# ===========================================================================
class TestHyperparameters:
    def test_hp_defaults_applied(self):
        hp_values = {}

        class HPStrategy(Strategy):
            def before(self):
                if self.index == 0:
                    hp_values['threshold'] = self.hp['threshold']
                    hp_values['multiplier'] = self.hp['multiplier']

            def should_long(self):
                return False

            def should_short(self):
                return False

            def go_long(self):
                pass

            def go_short(self):
                pass

            def should_cancel_entry(self):
                return False

            def hyperparameters(self):
                return [
                    {'name': 'threshold', 'type': int, 'min': 1, 'max': 100, 'default': 50},
                    {'name': 'multiplier', 'type': float, 'min': 0.1, 'max': 5.0, 'default': 1.5},
                ]

        _run(HPStrategy)

        assert hp_values['threshold'] == 50
        assert hp_values['multiplier'] == 1.5

    def test_index_increments_correctly(self):
        indices = []

        class IndexTracker(Strategy):
            def before(self):
                indices.append(self.index)

            def should_long(self):
                return False

            def should_short(self):
                return False

            def go_long(self):
                pass

            def go_short(self):
                pass

            def should_cancel_entry(self):
                return False

        prices = list(range(10, 20))  # 10 candles
        _run(IndexTracker, prices)

        assert indices == list(range(10))


# ===========================================================================
# on_close_position callback
# ===========================================================================
class TestCloseCallback:
    def test_on_close_position_called(self):
        close_events = []

        class CloseCallback(Strategy):
            def should_long(self):
                return self.index == 2 and not self.position.is_open

            def should_short(self):
                return False

            def go_long(self):
                qty = 1
                self.buy = qty, self.price
                self.take_profit = qty, self.price + 2
                self.stop_loss = qty, self.price - 10

            def go_short(self):
                pass

            def should_cancel_entry(self):
                return False

            def on_close_position(self, order, closed_trade):
                close_events.append({
                    'pnl': closed_trade.pnl,
                    'type': closed_trade.type,
                })

        prices = list(range(10, 30))
        _run(CloseCallback, prices)

        assert len(close_events) >= 1
        assert 'pnl' in close_events[0]
        assert close_events[0]['type'] == 'long'
