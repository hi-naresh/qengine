import json
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from qengine.services import auth as authenticator
from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser
import qengine.helpers as jh

router = APIRouter(prefix="/settings", tags=["Settings"])

# Shared settings ID for all admin users — admin configs are global, not per-admin
ADMIN_SETTINGS_ID = '00000000-0000-0000-0000-000000000000'


def _settings_uid(current_user) -> str:
    """Return the settings user_id: shared admin ID for admins, personal ID for regular users."""
    if current_user.is_admin:
        return ADMIN_SETTINGS_ID
    return current_user.effective_user_id


def _get_env_settings() -> dict:
    """Build settings dict from .env file as fallback when DB has no stored settings."""
    import os
    from qengine.services.env import ENV_VALUES

    def _env(key):
        return os.environ.get(key, '') or ENV_VALUES.get(key, '')

    settings = {}

    # LLM: check for API keys in .env
    gemini_key = _env('GEMINI_API_KEY')
    anthropic_key = _env('ANTHROPIC_API_KEY')
    openai_key = _env('OPENAI_API_KEY')
    if gemini_key:
        settings['llm'] = {'provider': 'gemini', 'api_key': gemini_key, 'model': _env('LLM_MODEL') or 'gemini-2.5-flash', 'temperature': 0.3}
    elif anthropic_key:
        settings['llm'] = {'provider': 'anthropic', 'api_key': anthropic_key, 'model': _env('LLM_MODEL') or 'claude-sonnet-4-6', 'temperature': 0.3}
    elif openai_key:
        settings['llm'] = {'provider': 'openai', 'api_key': openai_key, 'model': _env('LLM_MODEL') or 'gpt-4o', 'temperature': 0.3}

    # Brokers: check for API keys in .env
    brokers = {}
    oanda_key = _env('OANDA_API_KEY')
    if oanda_key:
        is_demo = 'fxpractice' in _env('OANDA_API_URL').lower() or not _env('OANDA_API_URL')
        broker_id = 'OANDA Demo' if is_demo else 'OANDA'
        brokers[broker_id] = {'api_key': oanda_key, 'account_id': _env('OANDA_ACCOUNT_ID'), 'api_secret': ''}

    ig_key = _env('IG_API_KEY')
    if ig_key:
        is_demo = _env('IG_DEMO') != 'false'  # default to demo
        broker_id = 'IG Markets Demo' if is_demo else 'IG Markets'
        brokers[broker_id] = {
            'api_key': ig_key,
            'api_secret': _env('IG_PASSWORD'),
            'account_id': _env('IG_USERNAME'),
            'additional_fields': {'ig_account_id': _env('IG_ACCOUNT_ID')},
        }

    if brokers:
        settings['brokers'] = brokers

    return settings


def _get_settings_with_fallback(current_user, section: str = None) -> dict:
    """Load settings for the user.

    Admins: shared DB (ADMIN_SETTINGS_ID) → .env fallback.
    Regular users: their own DB only (no admin/env fallback — they configure their own).
    """
    uid = _settings_uid(current_user)
    settings = _get_settings_from_db(uid)

    # Only admins get .env fallback (regular users must configure their own)
    if current_user.is_admin:
        env_settings = _get_env_settings()
        if section:
            if not settings.get(section) and env_settings.get(section):
                settings[section] = env_settings[section]
        else:
            for key in ('brokers', 'llm'):
                if not settings.get(key) and env_settings.get(key):
                    settings[key] = env_settings[key]

    return settings


class BrokerSettingsRequestJson(BaseModel):
    broker: str
    api_key: str = ''
    api_secret: str = ''
    account_id: str = ''
    additional_fields: Optional[dict] = None


class LLMSettingsRequestJson(BaseModel):
    provider: str
    api_key: str
    model: Optional[str] = None
    temperature: float = 0.3


