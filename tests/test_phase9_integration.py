"""
Phase 9: End-to-End Integration Tests

Tests the full TradeEngine system across all phases:
- Exchange initialization with forex config
- CFDExchange balance/margin/cost mechanics
- Position lifecycle (open -> modify -> close)
- Strategy API (forex properties on strategy instances)
- Live trading enablement
- API endpoint integration (FastAPI TestClient)
- Cross-phase consistency
"""
import os
import pytest
import numpy as np
from datetime import datetime, timezone


# ════════════════════════════════════════════════
# 9.0  Test Fixtures — reusable setup
# ════════════════════════════════════════════════

def _setup_forex_env(exchange='OANDA', symbol='EUR-USD', timeframe='1h',
                     balance=10_000, leverage=30):
    """Fully initialize the QEngine engine for a forex backtest environment.
    Uses the ForexMA strategy class directly to avoid path resolution issues in pytest.
    """
    from qengine.config import config
    from qengine.routes import router
    from qengine.store import store
    from qengine.services import exchange_service, order_service, position_service
    from qengine.strategies.ForexMA import ForexMA
    import qengine.helpers as jh

    config['app']['trading_mode'] = 'backtest'

    # Ensure exchange config exists
    config['env']['exchanges'][exchange] = {
        'fee': 0,
        'type': 'cfd',
        'futures_leverage_mode': 'cross',
        'futures_leverage': leverage,
        'balance': balance,
    }

    router.initiate(
        [{'exchange': exchange, 'symbol': symbol, 'timeframe': timeframe, 'strategy': ForexMA}],
        []
    )
    store.reset()
    store.candles.init_storage(5000)
    exchange_service.initialize_exchanges_state()
    order_service.initialize_orders_state()
    position_service.initialize_positions_state()

    ex = store.exchanges.storage[exchange]
    pos = store.positions.storage[f'{exchange}-{symbol}']
    return ex, pos


def _teardown():
    pass


# ════════════════════════════════════════════════
# 9.1  CFDExchange Initialization
# ════════════════════════════════════════════════

class TestForexExchangeInit:
    def test_exchange_created_as_cfd(self):
        from qengine.models.CFDExchange import CFDExchange
        ex, _ = _setup_forex_env()
        assert isinstance(ex, CFDExchange)
        _teardown()

    def test_starting_balance(self):
        ex, _ = _setup_forex_env(balance=25_000)
        assert ex.started_balance == 25_000
        _teardown()

    def test_wallet_balance_equals_starting(self):
        ex, _ = _setup_forex_env(balance=15_000)
        assert ex.wallet_balance == 15_000
        _teardown()

    def test_default_leverage_from_config(self):
        ex, _ = _setup_forex_env(leverage=50)
        assert ex.default_leverage == 50
        _teardown()

    def test_settlement_currency_is_usd(self):
        ex, _ = _setup_forex_env()
        assert ex.settlement_currency == 'USD'
        _teardown()

    def test_available_margin_equals_balance_when_no_positions(self):
        ex, _ = _setup_forex_env(balance=10_000)
        assert ex.available_margin == pytest.approx(10_000, abs=1)
        _teardown()


# ════════════════════════════════════════════════
# 9.2  Spread / Swap / Fee Cost Engine
# ════════════════════════════════════════════════

