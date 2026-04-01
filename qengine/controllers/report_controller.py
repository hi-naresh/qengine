from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from qengine.services.auth_dependency import get_current_user, CurrentUser
import qengine.helpers as jh

router = APIRouter()


class ReportListRequest(BaseModel):
    status: Optional[str] = None  # new, reviewed, submitted, or None for all
    session_type: Optional[str] = None  # backtest, live, optimization, etc.
    limit: int = 50
    offset: int = 0


class ReportDismissRequest(BaseModel):
    id: str


class ReportSubmitIssueRequest(BaseModel):
    id: str
    title: Optional[str] = None
    priority: str = 'high'
    labels: Optional[str] = None


class ReportClearRequest(BaseModel):
    status: Optional[str] = None  # clear by status, or None for all non-submitted
    days_old: Optional[int] = None  # clear older than N days


class ReportBulkDismissRequest(BaseModel):
    ids: Optional[list] = None  # specific IDs, or None for all new


@router.get('/reports/debug')
async def debug_reports():
    """Debug endpoint — no auth required. Visit in browser to verify backend works."""
    import sys
    from qengine.services.error_tracker import _get_redis_reports, _get_file_reports

    redis_reports = _get_redis_reports()
    file_reports = _get_file_reports()

    db_count = 0
    db_error = None
    try:
        from qengine.models.ErrorReport import ErrorReport
        from qengine.services.error_tracker import _ensure_db_connection
        _ensure_db_connection()
        db_count = ErrorReport.select().count()
    except Exception as e:
        db_error = str(e)

    result = {
        'redis_count': len(redis_reports),
        'file_count': len(file_reports),
        'db_count': db_count,
        'db_error': db_error,
        'file_reports': [{'id': r.get('id', '')[:8], 'type': r.get('error_type'), 'msg': r.get('message', '')[:100]} for r in file_reports],
        'redis_reports': [{'id': r.get('id', '')[:8], 'type': r.get('error_type'), 'msg': r.get('message', '')[:100]} for r in redis_reports],
    }
    print(f"[REPORTS DEBUG] {result}", file=sys.stderr)
    return result


@router.post('/reports/list')
async def list_reports(req: ReportListRequest, current_user: CurrentUser = Depends(get_current_user)):
    import sys
    from qengine.services.error_tracker import get_all_reports

    user_id = current_user.effective_user_id if not current_user.is_admin or current_user.is_impersonating else None

    print(f"[REPORTS] /reports/list called: status={req.status}, type={req.session_type}, user_id={user_id}", file=sys.stderr)

    reports, total = get_all_reports(
        status=req.status,
        session_type=req.session_type,
        limit=req.limit,
        offset=req.offset,
        user_id=user_id,
    )

    print(f"[REPORTS] Returning {len(reports)} reports (total={total})", file=sys.stderr)

    return {
        'reports': reports,
        'total': total,
    }


@router.post('/reports/get')
async def get_report(req: ReportDismissRequest, current_user: CurrentUser = Depends(get_current_user)):
    from qengine.models.ErrorReport import ErrorReport

    try:
        report = ErrorReport.get_by_id(req.id)
        return {'status': 'ok', 'report': report.to_dict()}
    except Exception:
        pass

    # Fallback: check Redis
    from qengine.services.error_tracker import _get_redis_reports
    for r in _get_redis_reports():
        if r.get('id') == req.id:
            return {'status': 'ok', 'report': r}

    return {'status': 'error', 'message': 'Report not found'}


@router.post('/reports/dismiss')
async def dismiss_report(req: ReportDismissRequest, current_user: CurrentUser = Depends(get_current_user)):
    # Try DB first
    try:
        from qengine.models.ErrorReport import ErrorReport
        from qengine.services.error_tracker import _ensure_db_connection
        _ensure_db_connection()
        report = ErrorReport.get_by_id(req.id)
        report.status = 'reviewed'
        report.save()
        return {'status': 'ok'}
    except Exception:
        pass

    # Fallback: update in Redis
    from qengine.services.error_tracker import _update_redis_report
    if _update_redis_report(req.id, {'status': 'reviewed'}):
        return {'status': 'ok'}

    return {'status': 'error', 'message': 'Report not found'}


@router.post('/reports/bulk-dismiss')
async def bulk_dismiss(req: ReportBulkDismissRequest, current_user: CurrentUser = Depends(get_current_user)):
    count = 0

    # Try DB
    try:
        from qengine.models.ErrorReport import ErrorReport
        from qengine.services.error_tracker import _ensure_db_connection
        _ensure_db_connection()
        if req.ids:
            count = (ErrorReport.update(status='reviewed')
                     .where(ErrorReport.id.in_(req.ids))
                     .execute())
        else:
            count = (ErrorReport.update(status='reviewed')
                     .where(ErrorReport.status == 'new')
                     .execute())
    except Exception:
        pass

    # Also update in Redis
    from qengine.services.error_tracker import _get_redis_reports, _update_redis_report
    for r in _get_redis_reports():
        if req.ids:
            if r.get('id') in req.ids and r.get('status') != 'reviewed':
                _update_redis_report(r['id'], {'status': 'reviewed'})
                count += 1
        else:
            if r.get('status') == 'new':
                _update_redis_report(r['id'], {'status': 'reviewed'})
                count += 1

    return {'status': 'ok', 'dismissed': count}


