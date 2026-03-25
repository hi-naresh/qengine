import json
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from qengine.services import auth as authenticator
import qengine.helpers as jh

router = APIRouter(prefix="/settings", tags=["Settings"])


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


def _get_settings_from_db() -> dict:
    """Load settings from the Option table."""
    from qengine.services.db import database
    from qengine.models.Option import Option
    import peewee

    database.open_connection()
    try:
        o = Option.get(Option.type == 'app_settings')
        data = json.loads(o.json)
    except peewee.DoesNotExist:
        data = {'brokers': {}, 'llm': {}}
    finally:
        database.close_connection()
    return data


def _save_settings_to_db(data: dict) -> None:
    """Persist settings to the Option table."""
    from qengine.services.db import database
    from qengine.models.Option import Option
    import peewee

    database.open_connection()
    try:
        o = Option.get(Option.type == 'app_settings')
        o.json = json.dumps(data)
        o.updated_at = jh.now(True)
        o.save()
    except peewee.DoesNotExist:
        o = Option({
            'id': jh.generate_unique_id(),
            'updated_at': jh.now(True),
            'type': 'app_settings',
            'json': json.dumps(data)
        })
        o.save(force_insert=True)
    finally:
        database.close_connection()


# ── Broker Settings ──

@router.get("/brokers")
def get_broker_settings(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """Get all saved broker configurations (keys are masked)."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    settings = _get_settings_from_db()
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
    authorization: Optional[str] = Header(None),
) -> JSONResponse:
    """Save broker API credentials."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    settings = _get_settings_from_db()
    if 'brokers' not in settings:
        settings['brokers'] = {}

    settings['brokers'][request_json.broker] = {
        'api_key': request_json.api_key,
        'api_secret': request_json.api_secret,
        'account_id': request_json.account_id,
        'additional_fields': request_json.additional_fields or {},
    }

    _save_settings_to_db(settings)

    return JSONResponse({'message': f'Broker {request_json.broker} settings saved'}, status_code=200)


@router.delete("/brokers/{broker_id}")
def delete_broker_settings(broker_id: str, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """Remove broker settings."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    settings = _get_settings_from_db()
    brokers = settings.get('brokers', {})

    if broker_id not in brokers:
        return JSONResponse({'error': f'No settings for broker {broker_id}'}, status_code=404)

    del brokers[broker_id]
    settings['brokers'] = brokers
    _save_settings_to_db(settings)

    return JSONResponse({'message': f'Broker {broker_id} settings removed'}, status_code=200)


# ── LLM Settings ──

@router.get("/llm")
def get_llm_settings(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """Get LLM configuration (key masked)."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    settings = _get_settings_from_db()
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
    authorization: Optional[str] = Header(None),
) -> JSONResponse:
    """Save LLM configuration and apply it to the engine."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    settings = _get_settings_from_db()
    settings['llm'] = {
        'provider': request_json.provider,
        'api_key': request_json.api_key,
        'model': request_json.model or '',
        'temperature': request_json.temperature,
    }
    _save_settings_to_db(settings)

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
def delete_llm_settings(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """Remove LLM configuration."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    settings = _get_settings_from_db()
    settings['llm'] = {}
    _save_settings_to_db(settings)

    return JSONResponse({'message': 'LLM settings removed'}, status_code=200)


# ── General Settings ──

@router.get("/all")
def get_all_settings(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """Get all application settings."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    settings = _get_settings_from_db()

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


@router.get("/backtest/{broker_id}")
def get_backtest_settings(broker_id: str, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """Get backtest cost/randomness settings for a specific broker."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    settings = _get_settings_from_db()
    bt_all = settings.get('backtest_brokers', {})
    bt = bt_all.get(broker_id, settings.get('backtest', _default_backtest_settings()))
    return JSONResponse({'data': bt}, status_code=200)


@router.post("/backtest")
def save_backtest_settings(
    request_json: BacktestSettingsRequestJson,
    authorization: Optional[str] = Header(None),
) -> JSONResponse:
    """Save backtest cost/randomness settings for a specific broker."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    settings = _get_settings_from_db()
    if 'backtest_brokers' not in settings:
        settings['backtest_brokers'] = {}

    settings['backtest_brokers'][request_json.broker_id] = {
        'spread_pips': request_json.spread_pips,
        'spread_randomness': max(0.0, min(1.0, request_json.spread_randomness)),
        'slippage_pips': request_json.slippage_pips,
        'slippage_randomness': max(0.0, min(1.0, request_json.slippage_randomness)),
        'swap_enabled': request_json.swap_enabled,
        'commission_per_lot': request_json.commission_per_lot,
    }
    _save_settings_to_db(settings)

    return JSONResponse({'message': f'Backtest settings saved for {request_json.broker_id}'}, status_code=200)


def _default_backtest_settings() -> dict:
    return {
        'spread_pips': 2.0,
        'spread_randomness': 0.0,
        'slippage_pips': 0.0,
        'slippage_randomness': 0.0,
        'swap_enabled': True,
        'commission_per_lot': 0.0,
    }


def get_backtest_cost_settings(broker_id: str = None) -> dict:
    """Public helper: load backtest cost settings from DB for a specific broker."""
    try:
        settings = _get_settings_from_db()
        if broker_id:
            bt_all = settings.get('backtest_brokers', {})
            if broker_id in bt_all:
                return bt_all[broker_id]
        # Fallback to legacy global settings, then defaults
        return settings.get('backtest', _default_backtest_settings())
    except Exception:
        return _default_backtest_settings()


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
    authorization: Optional[str] = Header(None),
) -> JSONResponse:
    """Test broker API connection with provided credentials."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    broker = request_json.broker
    api_key = request_json.api_key
    account_id = request_json.account_id
    api_secret = request_json.api_secret
    additional_fields = request_json.additional_fields or {}

    # If no credentials provided, use stored ones for retest
    if not api_key:
        settings = _get_settings_from_db()
        stored = settings.get('brokers', {}).get(broker, {})
        api_key = stored.get('api_key', '')
        api_secret = api_secret or stored.get('api_secret', '')
        account_id = account_id or stored.get('account_id', '')
        if not additional_fields:
            additional_fields = stored.get('additional_fields', {})

    try:
        result = _test_broker(broker, api_key, api_secret, account_id, additional_fields)
        return JSONResponse({'data': result}, status_code=200)
    except Exception as e:
        return JSONResponse({
            'data': {'connected': False, 'error': str(e), 'details': {}}
        }, status_code=200)


@router.post("/test-llm")
def test_llm_connection(
    request_json: LLMSettingsRequestJson,
    authorization: Optional[str] = Header(None),
) -> JSONResponse:
    """Test LLM provider connection with provided credentials."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        result = _test_llm(
            request_json.provider,
            request_json.api_key,
            request_json.model,
        )
        return JSONResponse({'data': result}, status_code=200)
    except Exception as e:
        return JSONResponse({
            'data': {'connected': False, 'error': str(e), 'details': {}}
        }, status_code=200)


def _test_broker(broker: str, api_key: str, api_secret: str, account_id: str, additional_fields: dict = None) -> dict:
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
                stored = _get_settings_from_db().get('brokers', {}).get(broker, {})
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

    if provider == 'gemini':
        from google import genai
        client = genai.Client(api_key=api_key)
        mdl = model or 'gemini-2.0-flash'
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

    elif provider == 'anthropic':
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

    elif provider == 'openai':
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

    return {'connected': False, 'error': f'Unknown provider: {provider}', 'details': {}}
