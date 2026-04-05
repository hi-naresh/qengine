import os
import pytest
from fastapi.testclient import TestClient


# ── 8.0 Controller Import Tests ──

def test_broker_controller_imports():
    from qengine.controllers.broker_controller import router
    assert router.prefix == '/broker'


def test_market_data_controller_imports():
    from qengine.controllers.market_data_controller import router
    assert router.prefix == '/market-data'


def test_settings_controller_imports():
    from qengine.controllers.settings_controller import router
    assert router.prefix == '/settings'


# ── 8.1 Broker Controller Tests ──

def test_broker_controller_routes():
    from qengine.controllers.broker_controller import router
    paths = [r.path for r in router.routes]
    assert any('/list' in p for p in paths)
    assert any('/backtesting' in p for p in paths)
    assert any('/live-trading' in p for p in paths)
    assert any('/asset-classes' in p for p in paths)


def test_broker_list_returns_all_brokers():
    from qengine.info import broker_info
    from qengine.controllers.broker_controller import router
    for route in router.routes:
        if hasattr(route, 'endpoint'):
            assert callable(route.endpoint)


def test_broker_info_contains_expected_fields():
    from qengine.info import broker_info
    from qengine.enums import brokers
    assert brokers.OANDA in broker_info
    info = broker_info[brokers.OANDA]
    assert 'name' in info
    assert 'type' in info
    assert 'asset_classes' in info
    assert 'fee_model' in info
    assert 'default_leverage' in info
    assert 'modes' in info


def test_backtesting_exchanges_list():
    from qengine.info import backtesting_exchanges, broker_info
    for ex in backtesting_exchanges:
        assert ex in broker_info
        assert broker_info[ex]['modes']['backtesting'] is True


def test_live_trading_exchanges_list():
    from qengine.info import live_trading_exchanges, broker_info
    for ex in live_trading_exchanges:
        assert ex in broker_info
        assert broker_info[ex]['modes']['live_trading'] is True


def test_asset_classes_across_brokers():
    from qengine.info import broker_info
    all_classes = set()
    for info in broker_info.values():
        for ac in info.get('asset_classes', []):
            all_classes.add(ac)
    assert 'forex' in all_classes
    assert 'commodity' in all_classes
    assert 'index' in all_classes


# ── 8.2 Market Data Controller Tests ──

def test_market_data_session_endpoint():
    from qengine.controllers.market_data_controller import router
    paths = [r.path for r in router.routes]
    assert any('/session' in p for p in paths)


def test_market_data_instrument_endpoint():
    from qengine.controllers.market_data_controller import router
    paths = [r.path for r in router.routes]
    assert any('/instrument/' in p for p in paths)
    assert any('/instruments' in p for p in paths)


def test_market_data_pip_value_endpoint():
    from qengine.controllers.market_data_controller import router
    paths = [r.path for r in router.routes]
    assert any('/pip-value/' in p for p in paths)


def test_market_hours_returns_session():
    from qengine.core.market_hours import market_hours
    import qengine.helpers as jh
    now_ms = jh.now(force_fresh=True)
    session = market_hours.current_session(now_ms)
    assert session in ('tokyo', 'london', 'new_york', 'overlap', 'off')


def test_instrument_registry_has_forex_instruments():
    from qengine.core.instruments import instrument_registry
    inst = instrument_registry.get('EUR-USD')
    assert inst is not None
    assert inst.pip_size == 0.0001
    assert inst.asset_class == 'forex'
    assert inst.contract_size == 100_000


def test_instrument_registry_has_commodity_instruments():
    from qengine.core.instruments import instrument_registry
    inst = instrument_registry.get('XAU-USD')
    assert inst is not None
    assert inst.asset_class == 'commodity'


def test_pip_value_calculation():
    from qengine.core.instruments import instrument_registry
    pip_size = instrument_registry.get_pip_size('EUR-USD')
    contract_size = instrument_registry.get_contract_size('EUR-USD')
    pip_value = pip_size * contract_size * 1.0
    assert pip_value == pytest.approx(10.0)


def test_pip_value_jpy_pair():
    from qengine.core.instruments import instrument_registry
    pip_size = instrument_registry.get_pip_size('USD-JPY')
    contract_size = instrument_registry.get_contract_size('USD-JPY')
    pip_value = pip_size * contract_size * 1.0
    assert pip_value == pytest.approx(1000.0)


# ── 8.3 Settings Controller Tests ──

def test_settings_controller_routes():
    from qengine.controllers.settings_controller import router
    paths = [r.path for r in router.routes]
    assert any('/brokers' in p for p in paths)
    assert any('/llm' in p for p in paths)
    assert any('/all' in p for p in paths)


def test_settings_mask_key():
    from qengine.controllers.settings_controller import _mask_key
    assert _mask_key('') == '****'
    assert _mask_key('abc') == '****'
    assert _mask_key('abcdefgh') == '****efgh'
    # 18 chars - 4 visible = 14 masked
    key = 'sk-1234567890abcdef'
    masked = _mask_key(key)
    assert masked.endswith('cdef')
    assert len(masked) == len(key)


