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

    return {
        'issues': [i.to_dict() for i in issues],
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