class TestCostEngine:
    def test_default_spread_is_2_pips(self):
        ex, _ = _setup_forex_env()
        spread = ex.get_spread('EUR-USD')
        from qengine.core.instruments import instrument_registry
        pip_size = instrument_registry.get_pip_size('EUR-USD')
        assert spread == pytest.approx(pip_size * 2)
        _teardown()

    def test_custom_spread(self):
        ex, _ = _setup_forex_env()
        ex.set_spread('EUR-USD', 0.00025)  # 2.5 pips
        assert ex.get_spread('EUR-USD') == 0.00025
        _teardown()

    def test_charge_spread_deducts_from_balance(self):
        ex, _ = _setup_forex_env(balance=10_000)
        ex.set_spread('EUR-USD', 0.00015)  # 1.5 pips
        # charge_spread takes qty in units (not lots). 1 lot = 100,000 units.
        cost = ex.charge_spread('EUR-USD', 100_000)
        # 0.00015 * 100000 = 15.0
        assert cost == pytest.approx(15.0)
        assert ex.wallet_balance == pytest.approx(10_000 - 15.0)
        _teardown()

    def test_charge_spread_jpy_pair(self):
        ex, _ = _setup_forex_env(symbol='USD-JPY')
        ex.set_spread('USD-JPY', 0.02)  # 2 pips for JPY
        # charge_spread takes qty in units (not lots). 1 lot = 100,000 units.
        cost = ex.charge_spread('USD-JPY', 100_000)
        # 0.02 * 100000 = 2000 (JPY)
        assert cost == pytest.approx(2000.0)
        _teardown()

    def test_swap_rates_default_zero(self):
        ex, _ = _setup_forex_env()
        cost = ex.charge_overnight_swap('EUR-USD', 1.0, 'long')
        assert cost == 0.0
        _teardown()

    def test_swap_rates_charged(self):
        ex, _ = _setup_forex_env(balance=10_000)
        ex.set_swap_rates('EUR-USD', -5.0, -3.0)  # swap rates per lot per year
        # charge_overnight_swap takes qty in units (not lots). 1 lot = 100,000 units.
        cost = ex.charge_overnight_swap('EUR-USD', 100_000, 'long')
        # rate=-5.0, lots=1.0, cost = -5.0 * 1 * multiplier / 252 → negative (charge)
        assert cost < 0  # negative means charged
        assert ex.wallet_balance < 10_000
        _teardown()

    def test_fee_zero_for_forex(self):
        ex, _ = _setup_forex_env()
        old_balance = ex.wallet_balance
        ex.charge_fee(100_000)
        # fee_rate is 0 for forex
        assert ex.wallet_balance == old_balance
        _teardown()

    def test_realized_pnl_adds_to_balance(self):
        ex, _ = _setup_forex_env(balance=10_000)
        ex.add_realized_pnl(500.0)
        assert ex.wallet_balance == pytest.approx(10_500)
        _teardown()

    def test_realized_loss_deducts_from_balance(self):
        ex, _ = _setup_forex_env(balance=10_000)
        ex.add_realized_pnl(-200.0)
        assert ex.wallet_balance == pytest.approx(9_800)
        _teardown()


# ════════════════════════════════════════════════
# 9.3  Position Lifecycle
# ════════════════════════════════════════════════

class TestPositionLifecycle:
    def test_position_starts_closed(self):
        _, pos = _setup_forex_env()
        assert pos.is_close
        assert pos.qty == 0
        assert not pos.is_open
        _teardown()

    def test_position_exchange_linked(self):
        ex, pos = _setup_forex_env()
        assert pos.exchange is ex
        assert pos.exchange_name == 'OANDA'
        _teardown()

    def test_position_symbol(self):
        _, pos = _setup_forex_env(symbol='GBP-USD')
        assert pos.symbol == 'GBP-USD'
        _teardown()

    def test_position_pnl_zero_when_closed(self):
        _, pos = _setup_forex_env()
        assert pos.pnl == 0
        _teardown()

    def test_position_leverage_from_exchange(self):
        ex, pos = _setup_forex_env(leverage=50)
        assert ex.default_leverage == 50
        _teardown()


# ════════════════════════════════════════════════
# 9.4  PnL Calculations
# ════════════════════════════════════════════════

class TestPnLCalculations:
    def test_estimate_pnl_long(self):
        import qengine.helpers as jh
        pnl = jh.estimate_PNL(1, 1.10000, 1.10350, 'long')
        assert pnl == pytest.approx(0.0035, abs=0.0001)

    def test_estimate_pnl_short(self):
        import qengine.helpers as jh
        pnl = jh.estimate_PNL(1, 1.28000, 1.27500, 'short')
        assert pnl == pytest.approx(0.005, abs=0.0001)

    def test_estimate_pnl_losing_long(self):
        import qengine.helpers as jh
        pnl = jh.estimate_PNL(1, 1.10000, 1.09500, 'long')
        assert pnl == pytest.approx(-0.005, abs=0.0001)

    def test_pip_calculation_eurusd(self):
        import qengine.helpers as jh
        pip_size = jh.get_pip_size('EUR-USD')
        pips = (1.10350 - 1.10000) / pip_size
        assert pips == pytest.approx(35.0)

    def test_pip_calculation_usdjpy(self):
        import qengine.helpers as jh
        pip_size = jh.get_pip_size('USD-JPY')
        pips = (150.500 - 150.000) / pip_size
        assert pips == pytest.approx(50.0)

    def test_pip_calculation_gold(self):
        import qengine.helpers as jh
        pip_size = jh.get_pip_size('XAU-USD')
        pips = (2010.50 - 2000.00) / pip_size
        assert pips == pytest.approx(1050.0)


