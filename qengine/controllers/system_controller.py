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


@router.get("/db-storage")
def db_storage(current_user: CurrentUser = Depends(require_admin)) -> JSONResponse:
    """Comprehensive PostgreSQL storage analytics: total, per-table, per-user."""
    from qengine.services.db import database
    from qengine.services.env import ENV_VALUES

    db = database.db
    storage_limit_mb = int(ENV_VALUES.get('DB_STORAGE_LIMIT_MB', '500'))

    try:
        # Total database size
        cursor = db.execute_sql(
            "SELECT pg_database_size(current_database())"
        )
        total_bytes = cursor.fetchone()[0]

        # Per-table sizes (only app tables, not pg_ internal)
        cursor = db.execute_sql("""
            SELECT
                tablename,
                pg_total_relation_size(quote_ident(tablename)) as total_size,
                pg_relation_size(quote_ident(tablename)) as data_size,
                (SELECT count(*) FROM information_schema.columns c WHERE c.table_name = t.tablename) as col_count
            FROM pg_tables t
            WHERE schemaname = 'public'
            ORDER BY total_size DESC
        """)
        tables = []
        for row in cursor.fetchall():
            tables.append({
                'name': row[0],
                'total_bytes': row[1],
                'data_bytes': row[2],
                'index_bytes': row[1] - row[2],
            })

        # Row counts for key tables (fast estimate via pg_stat)
        cursor = db.execute_sql("""
            SELECT relname, n_live_tup
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            ORDER BY n_live_tup DESC
        """)
        row_counts = {r[0]: r[1] for r in cursor.fetchall()}
        for t in tables:
            t['rows'] = row_counts.get(t['name'], 0)

        # Per-user storage (for user-scoped tables)
        user_scoped_tables = [
            'backtestsession', 'livesession', 'optimizationsession',
            'montecarlosession', 'closedtrade', 'order',
            'liveequitysnapshot', 'issue', 'issuecomment',
            'exchangeapikeys', 'notificationapikeys', 'opentab', 'option'
        ]

        # Build UNION query for per-user row counts across all scoped tables
        union_parts = []
        for tbl in user_scoped_tables:
            # Check table exists
            exists = db.execute_sql(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                (tbl,)
            ).fetchone()
            if exists:
                # Check if user_id column exists
                has_uid = db.execute_sql(
                    "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name='user_id'",
                    (tbl,)
                ).fetchone()
                if has_uid:
                    union_parts.append(
                        f"SELECT user_id, '{tbl}' as tbl, count(*) as cnt FROM \"{tbl}\" WHERE user_id IS NOT NULL GROUP BY user_id"
                    )

        per_user = {}
        if union_parts:
            query = " UNION ALL ".join(union_parts)
            cursor = db.execute_sql(f"SELECT user_id, tbl, cnt FROM ({query}) sub ORDER BY user_id")
            for row in cursor.fetchall():
                uid = str(row[0])
                if uid not in per_user:
                    per_user[uid] = {'total_rows': 0, 'tables': {}}
                per_user[uid]['tables'][row[1]] = row[2]
                per_user[uid]['total_rows'] += row[2]

        # Resolve usernames and roles
        if per_user:
            from qengine.models.User import User
            users_q = User.select(User.id, User.username, User.role).where(User.id.in_(list(per_user.keys())))
            user_map = {str(u.id): u for u in users_q}
            for uid, data in per_user.items():
                u = user_map.get(uid)
                data['username'] = u.username if u else 'unknown'
                data['role'] = u.role if u else 'unknown'

        # Candle data size (shared, not per-user)
        candle_size = 0
        candle_rows = 0
        for t in tables:
            if t['name'] == 'candle':
                candle_size = t['total_bytes']
                candle_rows = t['rows']
                break

        return JSONResponse({
            'data': {
                'total_bytes': total_bytes,
                'storage_limit_mb': storage_limit_mb,
                'usage_percent': round((total_bytes / (storage_limit_mb * 1024 * 1024)) * 100, 1),
                'tables': tables,
                'per_user': per_user,
                'candle_bytes': candle_size,
                'candle_rows': candle_rows,
            }
        }, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


class FlushDataRequestJson(BaseModel):
    target: str  # 'user_sessions', 'candles', 'all_sessions', 'table'
    user_id: str = None
    table_name: str = None
    older_than_days: int = None


@router.post("/flush-data")
def flush_data(json_request: FlushDataRequestJson,
               current_user: CurrentUser = Depends(require_admin)) -> JSONResponse:
    """Flush heavyweight data: user sessions, candles, or specific tables."""
    from qengine.services.db import database
    import time

    db = database.db
    target = json_request.target
    deleted = 0

    try:
        age_filter = ""
        age_params = []
        if json_request.older_than_days and json_request.older_than_days > 0:
            cutoff_ms = int((time.time() - json_request.older_than_days * 86400) * 1000)
            age_filter = " AND created_at < %s"
            age_params = [cutoff_ms]

        if target == 'user_sessions':
            if not json_request.user_id:
                return JSONResponse({'error': 'user_id required'}, status_code=400)
            session_tables = ['backtestsession', 'optimizationsession', 'montecarlosession']
            result_tables = ['closedtrade', 'order']
            for tbl in session_tables + result_tables:
                cursor = db.execute_sql(
                    f"DELETE FROM \"{tbl}\" WHERE user_id = %s" + age_filter,
                    [json_request.user_id] + age_params
                )
                deleted += cursor.rowcount
            # Also clean liveequitysnapshot
            cursor = db.execute_sql(
                f"DELETE FROM liveequitysnapshot WHERE user_id = %s" + age_filter,
                [json_request.user_id] + age_params
            )
            deleted += cursor.rowcount

        elif target == 'all_sessions':
            session_tables = ['backtestsession', 'optimizationsession', 'montecarlosession',
                              'closedtrade', 'order', 'liveequitysnapshot']
            for tbl in session_tables:
                if age_filter:
                    cursor = db.execute_sql(f"DELETE FROM \"{tbl}\" WHERE 1=1" + age_filter, age_params)
                else:
                    cursor = db.execute_sql(f"TRUNCATE \"{tbl}\"")
                deleted += cursor.rowcount if age_filter else 0

        elif target == 'candles':
            cursor = db.execute_sql("SELECT count(*) FROM candle")
            count = cursor.fetchone()[0]
            db.execute_sql("TRUNCATE candle")
            deleted = count

        elif target == 'table':
            if not json_request.table_name:
                return JSONResponse({'error': 'table_name required'}, status_code=400)
            # Safety: only allow known tables
            allowed = {'backtestsession', 'optimizationsession', 'montecarlosession',
                       'closedtrade', 'order', 'liveequitysnapshot', 'candle',
                       'opentab', 'option'}
            if json_request.table_name not in allowed:
                return JSONResponse({'error': f'Cannot flush table: {json_request.table_name}'}, status_code=400)
            cursor = db.execute_sql(f"SELECT count(*) FROM \"{json_request.table_name}\"")
            count = cursor.fetchone()[0]
            db.execute_sql(f"TRUNCATE \"{json_request.table_name}\"")
            deleted = count

        else:
            return JSONResponse({'error': f'Unknown target: {target}'}, status_code=400)

        # Run VACUUM to reclaim space
        old_autocommit = db.autocommit
        db.set_autocommit(True)
        try:
            db.execute_sql("VACUUM")
        finally:
            db.set_autocommit(old_autocommit)

        from qengine.services.audit_logger import audit
        audit('flush_data', user_id=current_user.id, detail=f'target={target}, deleted={deleted}')

        return JSONResponse({
            'status': 'success',
            'deleted': deleted,
            'message': f'Flushed {deleted} rows. VACUUM run to reclaim space.'
        }, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


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
            resp = http_requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                json={'chat_id': chat_id, 'parse_mode': 'Markdown', 'text': test_msg},
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
    except http_requests.exceptions.Timeout:
        return JSONResponse({'status': 'error', 'message': 'Request timed out - service may be down'}, status_code=400)
    except http_requests.exceptions.ConnectionError:
        return JSONResponse({'status': 'error', 'message': 'Connection error - check your credentials/webhook URL'}, status_code=400)
    except http_requests.exceptions.RequestException as e:
        return JSONResponse({'status': 'error', 'message': f'Request failed: {e}'}, status_code=400)
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=500)
