from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from qengine.services.auth_dependency import get_current_user, CurrentUser
from qengine.services import pipeline_handler

router = APIRouter(prefix="/pipelines", tags=["Pipelines"])


class PipelineNameJson(BaseModel):
    name: str


class SavePipelineJson(BaseModel):
    name: str
    content: str


# ── Discovery (for backtest config dropdown) ──

@router.get("/registered")
def get_registered_pipelines():
    """List all registered pipeline classes with default configs and architecture metadata."""
    from qengine.framework import list_pipelines, get_pipeline_class
    result = []
    for name in list_pipelines():
        cls = get_pipeline_class(name)
        result.append({
            'name': name,
            'description': cls.__doc__.strip() if cls.__doc__ else '',
            'default_config': cls.default_config(),
            'architecture': cls.architecture(),
        })
    return JSONResponse(content=result)


# ── CRUD (mirrors strategy_controller pattern) ──

@router.get("/all")
def get_all_pipelines(current_user: CurrentUser = Depends(get_current_user)):
    """List all pipelines visible to the current user."""
    is_admin = current_user.role == 'admin' and not current_user.impersonating_user_id
    user_id = current_user.effective_user_id if not is_admin else None
    return pipeline_handler.get_pipelines(user_id=user_id, is_admin=is_admin)


@router.post("/get")
def get_pipeline(json_request: PipelineNameJson, current_user: CurrentUser = Depends(get_current_user)):
    """Get pipeline source code."""
    is_admin = current_user.role == 'admin'
    return pipeline_handler.get_pipeline(
        json_request.name,
        user_id=current_user.effective_user_id,
        is_admin=is_admin,
    )


@router.post("/make")
def make_pipeline(json_request: PipelineNameJson, current_user: CurrentUser = Depends(get_current_user)):
    """Create a new pipeline from the example template."""
    return pipeline_handler.generate(json_request.name, user_id=current_user.effective_user_id)


@router.post("/save")
def save_pipeline(json_request: SavePipelineJson, current_user: CurrentUser = Depends(get_current_user)):
    """Save pipeline source code."""
    is_admin = current_user.role == 'admin'
    return pipeline_handler.save_pipeline(
        json_request.name,
        json_request.content,
        user_id=current_user.effective_user_id,
        is_admin=is_admin,
    )


@router.post("/delete")
def delete_pipeline(json_request: PipelineNameJson, current_user: CurrentUser = Depends(get_current_user)):
    """Delete a pipeline."""
    is_admin = current_user.role == 'admin'
    return pipeline_handler.delete_pipeline(
        json_request.name,
        user_id=current_user.effective_user_id,
        is_admin=is_admin,
    )