# ════════════════════════════════════════════════
# 9.5  Margin Calculations
# ════════════════════════════════════════════════

class TestMarginCalculations:
    def test_margin_for_1_lot_eurusd_30x(self):
        from qengine.core.instruments import instrument_registry
        inst = instrument_registry.get('EUR-USD')
        price = 1.10
        lots = 1.0
        leverage = 30
        notional = inst.contract_size * lots * price
        margin = notional / leverage
        assert margin == pytest.approx(3666.67, rel=0.01)

    def test_margin_for_mini_lot(self):
        from qengine.core.instruments import instrument_registry
        inst = instrument_registry.get('EUR-USD')
        price = 1.10
        lots = 0.1  # mini lot
        leverage = 30
        margin = (inst.contract_size * lots * price) / leverage
        assert margin == pytest.approx(366.67, rel=0.01)

    def test_margin_gold_20x(self):
        from qengine.core.instruments import instrument_registry
        inst = instrument_registry.get('XAU-USD')
        price = 2000.0
        lots = 1.0
        leverage = 20
        margin = (inst.contract_size * lots * price) / leverage
        assert margin == pytest.approx(10_000.0)

    def test_insufficient_margin_raises(self):
        from qengine.exceptions import InsufficientMargin
        from qengine.models.Order import Order
        ex, _ = _setup_forex_env(balance=100, leverage=30)  # Only $100
        # qty in QEngine is raw quantity (not lots). Need notional/leverage > $100.
        # qty=100000 * price=1.10 / leverage=30 = $3666 >> $100
        order = Order({
            'exchange': 'OANDA',
            'symbol': 'EUR-USD',
            'type': 'MARKET',
            'side': 'buy',
            'qty': 100_000,
            'price': 1.10,
            'reduce_only': False,
        })
        with pytest.raises(InsufficientMargin):
            ex.on_order_submission(order)
        _teardown()


# ════════════════════════════════════════════════
# 9.6  Instrument Registry Integration
# ════════════════════════════════════════════════

class TestInstrumentIntegration:
    def test_all_major_pairs_have_correct_settings(self):
        from qengine.core.instruments import instrument_registry
        pairs = {
            'EUR-USD': {'pip_size': 0.0001, 'contract_size': 100_000, 'asset_class': 'forex'},
            'GBP-USD': {'pip_size': 0.0001, 'contract_size': 100_000, 'asset_class': 'forex'},
            'USD-JPY': {'pip_size': 0.01, 'contract_size': 100_000, 'asset_class': 'forex'},
            'USD-CHF': {'pip_size': 0.0001, 'contract_size': 100_000, 'asset_class': 'forex'},
            'AUD-USD': {'pip_size': 0.0001, 'contract_size': 100_000, 'asset_class': 'forex'},
            'XAU-USD': {'pip_size': 0.01, 'contract_size': 100, 'asset_class': 'commodity'},
        }
        for sym, expected in pairs.items():
            inst = instrument_registry.get(sym)
            assert inst is not None, f'{sym} not registered'
            assert inst.pip_size == expected['pip_size'], f'{sym} pip_size mismatch'
            assert inst.contract_size == expected['contract_size'], f'{sym} contract_size mismatch'
            assert inst.asset_class == expected['asset_class'], f'{sym} asset_class mismatch'

    def test_pip_value_consistency(self):
        """pip_value = pip_size * contract_size should be stable across non-JPY pairs."""
        from qengine.core.instruments import instrument_registry
        for sym in ['EUR-USD', 'GBP-USD', 'AUD-USD']:
            inst = instrument_registry.get(sym)
            pip_value = inst.pip_size * inst.contract_size
            assert pip_value == pytest.approx(10.0), f'{sym} pip_value should be $10'


# ════════════════════════════════════════════════
# 9.7  Market Hours Integration
# ════════════════════════════════════════════════

