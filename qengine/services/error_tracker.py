"""
Centralized error tracking service.
Captures errors from any part of the system and stores them as ErrorReport records.

Storage strategy (in order of preference):
1. Redis hash (qengine:error_reports) — works from ALL processes including spawned subprocesses
2. PostgreSQL via ErrorReport model — for long-term persistence
3. File-based JSON — last resort when both Redis and DB are unavailable
"""
import json
import os
import sys
import time
import traceback as tb_module
import uuid


# File-based fallback for when both Redis and DB are unavailable
_ERROR_LOG_DIR = 'storage/logs/error-reports'

# Redis key for error reports hash
_REDIS_KEY = 'qengine:error_reports'


def track_error(
    message: str,
    error_type: str = None,
    traceback: str = None,
    session_id: str = None,
    session_type: str = None,
    context: dict = None,
    user_id: str = None,
) -> None:
    """Store an error report. Uses Redis as primary (works from all processes),
    falls back to file if Redis is unavailable."""
    report_id = str(uuid.uuid4())
    now = int(time.time() * 1000)

    # Auto-detect session info if not provided
    if not session_id:
        try:
            from qengine.store import store
            session_id = store.app.session_id
        except Exception:
            pass

    if not session_type:
        session_type = _detect_session_type()

    # Auto-capture traceback if not provided
    if not traceback:
        traceback = tb_module.format_exc()
        if traceback == 'NoneType: None\n':
            traceback = None

    report_data = {
        'id': report_id,
        'session_id': str(session_id) if session_id else None,
        'session_type': session_type,
        'error_type': error_type,
        'message': str(message)[:10000],
        'traceback': traceback,
        'context': json.dumps(context) if isinstance(context, dict) else context,
        'status': 'new',
        'issue_id': None,
        'user_id': str(user_id) if user_id else None,
        'created_at': now,
    }

    # Try Redis first (works from subprocesses too)
    if _store_to_redis(report_data):
        return

    # Try DB
    if _store_to_db(report_data):
        return

    # Last resort: file
    _store_to_file(report_data)


def track_exception(
    exc: Exception,
    session_id: str = None,
    session_type: str = None,
    context: dict = None,
    user_id: str = None,
) -> None:
    """Track an exception object directly."""
    track_error(
        message=str(exc),
        error_type=type(exc).__name__,
        traceback=tb_module.format_exc(),
        session_id=session_id,
        session_type=session_type,
        context=context,
        user_id=user_id,
    )


def get_all_reports(status=None, session_type=None, limit=50, offset=0, user_id=None):
    """Get all error reports from ALL sources (DB + Redis + files).
    Always combines all sources and deduplicates by ID to ensure nothing is missed."""
    # Try to flush unflushed reports into DB first (best-effort)
    _flush_redis_to_db()
    _flush_files_to_db()

    # Collect reports from all sources, deduplicate by ID
    seen_ids = set()
    all_reports = []

    # 1. DB reports (most authoritative — already flushed + have updated statuses)
    db_count = 0
    try:
        from qengine.models.ErrorReport import ErrorReport
        _ensure_db_connection()

        query = ErrorReport.select().order_by(ErrorReport.created_at.desc())
        for r in query:
            d = r.to_dict()
            if d['id'] not in seen_ids:
                seen_ids.add(d['id'])
                all_reports.append(d)
                db_count += 1
    except Exception as e:
        print(f"[ERROR_TRACKER] DB read failed: {e}", file=sys.stderr)

    # 2. Redis reports (may not have been flushed to DB)
    redis_count = 0
    for r in _get_redis_reports():
        rid = r.get('id')
        if rid and rid not in seen_ids:
            seen_ids.add(rid)
            all_reports.append(r)
            redis_count += 1

    # 3. File reports (may not have been flushed to DB or Redis)
    file_count = 0
    for r in _get_file_reports():
        rid = r.get('id')
        if rid and rid not in seen_ids:
            seen_ids.add(rid)
            all_reports.append(r)
            file_count += 1

    print(f"[ERROR_TRACKER] get_all_reports: db={db_count}, redis={redis_count}, files={file_count}, total={len(all_reports)}", file=sys.stderr)

    # Sort by created_at descending
    all_reports.sort(key=lambda r: r.get('created_at', 0), reverse=True)

    # Apply filters
    if status:
        all_reports = [r for r in all_reports if r.get('status') == status]
    if session_type:
        all_reports = [r for r in all_reports if r.get('session_type') == session_type]
    if user_id:
        all_reports = [r for r in all_reports if r.get('user_id') in (str(user_id), None)]

    total = len(all_reports)
    reports = all_reports[offset:offset + limit]
    return reports, total


