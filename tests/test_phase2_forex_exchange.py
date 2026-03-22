import numpy as np
import pytest

import qengine.helpers as jh
from qengine.config import config, reset_config
from qengine.enums import exchanges, brokers, sides, timeframes
from qengine.factories import candles_from_close_prices
from qengine.modes import backtest_mode
from qengine.models.ForexCFDExchange import ForexCFDExchange
from qengine.models.Position import Position
from qengine.core.market_hours import market_hours
from qengine.core.instruments import instrument_registry
from qengine.store import store
from qengine.routes import router


# ── Helper to set up forex backtesting ──

def setup_forex_backtest(leverage=30, balance=10_000):
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['balance'] = balance
    config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'forex_cfd'
    config['env']['exchanges'][exchanges.SANDBOX]['futures_leverage_mode'] = 'cross'
    config['env']['exchanges'][exchanges.SANDBOX]['futures_leverage'] = leverage


def get_forex_candles(symbol='EUR-USD', count=100):
    return {
        jh.key(exchanges.SANDBOX, symbol): {
            'exchange': exchanges.SANDBOX,
            'symbol': symbol,
            'candles': candles_from_close_prices(range(1, count)),
        }
    }


def run_forex_backtest(strategy_name, symbol='EUR-USD', leverage=30, candles_count=100, timeframe='1m'):
    setup_forex_backtest(leverage=leverage)
    routes = [{'symbol': symbol, 'timeframe': timeframe, 'strategy': strategy_name}]
    candles = get_forex_candles(symbol, candles_count)
    backtest_mode.run('000', False, {}, exchanges.SANDBOX, routes, [], '2019-04-01', '2019-04-02', candles)


# ── 2.1 ForexCFDExchange Model Tests ──

def test_forex_exchange_instantiation():
    """Test that ForexCFDExchange can be instantiated via the backtest engine."""
    setup_forex_backtest()
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'EUR-USD', 'timeframe': '1m', 'strategy': 'Test19'}
    ])

    from qengine.services.exchange_service import initialize_exchanges_state
    initialize_exchanges_state()

    exchange = store.exchanges.storage[exchanges.SANDBOX]
    assert isinstance(exchange, ForexCFDExchange)
    assert exchange.type == 'forex_cfd'
    assert exchange.default_leverage == 30
    assert exchange.wallet_balance == 10_000


def test_forex_exchange_spread():
    setup_forex_backtest()
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'EUR-USD', 'timeframe': '1m', 'strategy': 'Test19'}
    ])

    from qengine.services.exchange_service import initialize_exchanges_state
    initialize_exchanges_state()

    exchange = store.exchanges.storage[exchanges.SANDBOX]
    assert isinstance(exchange, ForexCFDExchange)

    # Default spread should be 2 pips
    default_spread = exchange.get_spread('EUR-USD')
    assert default_spread == 0.0001 * 2  # 2 pips for EUR-USD

    # Custom spread
    exchange.set_spread('EUR-USD', 0.00015)  # 1.5 pips
    assert exchange.get_spread('EUR-USD') == 0.00015


def test_forex_exchange_charge_spread():
    setup_forex_backtest()
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'EUR-USD', 'timeframe': '1m', 'strategy': 'Test19'}
    ])

    from qengine.services.exchange_service import initialize_exchanges_state
    initialize_exchanges_state()

    exchange = store.exchanges.storage[exchanges.SANDBOX]
    exchange.set_spread('EUR-USD', 0.0002)  # 2 pips

    initial_balance = exchange.wallet_balance
    # Charge spread for 0.1 lots (qty=0.1, contract_size=100000)
    # cost = 0.0002 * 100000 * 0.1 = 2.0
    cost = exchange.charge_spread('EUR-USD', 0.1)
    assert round(cost, 2) == 2.0
    assert round(exchange.wallet_balance, 2) == round(initial_balance - 2.0, 2)


