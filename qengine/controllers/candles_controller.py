from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse
from qengine.repositories import candle_repository
from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser
from qengine.services.multiprocessing import process_manager
from qengine.services.web import ImportCandlesRequestJson, CancelRequestJson, GetCandlesRequestJson, DeleteCandlesRequestJson
import qengine.helpers as jh

router = APIRouter(prefix="/candles", tags=["Candles"])


@router.post("/import")
def import_candles(request_json: ImportCandlesRequestJson, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """
    Import candles for a specific exchange and symbol
    """
    jh.validate_cwd()

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
def cancel_import_candles(request_json: CancelRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """
    Cancel an import candles process
    """
    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Candles process with ID of {request_json.id} was requested for termination'},
                        status_code=202)


@router.post("/clear-cache")
def clear_candles_database_cache(current_user: CurrentUser = Depends(require_admin)):
    """
    Clear the candles database cache
    """
    from qengine.services.cache import cache
    cache.flush()

    return JSONResponse({
        'status': 'success',
        'message': 'Candles database cache cleared successfully',
    }, status_code=200)


@router.post("/get")
def get_candles(json_request: GetCandlesRequestJson, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """
    Get candles for a specific exchange, symbol, and timeframe
    """
    jh.validate_cwd()

    from qengine.modes.data_provider import get_candles as gc

    arr = gc(json_request.exchange, json_request.symbol, json_request.timeframe)

    return JSONResponse({
        'id': json_request.id,
        'data': arr
    }, status_code=200)


@router.post("/existing")
def get_existing_candles(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """
    Get all existing candles in the database
    """
    try:
        data = candle_repository.get_existing_candles()
        return JSONResponse({'data': data}, status_code=200)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/delete")
def delete_candles(json_request: DeleteCandlesRequestJson, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """
    Delete candles for a specific exchange and symbol
    """
    try:
        candle_repository.delete_candles_from_db(json_request.exchange, json_request.symbol)
        return JSONResponse({'message': 'Candles deleted successfully'}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/delete-all")
def delete_all_candles(current_user: CurrentUser = Depends(require_admin)) -> JSONResponse:
    """
    Delete ALL imported candle data from the database.
    """
    try:
        from qengine.models.Candle import Candle
        count = Candle.select().count()
        Candle.delete().execute()
        return JSONResponse({'message': f'Deleted all candle data ({count:,} candles)', 'deleted': count}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)
