from typing import Optional
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
import requests
import re

from qengine.services import auth as authenticator
from qengine.services.auth_dependency import get_current_user, require_admin, CurrentUser
from qengine.services.web import (
    NewStrategyRequestJson,
    GetStrategyRequestJson,
    SaveStrategyRequestJson,
    DeleteStrategyRequestJson,
    ImportStrategyRequestJson,
    AIGenerateAndSaveRequestJson,
    AIRefineAndSaveRequestJson,
)
import qengine.helpers as jh
from qengine.info import QENGINE_API2_URL

router = APIRouter(prefix="/strategy", tags=["Strategy"])


@router.post("/make")
def make_strategy(json_request: NewStrategyRequestJson, current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """
    Create a new strategy
    """
    from qengine.services import strategy_handler
    return strategy_handler.generate(json_request.name, user_id=current_user.effective_user_id)


@router.get("/all")
def get_strategies(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """
    Get all strategies
    """
    from qengine.services import strategy_handler
    return strategy_handler.get_strategies(
        user_id=current_user.effective_user_id if not (current_user.is_admin and not current_user.is_impersonating) else None,
        is_admin=current_user.is_admin,
    )


@router.post("/get")
def get_strategy(
        json_request: GetStrategyRequestJson,
        current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get a specific strategy
    """
    from qengine.services import strategy_handler
    return strategy_handler.get_strategy(json_request.name, user_id=current_user.effective_user_id, is_admin=current_user.is_admin)


@router.post("/save")
def save_strategy(
        json_request: SaveStrategyRequestJson,
        current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Save a strategy
    """
    from qengine.services import strategy_handler
    return strategy_handler.save_strategy(json_request.name, json_request.content, user_id=current_user.effective_user_id, is_admin=current_user.is_admin)


@router.post("/delete")
def delete_strategy(
        json_request: DeleteStrategyRequestJson,
        current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Delete a strategy
    """
    from qengine.services import strategy_handler
    return strategy_handler.delete_strategy(json_request.name, user_id=current_user.effective_user_id, is_admin=current_user.is_admin)


@router.get("/index")
async def index_marketplace_strategies(
        period: str = Query(...),
        sort_by: str = Query("Sharpe Ratio"),
        submitted_after: Optional[str] = Query(None),
        submitted_before: Optional[str] = Query(None),
        current_user: CurrentUser = Depends(get_current_user),
        marketplace_token: Optional[str] = Header(None, alias="X-Marketplace-Token")
) -> JSONResponse:
    """
    Browse strategies from qengine.trade
    """
    try:
        headers = {}
        if marketplace_token:
            headers['Authorization'] = f'Bearer {marketplace_token}'
            
        params = {'period': period, 'sort_by': sort_by}
        if submitted_after:
            params['submitted_after'] = submitted_after
        if submitted_before:
            params['submitted_before'] = submitted_before

        response = requests.get(
            f'{QENGINE_API2_URL}/strategies',
            params=params,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            return JSONResponse(response.json())
        else:
            return JSONResponse({
                'status': 'error',
                'message': f'Failed to fetch strategies: {response.text}'
            }, status_code=response.status_code)
    except requests.exceptions.RequestException as e:
        return JSONResponse({
            'status': 'error',
            'message': f'Error connecting to marketplace API: {str(e)}'
        },         status_code=500)


@router.get("/periods")
async def get_marketplace_periods(
        current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get available trading periods from qengine.trade
    """
    try:
        response = requests.get(
            f'{QENGINE_API2_URL}/strategies/periods',
            timeout=10
        )

        if response.status_code == 200:
            return JSONResponse(response.json())
        else:
            return JSONResponse({
                'status': 'error',
                'message': f'Failed to fetch periods: {response.text}'
            }, status_code=response.status_code)
    except requests.exceptions.RequestException as e:
        return JSONResponse({
            'status': 'error',
            'message': f'Error connecting to marketplace API: {str(e)}'
        }, status_code=500)


@router.get("/marketplace/{slug}")
async def get_marketplace_strategy(
        slug: str,
        current_user: CurrentUser = Depends(get_current_user),
        marketplace_token: Optional[str] = Header(None, alias="X-Marketplace-Token")
) -> JSONResponse:
    """
    Get a specific strategy from qengine.trade
    """
    try:
        headers = {}
        if marketplace_token:
            headers['Authorization'] = f'Bearer {marketplace_token}'
            
        response = requests.get(
            f'{QENGINE_API2_URL}/strategies/{slug}',
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            return JSONResponse(response.json())
        else:
            return JSONResponse({
                'status': 'error',
                'message': f'Failed to fetch strategy: {response.text}'
            }, status_code=response.status_code)
    except requests.exceptions.RequestException as e:
        return JSONResponse({
            'status': 'error',
            'message': f'Error connecting to marketplace API: {str(e)}'
        }, status_code=500)


@router.get("/marketplace/{slug}/metrics")
async def get_marketplace_strategy_metrics(
        slug: str,
        period: str = Query(...),
        symbol: str = Query(...),
        timeframe: str = Query(...),
        current_user: CurrentUser = Depends(get_current_user),
        marketplace_token: Optional[str] = Header(None, alias="X-Marketplace-Token")
) -> JSONResponse:
    """
    Get metrics for a specific strategy from qengine.trade
    """
    try:
        headers = {}
        if marketplace_token:
            headers['Authorization'] = f'Bearer {marketplace_token}'
            
        response = requests.get(
            f'{QENGINE_API2_URL}/strategies/{slug}/metrics',
            params={'period': period, 'symbol': symbol, 'timeframe': timeframe},
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            return JSONResponse(response.json())
        else:
            return JSONResponse({
                'status': 'error',
                'message': f'Failed to fetch strategy metrics: {response.text}'
            }, status_code=response.status_code)
    except requests.exceptions.RequestException as e:
        return JSONResponse({
            'status': 'error',
            'message': f'Error connecting to marketplace API: {str(e)}'
        }, status_code=500)


@router.post("/import")
async def import_strategy(
        json_request: ImportStrategyRequestJson,
        current_user: CurrentUser = Depends(get_current_user),
        marketplace_token: Optional[str] = Header(None, alias="X-Marketplace-Token")
) -> JSONResponse:
    """
    Import a strategy from qengine.trade
    """
    try:
        # Fetch the strategy from qengine.trade
        headers = {}
        if marketplace_token:
            headers['Authorization'] = f'Bearer {marketplace_token}'
            
        response = requests.get(
            f'{QENGINE_API2_URL}/strategies/{json_request.slug}',
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            return JSONResponse({
                'status': 'error',
                'message': f'Failed to fetch strategy: {response.text}'
            }, status_code=response.status_code)
        
        strategy_data = response.json()
        
        # Check if code is available
        if not strategy_data.get('code'):
            return JSONResponse({
                'status': 'error',
                'message': 'Strategy code not available. You may not have access to this strategy.'
            }, status_code=403)

        # Extract the Python class name from the code
        code = strategy_data.get('code')
        class_match = re.search(r'class\s+(\w+)', code)
        if not class_match:
            return JSONResponse({
                'status': 'error',
                'message': 'No Python class definition found in strategy code. Cannot import strategy.'
            }, status_code=400)

        class_name = class_match.group(1)

        # Import the strategy
        from qengine.services import strategy_handler
        return strategy_handler.import_strategy(
            name=class_name,
            code=code,
            user_id=current_user.effective_user_id,
        )

    except requests.exceptions.RequestException as e:
        return JSONResponse({
            'status': 'error',
            'message': f'Error connecting to marketplace API: {str(e)}'
        }, status_code=500)


@router.post("/ai/generate")
def ai_generate_strategy(
    json_request: AIGenerateAndSaveRequestJson,
    current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """Generate a strategy using LLM and optionally save it to disk."""
    from qengine.services.llm_engine import llm_engine
    from qengine.controllers.settings_controller import _settings_uid

    if not llm_engine.is_configured:
        llm_engine.configure_from_env(user_id=_settings_uid(current_user))
    if not llm_engine.is_configured:
        return JSONResponse(
            {'error': 'LLM not configured. Set API key in Settings or environment.'},
            status_code=400,
        )

    result = llm_engine.generate_strategy(
        description=json_request.description,
        asset_class=json_request.asset_class,
        symbol=json_request.symbol,
    )

    if not result['valid']:
        return JSONResponse({
            'status': 'error',
            'code': result['code'],
            'explanation': result['explanation'],
            'errors': result['errors'],
        }, status_code=200)

    # Determine strategy name from code or request
    name = json_request.name
    if not name:
        class_match = re.search(r'class\s+(\w+)', result['code'])
        name = class_match.group(1) if class_match else 'AIStrategy'

    saved = False
    if json_request.save:
        from qengine.services import strategy_handler
        strategy_handler.import_strategy(name=name, code=result['code'], user_id=current_user.effective_user_id)
        saved = True

    return JSONResponse({
        'status': 'ok',
        'name': name,
        'code': result['code'],
        'explanation': result['explanation'],
        'valid': True,
        'saved': saved,
    })


@router.post("/ai/refine")
def ai_refine_strategy(
    json_request: AIRefineAndSaveRequestJson,
    current_user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    """Refine an existing strategy using LLM feedback and save it."""
    from qengine.services.llm_engine import llm_engine
    from qengine.services import strategy_handler
    from qengine.controllers.settings_controller import _settings_uid

    if not llm_engine.is_configured:
        llm_engine.configure_from_env(user_id=_settings_uid(current_user))
    if not llm_engine.is_configured:
        return JSONResponse(
            {'error': 'LLM not configured. Set API key in Settings or environment.'},
            status_code=400,
        )

    # Read current strategy code via resolve_strategy_path
    import os
    resolved = strategy_handler.resolve_strategy_path(json_request.name, current_user.effective_user_id)
    if not resolved:
        return JSONResponse({'error': f'Strategy {json_request.name} not found or empty.'}, status_code=404)
    strategy_path = f'{resolved}/__init__.py'
    if not os.path.isfile(strategy_path):
        return JSONResponse({'error': f'Strategy {json_request.name} not found or empty.'}, status_code=404)

    with open(strategy_path, 'r') as f:
        current_code = f.read()

    if not current_code.strip():
        return JSONResponse({'error': f'Strategy {json_request.name} not found or empty.'}, status_code=404)

    result = llm_engine.refine_strategy(
        current_code=current_code,
        feedback=json_request.feedback,
        backtest_results=json_request.backtest_results,
    )

    if result['valid']:
        strategy_handler.save_strategy(json_request.name, result['code'], user_id=current_user.effective_user_id)

    return JSONResponse({
        'status': 'ok' if result['valid'] else 'error',
        'name': json_request.name,
        'code': result['code'],
        'explanation': result['explanation'],
        'valid': result['valid'],
        'errors': result.get('errors', []),
        'saved': result['valid'],
    })
