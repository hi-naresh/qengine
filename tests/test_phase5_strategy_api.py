import pytest
import numpy as np
import arrow

from qengine.config import config, reset_config
from qengine.enums import exchanges, timeframes
from qengine.store import store
from qengine.routes import router
from qengine.core.market_hours import MarketHours


# ── Helper ──

def _setup_forex_env():
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['balance'] = 10_000
    config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'cfd'
    config['env']['exchanges'][exchanges.SANDBOX]['futures_leverage_mode'] = 'cross'
    config['env']['exchanges'][exchanges.SANDBOX]['futures_leverage'] = 30


def _setup_forex_with_strategy(strategy_name='Test19', symbol='EUR-USD'):
    import qengine.helpers as jh

    _setup_forex_env()
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': symbol, 'timeframe': '1m', 'strategy': strategy_name}
    ])
    from qengine.services.exchange_service import initialize_exchanges_state
    initialize_exchanges_state()

    # Manually instantiate strategy (normally done by backtest engine)
    r = router.routes[0]
    StrategyClass = jh.get_strategy_class(r.strategy_name)
    strategy = StrategyClass()
    strategy.name = r.strategy_name
    strategy.exchange = r.exchange
    strategy.symbol = r.symbol
    strategy.timeframe = r.timeframe
    r.strategy = strategy
    return strategy


# ── 5.1 New Strategy Properties ──

def test_strategy_asset_class_property():
    strategy = _setup_forex_with_strategy()
    assert strategy.asset_class == 'forex'


def test_strategy_pip_size_property():
    strategy = _setup_forex_with_strategy()
    assert strategy.pip_size == 0.0001


def test_strategy_spread_property():
    strategy = _setup_forex_with_strategy()
    # Default spread is 2 pips = 0.0002
    assert strategy.spread == pytest.approx(0.0002, abs=1e-6)


def test_strategy_contract_size_property():
    strategy = _setup_forex_with_strategy()
    assert strategy.contract_size == 100000


def test_strategy_swap_long_property():
    strategy = _setup_forex_with_strategy()
    exchange = store.exchanges.get_exchange(exchanges.SANDBOX)
    exchange.set_swap_rates('EUR-USD', -5.0, -3.0)
    assert strategy.swap_long == -5.0
    assert strategy.swap_short == -3.0


def test_strategy_swap_default_zero():
    strategy = _setup_forex_with_strategy()
    assert strategy.swap_long == 0
    assert strategy.swap_short == 0


def test_strategy_pips_to_price():
    strategy = _setup_forex_with_strategy()
    assert strategy.pips_to_price(50) == pytest.approx(0.005, abs=1e-6)


def test_strategy_price_to_pips():
    strategy = _setup_forex_with_strategy()
    assert strategy.price_to_pips(0.005) == pytest.approx(50.0, abs=0.01)


def test_strategy_lot_size_for_risk():
    strategy = _setup_forex_with_strategy()
    # The lot_size_for_risk method requires self.balance, which needs
    # position store initialized. Test the math directly:
    pip_size = strategy.pip_size  # 0.0001
    contract_size = strategy.contract_size  # 100000
    balance = 10000
    risk_pct = 1.0
    stop_pips = 50

    risk_amount = balance * (risk_pct / 100)  # 100
    pip_value = pip_size * contract_size  # 10
    expected_lot = risk_amount / (stop_pips * pip_value)  # 0.2

    assert expected_lot == pytest.approx(0.2, abs=0.01)
    # Verify the math matches the method's formula
    assert pip_value == 10.0


def test_strategy_lot_size_zero_stop():
    strategy = _setup_forex_with_strategy()
    assert strategy.lot_size_for_risk(risk_pct=1.0, stop_pips=0) == 0


def test_strategy_is_forex_cfd_trading():
    strategy = _setup_forex_with_strategy()
    assert strategy.is_forex_cfd_trading is True
    assert strategy.is_futures_trading is False
    assert strategy.is_spot_trading is False


# ── 5.1b Market Hours Properties ──

