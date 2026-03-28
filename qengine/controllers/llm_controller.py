from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from qengine.services.auth_dependency import get_current_user, CurrentUser
from qengine.services.llm_engine import llm_engine
from qengine.services.web import (
    GenerateStrategyRequestJson,
    RefineStrategyRequestJson,
    ValidateStrategyRequestJson,
    ConfigureLLMRequestJson,
)

router = APIRouter(prefix="/llm", tags=["LLM Strategy Engine"])


def _ensure_llm_configured(current_user=None):
    """Configure LLM from the current user's settings (admin uses shared, users use their own)."""
    llm_engine.provider = None
    llm_engine.api_key = None
    try:
        from qengine.controllers.settings_controller import _get_settings_from_db, ADMIN_SETTINGS_ID
        uid = ADMIN_SETTINGS_ID if (current_user and current_user.is_admin) else (current_user.effective_user_id if current_user else ADMIN_SETTINGS_ID)
        settings = _get_settings_from_db(uid)
        llm_conf = settings.get('llm', {})
        if llm_conf.get('api_key') and llm_conf.get('provider'):
            llm_engine.configure(
                provider=llm_conf['provider'],
                api_key=llm_conf['api_key'],
                model=llm_conf.get('model') or None,
                temperature=llm_conf.get('temperature', 0.3),
            )
            return
    except Exception:
        pass


@router.post("/generate")
def generate_strategy(
    request_json: GenerateStrategyRequestJson,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Generate a new strategy from natural language description."""

    _ensure_llm_configured(current_user)

    if not llm_engine.is_configured:
        return JSONResponse(
            status_code=400,
            content={'error': 'LLM not configured. Please set API key in settings.'}
        )

    try:
        result = llm_engine.generate_strategy(
            description=request_json.description,
            asset_class=request_json.asset_class,
            symbol=request_json.symbol,
        )
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={'error': f'LLM generation failed: {str(e)}', 'valid': False, 'errors': [str(e)]}
        )


@router.post("/refine")
def refine_strategy(
    request_json: RefineStrategyRequestJson,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Refine existing strategy with feedback."""

    _ensure_llm_configured(current_user)

    if not llm_engine.is_configured:
        return JSONResponse(
            status_code=400,
            content={'error': 'LLM not configured. Please set API key in settings.'}
        )

    try:
        result = llm_engine.refine_strategy(
            current_code=request_json.code,
            feedback=request_json.feedback,
            backtest_results=request_json.backtest_results,
        )
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={'error': f'LLM refinement failed: {str(e)}', 'valid': False, 'errors': [str(e)]}
        )


@router.post("/validate")
def validate_strategy(
    request_json: ValidateStrategyRequestJson,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Validate strategy code syntax and structure."""

    try:
        result = llm_engine.validate_strategy(request_json.code)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={'valid': False, 'errors': [f'Validation error: {str(e)}']}
        )


@router.post("/configure")
def configure_llm(
    request_json: ConfigureLLMRequestJson,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Configure the LLM engine with provider and API key."""

    llm_engine.configure(
        provider=request_json.provider,
        api_key=request_json.api_key,
        model=request_json.model,
        temperature=request_json.temperature,
    )
    return JSONResponse(content={'status': 'configured', 'provider': request_json.provider})


@router.get("/status")
def llm_status(current_user: CurrentUser = Depends(get_current_user)):
    """Check LLM configuration status."""

    _ensure_llm_configured(current_user)

    return JSONResponse(content={
        'configured': llm_engine.is_configured,
        'provider': llm_engine.provider,
        'model': llm_engine.model,
    })
