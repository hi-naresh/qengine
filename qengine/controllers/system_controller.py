import os
import shutil
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from qengine.services import auth as authenticator
from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser
from qengine.services.web import FeedbackRequestJson, ReportExceptionRequestJson, HelpSearchRequestJson
from qengine.services.multiprocessing import process_manager
import qengine.helpers as jh

router = APIRouter(prefix="/system", tags=["System"])


class TestNotificationRequestJson(BaseModel):
    driver: str
    fields: dict


@router.post("/feedback")
def feedback(json_request: FeedbackRequestJson, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """
    Send feedback to the QEngine team
    """
    from qengine.services import upstream_api
    return upstream_api.feedback(json_request.description, json_request.email)


@router.post("/report-exception")
def report_exception(json_request: ReportExceptionRequestJson,
                     current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """
    Report an exception to the QEngine team
    """
    from qengine.services import upstream_api
    
    return upstream_api.report_exception(
        json_request.description,
        json_request.traceback,
        json_request.mode,
        json_request.attach_logs,
        json_request.session_id,
        json_request.email,
        has_live=jh.has_live_trade_plugin()
    )


@router.post("/general-info")
def general_info(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """
    Get general information about the system
    """
    from qengine.services.general_info import get_general_info

    try:
        data = get_general_info(has_live=jh.has_live_trade_plugin())
    except Exception as e:
        jh.error(str(e))
        return JSONResponse({
            'error': str(e)
        }, status_code=500)

    return JSONResponse(
        data,
        status_code=200
    )


@router.post("/active-workers")
def active_workers(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """
    Get a list of active workers
    """
    return JSONResponse({
        'data': list(process_manager.active_workers)
    }, status_code=200)


@router.post("/help-search")
def help_search(json_request: HelpSearchRequestJson, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """
    Proxy endpoint for help center search to avoid CORS issues
    """
    import requests
    from qengine.info import QENGINE_API_URL
    from qengine.services.auth import get_access_token
    
    try:
        url = f'{QENGINE_API_URL}/help/search?item={json_request.query}'
        
        access_token = get_access_token()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*'
        }
        
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
        
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code == 200:
            return JSONResponse(res.json(), status_code=200)
        else:
            return JSONResponse({
                'error': f'Search request failed with status {res.status_code}'
            }, status_code=res.status_code)
    except Exception as e:
        return JSONResponse({
            'error': str(e)
        }, status_code=500)


@router.post("/clear-cache")
def clear_cache(current_user: CurrentUser = Depends(require_admin)) -> JSONResponse:
    from qengine.services.cache import cache
    cache.flush()

    return JSONResponse({
        'status': 'success',
        'message': 'Pickle cache cleared successfully.'
    }, status_code=200)


@router.post("/flush-redis")
def flush_redis(current_user: CurrentUser = Depends(require_admin)) -> JSONResponse:
    try:
        from qengine.services.redis import sync_redis
        if sync_redis:
            from qengine.services.env import ENV_VALUES
            db_index = int(ENV_VALUES.get('REDIS_DB') or 0)
            sync_redis.flushdb()
            return JSONResponse({
                'status': 'success',
                'message': f'Redis DB {db_index} flushed successfully.'
            }, status_code=200)
        else:
            return JSONResponse({
                'status': 'error',
                'message': 'Redis is not connected.'
            }, status_code=400)
    except Exception as e:
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=500)


@router.post("/clear-logs")
def clear_logs(current_user: CurrentUser = Depends(require_admin)) -> JSONResponse:
    log_dirs = [
        'storage/logs/backtest-mode',
        'storage/logs/optimize-mode',
        'storage/logs/live-mode',
        'storage/logs/collect-mode',
        'storage/logs/monte-carlo-mode',
    ]
    cleared = 0
    for d in log_dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                fp = os.path.join(d, f)
                if os.path.isfile(fp):
                    os.remove(fp)
                    cleared += 1
    # Also clear the misc etc.txt log
    etc_log = 'storage/logs/etc.txt'
    if os.path.isfile(etc_log):
        os.remove(etc_log)
        cleared += 1

    return JSONResponse({
        'status': 'success',
        'message': f'Cleared {cleared} log file(s).'
    }, status_code=200)


@router.get("/storage-info")
def storage_info(current_user: CurrentUser = Depends(require_admin)) -> JSONResponse:
    def dir_size(path):
        total = 0
        if os.path.isdir(path):
            for dirpath, dirnames, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.isfile(fp):
                        total += os.path.getsize(fp)
        return total

    def file_count(path):
        count = 0
        if os.path.isdir(path):
            for dirpath, dirnames, filenames in os.walk(path):
                count += len(filenames)
        return count

    cache_size = dir_size('storage/temp')
    log_size = dir_size('storage/logs')

    # Redis info
    redis_keys = 0
    redis_memory = 'N/A'
    try:
        from qengine.services.redis import sync_redis
        if sync_redis:
            info = sync_redis.info('memory')
            redis_memory = info.get('used_memory_human', 'N/A')
            redis_keys = sync_redis.dbsize()
    except Exception:
        pass

    return JSONResponse({
        'data': {
            'cache_size_bytes': cache_size,
            'cache_files': file_count('storage/temp'),
            'log_size_bytes': log_size,
            'log_files': file_count('storage/logs'),
            'redis_keys': redis_keys,
            'redis_memory': redis_memory,
        }
    }, status_code=200)


@router.post("/test-notification")
def test_notification(json_request: TestNotificationRequestJson,
                      current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    import requests as http_requests

    driver = json_request.driver
    fields = json_request.fields
    test_msg = 'TradeEngine test notification - if you see this, it works!'

    try:
        if driver == 'telegram':
            token = fields.get('bot_token', '')
            chat_id = fields.get('chat_id', '')
            if not token or not chat_id:
                return JSONResponse({'status': 'error', 'message': 'bot_token and chat_id are required'}, status_code=400)
            resp = http_requests.get(
                f'https://api.telegram.org/bot{token}/sendMessage',
                params={'chat_id': chat_id, 'text': test_msg},
                timeout=10
            )
            if resp.status_code // 100 != 2:
                return JSONResponse({'status': 'error', 'message': f'Telegram error: {resp.text}'}, status_code=400)
        elif driver == 'discord':
            webhook = fields.get('webhook', '')
            if not webhook:
                return JSONResponse({'status': 'error', 'message': 'webhook URL is required'}, status_code=400)
            resp = http_requests.post(webhook, json={'content': test_msg}, timeout=10)
            if resp.status_code // 100 != 2:
                return JSONResponse({'status': 'error', 'message': f'Discord error: {resp.text}'}, status_code=400)
        elif driver == 'slack':
            webhook = fields.get('webhook', '')
            if not webhook:
                return JSONResponse({'status': 'error', 'message': 'webhook URL is required'}, status_code=400)
            resp = http_requests.post(webhook, json={'text': test_msg}, timeout=10)
            if resp.status_code // 100 != 2:
                return JSONResponse({'status': 'error', 'message': f'Slack error: {resp.text}'}, status_code=400)
        else:
            return JSONResponse({'status': 'error', 'message': f'Unknown driver: {driver}'}, status_code=400)

        return JSONResponse({'status': 'success', 'message': 'Test notification sent successfully!'}, status_code=200)
    except http_requests.exceptions.ConnectionError:
        return JSONResponse({'status': 'error', 'message': 'Connection error - check your credentials/webhook URL'}, status_code=400)
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)