def test_forex_exchange_swap_rates():
    setup_forex_backtest()
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'EUR-USD', 'timeframe': '1m', 'strategy': 'Test19'}
    ])

    from qengine.services.exchange_service import initialize_exchanges_state
    initialize_exchanges_state()

    exchange = store.exchanges.storage[exchanges.SANDBOX]

    # Set swap rates (per lot per day)
    exchange.set_swap_rates('EUR-USD', swap_long=-0.5, swap_short=0.3)

    initial_balance = exchange.wallet_balance
    # charge_overnight_swap for 0.1 lots long
    # cost = |(-0.5) * 100000 * 0.1 / 365| = |(-5000) / 365| = ~13.70
    charge = exchange.charge_overnight_swap('EUR-USD', 0.1, 'long')
    assert charge > 0
    assert exchange.wallet_balance < initial_balance


def test_forex_exchange_no_swap_when_zero():
    setup_forex_backtest()
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'EUR-USD', 'timeframe': '1m', 'strategy': 'Test19'}
    ])

    from qengine.services.exchange_service import initialize_exchanges_state
    initialize_exchanges_state()

    exchange = store.exchanges.storage[exchanges.SANDBOX]
    # Default swap rates are (0, 0)
    initial_balance = exchange.wallet_balance
    charge = exchange.charge_overnight_swap('EUR-USD', 0.1, 'long')
    assert charge == 0.0
    assert exchange.wallet_balance == initial_balance


# ── 2.2 Forex Backtest Integration ──

def test_forex_backtest_runs():
    """Test that a simple backtest runs with forex_cfd exchange type."""
    run_forex_backtest('Test19')
    # If it gets here without error, it passed


def test_forex_backtest_with_different_leverage():
    """Test that leverage setting works with forex exchange."""
    run_forex_backtest('Test19', leverage=50)


# ── 2.3 Position Model Forex Properties ──

def test_position_pip_pnl():
    pos = Position()
    pos.symbol = 'EUR-USD'
    pos.entry_price = 1.1000
    pos.current_price = 1.1050
    pos.qty = 1.0  # long
    pos.exchange_name = exchanges.SANDBOX

    # Mock exchange
    class MockExchange:
        type = 'forex_cfd'
        default_leverage = 30
    pos.exchange = MockExchange()

    # 50 pips profit (1.1050 - 1.1000) / 0.0001
    assert round(pos.pip_pnl, 1) == 50.0
    assert pos.type == 'long'


def test_position_pip_pnl_short():
    pos = Position()
    pos.symbol = 'EUR-USD'
    pos.entry_price = 1.1050
    pos.current_price = 1.1000
    pos.qty = -1.0  # short
    pos.exchange_name = exchanges.SANDBOX

    class MockExchange:
        type = 'forex_cfd'
        default_leverage = 30
    pos.exchange = MockExchange()

    # 50 pips profit (short: entry - current) / pip_size
    assert round(pos.pip_pnl, 1) == 50.0


def test_position_pip_pnl_jpy_pair():
    pos = Position()
    pos.symbol = 'USD-JPY'
    pos.entry_price = 150.00
    pos.current_price = 150.50
    pos.qty = 1.0
    pos.exchange_name = exchanges.SANDBOX

    class MockExchange:
        type = 'forex_cfd'
        default_leverage = 30
    pos.exchange = MockExchange()

    # 50 pips for JPY pair (0.50 / 0.01)
    assert pos.pip_pnl == 50.0


def test_position_pip_pnl_closed():
    pos = Position()
    pos.symbol = 'EUR-USD'
    pos.entry_price = 1.1000
    pos.current_price = 1.1050
    pos.qty = 0  # closed
    pos.exchange_name = exchanges.SANDBOX

    class MockExchange:
        type = 'forex_cfd'
        default_leverage = 30
    pos.exchange = MockExchange()

    assert pos.pip_pnl == 0