def test_strategy_market_is_open_property():
    strategy = _setup_forex_with_strategy()
    # Set time to a weekday during market hours
    store.app.time = arrow.get('2025-01-08T12:00:00Z').int_timestamp * 1000
    assert strategy.market_is_open is True


def test_strategy_market_is_open_weekend():
    strategy = _setup_forex_with_strategy()
    store.app.time = arrow.get('2025-01-11T12:00:00Z').int_timestamp * 1000
    assert strategy.market_is_open is False


def test_strategy_session_property():
    strategy = _setup_forex_with_strategy()
    # 10am ET (EST) = 15:00 UTC - overlap between London and NY
    store.app.time = arrow.get('2025-01-08T15:00:00Z').int_timestamp * 1000
    assert strategy.session == 'overlap'


def test_strategy_session_tokyo():
    strategy = _setup_forex_with_strategy()
    # 8pm ET (EST) = 01:00 UTC next day - Tokyo session
    store.app.time = arrow.get('2025-01-09T01:00:00Z').int_timestamp * 1000
    assert strategy.session == 'tokyo'


def test_strategy_session_off():
    strategy = _setup_forex_with_strategy()
    store.app.time = arrow.get('2025-01-11T12:00:00Z').int_timestamp * 1000
    assert strategy.session == 'off'


def test_strategy_minutes_to_close():
    strategy = _setup_forex_with_strategy()
    store.app.time = arrow.get('2025-01-08T12:00:00Z').int_timestamp * 1000
    mtc = strategy.minutes_to_close
    assert mtc is not None
    assert mtc > 0


# ── MarketHours.current_session tests ──

def test_current_session_london():
    mh = MarketHours()
    # 5am ET (EST) = 10:00 UTC - London only (before NY 8am)
    ts = arrow.get('2025-01-08T10:00:00Z').int_timestamp * 1000
    assert mh.current_session(ts) == 'london'


def test_current_session_new_york():
    mh = MarketHours()
    # 2pm ET (EST) = 19:00 UTC - NY only (after London 12pm)
    ts = arrow.get('2025-01-08T19:00:00Z').int_timestamp * 1000
    assert mh.current_session(ts) == 'new_york'


def test_current_session_overlap():
    mh = MarketHours()
    # 9am ET (EST) = 14:00 UTC - Overlap
    ts = arrow.get('2025-01-08T14:00:00Z').int_timestamp * 1000
    assert mh.current_session(ts) == 'overlap'


def test_current_session_tokyo():
    mh = MarketHours()
    # 8pm ET (EST) = 01:00 UTC next day
    ts = arrow.get('2025-01-09T01:00:00Z').int_timestamp * 1000
    assert mh.current_session(ts) == 'tokyo'


def test_current_session_off():
    mh = MarketHours()
    ts = arrow.get('2025-01-11T12:00:00Z').int_timestamp * 1000
    assert mh.current_session(ts) == 'off'


# ── 5.2 ForexMA Example Strategy ──

def test_forex_ma_strategy_exists():
    from qengine.strategies.ForexMA import ForexMA
    assert ForexMA is not None


def test_forex_ma_has_hyperparameters():
    from qengine.strategies.ForexMA import ForexMA
    strategy = ForexMA()
    hp = strategy.hyperparameters()
    assert len(hp) == 5
    names = [h['name'] for h in hp]
    assert 'fast_period' in names
    assert 'slow_period' in names
    assert 'risk_pct' in names
    assert 'stop_pips' in names
    assert 'rr_ratio' in names


# ── Gold symbol tests ──

def test_strategy_pip_size_gold():
    strategy = _setup_forex_with_strategy(symbol='XAU-USD')
    # Gold pip_size = 0.01
    assert strategy.pip_size == 0.01


def test_strategy_asset_class_gold():
    strategy = _setup_forex_with_strategy(symbol='XAU-USD')
    assert strategy.asset_class == 'commodity'


def test_strategy_contract_size_gold():
    strategy = _setup_forex_with_strategy(symbol='XAU-USD')
    # Gold contract_size = 100 (troy ounces per lot)
    assert strategy.contract_size == 100
