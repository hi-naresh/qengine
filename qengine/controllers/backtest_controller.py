import math
from typing import Optional
from fastapi import APIRouter, Header, Query, Body
from fastapi.responses import JSONResponse, FileResponse
import json
from qengine.services import auth as authenticator
from qengine.services.multiprocessing import process_manager
from qengine.services.web import BacktestRequestJson, CancelRequestJson, UpdateBacktestSessionStateRequestJson, GetBacktestSessionsRequestJson, UpdateBacktestSessionNotesRequestJson
import qengine.helpers as jh
from qengine.models.BacktestSession import (
    get_backtest_sessions as get_sessions,
    update_backtest_session_state,
    update_backtest_session_notes,
    delete_backtest_session,
    get_backtest_session_by_id as get_backtest_session_by_id_from_db,
    update_backtest_session_status,
    purge_backtest_sessions
)
from qengine.services.transformers import get_backtest_session, get_backtest_session_for_load_more
from qengine.modes.backtest_mode import run as run_backtest
from qengine.modes.data_provider import get_backtest_logs, download_backtest_log


router = APIRouter(prefix="/backtest", tags=["Backtest"])


@router.post("")
def backtest(request_json: BacktestRequestJson, authorization: Optional[str] = Header(None)):
    """
    Start a backtest process
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    jh.validate_cwd()

    process_manager.add_task(
        run_backtest,
        request_json.id,
        request_json.debug_mode,
        request_json.config,
        request_json.exchange,
        request_json.routes,
        request_json.data_routes,
        request_json.start_date,
        request_json.finish_date,
        None,
        request_json.export_chart,
        request_json.export_tradingview,
        request_json.export_csv,
        request_json.export_json,
        request_json.fast_mode,
        request_json.benchmark,
        request_json.hyperparameters,
        request_json.cost_model
    )

    return JSONResponse({'message': 'Started backtesting...'}, status_code=202)


@router.post("/cancel")
def cancel_backtest(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    """
    Cancel a backtest process
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.cancel_process(request_json.id)
    
    update_backtest_session_status(request_json.id, 'cancelled')

    return JSONResponse({'message': f'Backtest process with ID of {request_json.id} was requested for termination'},
                        status_code=202)


