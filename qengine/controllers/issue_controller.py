from fastapi import APIRouter, Header
from pydantic import BaseModel
from typing import Optional, List
from qengine.services import auth as authenticator
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
async def list_issues(req: IssueListRequest, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from qengine.models.Issue import Issue

    query = Issue.select().order_by(Issue.created_at.desc())

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

    return {
        'issues': result,
        'total': total,
    }


@router.post('/issues/create')
async def create_issue(req: IssueCreateRequest, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

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
        created_at=now,
        updated_at=now,
    )

    return {'status': 'ok', 'issue': issue.to_dict()}


@router.post('/issues/update')
async def update_issue(req: IssueUpdateRequest, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from qengine.models.Issue import Issue

    try:
        issue = Issue.get_by_id(req.id)
    except Issue.DoesNotExist:
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
async def delete_issue(req: IssueDeleteRequest, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from qengine.models.Issue import Issue

    try:
        issue = Issue.get_by_id(req.id)
        issue.delete_instance()
        return {'status': 'ok'}
    except Issue.DoesNotExist:
        return {'status': 'error', 'message': 'Issue not found'}


@router.post('/issues/clear')
async def clear_issues(req: IssueClearRequest, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from qengine.models.Issue import Issue

    if req.status:
        count = Issue.delete().where(Issue.status == req.status).execute()
    else:
        count = Issue.delete().execute()

    return {'status': 'ok', 'deleted': count}


@router.post('/issues/active-count')
async def active_issue_count(authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from qengine.models.Issue import Issue

    count = Issue.select().where(Issue.status != 'done').count()
    return {'count': count}


@router.post('/issues/comments/list')
async def list_comments(req: CommentListRequest, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from qengine.models.IssueComment import IssueComment

    comments = list(
        IssueComment.select()
        .where(IssueComment.issue_id == req.issue_id)
        .order_by(IssueComment.created_at.asc())
    )

    return {'comments': [c.to_dict() for c in comments]}


@router.post('/issues/comments/create')
async def create_comment(req: CommentCreateRequest, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from qengine.models.IssueComment import IssueComment
    import uuid

    now = jh.now_to_timestamp()

    comment = IssueComment.create(
        id=uuid.uuid4(),
        issue_id=req.issue_id,
        parent_id=req.parent_id,
        author=req.author,
        body=req.body,
        created_at=now,
        updated_at=now,
    )

    return {'status': 'ok', 'comment': comment.to_dict()}


@router.post('/issues/comments/delete')
async def delete_comment(req: CommentDeleteRequest, authorization: Optional[str] = Header(None)):
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from qengine.models.IssueComment import IssueComment

    try:
        comment = IssueComment.get_by_id(req.id)
        # Also delete replies to this comment
        IssueComment.delete().where(IssueComment.parent_id == req.id).execute()
        comment.delete_instance()
        return {'status': 'ok'}
    except IssueComment.DoesNotExist:
        return {'status': 'error', 'message': 'Comment not found'}
