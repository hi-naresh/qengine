"""
Strategy Playground Controller

Provides endpoints for generating synthetic market scenarios and running
quick simulations to test strategy behavior without needing real data.
"""
from typing import Optional, List, Dict
from fastapi import APIRouter, Header, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from qengine.services import auth as authenticator
from qengine.services.scenario_generator import generate_scenario, SCENARIOS
from qengine.services.multiprocessing import process_manager
import qengine.helpers as jh


router = APIRouter(prefix="/playground", tags=["Playground"])


class PlaygroundScenarioRequest(BaseModel):
    scenario: str = 'ranging'
    duration_minutes: int = 360
    symbol: str = 'EUR-USD'
    start_price: float = 1.1000
    volatility: float = 0.0002
    trend_strength: float = 0.00005
    volume_base: float = 1000.0
    seed: Optional[int] = None


class PlaygroundRunRequest(BaseModel):
    id: str
    strategy: str
    exchange: str = 'Sandbox'
    symbol: str = 'EUR-USD'
    timeframe: str = '5m'
    scenario: str = 'ranging'
    duration_minutes: int = 360
    start_price: float = 1.1000
    volatility: float = 0.0002
    trend_strength: float = 0.00005
    volume_base: float = 1000.0
    seed: Optional[int] = None
    balance: float = 10000.0
    leverage: int = 30
    warm_up_candles: int = 50
    hyperparameters: Optional[dict] = None


@router.post("/strategy-hyperparams")
def get_strategy_hyperparams(request_json: dict = Body(...), authorization: Optional[str] = Header(None)):
    """Extract hyperparameters definition from a strategy's code."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    import re
    name = request_json.get('name', '')
    if not name:
        return JSONResponse({'hyperparameters': []})
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)

    try:
        import ast
        import os
        path = f'strategies/{name}/__init__.py'
        if not os.path.exists(path):
            return JSONResponse({'hyperparameters': []})

        with open(path, 'r') as f:
            code = f.read()

        # Parse the AST to find the hyperparameters() method's return value
        tree = ast.parse(code)
        hp_list = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'hyperparameters':
                for stmt in node.body:
                    if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.List):
                        for elt in stmt.value.elts:
                            if isinstance(elt, ast.Dict):
                                hp = {}
                                for k, v in zip(elt.keys, elt.values):
                                    key = k.s if isinstance(k, ast.Constant) else str(k)
                                    if isinstance(v, ast.Constant):
                                        hp[key] = v.value
                                    elif isinstance(v, ast.Name):
                                        hp[key] = v.id
                                    elif isinstance(v, ast.List):
                                        hp[key] = [
                                            e.value if isinstance(e, ast.Constant) else str(e)
                                            for e in v.elts
                                        ]
                                    elif isinstance(v, ast.Dict):
                                        # Nested dict (e.g. depends_on: {'signal_mode': ['ema', ...]})
                                        nested = {}
                                        for nk, nv in zip(v.keys, v.values):
                                            nkey = nk.value if isinstance(nk, ast.Constant) else str(nk)
                                            if isinstance(nv, ast.List):
                                                nested[nkey] = [
                                                    e.value if isinstance(e, ast.Constant) else str(e)
                                                    for e in nv.elts
                                                ]
                                            elif isinstance(nv, ast.Constant):
                                                nested[nkey] = nv.value
                                        hp[key] = nested
                                    elif isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.USub):
                                        if isinstance(v.operand, ast.Constant):
                                            hp[key] = -v.operand.value
                                hp_list.append(hp)
                break

        return JSONResponse({'hyperparameters': hp_list})
    except Exception as e:
        return JSONResponse({'hyperparameters': [], 'error': str(e)})


@router.get("/scenarios")
def get_scenarios(authorization: Optional[str] = Header(None)):
    """Return the list of available market scenarios."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    return JSONResponse({'scenarios': SCENARIOS})


@router.post("/preview-scenario")
def preview_scenario(
    request_json: PlaygroundScenarioRequest,
    authorization: Optional[str] = Header(None)
):
    """Generate and return synthetic candle data for preview (no simulation)."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        candles = generate_scenario(
            scenario=request_json.scenario,
            duration_minutes=request_json.duration_minutes,
            symbol=request_json.symbol,
            start_price=request_json.start_price,
            volatility=request_json.volatility,
            trend_strength=request_json.trend_strength,
            volume_base=request_json.volume_base,
            seed=request_json.seed,
        )

        candle_list = [{
            'time': int(c[0] / 1000),
            'open': round(float(c[1]), 5),
            'close': round(float(c[2]), 5),
            'high': round(float(c[3]), 5),
            'low': round(float(c[4]), 5),
            'volume': round(float(c[5]), 2),
        } for c in candles]

        return JSONResponse({
            'candles': candle_list,
            'count': len(candle_list),
        })
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/run")
def run_playground(
    request_json: PlaygroundRunRequest,
    authorization: Optional[str] = Header(None)
):
    """Run a quick playground simulation with synthetic data."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        process_manager.add_task(
            _run_playground_simulation,
            request_json.id,
            request_json.strategy,
            request_json.exchange,
            request_json.symbol,
            request_json.timeframe,
            request_json.scenario,
            request_json.duration_minutes,
            request_json.start_price,
            request_json.volatility,
            request_json.trend_strength,
            request_json.volume_base,
            request_json.seed,
            request_json.balance,
            request_json.leverage,
            request_json.warm_up_candles,
            request_json.hyperparameters,
        )
        return JSONResponse({'message': 'Playground simulation started...'}, status_code=202)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/cancel")
def cancel_playground(request_json: dict = Body(...), authorization: Optional[str] = Header(None)):
    """Cancel a running playground simulation."""
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    process_manager.cancel_process(request_json.get('id', ''))
    return JSONResponse({'message': 'Cancelled'})


