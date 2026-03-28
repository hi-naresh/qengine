import math
from fastapi import APIRouter, Depends, Body
from fastapi.responses import JSONResponse, FileResponse
import json
from qengine.services import auth as authenticator
from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser
from qengine.services.quota import check_quota, increment_quota
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
def backtest(request_json: BacktestRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """
    Start a backtest process
    """
    jh.validate_cwd()

    allowed, msg = check_quota(current_user.effective_user_id, 'backtest')
    if not allowed:
        return JSONResponse({'message': msg}, status_code=403)

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
        request_json.cost_model,
        current_user.effective_user_id
    )

    increment_quota(current_user.effective_user_id, 'backtest')

    return JSONResponse({'message': 'Started backtesting...'}, status_code=202)


@router.post("/cancel")
def cancel_backtest(request_json: CancelRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """
    Cancel a backtest process
    """

    process_manager.cancel_process(request_json.id)
    
    update_backtest_session_status(request_json.id, 'cancelled')

    return JSONResponse({'message': f'Backtest process with ID of {request_json.id} was requested for termination'},
                        status_code=202)


@router.get("/logs/{session_id}")
def get_logs(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """
    Get logs as text for a specific session. Similar to download but returns text content instead of file.
    """

    try:
        content = get_backtest_logs(session_id)

        if content is None:
            return JSONResponse({'error': 'Log file not found'}, status_code=404)

        return JSONResponse({'content': content}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.get("/download-log/{session_id}")
def download_backtest_log_endpoint(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """
    Download log file for a specific backtest session
    """

    try:
        return download_backtest_log(session_id)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/sessions")
def get_backtest_sessions(request_json: GetBacktestSessionsRequestJson = Body(default=GetBacktestSessionsRequestJson()), current_user: CurrentUser = Depends(get_current_user)):
    """
    Get a list of backtest sessions sorted by most recently updated with pagination
    """
    # Scope to user unless admin (and not impersonating)
    user_id = current_user.effective_user_id if not current_user.is_admin or current_user.is_impersonating else None

    # Get sessions from the database with pagination and filters
    sessions = get_sessions(
        limit=request_json.limit,
        offset=request_json.offset,
        title_search=request_json.title_search,
        status_filter=request_json.status_filter,
        date_filter=request_json.date_filter,
        user_id=user_id,
    )

    # Transform the sessions using the transformer
    transformed_sessions = [get_backtest_session(session) for session in sessions]

    # Add owner labels for admin view
    if not user_id:
        from qengine.services.transformers import enrich_with_owner
        enrich_with_owner(transformed_sessions, sessions)

    return JSONResponse({
        'sessions': transformed_sessions,
        'count': len(transformed_sessions)
    })


@router.post("/sessions/{session_id}")
def get_backtest_session_by_id(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """
    Get a single backtest session by ID
    """

    # Get the session from the database
    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    if not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    # Transform the session using the transformer
    transformed_session = get_backtest_session_for_load_more(session)
    transformed_session = jh.clean_infinite_values(transformed_session)

    return JSONResponse({
        'session': transformed_session
    })


@router.post("/update-state")
def update_session_state(request_json: UpdateBacktestSessionStateRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """
    Update the state of a backtest session
    """

    session = get_backtest_session_by_id_from_db(request_json.id)
    if session and not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    update_backtest_session_state(request_json.id, request_json.state, user_id=current_user.effective_user_id)

    return JSONResponse({
        'message': 'Backtest session state updated successfully'
    })


@router.post("/sessions/{session_id}/remove")
def remove_backtest_session(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """
    Remove a backtest session from the database
    """

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    if not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

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
def update_session_notes(session_id: str, request_json: UpdateBacktestSessionNotesRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """
    Update the notes (title, description, strategy_codes) of a backtest session
    """

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    if not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    update_backtest_session_notes(session_id, request_json.title, request_json.description, request_json.strategy_codes)

    return JSONResponse({
        'message': 'Backtest session notes updated successfully'
    })


@router.post("/purge-sessions")
def purge_sessions(request_json: dict = Body(...), current_user: CurrentUser = Depends(require_admin)):
    """
    Purge backtest sessions older than specified days (admin only)
    """

    days_old = request_json.get('days_old', None)
    
    deleted_count = purge_backtest_sessions(days_old)
    
    return JSONResponse({
        'message': f'Successfully purged {deleted_count} session(s)',
        'deleted_count': deleted_count
    }, status_code=200)


@router.post("/sessions/{session_id}/chart-data")
def get_backtest_session_chart_data(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """
    Get chart data for a specific backtest session
    """

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    if not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    chart_data = jh.clean_infinite_values(json.loads(session.chart_data)) if session.chart_data else None

    return JSONResponse({
        'chart_data': chart_data
    })


@router.post("/sessions/{session_id}/strategy-code")
def get_backtest_session_strategy_codes(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """
    Get strategy codes for a specific backtest session
    """

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    if not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    return JSONResponse({
        'strategy_code': json.loads(session.strategy_codes) if session.strategy_codes else {}
    })


@router.post("/sessions/{session_id}/logs")
def get_backtest_session_logs(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """
    Get backtest logs for a specific session from the database
    """

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    if not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    return JSONResponse({
        'logs': json.loads(session.logs) if session.logs else []
    })


@router.post("/exposure-table")
def compute_exposure_table(request_json: dict = Body(...), current_user: CurrentUser = Depends(get_current_user)):
    """
    Compute a theoretical exposure table from strategy hyperparameters.
    initial_size / base_size = % of equity used as MARGIN for level 0.
    qty = margin * leverage / price  (same formula as the live strategy).

    Request body:
      - exchange: str
      - symbol: str
      - hyperparameters: dict
      - balance: float
    """

    from qengine.core.instruments import instrument_registry
    from qengine.info import exchange_info

    symbol = request_json.get('symbol', '')
    exchange_name = request_json.get('exchange', '')
    hp = request_json.get('hyperparameters') or {}
    balance = float(request_json.get('balance', 10000))

    # Instrument properties
    pip_size = instrument_registry.get_pip_size(symbol)
    contract_size = instrument_registry.get_contract_size(symbol)
    pip_value_per_unit = pip_size  # P&L per unit per pip move

    # Leverage from broker info / instrument margin rate
    broker = exchange_info.get(exchange_name, {})
    leverage = broker.get('default_leverage', 30)
    inst = instrument_registry.get(symbol)
    margin_rate = getattr(inst, 'margin_rate', 0) if inst else 0
    if margin_rate > 0:
        leverage = 1.0 / margin_rate

    # Extract hedging params (support multiple naming conventions)
    # This is % of equity as MARGIN (e.g. 1 = 1% of balance used as margin)
    base_pct = float(hp.get('base_size', hp.get('initial_size', hp.get('lot_size', hp.get('qty', 1.0)))))
    sizing_operator = str(hp.get('sizing_operator', 'multiplier'))
    sizing_factor = float(hp.get('sizing_factor', hp.get('multiplier', hp.get('lot_multiplier', 2.0))))
    max_levels = int(hp.get('max_levels', hp.get('max_orders', 1)))

    # TP and hedge distances in pips (support tp_distance, tp_upper, tp_pips, take_profit_pips)
    tp_pips = float(hp.get('tp_distance', hp.get('tp_upper', hp.get('tp_pips', hp.get('take_profit_pips', 0)))))
    tp_lower = float(hp.get('tp_lower', tp_pips))
    risk_reward = float(hp.get('risk_reward', 0))
    hedge_pips = float(hp.get('hedge_distance', hp.get('hedge_pips', hp.get('sl_pips', hp.get('stop_loss_pips', 0)))))

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

    # Convert % equity (as margin) to units:
    # margin = balance * pct / 100
    # units  = margin * leverage / price
    # This matches the strategy's _base_qty() formula exactly.
    if price > 0:
        base_units = (balance * base_pct / 100.0) * leverage / price
    else:
        base_units = 0

    # Direction alternation
    initial_dir = str(hp.get('direction', 'long')).lower()
    directions = []
    d = initial_dir
    for _ in range(max_levels):
        directions.append(d)
        d = 'short' if d == 'long' else 'long'

    table = []
    cumulative_margin = 0.0

    # Surefire hedge zigzag model:
    # Entries alternate between two price levels on a number line (pips from L0 entry).
    # L0 enters at 0. If L0 is LONG and loses, price drops to -hedge_pips → L1 SHORT enters there.
    # If L1 loses, price rises back to 0 → L2 LONG enters there. And so on.
    # So: even levels enter at 0, odd levels enter at hedge_offset.
    hedge_offset = -hedge_pips if initial_dir == 'long' else hedge_pips

    # Track all open legs: (direction, units, entry_pips)
    open_legs = []

    for level in range(max_levels):
        factor = _sizing_multiplier(level)
        level_pct = base_pct * factor
        level_units = base_units * factor
        level_lots = level_units / contract_size if contract_size > 0 else level_units

        margin_required = level_units * price / leverage if leverage > 0 else level_units * price
        cumulative_margin += margin_required
        margin_pct = (cumulative_margin / balance * 100) if balance > 0 else 0

        direction = directions[level]
        entry_pips = 0.0 if level % 2 == 0 else hedge_offset

        open_legs.append((direction, level_units, entry_pips))

        # Leg loss: this single leg's loss if price moves hedge_pips against it
        leg_loss = level_units * pip_value_per_unit * hedge_pips if pip_value_per_unit > 0 and hedge_pips > 0 else 0

        # --- Won: TP hits at this level, ALL open legs close ---
        # TP is tp_pips in the favorable direction from the current (last) entry.
        tp_profit_all = 0.0
        if has_tp_sl and tp_pips > 0:
            tp_price_pips = entry_pips + (tp_pips if direction == 'long' else -tp_pips)
            for leg_dir, leg_units, leg_entry in open_legs:
                if leg_dir == 'long':
                    pnl_pips = tp_price_pips - leg_entry
                else:
                    pnl_pips = leg_entry - tp_price_pips
                tp_profit_all += leg_units * pip_value_per_unit * pnl_pips

        # --- Bust scenarios: session busts at this level (no more hedges) ---
        # Price moves hedge_pips against the last leg → bust trigger fires.
        # Same-direction legs: all lose hedge_pips each.
        # Opposite-direction legs: at breakeven (their entry = bust trigger price).
        #
        # Two exit choices after bust:
        # 1) "Close all" — close everything at the bust trigger. Opposite at 0.
        # 2) "Opposite TP" — close losing legs, let opposite run to their TP (gain tp_pips each).
        bust_close = 0.0  # close all at hedge trigger
        bust_opp_tp = 0.0  # close losers, opposite hits TP
        if pip_value_per_unit > 0 and hedge_pips > 0:
            for leg_dir, leg_units, leg_entry in open_legs:
                if leg_dir == direction:
                    # Same direction as last leg — loses hedge_pips
                    same_dir_loss = -leg_units * pip_value_per_unit * hedge_pips
                    bust_close += same_dir_loss
                    bust_opp_tp += same_dir_loss
                else:
                    # Opposite direction — breakeven if closed now, or +tp_pips if TP runs
                    bust_opp_tp += leg_units * pip_value_per_unit * tp_pips

        row = {
            'level': level,
            'direction': direction.upper(),
            'equity_pct': round(level_pct, 2),
            'lots': round(level_lots, 4),
            'units': round(level_units, 0),
            'margin': round(margin_required, 2),
            'cumul_margin': round(cumulative_margin, 2),
            'margin_pct': round(margin_pct, 2),
        }

        if has_tp_sl:
            row['leg_loss'] = round(-leg_loss, 2)
            row['won'] = round(tp_profit_all, 2)
            row['bust_close'] = round(bust_close, 2)
            row['bust_opp_tp'] = round(bust_opp_tp, 2)

        table.append(row)

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