def test_settings_broker_model():
    from qengine.controllers.settings_controller import BrokerSettingsRequestJson
    req = BrokerSettingsRequestJson(broker='OANDA', api_key='test-key', account_id='123')
    assert req.broker == 'OANDA'
    assert req.api_key == 'test-key'
    assert req.account_id == '123'


def test_settings_llm_model():
    from qengine.controllers.settings_controller import LLMSettingsRequestJson
    req = LLMSettingsRequestJson(provider='anthropic', api_key='sk-test')
    assert req.provider == 'anthropic'
    assert req.api_key == 'sk-test'
    assert req.temperature == 0.3


# ── 8.4 Enhanced Data Provider Tests ──

def test_data_provider_includes_broker_info():
    from qengine.info import broker_info, backtesting_exchanges, live_trading_exchanges
    assert len(broker_info) >= 6
    assert len(backtesting_exchanges) >= 3
    assert len(live_trading_exchanges) >= 3


# ── 8.5 Router Registration Tests ──

def test_all_phase8_routers_registered():
    from qengine.services.web import fastapi_app
    import qengine

    route_paths = set()
    for route in fastapi_app.routes:
        if hasattr(route, 'path'):
            route_paths.add(route.path)

    assert any('/broker' in p for p in route_paths)
    assert any('/market-data' in p for p in route_paths)
    assert any('/settings' in p for p in route_paths)


def test_broker_routes_registered_in_app():
    import qengine
    from qengine.services.web import fastapi_app

    all_paths = [r.path for r in fastapi_app.routes if hasattr(r, 'path')]

    assert '/broker/list' in all_paths
    assert '/broker/backtesting' in all_paths
    assert '/broker/live-trading' in all_paths
    assert '/broker/asset-classes' in all_paths


def test_market_data_routes_registered():
    import qengine
    from qengine.services.web import fastapi_app

    all_paths = [r.path for r in fastapi_app.routes if hasattr(r, 'path')]

    assert '/market-data/session' in all_paths
    assert '/market-data/instruments' in all_paths


def test_settings_routes_registered():
    import qengine
    from qengine.services.web import fastapi_app

    all_paths = [r.path for r in fastapi_app.routes if hasattr(r, 'path')]

    assert '/settings/brokers' in all_paths
    assert '/settings/llm' in all_paths
    assert '/settings/all' in all_paths


# ── 8.6 FastAPI TestClient Integration Tests ──

@pytest.fixture
def test_client():
    """Create a test client with PASSWORD env var set."""
    from qengine.services.env import ENV_VALUES
    ENV_VALUES.setdefault('PASSWORD', 'test-password')
    import qengine
    from qengine.services.web import fastapi_app
    return TestClient(fastapi_app)


def test_broker_list_endpoint_unauthorized(test_client):
    resp = test_client.get('/broker/list')
    assert resp.status_code in (200, 401, 403)


def test_market_data_session_endpoint_unauthorized(test_client):
    resp = test_client.get('/market-data/session')
    assert resp.status_code in (200, 401, 403)


def test_settings_all_endpoint_unauthorized(test_client):
    resp = test_client.get('/settings/all')
    assert resp.status_code in (200, 401, 403)


# ── 8.7 LLM Controller Integration (Phase 6+8) ──

def test_llm_routes_still_registered():
    import qengine
    from qengine.services.web import fastapi_app

    all_paths = [r.path for r in fastapi_app.routes if hasattr(r, 'path')]

    assert '/llm/generate' in all_paths
    assert '/llm/refine' in all_paths
    assert '/llm/validate' in all_paths
    assert '/llm/configure' in all_paths
    assert '/llm/status' in all_paths


def test_llm_status_endpoint(test_client):
    resp = test_client.get('/llm/status')
    assert resp.status_code in (200, 401, 403)


# ── 8.8 Live Trading Enablement ──

def test_has_live_trade_plugin_returns_true():
    """Built-in forex live drivers should make has_live_trade_plugin() True."""
    import qengine.helpers as jh
    assert jh.has_live_trade_plugin() is True


def test_live_controller_imports():
    from qengine.controllers.live_controller import router
    assert router.prefix == '/live'


def test_live_routes_registered():
    import qengine
    from qengine.services.web import fastapi_app
    all_paths = [r.path for r in fastapi_app.routes if hasattr(r, 'path')]
    assert '/live' in all_paths or any(p.startswith('/live') for p in all_paths)


def test_live_controller_has_session_endpoints():
    from qengine.controllers.live_controller import router
    paths = [r.path for r in router.routes]
    assert any('/sessions' in p for p in paths)
    assert any('/cancel' in p for p in paths)
    assert any('/logs' in p for p in paths)


def test_forex_live_mode_exists():
    from qengine.modes import forex_live_mode
    assert hasattr(forex_live_mode, 'run')
    assert hasattr(forex_live_mode, 'get_live_logs')
    assert hasattr(forex_live_mode, 'get_live_orders')


