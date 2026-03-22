from typing import Optional
from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from qengine.services import auth as authenticator
from qengine.core.market_hours import market_hours
from qengine.core.instruments import instrument_registry
import qengine.helpers as jh

router = APIRouter(prefix="/market-data", tags=["Market Data"])


@router.get("/session")
def get_current_session(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """Return the current forex trading session."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    now_ms = jh.now(force_fresh=True)
    session = market_hours.current_session(now_ms)

    return JSONResponse({
        'data': {
            'session': session,
            'timestamp': now_ms,
        }
    }, status_code=200)


@router.get("/market-hours/{symbol}")
def get_market_hours(symbol: str, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """Return market open/close status and session info for a symbol."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    now_ms = jh.now(force_fresh=True)
    is_open = market_hours.is_market_open(symbol, now_ms)
    session = market_hours.current_session(now_ms)
    mins_to_close = market_hours.minutes_to_close(symbol, now_ms)

    result = {
        'symbol': symbol,
        'is_open': is_open,
        'session': session,
        'minutes_to_close': mins_to_close,
        'timestamp': now_ms,
    }

    if not is_open:
        next_open = market_hours.next_market_open(symbol, now_ms)
        result['next_open'] = next_open

    return JSONResponse({'data': result}, status_code=200)


@router.get("/instrument/{symbol}")
def get_instrument_info(symbol: str, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """Return instrument metadata (pip size, contract size, etc.)."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    inst = instrument_registry.get(symbol)
    if inst:
        return JSONResponse({
            'data': {
                'symbol': inst.symbol,
                'asset_class': inst.asset_class,
                'pip_size': inst.pip_size,
                'contract_size': inst.contract_size,
                'min_lot': inst.min_lot,
                'lot_step': inst.lot_step,
                'base_currency': inst.base_currency,
                'quote_currency': inst.quote_currency,
                'margin_rate': inst.margin_rate,
                'trading_hours': inst.trading_hours,
                'swap_long': inst.swap_long,
                'swap_short': inst.swap_short,
            }
        }, status_code=200)

    # Infer basic info from symbol
    asset_class = instrument_registry.get_asset_class(symbol)
    pip_size = instrument_registry.get_pip_size(symbol)
    contract_size = instrument_registry.get_contract_size(symbol)
    parts = symbol.split('-')
    base = parts[0] if len(parts) >= 2 else symbol
    quote = parts[1] if len(parts) >= 2 else 'USD'

    return JSONResponse({
        'data': {
            'symbol': symbol,
            'asset_class': asset_class,
            'pip_size': pip_size,
            'contract_size': contract_size,
            'base_currency': base,
            'quote_currency': quote,
            'inferred': True,
        }
    }, status_code=200)


@router.get("/instruments")
def list_instruments(
    asset_class: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
) -> JSONResponse:
    """List all registered instruments, optionally filtered by asset class."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    instruments = []
    for symbol, inst in instrument_registry._instruments.items():
        if asset_class and inst.asset_class != asset_class:
            continue
        instruments.append({
            'symbol': inst.symbol,
            'asset_class': inst.asset_class,
            'pip_size': inst.pip_size,
            'contract_size': inst.contract_size,
            'base_currency': inst.base_currency,
            'quote_currency': inst.quote_currency,
        })

    return JSONResponse({'data': instruments}, status_code=200)


@router.get("/pip-value/{symbol}")
def get_pip_value(
    symbol: str,
    lot_size: float = Query(default=1.0),
    authorization: Optional[str] = Header(None),
) -> JSONResponse:
    """Calculate pip value for a given symbol and lot size."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    pip_size = instrument_registry.get_pip_size(symbol)
    contract_size = instrument_registry.get_contract_size(symbol)
    pip_value = pip_size * contract_size * lot_size

    return JSONResponse({
        'data': {
            'symbol': symbol,
            'pip_size': pip_size,
            'contract_size': contract_size,
            'lot_size': lot_size,
            'pip_value': round(pip_value, 4),
        }
    }, status_code=200)


from pydantic import BaseModel


class CalculatorRequest(BaseModel):
    symbol: str
    broker_id: str
    account_balance: float = 10000.0
    risk_percent: float = 1.0
    stop_loss_pips: float = 50.0
    lot_size: float = 1.0


@router.post("/calculate")
def calculate(
    req: CalculatorRequest,
    authorization: Optional[str] = Header(None),
) -> JSONResponse:
    """Trading calculator: pip value, margin, position size, risk/reward."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from qengine.info import broker_info

    inst = instrument_registry.get(req.symbol)
    pip_size = inst.pip_size if inst else instrument_registry.get_pip_size(req.symbol)
    contract_size = inst.contract_size if inst else instrument_registry.get_contract_size(req.symbol)
    margin_rate = inst.margin_rate if inst else 0.0333

    info = broker_info.get(req.broker_id, {})
    leverage = info.get('default_leverage', 30)

    # Pip value per lot
    pip_value_per_lot = pip_size * contract_size

    # Position sizing from risk
    risk_amount = req.account_balance * (req.risk_percent / 100.0)
    sl_value = req.stop_loss_pips * pip_value_per_lot
    position_size_lots = round(risk_amount / sl_value, 2) if sl_value > 0 else 0.0

    # Margin required for given lot_size
    notional = contract_size * req.lot_size
    margin_from_rate = notional * margin_rate
    margin_from_leverage = notional / leverage
    margin_required = round(max(margin_from_rate, margin_from_leverage), 2)

    # Pip value for requested lot size
    pip_value = round(pip_value_per_lot * req.lot_size, 4)

    # Max lots the account can hold
    margin_per_lot = max(contract_size * margin_rate, contract_size / leverage)
    max_lots = round(req.account_balance / margin_per_lot, 2) if margin_per_lot > 0 else 0.0

    return JSONResponse({
        'data': {
            'symbol': req.symbol,
            'broker': req.broker_id,
            'leverage': leverage,
            'pip_size': pip_size,
            'contract_size': contract_size,
            'margin_rate': margin_rate,
            'pip_value_per_lot': round(pip_value_per_lot, 4),
            'pip_value': pip_value,
            'margin_required': margin_required,
            'risk_amount': round(risk_amount, 2),
            'position_size_lots': position_size_lots,
            'max_lots': max_lots,
        }
    }, status_code=200)
