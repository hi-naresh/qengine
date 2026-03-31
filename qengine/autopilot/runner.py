"""
AutopilotRunner — main loop for automated hyperparameter tuning with pipeline learning.

Runs repeated backtests, each time:
1. Brain suggests hyperparameters
2. Backtest executes with pipelines attached
3. Results are recorded and pipeline state carried forward
4. Progress published via WebSocket
"""
import os
import time
import copy
import traceback
from datetime import timedelta

from qengine.autopilot.brain import Brain
from qengine.autopilot.learner import Learner
from qengine.autopilot.state import AutopilotState
from qengine.services.redis import sync_publish, is_process_active


class AutopilotRunner:
    """
    Orchestrates repeated backtests with learning.

    Parameters:
        client_id: WebSocket session ID (for publish + cancellation)
        config: backtest config dict (starting_balance, fee, type, exchange, etc.)
        routes: list of route dicts
        data_routes: list of data route dicts
        candles: pre-loaded 1m candles dict
        warmup_candles: pre-loaded warmup candles dict
        pipeline_configs: list of pipeline config dicts (passed to each backtest)
        hp_space: hyperparameter search space for Brain
        max_iterations: maximum number of backtest iterations
        session_dir: directory for persistent state
        objective_key: metric key to optimize (default: 'net_profit_percentage')
        maximize: True = higher is better
    """

    def __init__(
        self,
        client_id: str,
        config: dict,
        routes: list,
        data_routes: list,
        candles: dict,
        warmup_candles: dict = None,
        pipeline_configs: list = None,
        hp_space: dict = None,
        max_iterations: int = 100,
        session_dir: str = None,
        objective_key: str = 'net_profit_percentage',
        maximize: bool = True,
    ):
        self.client_id = client_id
        self.config = config
        self.routes = routes
        self.data_routes = data_routes
        self.candles = candles
        self.warmup_candles = warmup_candles
        self.pipeline_configs = pipeline_configs or []
        self.max_iterations = max_iterations

        if session_dir is None:
            session_dir = os.path.join('storage', 'autopilot', client_id)
        self.session_dir = session_dir

        self.state = AutopilotState(session_dir)
        self.state.objective_key = objective_key
        self.state.maximize = maximize
        self.state.load()  # resume if previous state exists

        self.brain = Brain(hp_space or {}, seed=42)
        self.learner = Learner(session_dir)

    def run(self):
        """Main autopilot loop. Blocks until done or cancelled."""
        sync_publish('autopilot.started', {
            'client_id': self.client_id,
            'max_iterations': self.max_iterations,
            'resumed_from': self.state.iteration,
        })

        try:
            self._loop()
        except Exception as e:
            sync_publish('autopilot.error', {
                'error': f'{type(e).__name__}: {e}',
                'traceback': traceback.format_exc(),
            })
            raise
        finally:
            self.state.save()
            sync_publish('autopilot.finished', self.state.summary)

    def _loop(self):
        from qengine.research.backtest import backtest

        while self.state.iteration < self.max_iterations:
            if not is_process_active(self.client_id):
                break

            iteration = self.state.iteration
            hp = self.brain.suggest(iteration)

            sync_publish('autopilot.iteration_start', {
                'iteration': iteration,
                'hp': hp,
            })

            t0 = time.time()

            # Run backtest with current hp + pipelines
            result = backtest(
                config={**self.config},
                routes=copy.deepcopy(self.routes),
                data_routes=copy.deepcopy(self.data_routes),
                candles=self.candles,
                warmup_candles=self.warmup_candles,
                generate_equity_curve=True,
                hyperparameters=hp if hp else None,
                pipeline_configs=self.pipeline_configs if self.pipeline_configs else None,
            )

            elapsed = time.time() - t0
            metrics = result.get('metrics', {})
            pipeline_stats = result.get('pipeline_stats')

            # Record and learn
            self.state.record(metrics, hp, pipeline_stats)
            obj_value = metrics.get(self.state.objective_key, 0) or 0
            self.brain.report(iteration, obj_value)
            self.state.save()

            # Publish progress
            sync_publish('autopilot.iteration_end', {
                'iteration': iteration,
                'metrics': metrics,
                'hp': hp,
                'pipeline_stats': pipeline_stats,
                'elapsed_seconds': round(elapsed, 2),
                'best': self.state.summary,
            })


def run_autopilot(
    client_id: str,
    config: dict,
    routes: list,
    data_routes: list,
    start_date: str,
    finish_date: str,
    exchange: str,
    pipeline_configs: list = None,
    hp_space: dict = None,
    max_iterations: int = 100,
    objective_key: str = 'net_profit_percentage',
    maximize: bool = True,
) -> None:
    """
    Entry point for process_manager.add_task().
    Loads candles once, then runs the autopilot loop.
    """
    from qengine.config import config as qe_config, set_config
    from qengine.modes.backtest_mode import load_candles
    from qengine.services.validators import validate_routes
    from qengine.services import exchange_service, order_service, position_service
    from qengine.routes import router
    from qengine.store import store
    import qengine.helpers as jh

    qe_config['app']['trading_mode'] = 'backtest'

    # Format config for set_config
    exchange_config = {
        'balance': config['starting_balance'],
        'fee': config['fee'],
        'type': config['type'],
        'name': exchange,
    }
    if exchange_config['type'] in ('futures', 'cfd'):
        exchange_config['futures_leverage'] = config.get('futures_leverage', 1)
        exchange_config['futures_leverage_mode'] = config.get('futures_leverage_mode', 'cross')

    formatted_config = {
        'exchanges': {exchange: exchange_config},
        'logging': {
            'balance_update': False,
            'order_cancellation': False,
            'order_execution': False,
            'order_submission': False,
            'position_closed': False,
            'position_increased': False,
            'position_opened': False,
            'position_reduced': False,
            'shorter_period_candles': False,
            'trading_candles': False,
        },
        'warm_up_candles': config.get('warm_up_candles', 0),
    }
    set_config(formatted_config)

    # Add exchange to routes
    for r in routes:
        r['exchange'] = exchange
    for r in data_routes:
        r['exchange'] = exchange

    # Initialize enough state to load candles
    router.initiate(routes, data_routes)
    store.reset()
    store.candles.init_storage(5000)
    exchange_service.initialize_exchanges_state()
    order_service.initialize_orders_state()
    position_service.initialize_positions_state()

    # Load candles once
    sync_publish('autopilot.loading_candles', {'start': start_date, 'finish': finish_date})
    warmup_candles, candles = load_candles(
        jh.date_to_timestamp(start_date),
        jh.date_to_timestamp(finish_date),
    )

    from qengine.config import reset_config
    reset_config()
    store.reset()

    # Build research-style config
    research_config = {
        'starting_balance': config['starting_balance'],
        'fee': config['fee'],
        'type': config['type'],
        'exchange': exchange,
        'warm_up_candles': config.get('warm_up_candles', 0),
    }
    if config['type'] in ('futures', 'cfd'):
        research_config['futures_leverage'] = config.get('futures_leverage', 1)
        research_config['futures_leverage_mode'] = config.get('futures_leverage_mode', 'cross')

    runner = AutopilotRunner(
        client_id=client_id,
        config=research_config,
        routes=routes,
        data_routes=data_routes,
        candles=candles,
        warmup_candles=warmup_candles,
        pipeline_configs=pipeline_configs,
        hp_space=hp_space,
        max_iterations=max_iterations,
        objective_key=objective_key,
        maximize=maximize,
    )
    runner.run()