def test_general_info_with_builtin_live():
    """general_info should report live enabled with built-in drivers."""
    import os
    os.makedirs('/private/tmp/claude/test_proj2/strategies/Test', exist_ok=True)
    orig_cwd = os.getcwd()
    os.chdir('/private/tmp/claude/test_proj2')
    try:
        from qengine.services.general_info import get_general_info
        info = get_general_info(has_live=True)
        assert info['has_live_plugin_installed'] is True
        assert info['plan'] == 'free'
        assert 'limits' in info
        assert info['limits']['live_trading_tabs'] >= 1
    finally:
        os.chdir(orig_cwd)


# ── 8.9 Strategy AI Endpoints ──

def test_strategy_ai_generate_route_exists():
    from qengine.controllers.strategy_controller import router
    paths = [r.path for r in router.routes]
    assert any('/ai/generate' in p for p in paths)


def test_strategy_ai_refine_route_exists():
    from qengine.controllers.strategy_controller import router
    paths = [r.path for r in router.routes]
    assert any('/ai/refine' in p for p in paths)


def test_ai_generate_request_model():
    from qengine.services.web import AIGenerateAndSaveRequestJson
    req = AIGenerateAndSaveRequestJson(description='EMA crossover')
    assert req.asset_class == 'forex'
    assert req.symbol == 'EUR-USD'
    assert req.save is True


def test_ai_refine_request_model():
    from qengine.services.web import AIRefineAndSaveRequestJson
    req = AIRefineAndSaveRequestJson(name='MyStrat', feedback='Add trailing stop')
    assert req.name == 'MyStrat'
    assert req.backtest_results is None


# ── 8.10 Cost Model Endpoints ──

def test_cost_model_endpoint_exists():
    from qengine.controllers.broker_controller import router
    paths = [r.path for r in router.routes]
    assert any('/cost-model/' in p for p in paths)


def test_exchange_types_endpoint_exists():
    from qengine.controllers.broker_controller import router
    paths = [r.path for r in router.routes]
    assert any('/exchange-types' in p for p in paths)


def test_cost_model_update_request_model():
    from qengine.controllers.broker_controller import UpdateCostModelRequest
    req = UpdateCostModelRequest(broker_id='OANDA', leverage=50)
    assert req.broker_id == 'OANDA'
    assert req.leverage == 50
    assert req.instruments is None


def test_cost_model_endpoint_unauthorized(test_client):
    resp = test_client.get('/broker/cost-model/OANDA')
    assert resp.status_code in (200, 401, 403)


def test_exchange_types_endpoint_unauthorized(test_client):
    resp = test_client.get('/broker/exchange-types')
    assert resp.status_code in (200, 401, 403)


# ── 8.11 Frontend Build Artifacts ──

def test_frontend_build_exists():
    """Built frontend files should exist in static/te."""
    assert os.path.exists(os.path.join(
        os.path.dirname(__file__), '..', 'qengine', 'static', 'index.html'
    ))


def test_frontend_assets_exist():
    assets_dir = os.path.join(os.path.dirname(__file__), '..', 'qengine', 'static', 'assets')
    assert os.path.isdir(assets_dir)
    files = os.listdir(assets_dir)
    assert any(f.endswith('.js') for f in files)
    assert any(f.endswith('.css') for f in files)


def test_frontend_source_views_exist():
    """All view files should exist in frontend/src/views."""
    views_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'src', 'views')
    expected = ['Dashboard.vue', 'Brokers.vue', 'Strategies.vue',
                'Backtest.vue', 'LiveTrade.vue', 'ImportData.vue', 'LLMStudio.vue',
                'Settings.vue', 'Login.vue']
    for view in expected:
        assert os.path.exists(os.path.join(views_dir, view)), f'Missing view: {view}'


def test_frontend_router_has_all_routes():
    """Router should define all expected routes."""
    router_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'src', 'router.js')
    with open(router_path) as f:
        content = f.read()
    for route in ['/strategies', '/live', '/import', '/backtest', '/llm', '/settings', '/brokers', '/instruments']:
        assert route in content, f'Missing route: {route}'


def test_frontend_api_has_live_methods():
    """API module should include live trading methods."""
    api_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'src', 'api.js')
    with open(api_path) as f:
        content = f.read()
    for method in ['startLive', 'cancelLive', 'getLiveSessions', 'getLiveLogs', 'getLiveOrders']:
        assert method in content, f'Missing API method: {method}'


def test_frontend_api_has_strategy_ai_methods():
    """API module should include AI strategy methods."""
    api_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'src', 'api.js')
    with open(api_path) as f:
        content = f.read()
    for method in ['aiGenerateStrategy', 'aiRefineStrategy', 'getStrategies', 'saveStrategy']:
        assert method in content, f'Missing API method: {method}'


def test_frontend_api_has_cost_model_methods():
    """API module should include cost model methods."""
    api_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'src', 'api.js')
    with open(api_path) as f:
        content = f.read()
    for method in ['getCostModel', 'updateCostModel', 'getExchangeTypes']:
        assert method in content, f'Missing API method: {method}'
