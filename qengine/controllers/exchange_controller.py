from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from qengine.modes.import_candles_mode import CandleExchange
from qengine.modes.import_candles_mode.drivers import drivers, driver_names
from qengine.services import auth as authenticator
from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser
from qengine.services.redis import sync_redis
from qengine.services.web import ExchangeSupportedSymbolsRequestJson, StoreExchangeApiKeyRequestJson, DeleteExchangeApiKeyRequestJson
from qengine.services.env import is_dev_env


router = APIRouter(prefix="/exchange", tags=["Exchange"])


@router.post('/supported-symbols')
def exchange_supported_symbols(request_json: ExchangeSupportedSymbolsRequestJson, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    
    # if is_dev_env():
    #     return JSONResponse({
    #         'data': [    
    #             'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'DOGE-USDT'
    #         ]
    #     }, status_code=200)

    return get_exchange_supported_symbols(request_json.exchange)


@router.get('/api-keys')
def get_exchange_api_keys_endpoint(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:

    user_id = current_user.effective_user_id if not current_user.is_admin or current_user.is_impersonating else None

    from qengine.modes.exchange_api_keys import get_exchange_api_keys
    return get_exchange_api_keys(user_id=user_id)


@router.post('/api-keys/store')
def store_exchange_api_keys_endpoint(json_request: StoreExchangeApiKeyRequestJson,
                        current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:

    from qengine.modes.exchange_api_keys import store_exchange_api_keys
    return store_exchange_api_keys(
        json_request.exchange, json_request.name, json_request.api_key, json_request.api_secret,
        json_request.additional_fields, json_request.general_notifications_id, json_request.error_notifications_id,
        user_id=current_user.effective_user_id
    )


@router.post('/api-keys/delete')
def delete_exchange_api_keys_endpoint(json_request: DeleteExchangeApiKeyRequestJson,
                         current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:

    user_id = current_user.effective_user_id if not current_user.is_admin or current_user.is_impersonating else None

    from qengine.modes.exchange_api_keys import delete_exchange_api_keys
    return delete_exchange_api_keys(json_request.id, user_id=user_id)


def get_exchange_supported_symbols(exchange: str) -> JSONResponse:
    # first try to get from cache
    cache_key = f'exchange-symbols:{exchange}'
    cached_result = sync_redis.get(cache_key)
    if cached_result is not None:
        import json
        return JSONResponse({
            'data': json.loads(cached_result)
        }, status_code=200)

    arr = []

    try:
        driver: CandleExchange = drivers[exchange]()
    except KeyError:
        raise ValueError(f'{exchange} is not a supported exchange. Supported exchanges are: {driver_names}')

    try:
        arr = driver.get_available_symbols()
        if arr:
            # cache successful result for 5 minutes
            import json
            sync_redis.setex(cache_key, 300, json.dumps(arr))
    except Exception:
        arr = []

    # If driver returned empty (no API key configured), fall back to instrument registry
    if not arr:
        arr = _get_fallback_symbols(exchange)
        if arr:
            import json
            sync_redis.setex(cache_key, 300, json.dumps(arr))

    return JSONResponse({
        'data': arr
    }, status_code=200)


def _get_fallback_symbols(exchange: str) -> list:
    """Return symbols from the instrument registry as fallback when API is unavailable."""
    from qengine.core.instruments import instrument_registry
    from qengine.info import broker_info

    info = broker_info.get(exchange)
    if not info:
        return []

    supported_classes = info.get('asset_classes', [])
    symbols = []
    for sym, inst in instrument_registry._instruments.items():
        if inst.asset_class in supported_classes:
            symbols.append(sym)

    return sorted(symbols)
