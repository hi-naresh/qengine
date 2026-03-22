import os
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from qengine.services import auth as authenticator
from qengine.services.llm_engine import llm_engine
from qengine.services.web import (
    GenerateStrategyRequestJson,
    RefineStrategyRequestJson,
    ValidateStrategyRequestJson,
    ConfigureLLMRequestJson,
)

router = APIRouter(prefix="/llm", tags=["LLM Strategy Engine"])


def _ensure_llm_configured():
    """Try to configure LLM from DB settings, then env vars."""
    if llm_engine.is_configured:
        return
    # Try DB settings first
    try:
        from qengine.controllers.settings_controller import _get_settings_from_db
        settings = _get_settings_from_db()
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
    # Fall back to env vars
    llm_engine.configure_from_env()


@router.post("/generate")
def generate_strategy(
    request_json: GenerateStrategyRequestJson,
    authorization: Optional[str] = Header(None),
):
    """Generate a new strategy from natural language description."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    _ensure_llm_configured()

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
    authorization: Optional[str] = Header(None),
):
    """Refine existing strategy with feedback."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    _ensure_llm_configured()

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
    authorization: Optional[str] = Header(None),
):
    """Validate strategy code syntax and structure."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

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
    authorization: Optional[str] = Header(None),
):
    """Configure the LLM engine with provider and API key."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    llm_engine.configure(
        provider=request_json.provider,
        api_key=request_json.api_key,
        model=request_json.model,
        temperature=request_json.temperature,
    )
    return JSONResponse(content={'status': 'configured', 'provider': request_json.provider})


@router.get("/status")
def llm_status(authorization: Optional[str] = Header(None)):
    """Check LLM configuration status."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    _ensure_llm_configured()

    return JSONResponse(content={
        'configured': llm_engine.is_configured,
        'provider': llm_engine.provider,
        'model': llm_engine.model,
    })
