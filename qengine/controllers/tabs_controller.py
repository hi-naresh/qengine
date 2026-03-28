from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from qengine.repositories import open_tab_repository
from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser


router = APIRouter()


class TabsListRequest(BaseModel):
    module: str


class TabsAddRequest(BaseModel):
    module: str
    id: str


class TabsRemoveRequest(BaseModel):
    module: str
    id: str


class TabsReorderRequest(BaseModel):
    module: str
    ids: List[str]


class TabsResponse(BaseModel):
    ids: List[str]


@router.post('/tabs/list', response_model=TabsResponse)
async def list_tabs(req: TabsListRequest, current_user: CurrentUser = Depends(get_current_user)):
    """
    Get ordered list of open tab session IDs for a module
    """
    session_ids = open_tab_repository.get_open_tab_session_ids(req.module, user_id=current_user.effective_user_id)
    return TabsResponse(ids=session_ids)


@router.post('/tabs/add', response_model=TabsResponse)
async def add_tab(req: TabsAddRequest, current_user: CurrentUser = Depends(get_current_user)):
    """
    Add a new tab (or update if exists). Returns ordered list.
    For singleton modules, ensures only 1 tab exists.
    """
    session_ids = open_tab_repository.add_open_tab(req.module, req.id, user_id=current_user.effective_user_id)
    return TabsResponse(ids=session_ids)


@router.post('/tabs/remove', response_model=TabsResponse)
async def remove_tab(req: TabsRemoveRequest, current_user: CurrentUser = Depends(get_current_user)):
    """
    Remove a tab and reorder remaining tabs. Returns ordered list.
    """
    session_ids = open_tab_repository.remove_open_tab(req.module, req.id, user_id=current_user.effective_user_id)
    return TabsResponse(ids=session_ids)


@router.post('/tabs/reorder', response_model=TabsResponse)
async def reorder_tabs(req: TabsReorderRequest, current_user: CurrentUser = Depends(get_current_user)):
    """
    Reorder tabs to match the provided session_ids list.
    For singleton modules, ensures only 1 tab exists.
    """
    session_ids = open_tab_repository.reorder_open_tabs(req.module, req.ids, user_id=current_user.effective_user_id)
    return TabsResponse(ids=session_ids)