def test_position_margin_used():
    pos = Position()
    pos.symbol = 'EUR-USD'
    pos.entry_price = 1.1000
    pos.current_price = 1.1050
    pos.qty = 0.1  # 0.1 lots
    pos.exchange_name = exchanges.SANDBOX

    class MockExchange:
        type = 'forex_cfd'
        default_leverage = 30
    pos.exchange = MockExchange()

    # margin = |qty| * contract_size * entry_price * margin_rate
    # = 0.1 * 100000 * 1.1000 * 0.0333 = 366.3
    margin = pos.margin_used
    assert margin > 0
    assert round(margin, 1) == 366.3


def test_position_margin_used_closed():
    pos = Position()
    pos.symbol = 'EUR-USD'
    pos.qty = 0
    pos.exchange_name = exchanges.SANDBOX

    class MockExchange:
        type = 'forex_cfd'
        default_leverage = 30
    pos.exchange = MockExchange()

    assert pos.margin_used == 0


def test_position_mode_forex():
    pos = Position()
    pos.qty = 1.0
    pos.exchange_name = exchanges.SANDBOX

    class MockExchange:
        type = 'forex_cfd'
        default_leverage = 30
    pos.exchange = MockExchange()

    assert pos.mode == 'forex_cfd'


def test_position_leverage_forex():
    pos = Position()
    pos.qty = 1.0
    pos.exchange_name = exchanges.SANDBOX

    class MockExchange:
        type = 'forex_cfd'
        default_leverage = 30
    pos.exchange = MockExchange()

    assert pos.leverage == 30


def test_position_to_dict_forex():
    pos = Position()
    pos.symbol = 'EUR-USD'
    pos.entry_price = 1.1000
    pos.current_price = 1.1050
    pos.qty = 0.1
    pos.exchange_name = exchanges.SANDBOX

    class MockExchange:
        type = 'forex_cfd'
        default_leverage = 30
    pos.exchange = MockExchange()

    d = pos.to_dict
    assert 'pip_pnl' in d
    assert 'margin_used' in d
    assert round(d['pip_pnl'], 1) == 50.0
    assert d['mode'] == 'forex_cfd'


# ── 2.4 Market Hours Tests ──

def test_forex_open_weekday():
    """Monday 12:00 UTC - market should be open."""
    # Monday Jan 6, 2025 12:00 UTC
    from datetime import datetime, timezone
    dt = datetime(2025, 1, 6, 12, 0, tzinfo=timezone.utc)
    ts = int(dt.timestamp() * 1000)
    assert market_hours.is_market_open('EUR-USD', ts) is True


def test_forex_closed_saturday():
    """Saturday - market should be closed."""
    from datetime import datetime, timezone
    dt = datetime(2025, 1, 4, 12, 0, tzinfo=timezone.utc)  # Saturday
    ts = int(dt.timestamp() * 1000)
    assert market_hours.is_market_open('EUR-USD', ts) is False


def test_forex_closed_sunday_morning():
    """Sunday morning UTC (before 5pm ET) - market should be closed."""
    from datetime import datetime, timezone
    dt = datetime(2025, 1, 5, 12, 0, tzinfo=timezone.utc)  # Sunday 12:00 UTC = 7am ET
    ts = int(dt.timestamp() * 1000)
    assert market_hours.is_market_open('EUR-USD', ts) is False


def test_forex_open_sunday_evening():
    """Sunday 10:30pm UTC (5:30pm ET) - market should be open."""
    from datetime import datetime, timezone
    dt = datetime(2025, 1, 5, 22, 30, tzinfo=timezone.utc)  # Sunday 22:30 UTC = 5:30pm ET
    ts = int(dt.timestamp() * 1000)
    assert market_hours.is_market_open('EUR-USD', ts) is True


def test_forex_closed_friday_evening():
    """Friday 10:30pm UTC (5:30pm ET) - market should be closed."""
    from datetime import datetime, timezone
    dt = datetime(2025, 1, 3, 22, 30, tzinfo=timezone.utc)  # Friday 22:30 UTC = 5:30pm ET
    ts = int(dt.timestamp() * 1000)
    assert market_hours.is_market_open('EUR-USD', ts) is False


