from typing import Optional
from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from qengine.services import auth as authenticator
from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser
from qengine.services.quota import check_quota, increment_quota
from qengine.services.multiprocessing import process_manager
from qengine.services.web import (
    LiveRequestJson,
    LiveCancelRequestJson,
    GetLogsRequestJson,
    GetOrdersRequestJson,
    GetLiveSessionsRequestJson,
    UpdateLiveSessionNotesRequestJson,
    UpdateLiveSessionStateRequestJson
)
import qengine.helpers as jh
from qengine.repositories import live_session_repository
from qengine.services import transformers
from qengine.enums import live_session_statuses, live_session_modes, brokers

# Broker IDs that are demo/paper environments
_DEMO_BROKER_IDS = {brokers.OANDA_DEMO, brokers.IG_MARKETS_DEMO, brokers.IBKR_PAPER}

router = APIRouter(prefix="/live", tags=["Live Trading"])


def _is_demo_broker(exchange: str) -> bool:
    return exchange in _DEMO_BROKER_IDS


@router.post("")
def live(request_json: LiveRequestJson, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    allowed, msg = check_quota(current_user.effective_user_id, 'live')
    if not allowed:
        return JSONResponse({'message': msg}, status_code=403)

    jh.validate_cwd()

    # Infer paper/live mode from the broker ID — demo brokers always run in paper mode
    is_paper = _is_demo_broker(request_json.exchange)
    if request_json.paper_mode is not None:
        is_paper = request_json.paper_mode
    trading_mode = live_session_modes.PAPERTRADE if is_paper else live_session_modes.LIVETRADE

    live_session_repository.store_live_session(
        id=request_json.id,
        status=live_session_statuses.STARTING,
        session_mode=trading_mode,
        exchange=request_json.exchange,
        state={
            'form': {
                'debug_mode': request_json.debug_mode,
                'paper_mode': is_paper,
                'exchange': request_json.exchange,
                'exchange_api_key_id': request_json.exchange_api_key_id,
                'notification_api_key_id': request_json.notification_api_key_id,
                'routes': request_json.routes,
                'data_routes': request_json.data_routes,
                'hyperparameters': request_json.hyperparameters,
                'pipelines': request_json.pipelines,
            }
        },
        user_id=current_user.effective_user_id,
    )

    live_config = request_json.config
    if request_json.pipelines:
        live_config['pipelines'] = request_json.pipelines

    from qengine.modes import live_mode
    process_manager.add_task(
        live_mode.run,
        request_json.id,
        request_json.debug_mode,
        request_json.exchange,
        request_json.exchange_api_key_id,
        request_json.notification_api_key_id,
        live_config,
        request_json.routes,
        request_json.data_routes,
        trading_mode,
        request_json.hyperparameters,
        current_user.effective_user_id,
    )

    increment_quota(current_user.effective_user_id, 'live')

    mode = 'paper' if is_paper else 'live'
    return JSONResponse({'message': f"Started {mode} trading..."}, status_code=202)


@router.post("/cancel")
def cancel_live(request_json: LiveCancelRequestJson, current_user: CurrentUser = Depends(get_current_user)):

    session = live_session_repository.get_live_session_by_id(request_json.id)
    if session and not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    # Mark as stopping immediately so frontend sees the state change
    live_session_repository.update_live_session_status(request_json.id, live_session_statuses.STOPPING)

    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Stopping session {request_json.id}... closing positions and cancelling orders.'}, status_code=200)


@router.post('/logs')
def get_logs(json_request: GetLogsRequestJson, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:

    from qengine.modes.live_mode import get_live_logs
    arr = get_live_logs(json_request.id, json_request.type, json_request.start_time)

    return JSONResponse({
        'id': json_request.id,
        'data': arr
    }, status_code=200)


@router.post('/orders')
def get_orders(json_request: GetOrdersRequestJson, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:

    from qengine.modes.live_mode import get_live_orders
    arr = get_live_orders(json_request.session_id)

    return JSONResponse({
        'id': json_request.id,
        'data': arr
    }, status_code=200)


@router.post('/positions')
def get_positions(json_request: dict = Body(...), current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:

    session_id = json_request.get('session_id', json_request.get('id', ''))
    from qengine.modes.live_mode import get_live_positions
    arr = get_live_positions(session_id)

    return JSONResponse({
        'id': session_id,
        'data': arr
    }, status_code=200)


@router.get('/state/{session_id}')
def get_session_state(session_id: str, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Get comprehensive live session state (account, positions, orders, strategies)."""

    from qengine.modes.live_mode import get_live_state
    state = get_live_state(session_id)

    # Also get session metadata from DB
    session = live_session_repository.get_live_session_by_id(session_id)
    if session and not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)
    meta = {}
    if session:
        t = transformers.get_live_session(session)
        meta = {
            'id': t['id'],
            'status': t['status'],
            'is_active': t['is_active'],
            'mode': t['session_mode'],
            'exchange': t['exchange'],
            'created_at': t['created_at'],
            'title': t.get('title', ''),
            'routes': t.get('state', {}).get('form', {}).get('routes', []) if t.get('state') else [],
        }

    return JSONResponse({
        'meta': meta,
        'state': state,
    }, status_code=200)


@router.get('/report/{session_id}')
def get_session_report(session_id: str, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Get post-execution analysis report for a completed session."""

    session = live_session_repository.get_live_session_by_id(session_id)
    if session and not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    from qengine.modes.live_mode import get_session_report as _get_report
    report = _get_report(session_id)

    return JSONResponse({'data': report}, status_code=200)


@router.post("/sessions")
def get_live_sessions(
    request_json: GetLiveSessionsRequestJson = Body(default=GetLiveSessionsRequestJson()),
    current_user: CurrentUser = Depends(get_current_user)
):

    # Admins see all sessions (unless impersonating); regular users see only their own
    user_id = current_user.effective_user_id if not current_user.is_admin or current_user.is_impersonating else None

    sessions = live_session_repository.get_live_sessions(
        limit=request_json.limit,
        offset=request_json.offset,
        title_search=request_json.title_search,
        status_filter=request_json.status_filter,
        date_filter=request_json.date_filter,
        mode_filter=request_json.mode_filter,
        user_id=user_id,
    )

    transformed_sessions = [transformers.get_live_session(session) for session in sessions]

    # Add owner labels for admin view
    if not user_id:
        transformers.enrich_with_owner(transformed_sessions, sessions)

    return JSONResponse({
        'sessions': transformed_sessions,
        'count': len(transformed_sessions)
    })


@router.post("/sessions/{session_id}")
def get_live_session_by_id(session_id: str, current_user: CurrentUser = Depends(get_current_user)):

    session = live_session_repository.get_live_session_by_id(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    if session and not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    transformed_session = transformers.get_live_session(session)

    return JSONResponse({
        'session': transformed_session
    })


@router.post("/sessions/{session_id}/remove")
def remove_live_session(session_id: str, current_user: CurrentUser = Depends(get_current_user)):

    session = live_session_repository.get_live_session_by_id(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    if not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    result = live_session_repository.delete_live_session(session_id)

    if not result:
        return JSONResponse({
            'error': f'Failed to delete session with ID {session_id}'
        }, status_code=500)

    return JSONResponse({
        'message': 'Live session removed successfully'
    })


@router.post("/sessions/{session_id}/notes")
def update_session_notes(
    session_id: str,
    request_json: UpdateLiveSessionNotesRequestJson,
    current_user: CurrentUser = Depends(get_current_user)
):

    session = live_session_repository.get_live_session_by_id(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    if not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    live_session_repository.update_live_session_notes(
        session_id,
        request_json.title,
        request_json.description,
        request_json.strategy_codes
    )

    return JSONResponse({
        'message': 'Live session notes updated successfully'
    })


@router.post("/update-state")
def update_state(request_json: UpdateLiveSessionStateRequestJson, current_user: CurrentUser = Depends(get_current_user)):

    session = live_session_repository.get_live_session_by_id(request_json.id)
    if session and not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    live_session_repository.upsert_live_session_state(request_json.id, request_json.state)

    return JSONResponse({
        'message': 'Live session state updated successfully'
    }, status_code=200)


@router.post("/purge-sessions")
def purge_sessions(request_json: dict = Body(...), current_user: CurrentUser = Depends(require_admin)):

    days_old = request_json.get('days_old', None)

    deleted_count = live_session_repository.purge_live_sessions(days_old)

    return JSONResponse({
        'message': f'Successfully purged {deleted_count} session(s)',
        'deleted_count': deleted_count
    }, status_code=200)


@router.get("/equity-curve")
def get_equity_curve(
    session_id: str,
    from_ms: Optional[int] = None,
    to_ms: Optional[int] = None,
    timeframe: str = 'auto',
    max_points: int = 1000,
    current_user: CurrentUser = Depends(get_current_user)
) -> JSONResponse:

    from qengine.repositories import live_equity_repository

    session = live_session_repository.get_live_session_by_id(session_id)
    if session and not current_user.is_admin:
        if str(session.user_id) != current_user.effective_user_id:
            return JSONResponse({'error': 'Not found'}, status_code=404)

    try:
        if from_ms is None:
            if session and getattr(session, 'created_at', None):
                from_ms = session.created_at
            else:
                from_ms = jh.now(True) - (24 * 60 * 60 * 1000)

        result = live_equity_repository.query_equity_curve(
            session_id=session_id,
            from_ms=from_ms,
            to_ms=to_ms,
            timeframe=timeframe,
            max_points=max_points
        )

        return JSONResponse(result, status_code=200)
    except Exception as e:
        return JSONResponse({
            'message': f'Error fetching equity curve: {str(e)}'
        }, status_code=500)
