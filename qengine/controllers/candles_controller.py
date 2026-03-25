from typing import Optional
from fastapi import APIRouter, Header
from starlette.responses import JSONResponse
from qengine.repositories import candle_repository
from qengine.services import auth as authenticator
from qengine.services.multiprocessing import process_manager
from qengine.services.web import ImportCandlesRequestJson, CancelRequestJson, GetCandlesRequestJson, DeleteCandlesRequestJson
import qengine.helpers as jh

router = APIRouter(prefix="/candles", tags=["Candles"])


@router.post("/import")
def import_candles(request_json: ImportCandlesRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Import candles for a specific exchange and symbol
    """
    jh.validate_cwd()

    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from qengine.modes import import_candles_mode

    process_manager.add_task(
        import_candles_mode.run,
        request_json.id,
        request_json.exchange,
        request_json.symbol,
        request_json.start_date,
        'candles',   # mode
        True,        # running_via_dashboard
        False,       # show_progressbar
        request_json.granularity,  # granularity
    )

    return JSONResponse({'message': 'Started importing candles...'}, status_code=202)


@router.post("/cancel-import")
def cancel_import_candles(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    """
    Cancel an import candles process
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Candles process with ID of {request_json.id} was requested for termination'},
                        status_code=202)


@router.post("/clear-cache")
def clear_candles_database_cache(authorization: Optional[str] = Header(None)):
    """
    Clear the candles database cache
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from qengine.services.cache import cache
    cache.flush()

    return JSONResponse({
        'status': 'success',
        'message': 'Candles database cache cleared successfully',
    }, status_code=200)


@router.post("/get")
def get_candles(json_request: GetCandlesRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get candles for a specific exchange, symbol, and timeframe
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    jh.validate_cwd()

    from qengine.modes.data_provider import get_candles as gc

    arr = gc(json_request.exchange, json_request.symbol, json_request.timeframe)

    return JSONResponse({
        'id': json_request.id,
        'data': arr
    }, status_code=200)


@router.post("/existing")
def get_existing_candles(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get all existing candles in the database
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    try:
        data = candle_repository.get_existing_candles()
        return JSONResponse({'data': data}, status_code=200)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/delete")
def delete_candles(json_request: DeleteCandlesRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Delete candles for a specific exchange and symbol
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        candle_repository.delete_candles_from_db(json_request.exchange, json_request.symbol)
        return JSONResponse({'message': 'Candles deleted successfully'}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/delete-all")
def delete_all_candles(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Delete ALL imported candle data from the database.
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        from qengine.models.Candle import Candle
        count = Candle.select().count()
        Candle.delete().execute()
        return JSONResponse({'message': f'Deleted all candle data ({count:,} candles)', 'deleted': count}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)
