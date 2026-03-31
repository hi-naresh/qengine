from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
from qengine.services.auth_dependency import get_current_user, CurrentUser
from qengine.services.multiprocessing import process_manager


router = APIRouter(prefix="/autopilot", tags=["Autopilot"])


class AutopilotRequestJson(BaseModel):
    id: str
    config: dict
    exchange: str
    routes: List[Dict[str, str]]
    data_routes: List[Dict[str, str]]
    start_date: str
    finish_date: str
    pipeline_configs: Optional[List[dict]] = None
    hp_space: Optional[dict] = None
    max_iterations: int = 100
    objective_key: str = 'net_profit_percentage'
    maximize: bool = True


class CancelRequestJson(BaseModel):
    id: str


@router.post("")
def start_autopilot(request_json: AutopilotRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """Start an autopilot session (repeated backtests with learning)."""
    from qengine.autopilot.runner import run_autopilot

    process_manager.add_task(
        run_autopilot,
        request_json.id,
        request_json.config,
        request_json.routes,
        request_json.data_routes,
        request_json.start_date,
        request_json.finish_date,
        request_json.exchange,
        request_json.pipeline_configs,
        request_json.hp_space,
        request_json.max_iterations,
        request_json.objective_key,
        request_json.maximize,
    )

    return JSONResponse({'message': 'Autopilot started...'}, status_code=202)


@router.post("/cancel")
def cancel_autopilot(request_json: CancelRequestJson, current_user: CurrentUser = Depends(get_current_user)):
    """Cancel a running autopilot session."""
    process_manager.cancel_process(request_json.id)
    return JSONResponse({'message': f'Autopilot {request_json.id} cancellation requested'}, status_code=202)


@router.get("/state/{session_id}")
def get_autopilot_state(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Get the current state of an autopilot session."""
    import os
    import json

    state_path = os.path.join('storage', 'autopilot', session_id, 'state.json')
    if not os.path.exists(state_path):
        return JSONResponse({'message': 'Session not found'}, status_code=404)

    with open(state_path) as f:
        state = json.load(f)
    return JSONResponse(content=state)
