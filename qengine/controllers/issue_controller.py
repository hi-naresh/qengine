from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from qengine.services import auth as authenticator
from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser
import qengine.helpers as jh

router = APIRouter()


class IssueCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = 'todo'
    author: Optional[str] = None
    priority: str = 'medium'
    labels: Optional[List[str]] = None


class IssueUpdateRequest(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    author: Optional[str] = None
    priority: Optional[str] = None
    labels: Optional[List[str]] = None


class IssueDeleteRequest(BaseModel):
    id: str


class IssueListRequest(BaseModel):
    status: Optional[str] = None
    limit: int = 100
    offset: int = 0


class IssueClearRequest(BaseModel):
    status: Optional[str] = None  # None = clear all, or clear by status


class CommentCreateRequest(BaseModel):
    issue_id: str
    parent_id: Optional[str] = None
    author: Optional[str] = None
    body: str


class CommentListRequest(BaseModel):
    issue_id: str


class CommentDeleteRequest(BaseModel):
    id: str


@router.post('/issues/list')
async def list_issues(req: IssueListRequest, current_user: CurrentUser = Depends(get_current_user)):
    from qengine.models.Issue import Issue

    user_id = current_user.effective_user_id if not current_user.is_admin or current_user.is_impersonating else None

    query = Issue.select().order_by(Issue.created_at.desc())

    if user_id:
        query = query.where(Issue.user_id == user_id)

    if req.status:
        query = query.where(Issue.status == req.status)

    total = query.count()
    issues = list(query.offset(req.offset).limit(req.limit))

    from qengine.models.IssueComment import IssueComment
    import peewee as pw

    # Get comment counts per issue
    issue_ids = [i.id for i in issues]
    comment_counts = {}
    if issue_ids:
        counts = (IssueComment.select(IssueComment.issue_id, pw.fn.COUNT(IssueComment.id).alias('cnt'))
                  .where(IssueComment.issue_id.in_(issue_ids))
                  .group_by(IssueComment.issue_id))
        for row in counts:
            comment_counts[str(row.issue_id)] = row.cnt

    result = []
    for i in issues:
        d = i.to_dict()
        d['comment_count'] = comment_counts.get(str(i.id), 0)
        result.append(d)

    # Add owner labels for admin view
    if not user_id:
        from qengine.services.transformers import enrich_with_owner
        enrich_with_owner(result, issues)

    return {
        'issues': result,
        'total': total,
    }


@router.post('/issues/create')
async def create_issue(req: IssueCreateRequest, current_user: CurrentUser = Depends(get_current_user)):
    from qengine.models.Issue import Issue
    import uuid

    now = jh.now_to_timestamp()

    issue = Issue.create(
        id=uuid.uuid4(),
        title=req.title,
        description=req.description,
        status=req.status,
        author=req.author,
        priority=req.priority,
        labels=','.join(req.labels) if req.labels else None,
        user_id=current_user.effective_user_id,
        created_at=now,
        updated_at=now,
    )

    # Notify admins in real-time
    try:
        from qengine.services.redis import publish_admin_notification
        publish_admin_notification({
            'type': 'new_issue',
            'title': req.title,
            'priority': req.priority,
            'username': current_user.username,
        })
    except Exception:
        pass

    return {'status': 'ok', 'issue': issue.to_dict()}


@router.post('/issues/update')
async def update_issue(req: IssueUpdateRequest, current_user: CurrentUser = Depends(get_current_user)):
    from qengine.models.Issue import Issue

    try:
        issue = Issue.get_by_id(req.id)
    except Issue.DoesNotExist:
        return {'status': 'error', 'message': 'Issue not found'}

    # Verify ownership for non-admin users
    if not current_user.is_admin or current_user.is_impersonating:
        if str(issue.user_id) != str(current_user.effective_user_id):
            return {'status': 'error', 'message': 'Issue not found'}

    if req.title is not None:
        issue.title = req.title
    if req.description is not None:
        issue.description = req.description
    if req.status is not None:
        issue.status = req.status
    if req.author is not None:
        issue.author = req.author
    if req.priority is not None:
        issue.priority = req.priority
    if req.labels is not None:
        issue.labels = ','.join(req.labels) if req.labels else None

    issue.updated_at = jh.now_to_timestamp()
    issue.save()

    return {'status': 'ok', 'issue': issue.to_dict()}


@router.post('/issues/delete')
async def delete_issue(req: IssueDeleteRequest, current_user: CurrentUser = Depends(get_current_user)):
    from qengine.models.Issue import Issue

    try:
        issue = Issue.get_by_id(req.id)
    except Issue.DoesNotExist:
        return {'status': 'error', 'message': 'Issue not found'}

    # Verify ownership for non-admin users
    if not current_user.is_admin or current_user.is_impersonating:
        if str(issue.user_id) != str(current_user.effective_user_id):
            return {'status': 'error', 'message': 'Issue not found'}

    issue.delete_instance()
    return {'status': 'ok'}


@router.post('/issues/clear')
async def clear_issues(req: IssueClearRequest, current_user: CurrentUser = Depends(get_current_user)):
    from qengine.models.Issue import Issue

    user_id = current_user.effective_user_id if not current_user.is_admin or current_user.is_impersonating else None

    query = Issue.delete()

    if user_id:
        query = query.where(Issue.user_id == user_id)

    if req.status:
        query = query.where(Issue.status == req.status)

    count = query.execute()

    return {'status': 'ok', 'deleted': count}


@router.post('/issues/active-count')
async def active_issue_count(current_user: CurrentUser = Depends(get_current_user)):
    from qengine.models.Issue import Issue

    user_id = current_user.effective_user_id if not current_user.is_admin or current_user.is_impersonating else None

    query = Issue.select().where(Issue.status != 'done')

    if user_id:
        query = query.where(Issue.user_id == user_id)

    count = query.count()
    return {'count': count}


@router.post('/issues/comments/list')
async def list_comments(req: CommentListRequest, current_user: CurrentUser = Depends(get_current_user)):
    from qengine.models.Issue import Issue
    from qengine.models.IssueComment import IssueComment

    # Verify user owns the issue (non-admin)
    if not current_user.is_admin or current_user.is_impersonating:
        try:
            issue = Issue.get_by_id(req.issue_id)
            if str(issue.user_id) != str(current_user.effective_user_id):
                return {'comments': []}
        except Issue.DoesNotExist:
            return {'comments': []}

    comments = list(
        IssueComment.select()
        .where(IssueComment.issue_id == req.issue_id)
        .order_by(IssueComment.created_at.asc())
    )

    return {'comments': [c.to_dict() for c in comments]}


@router.post('/issues/comments/create')
async def create_comment(req: CommentCreateRequest, current_user: CurrentUser = Depends(get_current_user)):
    from qengine.models.IssueComment import IssueComment
    import uuid

    now = jh.now_to_timestamp()

    comment = IssueComment.create(
        id=uuid.uuid4(),
        issue_id=req.issue_id,
        parent_id=req.parent_id,
        author=req.author,
        body=req.body,
        user_id=current_user.effective_user_id,
        created_at=now,
        updated_at=now,
    )

    return {'status': 'ok', 'comment': comment.to_dict()}


@router.post('/issues/comments/delete')
async def delete_comment(req: CommentDeleteRequest, current_user: CurrentUser = Depends(get_current_user)):
    from qengine.models.IssueComment import IssueComment

    try:
        comment = IssueComment.get_by_id(req.id)
    except IssueComment.DoesNotExist:
        return {'status': 'error', 'message': 'Comment not found'}

    # Verify ownership for non-admin users
    if not current_user.is_admin or current_user.is_impersonating:
        if str(comment.user_id) != str(current_user.effective_user_id):
            return {'status': 'error', 'message': 'Comment not found'}

    # Also delete replies to this comment
    IssueComment.delete().where(IssueComment.parent_id == req.id).execute()
    comment.delete_instance()
    return {'status': 'ok'}
