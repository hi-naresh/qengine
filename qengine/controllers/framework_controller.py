import sys

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


class TrainPipelineJson(BaseModel):
    name: str
    config: Optional[dict] = None


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


@router.post("/train")
async def train_pipeline(json_request: TrainPipelineJson, current_user: CurrentUser = Depends(get_current_user)):
    """Train a pipeline that requires training (e.g., IslandPilot).

    Runs the training scripts in a background thread and returns immediately.
    Training status can be polled via /pipelines/registered (training_status field).
    """
    from qengine.framework import get_pipeline_class
    import subprocess
    import threading
    import os

    name = json_request.name
    cls = get_pipeline_class(name)
    arch = cls.architecture()

    if not arch.get('requires_training', False):
        return JSONResponse(content={'status': 'error', 'message': f'{name} does not require training'}, status_code=400)

    # For IslandPilot, run the research scripts
    if name == 'IslandPilot':
        scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'notebooks', 'phase4')
        scripts_dir = os.path.normpath(scripts_dir)
        python_exe = sys.executable

        def run_training():
            import logging
            log = logging.getLogger('pipeline_training')
            try:
                # Run script 40 (regime discovery) then 41 (evolution)
                for script in ['40_regime_discovery.py', '41_island_evolution.py']:
                    result = subprocess.run(
                        [python_exe, os.path.join(scripts_dir, script)],
                        cwd=scripts_dir,
                        capture_output=True, text=True, timeout=1800,
                    )
                    if result.returncode != 0:
                        log.error(f'Training script {script} failed: {result.stderr[:500]}')
                        return
                    log.info(f'Training script {script} completed')
                log.info(f'{name} training complete')
            except Exception as e:
                log.error(f'Training failed: {e}')

        thread = threading.Thread(target=run_training, daemon=True)
        thread.start()

        return JSONResponse(content={
            'status': 'started',
            'message': f'Training {name} in background. Poll /pipelines/registered for status.',
        })

    return JSONResponse(content={'status': 'error', 'message': f'No training handler for {name}'}, status_code=400)
