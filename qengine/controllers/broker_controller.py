from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from qengine.services import auth as authenticator
from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser
from qengine.info import broker_info, backtesting_exchanges, live_trading_exchanges
from qengine.enums import brokers

router = APIRouter(prefix="/broker", tags=["Broker"])


@router.get("/list")
def get_brokers(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Return all available brokers with metadata."""

    result = []
    for key, info in broker_info.items():
        result.append({
            'id': key,
            'name': info['name'],
            'type': info['type'],
            'asset_classes': info.get('asset_classes', []),
            'fee_model': info.get('fee_model', 'spread'),
            'default_leverage': info.get('default_leverage', 1),
            'modes': info.get('modes', {}),
            'settlement_currency': info.get('settlement_currency', 'USD'),
        })

    return JSONResponse({'data': result}, status_code=200)


# Mapping from base broker to its demo/paper variant ID
_BROKER_GROUPS = {
    brokers.OANDA: {
        'name': 'OANDA',
        'type': 'cfd',
        'live_id': brokers.OANDA,
        'demo_id': brokers.OANDA_DEMO,
        'demo_label': 'Demo',
    },
    brokers.IG_MARKETS: {
        'name': 'IG Markets',
        'type': 'cfd',
        'live_id': brokers.IG_MARKETS,
        'demo_id': brokers.IG_MARKETS_DEMO,
        'demo_label': 'Demo',
    },
    brokers.IBKR: {
        'name': 'Interactive Brokers',
        'type': 'cfd',
        'live_id': brokers.IBKR,
        'demo_id': brokers.IBKR_PAPER,
        'demo_label': 'Paper',
    },
}


@router.get("/grouped")
def get_brokers_grouped(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Return brokers grouped (demo+live under one entry) with connection status."""

    # Load saved broker credentials (admins share + .env fallback, users have own)
    from qengine.controllers.settings_controller import _get_settings_with_fallback
    settings = _get_settings_with_fallback(current_user, section='brokers')
    saved_brokers = settings.get('brokers', {})

    result = []
    for base_id, group in _BROKER_GROUPS.items():
        live_id = group['live_id']
        demo_id = group['demo_id']
        live_info = broker_info[live_id]
        demo_info = broker_info[demo_id]

        live_configured = bool(saved_brokers.get(live_id, {}).get('api_key'))
        demo_configured = bool(saved_brokers.get(demo_id, {}).get('api_key'))

        result.append({
            'id': base_id,
            'name': group['name'],
            'type': group['type'],
            'url': live_info.get('url', ''),
            'asset_classes': live_info.get('asset_classes', []),
            'fee_model': live_info.get('fee_model', 'spread'),
            'default_leverage': live_info.get('default_leverage', 1),
            'api_type': live_info.get('api_type', ''),
            'settlement_currency': live_info.get('settlement_currency', 'USD'),
            'supported_timeframes': live_info.get('supported_timeframes', []),
            'environments': {
                'live': {
                    'id': live_id,
                    'configured': live_configured,
                    'modes': live_info.get('modes', {}),
                },
                'demo': {
                    'id': demo_id,
                    'label': group['demo_label'],
                    'configured': demo_configured,
                    'modes': demo_info.get('modes', {}),
                },
            },
            'active': live_configured or demo_configured,
        })

    return JSONResponse({'data': result}, status_code=200)


@router.get("/connected")
def get_connected_brokers(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Return only broker environments that have API keys configured."""

    from qengine.controllers.settings_controller import _get_settings_with_fallback
    settings = _get_settings_with_fallback(current_user, section='brokers')
    saved_brokers = settings.get('brokers', {})

    result = []
    for broker_id, conf in saved_brokers.items():
        if not conf.get('api_key'):
            continue
        info = broker_info.get(broker_id)
        if not info:
            continue
        is_demo = broker_id in (brokers.OANDA_DEMO, brokers.IG_MARKETS_DEMO, brokers.IBKR_PAPER)
        result.append({
            'id': broker_id,
            'name': info['name'],
            'type': info['type'],
            'is_demo': is_demo,
            'account_id': conf.get('account_id', ''),
            'asset_classes': info.get('asset_classes', []),
            'fee_model': info.get('fee_model', 'spread'),
            'default_leverage': info.get('default_leverage', 1),
            'settlement_currency': info.get('settlement_currency', 'USD'),
            'modes': info.get('modes', {}),
        })

    return JSONResponse({'data': result}, status_code=200)


@router.get("/backtesting")
def get_backtesting_brokers(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Return brokers available for backtesting."""

    result = []
    for key in backtesting_exchanges:
        info = broker_info[key]
        result.append({
            'id': key,
            'name': info['name'],
            'type': info['type'],
            'asset_classes': info.get('asset_classes', []),
        })

    return JSONResponse({'data': result}, status_code=200)


@router.get("/live-trading")
def get_live_trading_brokers(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Return brokers available for live trading."""

    result = []
    for key in live_trading_exchanges:
        info = broker_info[key]
        result.append({
            'id': key,
            'name': info['name'],
            'type': info['type'],
            'asset_classes': info.get('asset_classes', []),
        })

    return JSONResponse({'data': result}, status_code=200)


@router.get("/info/{broker_id}")
def get_broker_info(broker_id: str, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Return detailed info for a specific broker."""

    # Find broker by ID (which is the broker_info key)
    info = broker_info.get(broker_id)
    if not info:
        return JSONResponse({'error': f'Broker {broker_id} not found'}, status_code=404)

    return JSONResponse({
        'data': {
            'id': broker_id,
            'name': info['name'],
            'type': info['type'],
            'url': info.get('url', ''),
            'asset_classes': info.get('asset_classes', []),
            'fee_model': info.get('fee_model', 'spread'),
            'default_leverage': info.get('default_leverage', 1),
            'supported_timeframes': info.get('supported_timeframes', []),
            'modes': info.get('modes', {}),
            'api_type': info.get('api_type', ''),
            'settlement_currency': info.get('settlement_currency', 'USD'),
        }
    }, status_code=200)


@router.get("/asset-classes")
def get_asset_classes(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Return all supported asset classes across all brokers."""

    all_classes = set()
    for info in broker_info.values():
        for ac in info.get('asset_classes', []):
            all_classes.add(ac)

    return JSONResponse({'data': sorted(all_classes)}, status_code=200)


@router.get("/asset-classes/{broker_id}")
def get_broker_asset_classes(broker_id: str, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Return asset classes supported by a specific broker."""

    info = broker_info.get(broker_id)
    if not info:
        return JSONResponse({'error': f'Broker {broker_id} not found'}, status_code=404)

    return JSONResponse({'data': info.get('asset_classes', [])}, status_code=200)


@router.get("/cost-model/{broker_id}")
def get_cost_model(broker_id: str, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Return cost model settings for a broker (leverage, fees, swap rates)."""

    info = broker_info.get(broker_id)
    if not info:
        return JSONResponse({'error': f'Broker {broker_id} not found'}, status_code=404)

    from qengine.core.instruments import instrument_registry

    # Gather instrument-level cost data for this broker's asset classes
    instruments_cost = []
    for symbol, inst in instrument_registry._instruments.items():
        if inst.asset_class in info.get('asset_classes', []):
            instruments_cost.append({
                'symbol': inst.symbol,
                'asset_class': inst.asset_class,
                'pip_size': inst.pip_size,
                'contract_size': inst.contract_size,
                'margin_rate': inst.margin_rate,
                'swap_long': inst.swap_long,
                'swap_short': inst.swap_short,
            })

    return JSONResponse({
        'data': {
            'broker': broker_id,
            'fee_model': info.get('fee_model', 'spread'),
            'default_leverage': info.get('default_leverage', 1),
            'settlement_currency': info.get('settlement_currency', 'USD'),
            'instruments': instruments_cost,
        }
    }, status_code=200)


class UpdateCostModelRequest(BaseModel):
    broker_id: str
    leverage: Optional[int] = None
    instruments: Optional[list] = None  # [{symbol, swap_long, swap_short}]


@router.post("/cost-model/update")
def update_cost_model(
    json_request: UpdateCostModelRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """Update cost model settings for a broker."""

    info = broker_info.get(json_request.broker_id)
    if not info:
        return JSONResponse({'error': f'Broker {json_request.broker_id} not found'}, status_code=404)

    # Update leverage
    if json_request.leverage is not None:
        broker_info[json_request.broker_id]['default_leverage'] = json_request.leverage
        # Also update config
        from qengine.config import config
        if json_request.broker_id in config['env']['exchanges']:
            config['env']['exchanges'][json_request.broker_id]['futures_leverage'] = json_request.leverage

    # Update instrument swap rates
    if json_request.instruments:
        from qengine.core.instruments import instrument_registry
        for item in json_request.instruments:
            inst = instrument_registry.get(item.get('symbol', ''))
            if inst:
                if 'swap_long' in item:
                    inst.swap_long = float(item['swap_long'])
                if 'swap_short' in item:
                    inst.swap_short = float(item['swap_short'])

    return JSONResponse({'message': 'Cost model updated successfully'}, status_code=200)


@router.get("/exchange-types")
def get_exchange_types(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Return all supported exchange/asset types."""

    return JSONResponse({
        'data': [
            {'id': 'cfd', 'name': 'CFD', 'description': 'CFD trading with true hedging (forex, indices, commodities, stocks)'},
            {'id': 'futures', 'name': 'Futures', 'description': 'Crypto/commodity futures (netting mode)'},
            {'id': 'spot', 'name': 'Spot', 'description': 'Spot trading (crypto)'},
        ]
    }, status_code=200)