def _get_settings_from_db(user_id: str) -> dict:
    """Load settings from the Option table for a specific user."""
    from qengine.services.db import database
    from qengine.models.Option import Option
    import peewee

    database.open_connection()
    try:
        o = Option.get((Option.type == 'app_settings') & (Option.user_id == user_id))
        data = json.loads(o.json)
    except peewee.DoesNotExist:
        data = {}
    finally:
        database.close_connection()
    return data


def _save_settings_to_db(data: dict, user_id: str) -> None:
    """Persist settings to the Option table for a specific user."""
    from qengine.services.db import database
    from qengine.models.Option import Option
    import peewee

    database.open_connection()
    try:
        o = Option.get((Option.type == 'app_settings') & (Option.user_id == user_id))
        o.json = json.dumps(data)
        o.updated_at = jh.now(True)
        o.save()
    except peewee.DoesNotExist:
        o = Option({
            'id': jh.generate_unique_id(),
            'updated_at': jh.now(True),
            'type': 'app_settings',
            'json': json.dumps(data),
            'user_id': user_id
        })
        o.save(force_insert=True)
    finally:
        database.close_connection()


# ── Broker Settings ──

@router.get("/brokers")
def get_broker_settings(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Get all saved broker configurations (keys are masked)."""
    settings = _get_settings_with_fallback(current_user, section='brokers')
    broker_settings = settings.get('brokers', {})

    # Mask sensitive fields
    masked = {}
    for broker_id, conf in broker_settings.items():
        masked[broker_id] = {
            'broker': broker_id,
            'configured': bool(conf.get('api_key')),
            'account_id': conf.get('account_id', ''),
            'api_key_masked': _mask_key(conf.get('api_key', '')),
        }
        if conf.get('additional_fields'):
            masked[broker_id]['has_additional_fields'] = True

    return JSONResponse({'data': masked}, status_code=200)


@router.post("/brokers")
def save_broker_settings(
    request_json: BrokerSettingsRequestJson,
    current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """Save broker API credentials."""
    uid = _settings_uid(current_user)
    settings = _get_settings_from_db(uid)
    if 'brokers' not in settings:
        settings['brokers'] = {}

    settings['brokers'][request_json.broker] = {
        'api_key': request_json.api_key,
        'api_secret': request_json.api_secret,
        'account_id': request_json.account_id,
        'additional_fields': request_json.additional_fields or {},
    }

    _save_settings_to_db(settings, uid)

    return JSONResponse({'message': f'Broker {request_json.broker} settings saved'}, status_code=200)


@router.delete("/brokers/{broker_id}")
def delete_broker_settings(broker_id: str, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Remove broker settings."""
    uid = _settings_uid(current_user)
    settings = _get_settings_from_db(uid)
    brokers = settings.get('brokers', {})

    if broker_id not in brokers:
        return JSONResponse({'error': f'No settings for broker {broker_id}'}, status_code=404)

    del brokers[broker_id]
    settings['brokers'] = brokers
    _save_settings_to_db(settings, uid)

    return JSONResponse({'message': f'Broker {broker_id} settings removed'}, status_code=200)


# ── LLM Settings ──

@router.get("/llm")
def get_llm_settings(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Get LLM configuration (key masked)."""
    settings = _get_settings_with_fallback(current_user, section='llm')
    llm_conf = settings.get('llm', {})

    return JSONResponse({
        'data': {
            'configured': bool(llm_conf.get('api_key')),
            'provider': llm_conf.get('provider', ''),
            'model': llm_conf.get('model', ''),
            'temperature': llm_conf.get('temperature', 0.3),
            'api_key_masked': _mask_key(llm_conf.get('api_key', '')),
        }
    }, status_code=200)


@router.post("/llm")
def save_llm_settings(
    request_json: LLMSettingsRequestJson,
    current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """Save LLM configuration and apply it to the engine."""
    uid = _settings_uid(current_user)
    settings = _get_settings_from_db(uid)
    settings['llm'] = {
        'provider': request_json.provider,
        'api_key': request_json.api_key,
        'model': request_json.model or '',
        'temperature': request_json.temperature,
    }
    _save_settings_to_db(settings, uid)

    # Apply to running LLM engine
    from qengine.services.llm_engine import llm_engine
    llm_engine.configure(
        provider=request_json.provider,
        api_key=request_json.api_key,
        model=request_json.model,
        temperature=request_json.temperature,
    )

    return JSONResponse({'message': 'LLM settings saved and applied'}, status_code=200)


@router.delete("/llm")
def delete_llm_settings(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Remove LLM configuration."""
    uid = _settings_uid(current_user)
    settings = _get_settings_from_db(uid)
    settings['llm'] = {}
    _save_settings_to_db(settings, uid)

    return JSONResponse({'message': 'LLM settings removed'}, status_code=200)


# ── General Settings ──

@router.get("/all")
def get_all_settings(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Get all application settings."""
    settings = _get_settings_with_fallback(current_user)

    # Mask sensitive data
    result = {
        'brokers': {},
        'llm': {
            'configured': bool(settings.get('llm', {}).get('api_key')),
            'provider': settings.get('llm', {}).get('provider', ''),
            'model': settings.get('llm', {}).get('model', ''),
            'temperature': settings.get('llm', {}).get('temperature', 0.3),
        },
    }

    for broker_id, conf in settings.get('brokers', {}).items():
        result['brokers'][broker_id] = {
            'configured': bool(conf.get('api_key')),
            'account_id': conf.get('account_id', ''),
        }

    return JSONResponse({'data': result}, status_code=200)


# ── Backtest Settings ──

class BacktestSettingsRequestJson(BaseModel):
    broker_id: str
    spread_pips: float = 2.0
    spread_randomness: float = 0.0   # 0.0 = fixed spread, 0.5 = +/-50% variation
    slippage_pips: float = 0.0
    slippage_randomness: float = 0.0  # 0.0 = fixed slippage, 1.0 = 0 to 2x
    swap_enabled: bool = True
    commission_per_lot: float = 0.0
    min_order_qty: float = 0         # 0 = use broker default; otherwise broker units (e.g. 1 for OANDA, 10000 for IG)
    stop_out_level: float = 50.0     # margin level % at which broker force-closes positions (OANDA=50, IG=50)
    stop_out_order: str = 'largest_margin'  # fifo, lifo, winner_first, loser_first, largest_margin
    swap_long: float = -10.0         # overnight swap for long positions ($/lot/night). Negative = charge.
    swap_short: float = -0.9         # overnight swap for short positions ($/lot/night). Negative = charge.


@router.get("/backtest/{broker_id}")
def get_backtest_settings(broker_id: str, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Get backtest cost/randomness settings for a specific broker."""
    settings = _get_settings_with_fallback(current_user, section='backtest_brokers')
    bt_all = settings.get('backtest_brokers', {})
    bt = bt_all.get(broker_id, settings.get('backtest', _default_backtest_settings()))

    # Check if real spread data exists in imported candles for this broker
    spread_available = False
    spread_candle_count = 0
    try:
        from qengine.models.Candle import Candle
        count = Candle.select().where(
            Candle.exchange == broker_id,
            Candle.spread.is_null(False),
        ).limit(1).count()
        if count > 0:
            spread_available = True
            spread_candle_count = Candle.select().where(
                Candle.exchange == broker_id,
                Candle.spread.is_null(False),
            ).count()
    except Exception:
        pass

    bt['_spread_in_data'] = spread_available
    bt['_spread_candle_count'] = spread_candle_count
    return JSONResponse({'data': bt}, status_code=200)


@router.post("/backtest")
def save_backtest_settings(
    request_json: BacktestSettingsRequestJson,
    current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """Save backtest cost/randomness settings for a specific broker."""
    uid = _settings_uid(current_user)
    settings = _get_settings_from_db(uid)
    if 'backtest_brokers' not in settings:
        settings['backtest_brokers'] = {}

    settings['backtest_brokers'][request_json.broker_id] = {
        'spread_pips': request_json.spread_pips,
        'spread_randomness': max(0.0, min(1.0, request_json.spread_randomness)),
        'slippage_pips': request_json.slippage_pips,
        'slippage_randomness': max(0.0, min(1.0, request_json.slippage_randomness)),
        'swap_enabled': request_json.swap_enabled,
        'commission_per_lot': request_json.commission_per_lot,
        'min_order_qty': max(0, request_json.min_order_qty),
        'stop_out_level': max(0.0, min(100.0, request_json.stop_out_level)),
        'stop_out_order': request_json.stop_out_order if request_json.stop_out_order in (
            'fifo', 'lifo', 'winner_first', 'loser_first', 'largest_margin'
        ) else 'largest_margin',
        'swap_long': request_json.swap_long,
        'swap_short': request_json.swap_short,
    }
    _save_settings_to_db(settings, uid)

    return JSONResponse({'message': f'Backtest settings saved for {request_json.broker_id}'}, status_code=200)


def _default_backtest_settings() -> dict:
    return {
        'spread_pips': 2.0,
        'spread_randomness': 0.0,
        'slippage_pips': 0.0,
        'slippage_randomness': 0.0,
        'swap_enabled': True,
        'swap_long': -10.0,
        'swap_short': -0.9,
        'commission_per_lot': 0.0,
        'min_order_qty': 0,
        'stop_out_level': 50.0,
        'stop_out_order': 'largest_margin',
    }


# Broker-specific defaults for CFD execution parameters.
# Applied when the DB doesn't have a value for the broker.
# These represent real broker specs and are used even when cost_model=False
# for structural correctness (min order size, margin rules).
_BROKER_DEFAULTS = {
    'OANDA': {
        'min_order_qty': 1,              # OANDA minimum is 1 unit
        'stop_out_level': 50.0,          # OANDA stop-out at 50% margin level
        'stop_out_order': 'largest_margin',  # OANDA closes largest exposure first
        'spread_pips': 2.0,              # typical EUR-USD spread
    },
    'IG': {
        'min_order_qty': 10_000,         # IG CFD minimum is 0.1 lots = 10,000 units for major FX
        'stop_out_level': 50.0,          # IG stop-out at 50%
        'stop_out_order': 'loser_first', # IG closes most-losing position first
        'spread_pips': 0.6,              # IG EUR-USD typical
    },
    'IBKR': {
        'min_order_qty': 1,              # IBKR minimum is 1 unit for forex
        'stop_out_level': 25.0,          # IBKR maintenance margin ~25%
        'stop_out_order': 'largest_margin',  # IBKR closes largest margin position
        'spread_pips': 0.3,              # IBKR ECN-style
    },
}

# Legacy compat
_BROKER_MIN_ORDER_QTY = {k: v['min_order_qty'] for k, v in _BROKER_DEFAULTS.items()}


def get_backtest_cost_settings(broker_id: str = None, user_id: str = None) -> dict:
    """Public helper: load backtest cost settings from DB for a specific broker and user."""
    try:
        settings = _get_settings_from_db(user_id or ADMIN_SETTINGS_ID)
        if broker_id:
            bt_all = settings.get('backtest_brokers', {})
            if broker_id in bt_all:
                result = bt_all[broker_id]
                # Inject broker-specific min_order_qty if not set by user
                if not result.get('min_order_qty') and broker_id in _BROKER_MIN_ORDER_QTY:
                    result['min_order_qty'] = _BROKER_MIN_ORDER_QTY[broker_id]
                return result
        # Fallback to legacy global settings, then defaults
        result = settings.get('backtest', _default_backtest_settings())
        if broker_id and broker_id in _BROKER_MIN_ORDER_QTY and not result.get('min_order_qty'):
            result['min_order_qty'] = _BROKER_MIN_ORDER_QTY[broker_id]
        return result
    except Exception:
        result = _default_backtest_settings()
        if broker_id and broker_id in _BROKER_MIN_ORDER_QTY:
            result['min_order_qty'] = _BROKER_MIN_ORDER_QTY[broker_id]
        return result


def _mask_key(key: str) -> str:
    """Mask an API key, showing only last 4 characters."""
    if not key or len(key) <= 4:
        return '****'
    return '*' * (len(key) - 4) + key[-4:]


# ── Connection Tests ──

class TestBrokerConnectionRequest(BaseModel):
    broker: str
    api_key: str = ''
    api_secret: str = ''
    account_id: str = ''
    additional_fields: Optional[dict] = None


@router.post("/test-broker")
def test_broker_connection(
    request_json: TestBrokerConnectionRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """Test broker API connection with provided credentials."""
    broker = request_json.broker
    api_key = request_json.api_key
    account_id = request_json.account_id
    api_secret = request_json.api_secret
    additional_fields = request_json.additional_fields or {}

    # If no credentials provided, use stored ones for retest (with admin fallback)
    if not api_key:
        settings = _get_settings_with_fallback(current_user, section='brokers')
        stored = settings.get('brokers', {}).get(broker, {})
        api_key = stored.get('api_key', '')
        api_secret = api_secret or stored.get('api_secret', '')
        account_id = account_id or stored.get('account_id', '')
        if not additional_fields:
            additional_fields = stored.get('additional_fields', {})

    try:
        result = _test_broker(broker, api_key, api_secret, account_id, additional_fields, user_id=_settings_uid(current_user))
        return JSONResponse({'data': result}, status_code=200)
    except Exception as e:
        return JSONResponse({
            'data': {'connected': False, 'error': str(e), 'details': {}}
        }, status_code=200)


@router.post("/test-llm")
def test_llm_connection(
    request_json: LLMSettingsRequestJson,
    current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """Test LLM provider connection with provided credentials."""
    provider = request_json.provider
    api_key = request_json.api_key
    model = request_json.model

    # If no API key provided, use stored one for retest (with admin fallback)
    if not api_key:
        settings = _get_settings_with_fallback(current_user, section='llm')
        llm_conf = settings.get('llm', {})
        api_key = llm_conf.get('api_key', '')
        if not provider:
            provider = llm_conf.get('provider', '')
        if not model:
            model = llm_conf.get('model', '')

    try:
        result = _test_llm(provider, api_key, model)
        return JSONResponse({'data': result}, status_code=200)
    except Exception as e:
        return JSONResponse({
            'data': {'connected': False, 'error': str(e), 'details': {}}
        }, status_code=200)


def _test_broker(broker: str, api_key: str, api_secret: str, account_id: str, additional_fields: dict = None, user_id: str = None) -> dict:
    """Test broker connection. Returns {connected, error, details}."""
    import requests
    import socket

    additional_fields = additional_fields or {}
    broker_lower = broker.lower()

    # OANDA
    if 'oanda' in broker_lower:
        is_demo = 'demo' in broker_lower
        base = 'https://api-fxpractice.oanda.com/v3' if is_demo else 'https://api-fxtrade.oanda.com/v3'
        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}

        # Test auth
        resp = requests.get(f'{base}/accounts', headers=headers, timeout=10)
        if resp.status_code != 200:
            return {'connected': False, 'error': f'Authentication failed ({resp.status_code})', 'details': {}}

        accounts = resp.json().get('accounts', [])
        if account_id and account_id not in [a['id'] for a in accounts]:
            return {
                'connected': False,
                'error': f'Account {account_id} not found',
                'details': {'available_accounts': [a['id'] for a in accounts]},
            }

        # Get account summary
        aid = account_id or (accounts[0]['id'] if accounts else '')
        if aid:
            resp2 = requests.get(f'{base}/accounts/{aid}/summary', headers=headers, timeout=10)
            if resp2.status_code == 200:
                acct = resp2.json().get('account', {})
                return {
                    'connected': True,
                    'error': None,
                    'details': {
                        'account_id': aid,
                        'balance': acct.get('balance', '0'),
                        'currency': acct.get('currency', 'USD'),
                        'nav': acct.get('NAV', '0'),
                        'open_trades': acct.get('openTradeCount', 0),
                    },
                }

        return {'connected': True, 'error': None, 'details': {'account_id': aid}}

    # IG Markets
    elif 'ig' in broker_lower:
        is_demo = 'demo' in broker_lower
        base = 'https://demo-api.ig.com/gateway/deal' if is_demo else 'https://api.ig.com/gateway/deal'

        # The settings form uses: api_key=IG API key, api_secret=password, account_id=username
        username = account_id
        password = api_secret
        ig_account_id = additional_fields.get('ig_account_id', '')

        # Also check .env and DB-stored settings as fallback
        if not ig_account_id:
            import os
            from qengine.services.env import ENV_VALUES
            ig_account_id = os.environ.get('IG_ACCOUNT_ID', ENV_VALUES.get('IG_ACCOUNT_ID', ''))
        if not ig_account_id:
            try:
                stored = _get_settings_from_db(user_id).get('brokers', {}).get(broker, {})
                ig_account_id = stored.get('additional_fields', {}).get('ig_account_id', '')
            except Exception:
                pass

        resp = requests.post(
            f'{base}/session',
            headers={'X-IG-API-KEY': api_key, 'Content-Type': 'application/json', 'Version': '2'},
            json={'identifier': username, 'password': password},
            timeout=10,
        )
        if resp.status_code != 200:
            return {'connected': False, 'error': f'Authentication failed ({resp.status_code})', 'details': {}}

        cst = resp.headers.get('CST', '')
        sec_token = resp.headers.get('X-SECURITY-TOKEN', '')
        auth_headers = {'X-IG-API-KEY': api_key, 'CST': cst, 'X-SECURITY-TOKEN': sec_token, 'Content-Type': 'application/json'}

        # Get accounts
        resp2 = requests.get(f'{base}/accounts', headers=auth_headers, timeout=10)
        if resp2.status_code == 200:
            accounts = resp2.json().get('accounts', [])
            all_accounts = [{'id': a.get('accountId'), 'type': a.get('accountType'), 'name': a.get('accountName')} for a in accounts]

            if accounts:
                # Find the target account: explicit ID first, then CFD type, then first
                acct = None
                if ig_account_id:
                    for a in accounts:
                        if a.get('accountId') == ig_account_id:
                            acct = a
                            break
                if acct is None:
                    for a in accounts:
                        if a.get('accountType', '').upper() == 'CFD':
                            acct = a
                            break
                if acct is None:
                    acct = accounts[0]

                # Switch to the selected account
                target_id = acct.get('accountId', '')
                current_id = resp.json().get('currentAccountId', '')
                if target_id and target_id != current_id:
                    switch_resp = requests.put(
                        f'{base}/session',
                        headers={**auth_headers, 'Version': '1'},
                        json={'accountId': target_id},
                        timeout=10,
                    )
                    if switch_resp.status_code != 200:
                        return {
                            'connected': True,
                            'error': f'Authenticated but failed to switch to account {target_id} ({switch_resp.status_code})',
                            'details': {'current_account': current_id, 'target_account': target_id, 'all_accounts': all_accounts},
                        }

                balance = acct.get('balance', {})
                return {
                    'connected': True,
                    'error': None,
                    'details': {
                        'account_id': target_id,
                        'account_type': acct.get('accountType', ''),
                        'account_name': acct.get('accountName', ''),
                        'balance': balance.get('balance', 0),
                        'currency': acct.get('currency', 'GBP'),
                        'available': balance.get('available', 0),
                        'all_accounts': all_accounts,
                    },
                }

        return {'connected': True, 'error': None, 'details': {}}

    # IBKR
    elif 'ibkr' in broker_lower or 'interactive' in broker_lower:
        # IBKR connects to local TWS/IB Gateway - test if port is open
        host = '127.0.0.1'
        port = 7497 if 'paper' in broker_lower else 7496
        try:
            with socket.create_connection((host, port), timeout=3):
                return {
                    'connected': True,
                    'error': None,
                    'details': {'host': host, 'port': port, 'account_id': account_id},
                }
        except (ConnectionRefusedError, OSError, socket.timeout):
            return {
                'connected': False,
                'error': f'TWS/IB Gateway not running at {host}:{port}',
                'details': {'host': host, 'port': port},
            }

    return {'connected': False, 'error': f'Unknown broker: {broker}', 'details': {}}


def _test_llm(provider: str, api_key: str, model: str = None) -> dict:
    """Test LLM provider connection. Returns {connected, error, details}."""

    if not api_key:
        return {'connected': False, 'error': 'API key is required', 'details': {}}

    if provider == 'gemini':
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            mdl = model or 'gemini-2.5-flash'
            response = client.models.generate_content(
                model=mdl,
                contents='Reply with exactly: CONNECTION_OK',
                config={'temperature': 0, 'max_output_tokens': 20},
            )
            text = (response.text or '').strip()
            return {
                'connected': True,
                'error': None,
                'details': {'provider': 'gemini', 'model': mdl, 'response': text or 'OK'},
            }
        except Exception as e:
            err = str(e)
            if 'API_KEY_INVALID' in err or '400' in err or 'invalid' in err.lower():
                return {'connected': False, 'error': 'Invalid API key', 'details': {'provider': 'gemini'}}
            return {'connected': False, 'error': f'Gemini error: {err}', 'details': {'provider': 'gemini'}}

    elif provider == 'anthropic':
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            mdl = model or 'claude-sonnet-4-6'
            response = client.messages.create(
                model=mdl,
                max_tokens=20,
                temperature=0,
                messages=[{'role': 'user', 'content': 'Reply with exactly: CONNECTION_OK'}],
            )
            text = (response.content[0].text if response.content else '') or ''
            return {
                'connected': True,
                'error': None,
                'details': {'provider': 'anthropic', 'model': mdl, 'response': text.strip() or 'OK'},
            }
        except Exception as e:
            err = str(e)
            if 'authentication' in err.lower() or '401' in err:
                return {'connected': False, 'error': 'Invalid API key', 'details': {'provider': 'anthropic'}}
            if 'rate' in err.lower() or '429' in err:
                return {'connected': False, 'error': 'Rate limited - try again in a moment', 'details': {'provider': 'anthropic'}}
            return {'connected': False, 'error': f'Anthropic error: {err}', 'details': {'provider': 'anthropic'}}

    elif provider == 'openai':
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            mdl = model or 'gpt-4o'
            response = client.chat.completions.create(
                model=mdl,
                temperature=0,
                max_tokens=20,
                messages=[{'role': 'user', 'content': 'Reply with exactly: CONNECTION_OK'}],
            )
            text = (response.choices[0].message.content if response.choices else '') or ''
            return {
                'connected': True,
                'error': None,
                'details': {'provider': 'openai', 'model': mdl, 'response': text.strip() or 'OK'},
            }
        except Exception as e:
            err = str(e)
            if 'authentication' in err.lower() or '401' in err or 'Incorrect API key' in err:
                return {'connected': False, 'error': 'Invalid API key', 'details': {'provider': 'openai'}}
            if 'rate' in err.lower() or '429' in err:
                return {'connected': False, 'error': 'Rate limited - try again in a moment', 'details': {'provider': 'openai'}}
            return {'connected': False, 'error': f'OpenAI error: {err}', 'details': {'provider': 'openai'}}

    return {'connected': False, 'error': f'Unknown provider: {provider}', 'details': {}}