def get_report_count(status='new', user_id=None):
    """Get count of error reports with given status from ALL sources."""
    # Try to flush first (best-effort)
    _flush_redis_to_db()
    _flush_files_to_db()

    seen_ids = set()
    count = 0

    # 1. Count from DB
    try:
        from qengine.models.ErrorReport import ErrorReport
        _ensure_db_connection()
        query = ErrorReport.select().where(ErrorReport.status == status)
        if user_id:
            query = query.where(
                (ErrorReport.user_id == user_id) | (ErrorReport.user_id.is_null())
            )
        for r in query:
            seen_ids.add(str(r.id))
            count += 1
    except Exception as e:
        print(f"[ERROR_TRACKER] DB count failed: {e}", file=sys.stderr)

    # 2. Count from Redis (unflushed)
    for r in _get_redis_reports():
        rid = r.get('id')
        if rid and rid not in seen_ids and r.get('status') == status:
            if user_id and r.get('user_id') not in (str(user_id), None):
                continue
            seen_ids.add(rid)
            count += 1

    # 3. Count from files (unflushed)
    for r in _get_file_reports():
        rid = r.get('id')
        if rid and rid not in seen_ids and r.get('status', 'new') == status:
            if user_id and r.get('user_id') not in (str(user_id), None):
                continue
            seen_ids.add(rid)
            count += 1

    return count


def ensure_table():
    """Ensure the ErrorReport table exists. Call at startup."""
    try:
        _ensure_db_connection()
        from qengine.models.ErrorReport import ErrorReport
        ErrorReport.create_table(safe=True)
    except Exception as e:
        print(f"[ERROR_TRACKER] Could not create ErrorReport table: {e}", file=sys.stderr)


# ── Redis storage ──

def _store_to_redis(report_data: dict) -> bool:
    """Store report to Redis hash. Returns True on success."""
    try:
        from qengine.services.redis import sync_redis
        if sync_redis is None:
            return False
        sync_redis.hset(_REDIS_KEY, report_data['id'], json.dumps(report_data))
        return True
    except Exception as e:
        print(f"[ERROR_TRACKER] Redis store failed: {e}", file=sys.stderr)
        return False


def _get_redis_reports() -> list:
    """Read all reports from Redis hash."""
    try:
        from qengine.services.redis import sync_redis
        if sync_redis is None:
            return []
        raw = sync_redis.hgetall(_REDIS_KEY)
        reports = []
        for _key, val in raw.items():
            try:
                data = json.loads(val)
                # Parse context
                ctx = data.get('context')
                if isinstance(ctx, str):
                    try:
                        ctx = json.loads(ctx)
                    except Exception:
                        pass
                    data['context'] = ctx
                reports.append(data)
            except Exception:
                pass
        return reports
    except Exception as e:
        print(f"[ERROR_TRACKER] Redis read failed: {e}", file=sys.stderr)
        return []


def _update_redis_report(report_id: str, updates: dict) -> bool:
    """Update a report in Redis hash."""
    try:
        from qengine.services.redis import sync_redis
        if sync_redis is None:
            return False
        raw = sync_redis.hget(_REDIS_KEY, report_id)
        if not raw:
            return False
        data = json.loads(raw)
        data.update(updates)
        sync_redis.hset(_REDIS_KEY, report_id, json.dumps(data))
        return True
    except Exception:
        return False


def _delete_redis_report(report_id: str) -> bool:
    """Delete a report from Redis hash."""
    try:
        from qengine.services.redis import sync_redis
        if sync_redis is None:
            return False
        sync_redis.hdel(_REDIS_KEY, report_id)
        return True
    except Exception:
        return False


def _flush_redis_to_db() -> int:
    """Move Redis reports into DB. Returns count of flushed reports."""
    count = 0
    try:
        from qengine.services.redis import sync_redis
        if sync_redis is None:
            return 0
        raw = sync_redis.hgetall(_REDIS_KEY)
        if not raw:
            return 0

        for report_id, val in raw.items():
            try:
                data = json.loads(val)
                if _store_to_db(data):
                    # Remove from Redis after successful DB insert
                    sync_redis.hdel(_REDIS_KEY, report_id)
                    count += 1
            except Exception:
                pass
    except Exception as e:
        print(f"[ERROR_TRACKER] Redis→DB flush failed: {e}", file=sys.stderr)
    return count