@router.get("/logs/{session_id}")
def get_logs(session_id: str, token: str = Query(...)):
    """
    Get logs as text for a specific session. Similar to download but returns text content instead of file.
    """
    if not authenticator.is_valid_token(token):
        return authenticator.unauthorized_response()

    try:
        content = get_backtest_logs(session_id)

        if content is None:
            return JSONResponse({'error': 'Log file not found'}, status_code=404)

        return JSONResponse({'content': content}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.get("/download-log/{session_id}")
def download_backtest_log_endpoint(session_id: str, token: str = Query(...)):
    """
    Download log file for a specific backtest session
    """
    if not authenticator.is_valid_token(token):
        return authenticator.unauthorized_response()

    try:
        return download_backtest_log(session_id)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/sessions")
def get_backtest_sessions(request_json: GetBacktestSessionsRequestJson = Body(default=GetBacktestSessionsRequestJson()), authorization: Optional[str] = Header(None)):
    """
    Get a list of backtest sessions sorted by most recently updated with pagination
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    # Get sessions from the database with pagination and filters
    sessions = get_sessions(
        limit=request_json.limit, 
        offset=request_json.offset,
        title_search=request_json.title_search,
        status_filter=request_json.status_filter,
        date_filter=request_json.date_filter
    )

    # Transform the sessions using the transformer
    transformed_sessions = [get_backtest_session(session) for session in sessions]

    return JSONResponse({
        'sessions': transformed_sessions,
        'count': len(transformed_sessions)
    })


@router.post("/sessions/{session_id}")
def get_backtest_session_by_id(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Get a single backtest session by ID
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    # Get the session from the database
    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    # Transform the session using the transformer
    transformed_session = get_backtest_session_for_load_more(session)
    transformed_session = jh.clean_infinite_values(transformed_session)

    return JSONResponse({
        'session': transformed_session
    })


@router.post("/update-state")
def update_session_state(request_json: UpdateBacktestSessionStateRequestJson, authorization: Optional[str] = Header(None)):
    """
    Update the state of a backtest session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    update_backtest_session_state(request_json.id, request_json.state)

    return JSONResponse({
        'message': 'Backtest session state updated successfully'
    })


@router.post("/sessions/{session_id}/remove")
def remove_backtest_session(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Remove a backtest session from the database
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    # Delete the session from the database
    result = delete_backtest_session(session_id)

    if not result:
        return JSONResponse({
            'error': f'Failed to delete session with ID {session_id}'
        }, status_code=500)

    return JSONResponse({
        'message': 'Backtest session removed successfully'
    })


@router.post("/sessions/{session_id}/notes")
def update_session_notes(session_id: str, request_json: UpdateBacktestSessionNotesRequestJson, authorization: Optional[str] = Header(None)):
    """
    Update the notes (title, description, strategy_codes) of a backtest session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    update_backtest_session_notes(session_id, request_json.title, request_json.description, request_json.strategy_codes)

    return JSONResponse({
        'message': 'Backtest session notes updated successfully'
    })


@router.post("/purge-sessions")
def purge_sessions(request_json: dict = Body(...), authorization: Optional[str] = Header(None)):
    """
    Purge backtest sessions older than specified days
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    days_old = request_json.get('days_old', None)
    
    deleted_count = purge_backtest_sessions(days_old)
    
    return JSONResponse({
        'message': f'Successfully purged {deleted_count} session(s)',
        'deleted_count': deleted_count
    }, status_code=200)


@router.post("/sessions/{session_id}/chart-data")
def get_backtest_session_chart_data(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Get chart data for a specific backtest session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    chart_data = jh.clean_infinite_values(json.loads(session.chart_data)) if session.chart_data else None

    return JSONResponse({
        'chart_data': chart_data
    })


@router.post("/sessions/{session_id}/strategy-code")
def get_backtest_session_strategy_codes(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Get strategy codes for a specific backtest session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    return JSONResponse({
        'strategy_code': json.loads(session.strategy_codes) if session.strategy_codes else {}
    })


@router.post("/sessions/{session_id}/logs")
def get_backtest_session_logs(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Get backtest logs for a specific session from the database
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    return JSONResponse({
        'logs': json.loads(session.logs) if session.logs else []
    })


@router.post("/exposure-table")
def compute_exposure_table(request_json: dict = Body(...), authorization: Optional[str] = Header(None)):
    """
    Compute a theoretical exposure table from strategy hyperparameters.
    The size HP (initial_size / base_size) is always treated as % of equity.
    e.g. initial_size=1 means 1% of balance used as notional for level 0.

    Request body:
      - exchange: str
      - symbol: str
      - hyperparameters: dict
      - balance: float
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from qengine.core.instruments import instrument_registry
    from qengine.info import exchange_info

    symbol = request_json.get('symbol', '')
    exchange_name = request_json.get('exchange', '')
    hp = request_json.get('hyperparameters') or {}
    balance = float(request_json.get('balance', 10000))

    # Instrument properties
    pip_size = instrument_registry.get_pip_size(symbol)
    contract_size = instrument_registry.get_contract_size(symbol)
    pip_value_per_lot = pip_size * contract_size if pip_size > 0 else 0

    # Leverage from broker info / instrument margin rate
    broker = exchange_info.get(exchange_name, {})
    leverage = broker.get('default_leverage', 30)
    inst = instrument_registry.get(symbol)
    margin_rate = getattr(inst, 'margin_rate', 0) if inst else 0
    if margin_rate > 0:
        leverage = 1.0 / margin_rate

    # Extract hedging params (support multiple naming conventions)
    # This is ALWAYS % of equity (e.g. 1 = 1%, 2.5 = 2.5%)
    base_pct = float(hp.get('base_size', hp.get('initial_size', hp.get('lot_size', hp.get('qty', 1.0)))))
    sizing_operator = str(hp.get('sizing_operator', 'multiplier'))
    sizing_factor = float(hp.get('sizing_factor', hp.get('multiplier', hp.get('lot_multiplier', 2.0))))
    max_levels = int(hp.get('max_levels', hp.get('max_orders', 1)))

    # TP and hedge distances in pips
    tp_pips = float(hp.get('tp_upper', hp.get('tp_pips', hp.get('take_profit_pips', 0))))
    tp_lower = float(hp.get('tp_lower', tp_pips))
    risk_reward = float(hp.get('risk_reward', 0))
    hedge_pips = float(hp.get('hedge_pips', hp.get('hedge_distance', hp.get('sl_pips', hp.get('stop_loss_pips', 0)))))

    if risk_reward > 0 and tp_pips > 0 and hedge_pips <= 0:
        hedge_pips = tp_pips / risk_reward

    has_tp_sl = tp_pips > 0 or hedge_pips > 0

    _FIB = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]

    def _sizing_multiplier(level: int) -> float:
        if sizing_operator == 'sqrt':
            return math.sqrt(sizing_factor) ** level
        elif sizing_operator == 'linear':
            return 1 + level
        elif sizing_operator == 'fibonacci':
            return _FIB[level] if level < len(_FIB) else _FIB[-1]
        else:  # 'multiplier'
            return sizing_factor ** level

    if max_levels <= 1:
        max_levels = 1

    price = _estimate_price(symbol)

    # Convert % equity to lots: notional = balance * pct/100, lots = notional / (contract_size * price)
    if contract_size > 0 and price > 0:
        base_lots = (balance * base_pct / 100.0) / (contract_size * price)
    else:
        base_lots = (balance * base_pct / 100.0) / price if price > 0 else 0

    # Direction alternation
    initial_dir = str(hp.get('direction', 'long')).lower()
    directions = []
    d = initial_dir
    for _ in range(max_levels):
        directions.append(d)
        d = 'short' if d == 'long' else 'long'

    table = []
    cumulative_margin = 0.0
    cumulative_loss = 0.0

    for level in range(max_levels):
        factor = _sizing_multiplier(level)
        level_pct = base_pct * factor
        lot_size = base_lots * factor
        units = lot_size * contract_size if contract_size > 0 else lot_size
        notional = lot_size * contract_size * price if contract_size > 0 else lot_size * price
        margin_required = notional / leverage if leverage > 0 else notional

        cumulative_margin += margin_required
        margin_pct = (cumulative_margin / balance * 100) if balance > 0 else 0

        dir_tp = tp_pips if directions[level] == 'long' else tp_lower
        leg_loss = lot_size * pip_value_per_lot * hedge_pips if pip_value_per_lot > 0 and hedge_pips > 0 else 0
        leg_tp_profit = lot_size * pip_value_per_lot * dir_tp if pip_value_per_lot > 0 and dir_tp > 0 else 0

        worst_float = cumulative_loss + leg_loss
        net_if_tp = leg_tp_profit - cumulative_loss

        row = {
            'level': level,
            'direction': directions[level].upper(),
            'equity_pct': round(level_pct, 2),
            'lots': round(lot_size, 4),
            'units': round(units, 0),
            'margin': round(margin_required, 2),
            'cumul_margin': round(cumulative_margin, 2),
            'margin_pct': round(margin_pct, 2),
        }

        if has_tp_sl:
            row['leg_loss'] = round(-leg_loss, 2)
            row['cumul_loss'] = round(-(cumulative_loss + leg_loss), 2)
            row['worst_float'] = round(-worst_float, 2)
            row['tp_profit'] = round(leg_tp_profit, 2)
            row['net_if_tp'] = round(net_if_tp, 2)

        table.append(row)
        cumulative_loss += leg_loss

    return JSONResponse({
        'table': table,
        'has_tp_sl': has_tp_sl,
        'contract_size': contract_size,
        'leverage': round(leverage, 1),
        'price': round(price, 5),
    })


def _estimate_price(symbol: str) -> float:
    """Rough price estimate for margin calculation. Uses recent candle if available."""
    try:
        from qengine.services.db import database
        from qengine.models.Candle import Candle
        import peewee
        if database.is_closed():
            database.open()
        candle = (Candle
                  .select(Candle.close)
                  .where(Candle.symbol == symbol)
                  .order_by(Candle.timestamp.desc())
                  .limit(1)
                  .first())
        if candle and candle.close > 0:
            return candle.close
    except Exception:
        pass

    # Fallback: heuristic from symbol name
    s = symbol.upper()
    if 'XAU' in s:
        return 2000.0
    if 'XAG' in s:
        return 25.0
    if 'JPY' in s:
        return 150.0
    if 'BTC' in s:
        return 60000.0
    return 1.10  # default for major FX pairs