def _run_playground_simulation(
    client_id: str,
    strategy_name: str,
    exchange_name: str,
    symbol: str,
    timeframe: str,
    scenario: str,
    duration_minutes: int,
    start_price: float,
    volatility: float,
    trend_strength: float,
    volume_base: float,
    seed: int,
    balance: float,
    leverage: int,
    warm_up_candles: int,
    hyperparameters: dict,
):
    """Execute playground simulation in a subprocess (same pattern as backtest)."""
    import time
    import numpy as np
    from qengine.config import config, set_config
    from qengine.routes import router as route_router
    from qengine.store import store
    from qengine.services import candle_service, order_service, position_service, exchange_service
    from qengine.services.redis import sync_publish, is_process_active
    from qengine.services.validators import validate_routes
    from qengine.services.scenario_generator import generate_scenario
    from qengine.modes.backtest_mode import (
        simulator, _handle_warmup_candles, _get_formatted_candles_for_frontend,
        _get_formatted_orders_for_frontend, _get_add_line_to_candle_chart,
        _get_add_extra_line_chart, _get_add_horizontal_line_to_candle_chart,
        _get_add_horizontal_line_to_extra_chart
    )
    from qengine.modes.utils import save_daily_portfolio_balance
    from qengine.services.failure import register_custom_exception_handler
    from qengine import exceptions
    from qengine.services.progressbar import Progressbar
    from timeloop import Timeloop
    from datetime import timedelta
    import qengine.services.metrics as stats
    import qengine.services.report as report
    from qengine.services import charts

    # Check termination
    status_checker = Timeloop()

    @status_checker.job(interval=timedelta(seconds=1))
    def handle_time():
        if is_process_active(client_id) is False:
            raise exceptions.Termination

    status_checker.start()

    config['app']['trading_mode'] = 'backtest'
    config['app']['debug_mode'] = False
    config['app']['skip_market_hours'] = True  # Playground uses synthetic data, skip market hours
    register_custom_exception_handler()

    # Build user config — detect exchange type from broker_info
    from qengine.info import broker_info
    exchange_type = broker_info.get(exchange_name, {}).get('type', 'cfd')
    user_config = {
        'warm_up_candles': warm_up_candles,
        'exchanges': {
            exchange_name: {
                'name': exchange_name,
                'fee': 0,
                'type': exchange_type,
                'balance': balance,
                'futures_leverage': leverage,
                'futures_leverage_mode': 'cross',
            }
        }
    }
    set_config(user_config)

    routes = [{'exchange': exchange_name, 'symbol': symbol, 'timeframe': timeframe, 'strategy': strategy_name}]
    data_routes = []

    route_router.initiate(routes, data_routes)
    store.reset()
    store.app.set_session_id(client_id)
    validate_routes(route_router)
    store.candles.init_storage(5000)
    exchange_service.initialize_exchanges_state()
    order_service.initialize_orders_state()
    position_service.initialize_positions_state()

    # Generate synthetic candles (need warmup + trading)
    total_minutes = duration_minutes + warm_up_candles
    raw_candles = generate_scenario(
        scenario=scenario,
        duration_minutes=total_minutes,
        symbol=symbol,
        start_price=start_price,
        volatility=volatility,
        trend_strength=trend_strength,
        volume_base=volume_base,
        seed=seed,
    )

    warmup_candles_arr = raw_candles[:warm_up_candles]
    trading_candles_arr = raw_candles[warm_up_candles:]

    key = jh.key(exchange_name, symbol)
    candles = {
        key: {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': trading_candles_arr,
        }
    }
    warmup_dict = {
        key: {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': warmup_candles_arr,
        }
    }

    # Inject warmup candles
    for c in config['app']['considering_candles']:
        ex, sym = c[0], c[1]
        candle_service.inject_warmup_candles_to_store(
            warmup_dict[jh.key(ex, sym)]['candles'], ex, sym
        )

    sync_publish('progressbar', {'current': 0, 'estimated_remaining_seconds': 0})

    try:
        result = simulator(
            candles,
            run_silently=False,
            hyperparameters=hyperparameters,
            generate_equity_curve=True,
            generate_hyperparameters=True,
            generate_logs=False,
            fast_mode=False,
        )
    except Exception as e:
        import traceback
        sync_publish('notification', {
            'message': f'Playground error: {str(e)}',
            'type': 'error',
        })
        sync_publish('playground_exception', {
            'error': str(e),
            'traceback': traceback.format_exc(),
        })
        return

    if result:
        chart_data = {
            'candles_chart': _get_formatted_candles_for_frontend(),
            'orders_chart': _get_formatted_orders_for_frontend(),
            'add_line_to_candle_chart': _get_add_line_to_candle_chart(),
            'add_extra_line_chart': _get_add_extra_line_chart(),
            'add_horizontal_line_to_candle_chart': _get_add_horizontal_line_to_candle_chart(),
            'add_horizontal_line_to_extra_chart': _get_add_horizontal_line_to_extra_chart(),
        }

        sync_publish('alert', {
            'message': f"Playground simulation completed in {result.get('execution_duration', 0)}s",
            'type': 'success',
        })
        playground_data = {
            'metrics': result.get('metrics'),
            'equity_curve': result.get('equity_curve'),
            'trades': result.get('trades'),
            'hyperparameters': result.get('hyperparameters'),
            'chart_data': chart_data,
            'execution_duration': result.get('execution_duration'),
            'scenario': scenario,
            'logs': result.get('logs', []),
        }
        if 'sessions' in result:
            playground_data['sessions'] = result['sessions']
        sync_publish('playground_result', playground_data)

    from qengine.services.db import database
    database.close_connection()