# ── DB storage ──

def _ensure_db_connection():
    """Ensure DB connection is alive, reconnecting if needed."""
    try:
        from qengine.services.db import database
        if database.db is not None and database.db.is_closed():
            # Connection is stale — reconnect the existing db object
            # (don't create a new one, or Peewee models with Meta.database = database.db
            #  would still reference the old object)
            try:
                database.db.connect()
            except Exception:
                # If reconnect fails, force full reconnect
                database.db = None
                database.open_connection()
                # Rebind ErrorReport to new db object
                try:
                    from qengine.models.ErrorReport import ErrorReport
                    ErrorReport._meta.database = database.db
                except Exception:
                    pass
        elif database.db is None:
            database.open_connection()
    except Exception:
        pass


def _store_to_db(report_data: dict) -> bool:
    """Try to store to DB. Returns True on success."""
    try:
        from qengine.models.ErrorReport import ErrorReport
        _ensure_db_connection()

        # Check if already exists (avoid duplicates from flush)
        try:
            ErrorReport.get_by_id(report_data['id'])
            return True  # Already exists
        except Exception:
            pass

        ErrorReport.create(
            id=report_data['id'],
            session_id=report_data.get('session_id'),
            session_type=report_data.get('session_type'),
            error_type=report_data.get('error_type'),
            message=report_data.get('message', '')[:10000],
            traceback=report_data.get('traceback'),
            context=report_data.get('context') if isinstance(report_data.get('context'), str) else (
                json.dumps(report_data['context']) if isinstance(report_data.get('context'), dict) else None
            ),
            status=report_data.get('status', 'new'),
            issue_id=report_data.get('issue_id'),
            user_id=report_data.get('user_id'),
            created_at=report_data.get('created_at', int(time.time() * 1000)),
        )
        return True
    except Exception as e:
        # Only print if it's not an import error in subprocess
        if 'peewee' not in str(type(e).__module__):
            print(f"[ERROR_TRACKER] DB store failed: {e}", file=sys.stderr)
        return False


# ── File storage (last resort) ──

def _store_to_file(report_data: dict):
    """Fallback: store to JSON file."""
    try:
        os.makedirs(_ERROR_LOG_DIR, exist_ok=True)
        fpath = os.path.join(_ERROR_LOG_DIR, f"{report_data['created_at']}_{report_data['id'][:8]}.json")
        with open(fpath, 'w') as f:
            json.dump(report_data, f)
    except Exception as e:
        print(f"[ERROR_TRACKER] File store also failed: {e}", file=sys.stderr)


def _get_file_reports() -> list:
    """Read any file-based reports."""
    reports = []
    try:
        if not os.path.exists(_ERROR_LOG_DIR):
            return []
        for fname in sorted(os.listdir(_ERROR_LOG_DIR), reverse=True):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(_ERROR_LOG_DIR, fname)
            try:
                with open(fpath, 'r') as f:
                    data = json.load(f)
                ctx = data.get('context')
                if isinstance(ctx, str):
                    try:
                        ctx = json.loads(ctx)
                    except Exception:
                        pass
                    data['context'] = ctx
                reports.append(data)
            except Exception:
                pass
    except Exception:
        pass
    return reports


def _flush_files_to_db() -> int:
    """Move file-based reports into DB. Returns count of flushed reports."""
    count = 0
    try:
        if not os.path.exists(_ERROR_LOG_DIR):
            return 0
        for fname in os.listdir(_ERROR_LOG_DIR):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(_ERROR_LOG_DIR, fname)
            try:
                with open(fpath, 'r') as f:
                    data = json.load(f)
                if _store_to_db(data):
                    os.remove(fpath)
                    count += 1
            except Exception:
                pass
    except Exception:
        pass
    return count


# Kept for backward compatibility
def flush_file_reports_to_db():
    return _flush_files_to_db()

def get_file_reports():
    return _get_file_reports()


def _detect_session_type() -> str:
    """Auto-detect the current session type from app mode."""
    try:
        import qengine.helpers as jh
        if jh.is_live():
            return 'live'
        if jh.is_backtesting():
            return 'backtest'
        if jh.is_optimizing():
            return 'optimization'
        mode = jh.app_mode()
        if 'monte' in mode:
            return 'monte-carlo'
        return mode or 'system'
    except Exception:
        return 'system'