@router.post('/reports/submit-issue')
async def submit_as_issue(req: ReportSubmitIssueRequest, current_user: CurrentUser = Depends(get_current_user)):
    from qengine.services.error_tracker import _ensure_db_connection
    _ensure_db_connection()

    # Get report from DB or Redis
    report_dict = None
    report_obj = None
    try:
        from qengine.models.ErrorReport import ErrorReport
        report_obj = ErrorReport.get_by_id(req.id)
        report_dict = report_obj.to_dict()
    except Exception:
        from qengine.services.error_tracker import _get_redis_reports
        for r in _get_redis_reports():
            if r.get('id') == req.id:
                report_dict = r
                break

    if not report_dict:
        return {'status': 'error', 'message': 'Report not found'}

    from qengine.models.Issue import Issue
    import uuid

    now = jh.now_to_timestamp()

    # Build issue description from error report
    description = f"**Error Type:** `{report_dict.get('error_type') or 'Unknown'}`\n"
    description += f"**Session Type:** {report_dict.get('session_type') or 'N/A'}\n"
    if report_dict.get('session_id'):
        description += f"**Session ID:** `{report_dict['session_id']}`\n"
    description += f"\n**Error Message:**\n```\n{report_dict.get('message', '')}\n```\n"
    if report_dict.get('traceback'):
        description += f"\n**Traceback:**\n```\n{report_dict['traceback']}\n```\n"
    if report_dict.get('context'):
        ctx = report_dict['context']
        if isinstance(ctx, dict):
            import json
            ctx = json.dumps(ctx, indent=2)
        description += f"\n**Context:**\n```json\n{ctx}\n```\n"

    title = req.title or f"[{report_dict.get('error_type') or 'Error'}] {report_dict.get('message', '')[:100]}"
    labels = req.labels or f"bug,auto-reported,{report_dict.get('session_type') or 'system'}"

    issue = Issue.create(
        id=uuid.uuid4(),
        title=title,
        description=description,
        status='todo',
        author=current_user.username,
        priority=req.priority,
        labels=labels,
        user_id=current_user.effective_user_id,
        created_at=now,
        updated_at=now,
    )

    # Update report status
    if report_obj:
        report_obj.status = 'submitted'
        report_obj.issue_id = issue.id
        report_obj.save()
    else:
        from qengine.services.error_tracker import _update_redis_report
        _update_redis_report(req.id, {'status': 'submitted', 'issue_id': str(issue.id)})

    return {
        'status': 'ok',
        'issue': issue.to_dict(),
    }


@router.post('/reports/clear')
async def clear_reports(req: ReportClearRequest, current_user: CurrentUser = Depends(get_current_user)):
    count = 0

    # Clear from DB
    try:
        from qengine.models.ErrorReport import ErrorReport
        from qengine.services.error_tracker import _ensure_db_connection
        _ensure_db_connection()

        query = ErrorReport.delete()
        if req.status:
            query = query.where(ErrorReport.status == req.status)
        else:
            query = query.where(ErrorReport.status != 'submitted')
        if req.days_old:
            cutoff = jh.now_to_timestamp() - (req.days_old * 86400 * 1000)
            query = query.where(ErrorReport.created_at < cutoff)
        count = query.execute()
    except Exception:
        pass

    # Clear from Redis
    from qengine.services.error_tracker import _get_redis_reports, _delete_redis_report
    for r in _get_redis_reports():
        should_delete = False
        if req.status:
            should_delete = r.get('status') == req.status
        else:
            should_delete = r.get('status') != 'submitted'

        if req.days_old and should_delete:
            cutoff = jh.now_to_timestamp() - (req.days_old * 86400 * 1000)
            should_delete = r.get('created_at', 0) < cutoff

        if should_delete:
            _delete_redis_report(r['id'])
            count += 1

    return {'status': 'ok', 'deleted': count}


@router.post('/reports/count')
async def report_count(current_user: CurrentUser = Depends(get_current_user)):
    import sys
    from qengine.services.error_tracker import get_report_count

    user_id = current_user.effective_user_id if not current_user.is_admin or current_user.is_impersonating else None
    count = get_report_count(status='new', user_id=user_id)
    print(f"[REPORTS] /reports/count: {count} new reports", file=sys.stderr)
    return {'count': count}
