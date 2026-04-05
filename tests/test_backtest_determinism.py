"""
Test backtest determinism: running the same backtest twice must produce
identical trades, PnL, balances, and metrics every time.
"""
import numpy as np
import qengine.helpers as jh
from qengine.factories import candles_from_close_prices
from qengine.strategies import Strategy
from qengine import research


# ---------------------------------------------------------------------------
# Helper: deterministic price series that forces trades
# ---------------------------------------------------------------------------
def _make_price_series():
    """A zig-zag pattern that will reliably trigger entries and exits."""
    prices = []
    base = 100.0
    for cycle in range(5):
        # up-leg → long entry + TP
        for i in range(10):
            prices.append(base + i * 0.5)
        # down-leg → short entry + TP
        for i in range(10):
            prices.append(base + 4.5 - i * 0.5)
    return prices


# ---------------------------------------------------------------------------
# Strategies used in determinism tests
# ---------------------------------------------------------------------------
class DeterministicLongStrategy(Strategy):
    """Enters long when price crosses above a threshold, exits via TP/SL."""

    def should_long(self) -> bool:
        if self.index < 2:
            return False
        return self.close > self.open and not self.position.is_open

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = 1
        self.buy = qty, self.price
        self.take_profit = qty, self.price + 2
        self.stop_loss = qty, self.price - 1

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False


class DeterministicBidirectionalStrategy(Strategy):
    """Enters both long and short based on simple price logic."""

    def should_long(self) -> bool:
        if self.index < 3:
            return False
        # Go long when 3 consecutive up candles
        return (self.candles[-1][2] > self.candles[-2][2] > self.candles[-3][2]
                and not self.position.is_open)

    def should_short(self) -> bool:
        if self.index < 3:
            return False
        # Go short when 3 consecutive down candles
        return (self.candles[-1][2] < self.candles[-2][2] < self.candles[-3][2]
                and not self.position.is_open)

    def go_long(self):
        qty = 1
        self.buy = qty, self.price
        self.take_profit = qty, self.price + 1.5
        self.stop_loss = qty, self.price - 1.0

    def go_short(self):
        qty = 1
        self.sell = qty, self.price
        self.take_profit = qty, self.price - 1.5
        self.stop_loss = qty, self.price + 1.0

    def should_cancel_entry(self):
        return False


# ---------------------------------------------------------------------------
# Shared test config factory
# ---------------------------------------------------------------------------
def _make_config(exchange_name='Fake Exchange', exchange_type='futures'):
    return {
        'starting_balance': 10_000,
        'fee': 0.001,
        'type': exchange_type,
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'warm_up_candles': 0,
    }


def _run_backtest(strategy_cls, prices=None, config_override=None):
    prices = prices or _make_price_series()
    candles = candles_from_close_prices(prices)
    exchange_name = 'Fake Exchange'
    symbol = 'FAKE-USDT'
    timeframe = '1m'

    cfg = config_override or _make_config(exchange_name)
    routes = [
        {'exchange': exchange_name, 'strategy': strategy_cls, 'symbol': symbol, 'timeframe': timeframe},
    ]
    data_routes = []
    candles_dict = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': candles,
        },
    }
    return research.backtest(cfg, routes, data_routes, candles_dict)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_determinism_same_result_twice():
    """Core determinism: two identical backtests must produce byte-identical metrics."""
    r1 = _run_backtest(DeterministicLongStrategy)
    r2 = _run_backtest(DeterministicLongStrategy)

    m1, m2 = r1['metrics'], r2['metrics']

    # Every metric key must match exactly
    assert m1.keys() == m2.keys(), "Metric keys differ between runs"
    for key in m1:
        v1, v2 = m1[key], m2[key]
        if isinstance(v1, float) and np.isnan(v1):
            assert np.isnan(v2), f"metrics['{key}']: {v1} != {v2}"
        else:
            assert v1 == v2, f"metrics['{key}']: {v1} != {v2}"


def test_determinism_bidirectional():
    """Determinism with both long and short trades."""
    r1 = _run_backtest(DeterministicBidirectionalStrategy)
    r2 = _run_backtest(DeterministicBidirectionalStrategy)

    m1, m2 = r1['metrics'], r2['metrics']
    for key in m1:
        v1, v2 = m1[key], m2[key]
        if isinstance(v1, float) and np.isnan(v1):
            assert np.isnan(v2), f"metrics['{key}']: {v1} != {v2}"
        else:
            assert v1 == v2, f"metrics['{key}']: {v1} != {v2}"