def test_commodity_metals_daily_break():
    """Metals have a daily break at 5pm ET."""
    from datetime import datetime, timezone
    # Wednesday 10pm UTC = 5pm ET (EST)
    dt = datetime(2025, 1, 8, 22, 0, tzinfo=timezone.utc)
    ts = int(dt.timestamp() * 1000)
    assert market_hours.is_market_open('XAU-USD', ts) is False


def test_commodity_metals_open_during_session():
    from datetime import datetime, timezone
    # Wednesday 3pm UTC = 10am ET - should be open
    dt = datetime(2025, 1, 8, 15, 0, tzinfo=timezone.utc)
    ts = int(dt.timestamp() * 1000)
    assert market_hours.is_market_open('XAU-USD', ts) is True


def test_rollover_time():
    """5pm ET is rollover time."""
    from datetime import datetime, timezone
    # 10pm UTC = 5pm ET (EST, January)
    dt = datetime(2025, 1, 8, 22, 0, tzinfo=timezone.utc)
    ts = int(dt.timestamp() * 1000)
    assert market_hours.is_rollover_time(ts) is True


def test_not_rollover_time():
    from datetime import datetime, timezone
    dt = datetime(2025, 1, 8, 15, 0, tzinfo=timezone.utc)
    ts = int(dt.timestamp() * 1000)
    assert market_hours.is_rollover_time(ts) is False


def test_unknown_symbol_defaults_to_forex():
    """Unknown symbols should default to forex hours."""
    from datetime import datetime, timezone
    dt = datetime(2025, 1, 6, 12, 0, tzinfo=timezone.utc)  # Monday
    ts = int(dt.timestamp() * 1000)
    assert market_hours.is_market_open('SOME-UNKNOWN', ts) is True


def test_minutes_to_close_when_closed():
    from datetime import datetime, timezone
    dt = datetime(2025, 1, 4, 12, 0, tzinfo=timezone.utc)  # Saturday
    ts = int(dt.timestamp() * 1000)
    assert market_hours.minutes_to_close('EUR-USD', ts) == 0


# ── 2.5 Exchange Service Factory Tests ──

def test_exchange_service_creates_forex_cfd():
    setup_forex_backtest()
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'EUR-USD', 'timeframe': '1m', 'strategy': 'Test19'}
    ])

    from qengine.services.exchange_service import initialize_exchanges_state
    initialize_exchanges_state()

    exchange = store.exchanges.storage[exchanges.SANDBOX]
    assert isinstance(exchange, ForexCFDExchange)
    assert exchange.type == 'forex_cfd'


def test_exchange_service_still_creates_futures():
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'futures'
    config['env']['exchanges'][exchanges.SANDBOX]['futures_leverage_mode'] = 'cross'
    config['env']['exchanges'][exchanges.SANDBOX]['futures_leverage'] = 10
    config['env']['exchanges'][exchanges.SANDBOX]['balance'] = 10_000

    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USDT', 'timeframe': '1m', 'strategy': 'Test19'}
    ])

    from qengine.services.exchange_service import initialize_exchanges_state
    from qengine.models.FuturesExchange import FuturesExchange
    initialize_exchanges_state()

    exchange = store.exchanges.storage[exchanges.SANDBOX]
    assert isinstance(exchange, FuturesExchange)
    assert exchange.type == 'futures'


def test_exchange_service_still_creates_spot():
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'spot'
    config['env']['exchanges'][exchanges.SANDBOX]['balance'] = 10_000

    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USDT', 'timeframe': '1m', 'strategy': 'Test19'}
    ])

    from qengine.services.exchange_service import initialize_exchanges_state
    from qengine.models.SpotExchange import SpotExchange
    initialize_exchanges_state()

    exchange = store.exchanges.storage[exchanges.SANDBOX]
    assert isinstance(exchange, SpotExchange)
    assert exchange.type == 'spot'
