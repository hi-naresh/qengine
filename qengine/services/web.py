import time
from typing import List, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware


fastapi_app = FastAPI()


@fastapi_app.on_event("startup")
def _migrate_strategies_on_startup():
    """Run one-time strategy directory migration and ensure shared examples exist."""
    try:
        from qengine.services.strategy_handler import migrate_existing_strategies, ensure_shared_example
        migrate_existing_strategies()
        ensure_shared_example()
    except Exception:
        pass  # Non-fatal: migration can be retried


origins = [
    "http://localhost:9000",
    "http://127.0.0.1:9000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with user context extracted from JWT.
    Also catches unhandled exceptions for error tracking."""

    # Paths that are too noisy to log at info level
    _SKIP_PATHS = {'/ws', '/favicon.ico'}

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()

        # Extract user from JWT (cheap — no DB call)
        user_id = None
        username = None
        token = request.headers.get('authorization', '')
        if token:
            try:
                from qengine.services import auth as authenticator
                payload = authenticator.decode_jwt(token)
                if payload:
                    user_id = payload.get('user_id')
                    username = payload.get('username')
            except Exception:
                pass

        try:
            response = await call_next(request)
        except Exception as exc:
            import traceback
            # Track the unhandled exception
            try:
                from qengine.services.error_tracker import track_error
                track_error(
                    message=f"{type(exc).__name__}: {exc}",
                    error_type=type(exc).__name__,
                    traceback=traceback.format_exc(),
                    session_type='http',
                    user_id=user_id,
                    context={
                        'method': request.method,
                        'path': request.url.path,
                        'user': username,
                    },
                )
            except Exception:
                pass
            raise  # Re-raise so FastAPI returns the 500

        duration_ms = (time.perf_counter() - start) * 1000

        path = request.url.path
        if path in self._SKIP_PATHS:
            return response

        ip = request.client.host if request.client else None

        from qengine.services.audit_logger import log_request
        log_request(
            method=request.method,
            path=path,
            status=response.status_code,
            duration_ms=duration_ms,
            user_id=user_id,
            username=username,
            ip=ip,
        )
        return response


fastapi_app.add_middleware(RequestLoggingMiddleware)


class BacktestRequestJson(BaseModel):
    id: str
    exchange: str
    routes: List[Dict[str, str]]
    data_routes: List[Dict[str, str]]
    config: dict
    start_date: str
    finish_date: str
    debug_mode: bool
    export_csv: bool
    export_json: bool
    export_chart: bool
    export_tradingview: bool
    fast_mode: bool
    benchmark: bool
    cost_model: bool = True
    hyperparameters: Optional[dict] = None
    pipelines: Optional[list] = None


class OptimizationRequestJson(BaseModel):
    id: Optional[str] = None
    exchange: str
    routes: List[Dict[str, str]]
    data_routes: List[Dict[str, str]]
    config: dict
    training_start_date: str
    training_finish_date: str
    testing_start_date: str
    testing_finish_date: str
    optimal_total: int
    fast_mode: bool
    cpu_cores: int
    state: dict


class ImportCandlesRequestJson(BaseModel):
    id: str
    exchange: str
    symbol: str
    start_date: str
    granularity: str = '1m'


class ExchangeSupportedSymbolsRequestJson(BaseModel):
    exchange: str


class CancelRequestJson(BaseModel):
    id: str


class LiveRequestJson(BaseModel):
    id: str
    config: dict
    exchange: str
    exchange_api_key_id: str
    notification_api_key_id: str
    routes: List[Dict[str, str]]
    data_routes: List[Dict[str, str]]
    debug_mode: bool
    paper_mode: Optional[bool] = None
    hyperparameters: Optional[dict] = None


class LiveCancelRequestJson(BaseModel):
    id: str
    paper_mode: Optional[bool] = None


class GetCandlesRequestJson(BaseModel):
    id: str
    exchange: str
    symbol: str
    timeframe: str


class GetLogsRequestJson(BaseModel):
    id: str
    type: str
    start_time: int


class GetOrdersRequestJson(BaseModel):
    id: str
    session_id: str


class StoreExchangeApiKeyRequestJson(BaseModel):
    exchange: str
    name: str
    api_key: str
    api_secret: str
    additional_fields: Optional[dict] = None
    general_notifications_id: Optional[str] = None
    error_notifications_id: Optional[str] = None


class StoreNotificationApiKeyRequestJson(BaseModel):
    name: str
    driver: str
    fields: dict


class DeleteExchangeApiKeyRequestJson(BaseModel):
    id: str


class DeleteNotificationApiKeyRequestJson(BaseModel):
    id: str


class ConfigRequestJson(BaseModel):
    current_config: dict


class LoginRequestJson(BaseModel):
    password: str
    username: Optional[str] = None


class RegisterRequestJson(BaseModel):
    username: str
    password: str
    name: Optional[str] = ''


class UpdateProfileRequestJson(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None
    current_password: Optional[str] = None


class DeleteAccountRequestJson(BaseModel):
    password: str
    delete_data: bool = True


class ImpersonateRequestJson(BaseModel):
    user_id: str


class UpdateUserQuotaRequestJson(BaseModel):
    user_id: str
    feature: str
    max_runs: int


class UpdateUserRequestJson(BaseModel):
    user_id: str
    is_active: Optional[bool] = None
    role: Optional[str] = None
    allowed_features: Optional[list] = None


class LoginMarketplaceRequestJson(BaseModel):
    email: str
    password: str


class NewStrategyRequestJson(BaseModel):
    name: str


class GetStrategyRequestJson(BaseModel):
    name: str


class SaveStrategyRequestJson(BaseModel):
    name: str
    content: str


class DeleteStrategyRequestJson(BaseModel):
    name: str


class ImportStrategyRequestJson(BaseModel):
    slug: str


class FeedbackRequestJson(BaseModel):
    description: str
    email: Optional[str] = None


class ReportExceptionRequestJson(BaseModel):
    description: str
    traceback: str
    mode: str
    attach_logs: bool
    session_id: Optional[str] = None
    email: Optional[str] = None


class HelpSearchRequestJson(BaseModel):
    query: str


class DeleteCandlesRequestJson(BaseModel):
    exchange: str
    symbol: str


class UpdateOptimizationSessionStateRequestJson(BaseModel):
    id: str
    state: dict


class UpdateOptimizationSessionStatusRequestJson(BaseModel):
    id: str
    status: str


class TerminateOptimizationRequestJson(BaseModel):
    id: str


class UpdateOptimizationSessionNotesRequestJson(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    strategy_codes: Optional[dict] = None


class GetOptimizationSessionsRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    title_search: Optional[str] = None
    status_filter: Optional[str] = None
    date_filter: Optional[str] = None


class UpdateBacktestSessionStateRequestJson(BaseModel):
    id: str
    state: dict


class GetBacktestSessionsRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    title_search: Optional[str] = None
    status_filter: Optional[str] = None
    date_filter: Optional[str] = None


class UpdateBacktestSessionNotesRequestJson(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    strategy_codes: Optional[dict] = None


class GetLiveSessionsRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    title_search: Optional[str] = None
    status_filter: Optional[str] = None
    date_filter: Optional[str] = None
    mode_filter: Optional[str] = None


class UpdateLiveSessionNotesRequestJson(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    strategy_codes: Optional[dict] = None


class UpdateLiveSessionStateRequestJson(BaseModel):
    id: str
    state: dict


class GetEquityCurveRequestJson(BaseModel):
    session_id: str
    from_ms: Optional[int] = None
    to_ms: Optional[int] = None
    timeframe: str = 'auto'
    max_points: int = 1000


class MonteCarloRequestJson(BaseModel):
    id: Optional[str] = None
    exchange: str
    routes: List[Dict[str, str]]
    data_routes: List[Dict[str, str]]
    config: dict
    start_date: str
    finish_date: str
    run_trades: bool
    run_candles: bool
    num_scenarios: int
    fast_mode: bool
    cpu_cores: int
    pipeline_type: Optional[str] = 'moving_block_bootstrap'
    pipeline_params: Optional[dict] = None
    risk_config: Optional[dict] = None
    state: dict


class UpdateMonteCarloSessionStateRequestJson(BaseModel):
    id: str
    state: dict


class TerminateMonteCarloRequestJson(BaseModel):
    id: str


class CancelMonteCarloRequestJson(BaseModel):
    id: str


class UpdateMonteCarloSessionNotesRequestJson(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    strategy_codes: Optional[dict] = None


class GetMonteCarloSessionsRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    title_search: Optional[str] = None
    status_filter: Optional[str] = None
    date_filter: Optional[str] = None


class GetOrdersHistoryRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    id_search: Optional[str] = None
    status_filter: Optional[str] = None
    symbol_filter: Optional[str] = None
    date_filter: Optional[str] = None
    exchange_filter: Optional[str] = None
    type_filter: Optional[str] = None
    side_filter: Optional[str] = None


class GetTradesHistoryRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    id_search: Optional[str] = None
    status_filter: Optional[str] = None
    symbol_filter: Optional[str] = None
    date_filter: Optional[str] = None
    exchange_filter: Optional[str] = None
    type_filter: Optional[str] = None
    

class ImportApiKeyRequestJson(BaseModel):
    content: str


# ── LLM Strategy Engine Request Models ──

class GenerateStrategyRequestJson(BaseModel):
    description: str
    asset_class: str = 'forex'
    symbol: str = 'EUR-USD'


class RefineStrategyRequestJson(BaseModel):
    code: str
    feedback: str
    backtest_results: Optional[dict] = None


class ValidateStrategyRequestJson(BaseModel):
    code: str


class ConfigureLLMRequestJson(BaseModel):
    provider: str
    api_key: str
    model: Optional[str] = None
    temperature: float = 0.3


class AIGenerateAndSaveRequestJson(BaseModel):
    """Generate a strategy with LLM and optionally save it."""
    description: str
    name: str = ''  # strategy class name — auto-derived if empty
    asset_class: str = 'forex'
    symbol: str = 'EUR-USD'
    save: bool = True  # whether to save to disk


class AIRefineAndSaveRequestJson(BaseModel):
    """Refine an existing strategy with LLM feedback."""
    name: str  # strategy name (folder name)
    feedback: str
    backtest_results: Optional[dict] = None


class AdminCreateUserRequestJson(BaseModel):
    username: str
    password: str
    role: str = 'user'


class AdminDeleteUserRequestJson(BaseModel):
    user_id: str
    delete_data: bool = True


class AdminResetPasswordRequestJson(BaseModel):
    user_id: str
    new_password: str


class QuotaRequestJson(BaseModel):
    feature: str
    requested_runs: int
    reason: str = ''


class ReviewQuotaRequestJson(BaseModel):
    request_id: str
    status: str  # 'approved' or 'denied'
    admin_note: str = ''
    approved_runs: Optional[int] = None  # admin can set different limit than requested