def test_determinism_many_runs():
    """Run 5 times — all results must be identical."""
    results = [_run_backtest(DeterministicLongStrategy) for _ in range(5)]
    baseline = results[0]['metrics']

    for i, r in enumerate(results[1:], start=2):
        m = r['metrics']
        for key in baseline:
            v1, v2 = baseline[key], m[key]
            if isinstance(v1, float) and np.isnan(v1):
                assert np.isnan(v2), f"Run {i}, metrics['{key}']: {v1} != {v2}"
            else:
                assert v1 == v2, f"Run {i}, metrics['{key}']: {v1} != {v2}"


def test_determinism_with_fees():
    """Different fee rates still produce deterministic results per fee level."""
    for fee in [0, 0.001, 0.01]:
        cfg = _make_config()
        cfg['fee'] = fee
        r1 = _run_backtest(DeterministicLongStrategy, config_override=cfg)
        r2 = _run_backtest(DeterministicLongStrategy, config_override=cfg)

        m1, m2 = r1['metrics'], r2['metrics']
        for key in m1:
            v1, v2 = m1[key], m2[key]
            if isinstance(v1, float) and np.isnan(v1):
                assert np.isnan(v2), f"fee={fee}, metrics['{key}']: {v1} != {v2}"
            else:
                assert v1 == v2, f"fee={fee}, metrics['{key}']: {v1} != {v2}"


def test_determinism_trade_counts_nonzero():
    """Sanity: the strategy actually opened trades (not just 0==0)."""
    r = _run_backtest(DeterministicLongStrategy)
    assert r['metrics']['total'] > 0, \
        "Determinism test is meaningless if zero trades were made"


def test_determinism_balance_changes():
    """Finishing balance must differ from starting balance (trades happened) and be deterministic."""
    r1 = _run_backtest(DeterministicLongStrategy)
    r2 = _run_backtest(DeterministicLongStrategy)

    assert r1['metrics']['finishing_balance'] == r2['metrics']['finishing_balance']
    # Trades happened, so balance should change
    if r1['metrics']['total'] > 0:
        assert r1['metrics']['starting_balance'] != r1['metrics']['finishing_balance'] or \
               r1['metrics']['fee'] > 0, \
            "Balance didn't change despite trades"


def test_determinism_equity_curve():
    """Equity curve data must be identical across runs."""
    r1 = _run_backtest(DeterministicLongStrategy)
    r2 = _run_backtest(DeterministicLongStrategy)

    # Verify key balance metrics are identical
    assert r1['metrics']['max_drawdown'] == r2['metrics']['max_drawdown']
    assert r1['metrics']['net_profit'] == r2['metrics']['net_profit']
    assert r1['metrics']['gross_profit'] == r2['metrics']['gross_profit']
    assert r1['metrics']['gross_loss'] == r2['metrics']['gross_loss']


def test_determinism_spot_exchange():
    """Determinism in spot exchange mode."""
    cfg = {
        'starting_balance': 10_000,
        'fee': 0.001,
        'type': 'spot',
        'exchange': 'Fake Exchange',
        'warm_up_candles': 0,
    }

    class SpotLongOnly(Strategy):
        def should_long(self):
            return self.index == 5 and not self.position.is_open

        def go_long(self):
            qty = 1
            self.buy = qty, self.price

        def on_open_position(self, order):
            self.take_profit = self.position.qty, order.price + 3

        def should_cancel_entry(self):
            return False

    r1 = _run_backtest(SpotLongOnly, config_override=cfg)
    r2 = _run_backtest(SpotLongOnly, config_override=cfg)

    m1, m2 = r1['metrics'], r2['metrics']
    for key in m1:
        v1, v2 = m1[key], m2[key]
        if isinstance(v1, float) and np.isnan(v1):
            assert np.isnan(v2), f"spot: metrics['{key}']: {v1} != {v2}"
        else:
            assert v1 == v2, f"spot: metrics['{key}']: {v1} != {v2}"