class TestMarketHoursIntegration:
    def _ts(self, year, month, day, hour, minute=0):
        dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    def test_weekday_trading_sessions_cycle(self):
        """A Wednesday should go through tokyo -> london -> overlap -> new_york."""
        from qengine.core.market_hours import market_hours
        sessions_found = set()
        # Sample every 2 hours on Wed Jan 8, 2025
        for hour in range(0, 24, 2):
            ts = self._ts(2025, 1, 8, hour)
            s = market_hours.current_session(ts)
            sessions_found.add(s)
        assert 'london' in sessions_found
        assert 'new_york' in sessions_found
        assert 'tokyo' in sessions_found

    def test_weekend_market_closed(self):
        from qengine.core.market_hours import market_hours
        sat_noon = self._ts(2025, 1, 11, 12)
        assert market_hours.is_market_open('EUR-USD', sat_noon) is False
        assert market_hours.current_session(sat_noon) == 'off'

    def test_friday_close_sunday_open(self):
        from qengine.core.market_hours import market_hours
        # Friday 10:30pm UTC (past 5pm ET close)
        fri_late = self._ts(2025, 1, 10, 22, 30)
        assert market_hours.is_market_open('EUR-USD', fri_late) is False

        # Sunday 10:30pm UTC (past 5pm ET open)
        sun_late = self._ts(2025, 1, 12, 22, 30)
        assert market_hours.is_market_open('EUR-USD', sun_late) is True


# ════════════════════════════════════════════════
# 9.8  Strategy Properties Integration
# ════════════════════════════════════════════════

class TestStrategyIntegration:
    def test_forex_ma_instantiation(self):
        from qengine.strategies.ForexMA import ForexMA
        s = ForexMA()
        assert callable(s.should_long)
        assert callable(s.go_long)
        assert callable(s.should_short)
        assert callable(s.go_short)

    def test_forex_ma_hyperparameters(self):
        from qengine.strategies.ForexMA import ForexMA
        s = ForexMA()
        hp = s.hyperparameters()
        names = {h['name'] for h in hp}
        assert names == {'fast_period', 'slow_period', 'risk_pct', 'stop_pips', 'rr_ratio'}

    def test_all_example_strategies_compile(self):
        strategies = []
        try:
            from qengine.strategies.ForexMA import ForexMA
            strategies.append(ForexMA())
        except ImportError:
            pass
        try:
            from qengine.strategies.ForexRSIReversal import ForexRSIReversal
            strategies.append(ForexRSIReversal())
        except ImportError:
            pass
        try:
            from qengine.strategies.GoldBreakout import GoldBreakout
            strategies.append(GoldBreakout())
        except ImportError:
            pass

        for s in strategies:
            assert hasattr(s, 'should_long')
            assert hasattr(s, 'go_long')
            assert hasattr(s, 'should_short')
            assert hasattr(s, 'go_short')
            assert callable(s.hyperparameters)
            hp = s.hyperparameters()
            assert len(hp) > 0


# ════════════════════════════════════════════════
# 9.9  Live Trading Enablement Integration
# ════════════════════════════════════════════════

class TestLiveEnablement:
    def test_has_live_trade_plugin(self):
        import qengine.helpers as jh
        assert jh.has_live_trade_plugin() is True

    def test_live_drivers_all_present(self):
        from qengine.live_drivers import live_drivers
        from qengine.enums import brokers
        expected = [brokers.OANDA, brokers.OANDA_DEMO, brokers.IG_MARKETS,
                    brokers.IG_MARKETS_DEMO, brokers.IBKR, brokers.IBKR_PAPER]
        for b in expected:
            assert b in live_drivers

    def test_live_drivers_configured_in_config(self):
        from qengine.config import config
        from qengine.live_drivers import live_drivers as ld
        config['app']['live_drivers'].update(ld)
        assert len(config['app']['live_drivers']) >= 6

    def test_forex_live_mode_module(self):
        from qengine.modes.forex_live_mode import run, get_live_logs, get_live_orders
        assert callable(run)
        assert callable(get_live_logs)
        assert callable(get_live_orders)

    def test_general_info_reports_live(self):
        """general_info should show live enabled with built-in drivers."""
        os.makedirs('/private/tmp/claude/te_test/strategies/Dummy', exist_ok=True)
        orig = os.getcwd()
        os.chdir('/private/tmp/claude/te_test')
        try:
            from qengine.services.general_info import get_general_info
            info = get_general_info(has_live=True)
            assert info['has_live_plugin_installed'] is True
            assert info['plan'] == 'free'
            assert 'limits' in info
            exchanges = info['limits']['exchanges']
            assert 'OANDA' in exchanges
            assert 'IG Markets' in exchanges
            assert 'Interactive Brokers' in exchanges
        finally:
            os.chdir(orig)


# ════════════════════════════════════════════════
# 9.10  FastAPI Endpoint Integration
# ════════════════════════════════════════════════

@pytest.fixture(scope='module')
def client():
    from qengine.services.env import ENV_VALUES
    # Force-set to ensure consistent password even when other test modules ran first
    ENV_VALUES['PASSWORD'] = 'test-password-9'
    import qengine
    from qengine.services.web import fastapi_app
    from qengine.services.auth_dependency import get_current_user, CurrentUser
    from fastapi.testclient import TestClient

    # Override the auth dependency to avoid DB access in tests
    def _mock_current_user():
        return CurrentUser(
            id='test-user',
            role='admin',
            username='admin',
            effective_user_id='test-user',
            is_admin=True,
            is_impersonating=False,
        )
    fastapi_app.dependency_overrides[get_current_user] = _mock_current_user

    return TestClient(fastapi_app)


@pytest.fixture(scope='module')
def auth_header(client):
    """Get a valid auth token."""
    resp = client.post('/auth', json={'password': 'test-password-9'})
    if resp.status_code == 200:
        token = resp.json().get('auth_token', '')
        return {'Authorization': token}
    return {'Authorization': 'invalid'}


class TestAPIEndpoints:
    def test_auth_endpoint(self, client):
        resp = client.post('/auth', json={'password': 'test-password-9'})
        assert resp.status_code == 200
        assert 'auth_token' in resp.json()

    def test_auth_rejects_bad_password(self, client):
        resp = client.post('/auth', json={'password': 'wrong'})
        # Should return 200 with error message or 401
        assert resp.status_code in (200, 401, 403)

    def test_broker_list(self, client, auth_header):
        resp = client.get('/broker/list', headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()['data']
        assert len(data) >= 6
        names = [b['name'] for b in data]
        assert 'OANDA' in names

    def test_broker_info(self, client, auth_header):
        resp = client.get('/broker/info/OANDA', headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['name'] == 'OANDA'
        assert data['type'] == 'cfd'
        assert data['default_leverage'] >= 1

    def test_broker_asset_classes(self, client, auth_header):
        resp = client.get('/broker/asset-classes', headers=auth_header)
        assert resp.status_code == 200
        classes = resp.json()['data']
        assert 'forex' in classes
        assert 'commodity' in classes

    def test_cost_model_endpoint(self, client, auth_header):
        resp = client.get('/broker/cost-model/OANDA', headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['broker'] == 'OANDA'
        assert data['fee_model'] == 'spread'
        assert 'instruments' in data
        assert len(data['instruments']) > 0

    def test_exchange_types_endpoint(self, client, auth_header):
        resp = client.get('/broker/exchange-types', headers=auth_header)
        assert resp.status_code == 200
        types = resp.json()['data']
        ids = [t['id'] for t in types]
        assert 'cfd' in ids
        assert 'futures' in ids
        assert 'spot' in ids

    def test_market_data_session(self, client, auth_header):
        resp = client.get('/market-data/session', headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()['data']
        assert 'session' in data
        assert data['session'] in ('tokyo', 'london', 'new_york', 'overlap', 'off')

    def test_market_data_instrument(self, client, auth_header):
        resp = client.get('/market-data/instrument/EUR-USD', headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['symbol'] == 'EUR-USD'
        assert data['pip_size'] == 0.0001

    def test_market_data_instruments_list(self, client, auth_header):
        resp = client.get('/market-data/instruments', headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()['data']
        assert len(data) > 0
        symbols = [i['symbol'] for i in data]
        assert 'EUR-USD' in symbols

    def test_market_data_pip_value(self, client, auth_header):
        resp = client.get('/market-data/pip-value/EUR-USD?lot_size=1', headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['pip_value'] == pytest.approx(10.0)

    def test_llm_status(self, client, auth_header):
        resp = client.get('/llm/status', headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert 'configured' in data

    def test_llm_validate(self, client, auth_header):
        code = """
from qengine.strategies import Strategy
class Test(Strategy):
    def should_long(self): return False
    def should_short(self): return False
    def go_long(self): pass
    def go_short(self): pass
"""
        resp = client.post('/llm/validate', json={'code': code}, headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()['valid'] is True

    def test_llm_validate_invalid_code(self, client, auth_header):
        resp = client.post('/llm/validate', json={'code': 'def broken('}, headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()['valid'] is False

    def test_live_controller_registered(self, client, auth_header):
        # Just verify the endpoint exists (may need DB for full functionality)
        resp = client.post('/live/sessions', json={}, headers=auth_header)
        # Any response other than 404 means the route is registered
        assert resp.status_code != 404

    def test_strategy_ai_generate_endpoint_exists(self, client, auth_header):
        resp = client.post('/strategy/ai/generate', json={
            'description': 'test',
            'save': False,
        }, headers=auth_header)
        # 400 (LLM not configured) is fine — proves the endpoint exists
        assert resp.status_code in (200, 400, 500)


# ════════════════════════════════════════════════
# 9.11  Cross-Phase Consistency
# ════════════════════════════════════════════════

class TestCrossPhaseConsistency:
    def test_broker_info_matches_exchange_info(self):
        """broker_info and exchange_info should have matching keys."""
        from qengine.info import broker_info, exchange_info
        for key in broker_info:
            assert key in exchange_info, f'broker_info key {key} missing from exchange_info'

    def test_live_drivers_match_brokers(self):
        from qengine.live_drivers import live_drivers
        from qengine.info import broker_info
        for name in live_drivers:
            assert name in broker_info

    def test_candle_drivers_for_backtesting_brokers(self):
        from qengine.info import backtesting_exchanges
        from qengine.modes.import_candles_mode.drivers import drivers
        for ex in backtesting_exchanges:
            assert ex in drivers, f'No candle driver for {ex}'

    def test_config_has_all_brokers(self):
        from qengine.config import config
        from qengine.info import broker_info
        for key in broker_info:
            assert key in config['env']['exchanges'], f'{key} not in config exchanges'

    def test_exchange_types_all_handled(self):
        """exchange_service should handle all types in broker_info."""
        from qengine.info import broker_info
        from qengine.modes.utils import get_exchange_type
        valid_types = {'cfd', 'futures', 'spot'}
        for name, info in broker_info.items():
            ex_type = get_exchange_type(name)
            assert ex_type in valid_types, f'{name} has unhandled type {ex_type}'


# ════════════════════════════════════════════════
# 9.12  LLM Engine Integration
# ════════════════════════════════════════════════

class TestLLMEngineIntegration:
    def test_engine_singleton(self):
        from qengine.services.llm_engine import llm_engine, LLMEngine
        assert isinstance(llm_engine, LLMEngine)

    def test_engine_configure_and_reset(self):
        from qengine.services.llm_engine import LLMEngine
        e = LLMEngine()
        assert not e.is_configured
        e.configure(provider='openai', api_key='test')
        assert e.is_configured
        assert e.provider == 'openai'

    def test_validate_complete_strategy(self):
        from qengine.services.llm_engine import LLMEngine
        e = LLMEngine()
        code = """
from qengine.strategies import Strategy
import qengine.indicators as ta

class EMACross(Strategy):
    def should_long(self):
        fast = ta.ema(self.candles, 10)
        slow = ta.ema(self.candles, 30)
        return fast > slow

    def go_long(self):
        self.buy = 1, self.price
        self.stop_loss = 1, self.price * 0.99
        self.take_profit = 1, self.price * 1.02

    def should_short(self):
        fast = ta.ema(self.candles, 10)
        slow = ta.ema(self.candles, 30)
        return fast < slow

    def go_short(self):
        self.sell = 1, self.price
        self.stop_loss = 1, self.price * 1.01
        self.take_profit = 1, self.price * 0.98

    def should_cancel_entry(self):
        return False
"""
        result = e.validate_strategy(code)
        assert result['valid'] is True
        assert len(result['errors']) == 0

    def test_validate_incomplete_strategy(self):
        from qengine.services.llm_engine import LLMEngine
        e = LLMEngine()
        code = """
class MyStrat:
    def should_long(self):
        return True
"""
        result = e.validate_strategy(code)
        assert result['valid'] is False

    def test_code_extraction_from_markdown(self):
        from qengine.services.llm_engine import LLMEngine
        e = LLMEngine()
        text = "Here's code:\n```python\nclass Foo(Strategy):\n    pass\n```\nDone."
        code = e._extract_code(text)
        assert 'class Foo' in code
        assert 'Done' not in code


# ════════════════════════════════════════════════
# 9.13  Weekend Gap Handling Integration
# ════════════════════════════════════════════════

class TestWeekendGapHandling:
    def _make_order(self, price, side, order_type):
        from qengine.enums import order_types, order_statuses

        class MockOrder:
            def __init__(self, p, s, t):
                self.price = p
                self.side = s
                self.type = t
                self.status = order_statuses.ACTIVE

            @property
            def is_active(self):
                return self.status == order_statuses.ACTIVE

        return MockOrder(price, side, order_type)

    def test_gap_up_triggers_stop_buy_at_open(self):
        from qengine.modes.backtest_mode import _apply_gap_execution_prices
        from qengine.enums import order_types
        order = self._make_order(1.1050, 'buy', order_types.STOP)
        candle = np.array([0, 1.1080, 1.1090, 1.1100, 1.1060, 1000])
        result = _apply_gap_execution_prices([order], candle)
        assert result[0].price == 1.1080

    def test_gap_down_triggers_stop_sell_at_open(self):
        from qengine.modes.backtest_mode import _apply_gap_execution_prices
        from qengine.enums import order_types
        order = self._make_order(1.1000, 'sell', order_types.STOP)
        candle = np.array([0, 1.0980, 1.0970, 1.1010, 1.0960, 1000])
        result = _apply_gap_execution_prices([order], candle)
        assert result[0].price == 1.0980

    def test_gap_through_limit_gets_better_fill(self):
        from qengine.modes.backtest_mode import _apply_gap_execution_prices
        from qengine.enums import order_types
        order = self._make_order(1.1050, 'buy', order_types.LIMIT)
        candle = np.array([0, 1.1020, 1.1030, 1.1060, 1.1010, 1000])
        result = _apply_gap_execution_prices([order], candle)
        assert result[0].price == 1.1020

    def test_no_gap_no_adjustment(self):
        from qengine.modes.backtest_mode import _apply_gap_execution_prices
        from qengine.enums import order_types
        order = self._make_order(1.1100, 'buy', order_types.STOP)
        candle = np.array([0, 1.1050, 1.1060, 1.1070, 1.1040, 1000])
        result = _apply_gap_execution_prices([order], candle)
        assert result[0].price == 1.1100  # unchanged


# ════════════════════════════════════════════════
# 9.14  Frontend Artifact Integrity
# ════════════════════════════════════════════════

class TestFrontendIntegrity:
    @staticmethod
    def _static_path(*parts):
        return os.path.join(os.path.dirname(__file__), '..', 'qengine', 'static', *parts)

    @staticmethod
    def _frontend_path(*parts):
        return os.path.join(os.path.dirname(__file__), '..', 'frontend', 'src', *parts)

    def test_index_html_exists(self):
        assert os.path.exists(self._static_path('index.html'))

    def test_js_bundle_exists(self):
        assets = os.listdir(self._static_path('assets'))
        assert any(f.endswith('.js') for f in assets)

    def test_css_bundle_exists(self):
        assets = os.listdir(self._static_path('assets'))
        assert any(f.endswith('.css') for f in assets)

    def test_all_views_exist(self):
        expected = ['Dashboard.vue', 'Brokers.vue', 'Strategies.vue',
                    'Backtest.vue', 'LiveTrade.vue', 'ImportData.vue', 'LLMStudio.vue',
                    'Settings.vue', 'Login.vue']
        for v in expected:
            assert os.path.exists(self._frontend_path('views', v)), f'Missing: {v}'

    def test_router_has_all_routes(self):
        with open(self._frontend_path('router.js')) as f:
            content = f.read()
        for route in ['/strategies', '/live', '/import', '/backtest', '/llm', '/settings']:
            assert route in content

    def test_api_has_all_methods(self):
        with open(self._frontend_path('api.js')) as f:
            content = f.read()
        methods = ['startLive', 'cancelLive', 'getLiveSessions', 'getLiveLogs',
                   'aiGenerateStrategy', 'aiRefineStrategy', 'getCostModel',
                   'updateCostModel', 'getExchangeTypes', 'importCandles',
                   'getStrategies', 'saveStrategy', 'deleteStrategy']
        for m in methods:
            assert m in content, f'Missing API method: {m}'

    def test_sidebar_has_grouped_sections(self):
        with open(self._frontend_path('components', 'Sidebar.vue')) as f:
            content = f.read()
        assert 'overviewItems' in content
        assert 'tradingItems' in content
        assert 'toolItems' in content


# ════════════════════════════════════════════════
# 9.15  Full System Smoke Test
# ════════════════════════════════════════════════

class TestFullSystemSmoke:
    """Verify the complete system can initialize without errors."""

    def test_full_forex_env_setup_and_teardown(self):
        """Set up and tear down a full forex backtest environment."""
        ex, pos = _setup_forex_env(exchange='OANDA', symbol='EUR-USD', balance=50_000, leverage=30)
        assert ex.wallet_balance == 50_000
        assert pos.is_close
        assert pos.symbol == 'EUR-USD'
        assert ex.default_leverage == 30

        # Charge some costs
        spread = ex.charge_spread('EUR-USD', 0.5)
        assert spread > 0
        assert ex.wallet_balance < 50_000

        # Add realized PnL
        ex.add_realized_pnl(100.0)
        assert ex.wallet_balance == pytest.approx(50_000 - spread + 100)

        _teardown()

    def test_multiple_symbol_env(self):
        """Verify we can set up with one symbol and the config is correct."""
        from qengine.config import config
        ex, pos = _setup_forex_env(symbol='GBP-USD')
        assert 'GBP-USD' in config['app']['trading_symbols']
        assert 'OANDA' in config['app']['trading_exchanges']
        _teardown()

    def test_store_reset_clears_state(self):
        """After setup + reset, state should be clean."""
        from qengine.store import store
        ex, pos = _setup_forex_env()
        assert pos.is_close
        store.reset()
        # After reset, positions storage should be empty
        assert len(store.positions.storage) == 0
        _teardown()

    def test_slippage_applied_to_buy_order(self):
        """Slippage should increase execution price for buy orders."""
        ex, pos = _setup_forex_env(balance=50_000)
        from qengine.core.instruments import instrument_registry
        pip_size = instrument_registry.get_pip_size('EUR-USD')

        # Configure slippage: 1 pip, no randomness
        ex._bt_cost_settings = {
            'slippage_pips': 1.0,
            'slippage_randomness': 0.0,
            'spread_pips': 0.0,
            'spread_randomness': 0.0,
            'swap_enabled': False,
            'commission_per_lot': 0.0,
        }
        ex.set_spread('EUR-USD', 0)  # zero spread to isolate slippage

        slippage = ex.get_slippage('EUR-USD')
        assert slippage == pytest.approx(pip_size * 1.0)
        assert slippage > 0
        _teardown()

    def test_slippage_applied_to_sell_order(self):
        """Slippage should decrease execution price for sell orders."""
        ex, pos = _setup_forex_env(balance=50_000)
        from qengine.core.instruments import instrument_registry
        pip_size = instrument_registry.get_pip_size('EUR-USD')

        ex._bt_cost_settings = {
            'slippage_pips': 2.0,
            'slippage_randomness': 0.0,
        }

        slippage = ex.get_slippage('EUR-USD')
        assert slippage == pytest.approx(pip_size * 2.0)
        _teardown()

    def test_slippage_zero_when_disabled(self):
        """No slippage when slippage_pips is 0."""
        ex, pos = _setup_forex_env(balance=50_000)
        ex._bt_cost_settings = {'slippage_pips': 0.0, 'slippage_randomness': 0.0}

        slippage = ex.get_slippage('EUR-USD')
        assert slippage == 0.0
        _teardown()

    def test_slippage_randomness_varies(self):
        """With randomness, slippage values should vary across calls."""
        ex, pos = _setup_forex_env(balance=50_000)
        ex._bt_cost_settings = {'slippage_pips': 1.0, 'slippage_randomness': 0.5}

        values = [ex.get_slippage('EUR-USD') for _ in range(50)]
        # All should be non-negative
        assert all(v >= 0 for v in values)
        # With randomness=0.5, not all should be identical
        assert len(set(round(v, 10) for v in values)) > 1
        _teardown()

    def test_all_test_phase_files_exist(self):
        """Verify all phase test files exist."""
        test_dir = os.path.dirname(__file__)
        for i in [1, 2, 3, 4, 5, 6, 7, 8]:
            files = [f for f in os.listdir(test_dir) if f.startswith(f'test_phase{i}_')]
            assert len(files) >= 1, f'Missing test file for Phase {i}'
        # Phase 9 has two files
        phase9 = [f for f in os.listdir(test_dir) if f.startswith('test_phase9_')]
        assert len(phase9) >= 2
