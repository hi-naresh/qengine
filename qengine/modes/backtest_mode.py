import time
import re
from typing import Dict, List, Tuple, Optional
import numpy as np
import qengine.helpers as jh
import qengine.services.metrics as stats
from qengine import exceptions
from qengine.config import config
from qengine.enums import timeframes, order_types
from qengine.models import Order, Position
from qengine.models.CFDExchange import CFDExchange
from qengine.modes.utils import save_daily_portfolio_balance
from qengine.candle_pipelines import BaseCandlesPipeline
from qengine.routes import router
from qengine.services import charts
from qengine.services import report
from qengine.services import candle_service
from qengine.services.file import store_logs
from qengine.services.validators import validate_routes
from qengine.store import store
from qengine.services import logger
from qengine.services.failure import register_custom_exception_handler
from qengine.services.redis import sync_publish, is_process_active
from qengine.services import order_service
from timeloop import Timeloop
from datetime import timedelta
from qengine.services.progressbar import Progressbar
from qengine.constants import TIMEFRAME_TO_ONE_MINUTES
from qengine.services import candle_service, order_service, position_service, exchange_service
from qengine.services import ticket_service
from qengine.core.market_hours import MarketHours

_market_hours = MarketHours()


def run(
        client_id: str,
        debug_mode: bool,
        user_config: dict,
        exchange: str,
        routes: List[Dict[str, str]],
        data_routes: List[Dict[str, str]],
        start_date: str,
        finish_date: str,
        candles: dict = None,
        chart: bool = False,
        tradingview: bool = False,
        csv: bool = False,
        json: bool = False,
        fast_mode: bool = False,
        benchmark: bool = False,
        hyperparameters: dict = None,
        cost_model: bool = True,
        user_id: str = None
) -> None:
    if not jh.is_unit_testing():
        # at every second, we check to see if it's time to execute stuff
        status_checker = Timeloop()

        @status_checker.job(interval=timedelta(seconds=1))
        def handle_time():
            if is_process_active(client_id) is False:
                raise exceptions.Termination

        status_checker.start()

    from qengine.config import config
    config['app']['trading_mode'] = 'backtest'
    config['app']['cost_model'] = cost_model

    # debug flag
    config['app']['debug_mode'] = debug_mode

    register_custom_exception_handler()

    _execute_backtest(
        client_id, debug_mode, user_config, exchange, routes, data_routes, start_date, finish_date, candles, chart,
        tradingview, csv, json, fast_mode, benchmark, hyperparameters, user_id=user_id
    )


def _execute_backtest(
        client_id: str,
        debug_mode: bool,
        user_config: dict,
        exchange: str,
        routes: List[Dict[str, str]],
        data_routes: List[Dict[str, str]],
        start_date: str,
        finish_date: str,
        candles: dict = None,
        chart: bool = False,
        tradingview: bool = False,
        csv: bool = False,
        json: bool = False,
        fast_mode: bool = False,
        benchmark: bool = False,
        hyperparameters: dict = None,
        user_id: str = None
):
    """
    Executes the backtest that has been initiated from within the dashboard. The purpose of extracting these
    functionalities into this function is so that in case it fails due to a missing data route, it can add
    it and then re-execute itself.
    """
    from qengine.config import set_config

    # inject config
    if not jh.is_unit_testing():
        set_config(user_config)
    # add exchange to routes
    for r in routes:
        r['exchange'] = exchange
    for r in data_routes:
        r['exchange'] = exchange
    
    # set routes
    router.initiate(routes, data_routes)
    # reset store
    store.reset()
    # set session id
    store.app.set_session_id(client_id)
    # validate routes
    validate_routes(router)
    # initiate candle store
    store.candles.init_storage(5000)
    # initialize exchanges state
    exchange_service.initialize_exchanges_state()
    # initialize orders state
    order_service.initialize_orders_state()
    # initialize positions state
    position_service.initialize_positions_state()

    # Store backtest session in database (only for UI dashboard, not for CLI/research)
    if not jh.should_execute_silently():
        from qengine.models.BacktestSession import store_backtest_session, update_backtest_session_state
        store_backtest_session(
            id=client_id,
            status='running',
            user_id=user_id
        )
        # Persist route/config info so history labels show strategy/symbol/dates
        try:
            update_backtest_session_state(client_id, {
                'exchange': exchange,
                'routes': routes,
                'data_routes': data_routes,
                'start_date': start_date,
                'finish_date': finish_date,
            })
        except Exception:
            pass

    # Validate dates before loading candles
    if not start_date or not finish_date:
        raise exceptions.CandlesNotFound('Both start date and end date are required.')
    if start_date >= finish_date:
        raise exceptions.CandlesNotFound('End date must be after start date.')

    # load historical candles
    if candles is None:
        try:
            warmup_candles, candles = load_candles(
                jh.date_to_timestamp(start_date),
                jh.date_to_timestamp(finish_date)
            )
            _handle_warmup_candles(warmup_candles, start_date)
        except exceptions.CandlesNotFound as e:
            _handle_sync_no_candles(e, start_date, exchange)
        except exceptions.CandleNotFoundInDatabase as e:
            _handle_sync_no_candles(e, start_date, exchange)

    if not jh.should_execute_silently():
        sync_publish('general_info', {
            'session_id': jh.get_session_id(),
            'debug_mode': str(config['app']['debug_mode']),
        })
        # candles info
        key = f"{config['app']['considering_candles'][0][0]}-{config['app']['considering_candles'][0][1]}"
        sync_publish('candles_info', stats.candles_info(candles[key]['candles']))
        # routes info
        sync_publish('routes_info', stats.routes(router.routes))

    # run backtest simulation
    result = None
    try:
        result = simulator(
            candles,
            run_silently=jh.should_execute_silently(),
            hyperparameters=hyperparameters,
            generate_tradingview=tradingview,
            generate_csv=csv,
            generate_json=json,
            generate_equity_curve=True,
            benchmark=benchmark,
            generate_hyperparameters=True,
            generate_logs=debug_mode,
            fast_mode=fast_mode,
        )
    except exceptions.RouteNotFound as e:
        # Extract exchange, symbol, and timeframe using regular expressions
        match = re.search(r"symbol='(.+?)', timeframe='(.+?)'", str(e))
        if match:
            symbol = match.group(1)
            timeframe = match.group(2)
            # Adjust data_routes to include the missing route
            data_routes.append({
                'exchange': exchange,
                'symbol': symbol,
                'timeframe': timeframe
            })
            # to prevent an issue with warmupcandles being None
            candles = None
            # notify the user about the missing data route and retry the backtest simulation
            sync_publish('notification', {
                'message': f'Missing data route for "{symbol}" with "{timeframe}" timeframe. Adding it and retrying...',
                'type': 'error'
            })
            # retry the backtest simulation
            _execute_backtest(
                client_id, debug_mode, user_config, exchange, routes, data_routes, start_date, finish_date, candles,
                chart, tradingview, csv, json, fast_mode, benchmark, hyperparameters, user_id=user_id
            )
            return
        else:
            raise e
    except Exception as e:
        # Store exception in database (only for UI dashboard)
        if not jh.should_execute_silently():
            import traceback
            from qengine.models.BacktestSession import store_backtest_session_exception, update_backtest_session_status
            store_backtest_session_exception(client_id, str(e), traceback.format_exc())
            update_backtest_session_status(client_id, 'stopped')
        raise

    if result and not jh.should_execute_silently():
        # Prepare chart data if requested (call formatting functions once and cache)
        chart_data = None
        if chart:
            chart_data = {
                'candles_chart': _get_formatted_candles_for_frontend(),
                'orders_chart': _get_formatted_orders_for_frontend(),
                'add_line_to_candle_chart': _get_add_line_to_candle_chart(),
                'add_extra_line_chart': _get_add_extra_line_chart(),
                'add_horizontal_line_to_candle_chart': _get_add_horizontal_line_to_candle_chart(),
                'add_horizontal_line_to_extra_chart': _get_add_horizontal_line_to_extra_chart()
            }

        # Capture strategy codes for each route
        strategy_codes = {}
        import os
        for r in router.routes:
            key = f"{r.exchange}-{r.symbol}"
            if key not in strategy_codes:
                try:
                    from qengine.services.strategy_handler import find_strategy_file
                    strategy_path = find_strategy_file(r.strategy_name)
                    if strategy_path and os.path.exists(strategy_path):
                        with open(strategy_path, 'r') as f:
                            content = f.read()
                        strategy_codes[key] = content
                except Exception:
                    pass

        # Generate full HTML report
        _generate_full_report(client_id, result)

        # Update backtest session in database with results BEFORE publishing to WebSocket
        # (prevents race condition where frontend fetches empty DB before results are stored)
        from qengine.models.BacktestSession import update_backtest_session_results, update_backtest_session_status
        # Bundle all curve data into equity_curve for DB storage
        equity_curve_bundle = result.get('equity_curve')
        if equity_curve_bundle and (result.get('floating_pnl_curve') or result.get('margin_usage_curve')):
            equity_curve_bundle = {
                'equity': result['equity_curve'],
                'floating_pnl': result.get('floating_pnl_curve'),
                'margin_usage': result.get('margin_usage_curve'),
            }
        # Collect export file paths for history downloads
        export_paths = {}
        if result.get('tradingview'):
            export_paths['tradingview'] = result['tradingview']
        if result.get('csv'):
            export_paths['csv'] = result['csv']
        if result.get('json'):
            export_paths['json'] = result['json']
        full_report_path = f'storage/full-reports/{client_id}.html'
        if os.path.exists(full_report_path):
            export_paths['full_report'] = full_report_path

        # Pipeline stats for DB (strip bulky cycle_hp_log)
        pipeline_stats_for_db = None
        if result.get('pipeline_stats'):
            pipeline_stats_for_db = {}
            for rk, ps in result['pipeline_stats'].items():
                pipeline_stats_for_db[rk] = {k: v for k, v in ps.items() if k != 'cycle_hp_log'}

        # Strip 1m candles from chart_data before DB storage — they can be huge
        # (e.g. 1yr = ~375K candles → hundreds of MB as JSON) and cause PostgreSQL
        # "invalid memory alloc request size" errors. Frontend handles missing 1m gracefully.
        chart_data_for_db = None
        if chart_data:
            chart_data_for_db = dict(chart_data)
            if chart_data_for_db.get('candles_chart'):
                chart_data_for_db['candles_chart'] = [
                    {k: v for k, v in entry.items() if k != 'candles_1m'}
                    for entry in chart_data_for_db['candles_chart']
                ]

        update_backtest_session_results(
            id=client_id,
            metrics=result.get('metrics'),
            equity_curve=equity_curve_bundle,
            trades=result.get('trades'),
            hyperparameters=result.get('hyperparameters'),
            chart_data=chart_data_for_db,
            execution_duration=result.get('execution_duration'),
            strategy_codes=strategy_codes if strategy_codes else None,
            logs=result.get('logs'),
            sessions=result.get('sessions'),
            pipeline_stats=pipeline_stats_for_db,
            export_paths=export_paths if export_paths else None,
        )
        update_backtest_session_status(client_id, 'finished')

        # Publish results via WebSocket AFTER DB is updated
        if result.get('alert'):
            sync_publish('alert', {
                'message': result['alert'],
                'type': 'error'
            })
        else:
            sync_publish('alert', {
                'message': f"Successfully executed backtest simulation in: {result['execution_duration']} seconds",
                'type': 'success'
            })
        sync_publish('hyperparameters', result['hyperparameters'])
        sync_publish('equity_curve', result['equity_curve'], compression=True)
        if result.get('floating_pnl_curve'):
            sync_publish('floating_pnl_curve', result['floating_pnl_curve'], compression=True)
        if result.get('margin_usage_curve'):
            sync_publish('margin_usage_curve', result['margin_usage_curve'], compression=True)
        sync_publish('trades', result['trades'], compression=True)
        if 'sessions' in result:
            sync_publish('sessions', result['sessions'], compression=True)
        # Publish pipeline stats (if any pipelines were active)
        # Sent once at completion with compression — include all data except bulky cycle_hp_log
        if result.get('pipeline_stats'):
            ps_for_ws = {}
            for rk, ps in result['pipeline_stats'].items():
                ps_for_ws[rk] = {k: v for k, v in ps.items() if k != 'cycle_hp_log'}
            sync_publish('pipeline_stats', ps_for_ws, compression=True)
        # Publish backtest logs
        if result.get('logs'):
            sync_publish('backtest_logs', result['logs'], compression=True)
        # Publish metrics last - frontend uses this as the "completion" signal
        sync_publish('metrics', result['metrics'])

    # close database connection
    from qengine.services.db import database
    database.close_connection()
    

def _handle_sync_no_candles(e, start_date, exchange):
    # Extract a clean human-readable message
    error_str = str(e)
    # If the exception wraps a dict, extract the 'message' field
    if error_str.startswith('{') or error_str.startswith("{'"):
        try:
            import ast
            d = ast.literal_eval(error_str)
            if isinstance(d, dict) and 'message' in d:
                error_str = d['message']
        except Exception:
            pass

    match = re.search(r"for (.*?) on (.*?)[\.\s]", error_str)
    symbol = match.group(1) if match else 'unknown'

    warmup_num = jh.get_config('env.data.warmup_candles_num', 210)
    if warmup_num > 0 and 'warmup' not in error_str.lower():
        message = (
            f'Not enough candle data for {symbol} on {exchange}. '
            f'Your start date ({start_date}) needs {warmup_num} warmup candles before it. '
            f'Try moving your start date forward.'
        )
    else:
        message = error_str

    raise exceptions.CandlesNotFound(message)


def _get_formatted_candles_for_frontend():
    arr = []
    for r in router.routes:
        candles_arr = candle_service.get_candles(r.exchange, r.symbol, r.timeframe)
        # Find the index where the starting time actually begins.
        starting_index = 0
        for i, c in enumerate(candles_arr):
            if c[0] >= store.app.starting_time:
                starting_index = i
                break

        candles = [{
            'time': int(c[0]/1000),
            'open': c[1],
            'close': c[2],
            'high': c[3],
            'low': c[4],
            'volume': c[5]
        } for c in candles_arr[starting_index:]]

        # Also include 1m candles for timeframe switching on the frontend
        candles_1m = []
        if r.timeframe != '1m':
            candles_1m_arr = candle_service.get_candles(r.exchange, r.symbol, '1m')
            start_1m = 0
            for i, c in enumerate(candles_1m_arr):
                if c[0] >= store.app.starting_time:
                    start_1m = i
                    break
            candles_1m = [{
                'time': int(c[0]/1000),
                'open': c[1],
                'close': c[2],
                'high': c[3],
                'low': c[4],
                'volume': c[5]
            } for c in candles_1m_arr[start_1m:]]

        arr.append({
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'candles': candles,
            'candles_1m': candles_1m,
        })
    return arr


def _get_formatted_orders_for_frontend():
    arr = []
    for r in router.routes:
        arr.append({
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'orders': r.strategy._executed_orders
        })
    return arr


def _get_add_line_to_candle_chart():
    arr = []
    for r in router.routes:
        arr.append({
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'lines': r.strategy._add_line_to_candle_chart_values
        })
    return arr


def _get_add_extra_line_chart():
    arr = []
    for r in router.routes:
        arr.append({
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'charts': r.strategy._add_extra_line_chart_values
        })
    return arr


def _get_add_horizontal_line_to_candle_chart():
    arr = []
    for r in router.routes:
        arr.append({
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'lines': r.strategy._add_horizontal_line_to_candle_chart_values
        })
    return arr


def _get_add_horizontal_line_to_extra_chart():
    arr = []
    for r in router.routes:
        arr.append({
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'lines': r.strategy._add_horizontal_line_to_extra_chart_values
        })
    return arr


def _handle_missing_candles(exchange: str, symbol: str, start_date: int, message: str = None):
    """Helper function to handle missing candles scenarios"""
    formatted_date = jh.timestamp_to_date(start_date)
    if message is None:
        message = f'No candle data found for {symbol} on {exchange} starting from {formatted_date}. Check that you have imported candles for this date range.'

    raise exceptions.CandlesNotFound(message)


def load_candles(start_date: int, finish_date: int) -> Tuple[dict, dict]:
    warmup_num = jh.get_config('env.data.warmup_candles_num', 210)
    max_timeframe = jh.max_timeframe(config['app']['considering_timeframes'])

    # load and add required warm-up candles for backtest, and then Prepare trading candles
    trading_candles = {}
    warmup_candles = {}
    for c in config['app']['considering_candles']:
        exchange, symbol = c[0], c[1]

        # First try loading with warmup from before start_date
        warmup_candles_arr, trading_candle_arr = candle_service.get_candles_from_db(
            exchange, symbol, max_timeframe, start_date, finish_date, warmup_num, caching=True, is_for_engine=True
        )

        # Ensure that trading_candle_arr is not None or empty
        if trading_candle_arr is None or (isinstance(trading_candle_arr, np.ndarray) and trading_candle_arr.size == 0):
            _handle_missing_candles(
                exchange,
                symbol,
                start_date,
                f"Missing trading candles for {symbol} on {exchange}"
            )

        # Check that the last trading candle covers the requested finish date.
        if trading_candle_arr[-1][0] < (finish_date - 60_000):
            _handle_missing_candles(exchange, symbol, start_date)

        # If warmup candles are insufficient (empty or too few), carve warmup from the
        # beginning of trading candles so the backtester can still run.
        warmup_is_empty = (
            warmup_candles_arr is None
            or (isinstance(warmup_candles_arr, np.ndarray) and warmup_candles_arr.ndim == 1)
            or (isinstance(warmup_candles_arr, np.ndarray) and len(warmup_candles_arr) == 0)
        )
        if warmup_num > 0 and warmup_is_empty and len(trading_candle_arr) > warmup_num:
            # Use first warmup_num trading candles as warmup, rest as actual trading
            warmup_candles_arr = trading_candle_arr[:warmup_num]
            trading_candle_arr = trading_candle_arr[warmup_num:]

        # add trading candles
        trading_candles[jh.key(exchange, symbol)] = {
            'exchange': exchange,
            'symbol': symbol,
            'candles': trading_candle_arr
        }

        warmup_candles[jh.key(exchange, symbol)] = {
            'exchange': exchange,
            'symbol': symbol,
            'candles': warmup_candles_arr
        }

    return warmup_candles, trading_candles


def _handle_warmup_candles(warmup_candles: dict, start_date: str) -> None:
    try:
        for c in config['app']['considering_candles']:
            exchange, symbol = c[0], c[1]
            candle_service.inject_warmup_candles_to_store(warmup_candles[jh.key(exchange, symbol)]['candles'], exchange, symbol)
    except ValueError as e:
        # Extract exchange and symbol from error message
        match = re.search(r"for (.*?)/(.*?)\?", str(e))
        if match:
            exchange, symbol = match.groups()
            
            # Calculate warmup start date using the same logic as load_candles()
            warmup_num = jh.get_config('env.data.warmup_candles_num', 210)
            max_timeframe = jh.max_timeframe(config['app']['considering_timeframes'])
            # Convert max_timeframe to minutes and multiply by warmup_num
            warmup_minutes = TIMEFRAME_TO_ONE_MINUTES[max_timeframe] * warmup_num
            warmup_start_timestamp = jh.date_to_timestamp(start_date) - (warmup_minutes * 60_000)
            warmup_start_date = jh.timestamp_to_date(warmup_start_timestamp)
            # Publish the missing candles error to the frontend
            # This will trigger the alert in the BacktestTab.vue component
            # so that the user can import the missing candles
            sync_publish(
                "missing_candles",
                {
                    "message": f'Missing warmup candles for {symbol} on {exchange} from {warmup_start_date}',
                    "symbol": symbol,
                    "exchange": exchange,
                    "start_date": warmup_start_date,
                },
            )
            raise exceptions.CandlesNotFound(str(e))
        raise e


def simulator(*args, fast_mode: bool = False, **kwargs) -> dict:
    if fast_mode:
        return _skip_simulator(*args, **kwargs)

    return _step_simulator(*args, **kwargs)


def _step_simulator(
        candles: dict,
        run_silently: bool,
        hyperparameters: dict = None,
        generate_tradingview: bool = False,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_hyperparameters: bool = False,
        generate_logs: bool = False,
        with_candles_pipeline: bool = True,
        candles_pipeline_class = None,
        candles_pipeline_kwargs: dict = None,
) -> dict:
    # In case generating logs is specifically demanded, the debug mode must be enabled.
    if generate_logs:
        config['app']['debug_mode'] = True

    begin_time_track = time.time()

    key = f"{config['app']['considering_candles'][0][0]}-{config['app']['considering_candles'][0][1]}"
    first_candles_set = candles[key]['candles']

    length = _simulation_minutes_length(candles)
    _prepare_times_before_simulation(candles)
    candles_pipelines = _prepare_routes(
        hyperparameters=hyperparameters,
        with_candles_pipeline=with_candles_pipeline,
        candles_pipeline_class=candles_pipeline_class,
        candles_pipeline_kwargs=candles_pipeline_kwargs
    )

    # add initial balance
    save_daily_portfolio_balance(is_initial=True)

    # Log backtest start
    route_info = ', '.join([f"{r.symbol} {r.timeframe} ({r.strategy_name})" for r in router.routes])
    store.logs.add(f'Backtest started: {route_info}', 'market')

    progressbar = Progressbar(length, step=420)
    last_update_time = None
    margin_error_msg = None
    _prev_market_open = {}  # track market open/close state per symbol
    for i in range(length):
        # update time
        store.app.time = first_candles_set[i][0] + 60_000
        current_timestamp = first_candles_set[i][0]

        # Check for overnight swap at rollover time (5pm NY) — only if cost model is enabled
        if config['app'].get('cost_model', True) and _market_hours.is_rollover_time(current_timestamp):
            for r in router.routes:
                p = store.positions.get_position(r.exchange, r.symbol)
                if p and p.is_open:
                    e = store.exchanges.get_exchange(r.exchange)
                    if isinstance(e, CFDExchange):
                        # CFD mode: charge swap per ticket (gross exposure), not net qty
                        if p.is_cfd_mode and p._tickets:
                            for ticket in p._tickets:
                                e.charge_overnight_swap(r.symbol, ticket.qty, ticket.type)
                        else:
                            e.charge_overnight_swap(r.symbol, p.qty, p.type)

        # add candles
        for j in candles:
            candles_pipeline = candles_pipelines[j]
            short_candle = get_candles_from_pipeline(candles_pipeline, candles[j]['candles'], i)
            if i != 0:
                previous_short_candle = candles[j]['candles'][i - 1]
                short_candle = _get_fixed_jumped_candle(previous_short_candle, short_candle)
            exchange = candles[j]['exchange']
            symbol = candles[j]['symbol']

            candle_service.add_candle(short_candle, exchange, symbol, '1m', with_execution=False,
                                     with_generation=False)

            # print short candle
            if jh.is_debuggable('shorter_period_candles'):
                candle_service.print_candle(short_candle, True, symbol)

            _simulate_price_change_effect(short_candle, exchange, symbol)

            # generate and add candles for bigger timeframes
            for timeframe in config['app']['considering_timeframes']:
                # for 1m, no work is needed
                if timeframe == '1m':
                    continue

                count = TIMEFRAME_TO_ONE_MINUTES[timeframe]
                # until = count - ((i + 1) % count)

                if (i + 1) % count == 0:
                    generated_candle = candle_service.generate_candle_from_one_minutes(
                        timeframe,
                        candles[j]['candles'][(i - (count - 1)):(i + 1)]
                    )

                    candle_service.add_candle(
                        generated_candle, 
                        exchange, 
                        symbol, 
                        timeframe, 
                        with_execution=False,
                        with_generation=False
                    )

        last_update_time = _update_progress_bar(progressbar, run_silently, i, candle_step=420,
                                                last_update_time=last_update_time)

        # now that all new generated candles are ready, execute
        margin_error = None
        for r in router.routes:
            # Skip strategy execution if market is closed for this symbol
            # (skip_market_hours is set by playground mode to ensure synthetic data always trades)
            if not config['app'].get('skip_market_hours', False):
                e = store.exchanges.get_exchange(r.exchange)
                if isinstance(e, CFDExchange):
                    is_open = _market_hours.is_market_open(r.symbol, current_timestamp)
                    sym_key = f"{r.exchange}-{r.symbol}"
                    was_open = _prev_market_open.get(sym_key)
                    if was_open is not None and is_open != was_open:
                        state_txt = 'OPENED' if is_open else 'CLOSED'
                        store.logs.add(
                            f'Market {state_txt} for {r.symbol} at {jh.timestamp_to_time(current_timestamp)[:19]}',
                            'market'
                        )
                    _prev_market_open[sym_key] = is_open
                    if not is_open:
                        continue

            count = TIMEFRAME_TO_ONE_MINUTES[r.timeframe]
            try:
                # 1m timeframe
                if r.timeframe == timeframes.MINUTE_1:
                    r.strategy._execute()
                elif (i + 1) % count == 0:
                    # print candle
                    if jh.is_debuggable('trading_candles'):
                        candle_service.print_candle(candle_service.get_current_candle(r.exchange, r.symbol, r.timeframe), False,
                                     r.symbol)
                    r.strategy._execute()

                order_service.update_active_orders(r.exchange, r.symbol)
            except exceptions.InsufficientMargin as e:
                margin_error = e
                break

        if margin_error is not None:
            margin_error_msg = str(margin_error)
            # Log the margin error and break out of the simulation
            store.logs.add(f'MARGIN CALL: Backtest stopped early — {margin_error_msg}', 'market')
            logger.info(f'Backtest stopped early: {margin_error_msg}')
            if not run_silently:
                sync_publish('notification', {
                    'message': f'Insufficient margin — backtest stopped early. {margin_error_msg}',
                    'type': 'error'
                })
            break

        # now check to see if there's any MARKET orders waiting to be executed
        order_service.execute_simulated_market_orders()

        # Track per-session stats (floating PnL, margin, equity usage) every candle
        _update_session_stats(margin_error is not None)

        if i != 0 and i % 1440 == 0:
            save_daily_portfolio_balance()

    _finish_progress_bar(progressbar, run_silently)

    execution_duration = 0
    if not run_silently:
        # print executed time for the backtest session
        finish_time_track = time.time()
        execution_duration = round(finish_time_track - begin_time_track, 2)

    for r in router.routes:
        r.strategy._terminate()
        order_service.execute_simulated_market_orders()

    # now that backtest simulation is finished, add finishing balance
    save_daily_portfolio_balance()

    # set the ending time for the backtest session
    store.app.ending_time = store.app.time + 60_000

    # Log backtest completion summary
    total_trades = len(store.closed_trades.trades) if store.closed_trades.trades else 0
    store.logs.add(f'Backtest completed: {total_trades} trades in {execution_duration}s', 'market')

    result = _generate_outputs(
        candles,
        generate_tradingview=generate_tradingview,
        generate_csv=generate_csv,
        generate_json=generate_json,
        generate_equity_curve=generate_equity_curve,
        benchmark=benchmark,
        generate_hyperparameters=generate_hyperparameters,
        generate_logs=generate_logs,
    )
    result['execution_duration'] = execution_duration
    if margin_error_msg:
        result['alert'] = f'Insufficient margin — backtest stopped early. {margin_error_msg}'
    return result


def _simulation_minutes_length(candles: dict) -> int:
    key = f"{config['app']['considering_candles'][0][0]}-{config['app']['considering_candles'][0][1]}"
    first_candles_set = candles[key]["candles"]
    return len(first_candles_set)


def _prepare_times_before_simulation(candles: dict) -> None:
    # result = {}
    # begin_time_track = time.time()
    key = f"{config['app']['considering_candles'][0][0]}-{config['app']['considering_candles'][0][1]}"
    first_candles_set = candles[key]["candles"]
    # length = len(first_candles_set)
    # to preset the array size for performance
    try:
        store.app.starting_time = first_candles_set[0][0]
    except IndexError:
        raise IndexError('Check your "warm_up_candles" config value')
    store.app.time = first_candles_set[0][0]


def _prepare_routes(
                    hyperparameters: dict = None,
                    with_candles_pipeline: bool = True,
                    candles_pipeline_class = None,
                    candles_pipeline_kwargs: dict = None,
                    ) -> Dict[str, BaseCandlesPipeline | None]:
    # initiate strategies
    candles_pipeline = {}

    for r in router.routes:
        # if the r.strategy is str read it from file
        if isinstance(r.strategy_name, str):
            StrategyClass = jh.get_strategy_class(r.strategy_name)
        # else it is a class object so just use it
        else:
            StrategyClass = r.strategy_name

        try:
            r.strategy = StrategyClass()
        except TypeError:
            raise exceptions.InvalidStrategy(
                "Strategy validation failed. Make sure your strategy has the mandatory methods such as should_long(), "
                "go_long(), etc. For working examples, visit: https://docs.qengine.dev/strategies"
            )
        except:
            raise

        r.strategy.name = r.strategy_name
        r.strategy.exchange = r.exchange
        r.strategy.symbol = r.symbol
        r.strategy.timeframe = r.timeframe

        # read the dna from strategy's dna() and use it for injecting inject hyperparameters
        # first convert DNS string into hyperparameters
        if len(r.strategy.dna()) > 0 and hyperparameters is None:
            hyperparameters = jh.dna_to_hp(
                r.strategy.hyperparameters(), r.strategy.dna()
            )

        # inject hyperparameters sent within the optimize mode
        if hyperparameters is not None:
            r.strategy.hp = hyperparameters

        # init few objects that couldn't be initiated in Strategy __init__
        # it also injects hyperparameters into self.hp in case the route does not uses any DNAs
        r.strategy._init_objects()

        # Attach autopilot pipelines if configured
        pipeline_configs = config.get('app', {}).get('pipelines')
        if pipeline_configs:
            from qengine.framework import create_pipelines
            r.strategy._pipelines = create_pipelines(pipeline_configs)

        # monte-carlo simulation
        if with_candles_pipeline:
            if candles_pipeline_class is not None:
                # Use the provided pipeline class with kwargs if available
                kwargs = candles_pipeline_kwargs or {}
                candles_pipeline[jh.key(r.exchange, r.symbol)] = candles_pipeline_class(**kwargs)
            else:
                # Otherwise, fall back to the strategy's pipeline
                candles_pipeline[jh.key(r.exchange, r.symbol)] = r.strategy.candles_pipeline()
        else: # normal backtest
            candles_pipeline[jh.key(r.exchange, r.symbol)] = None

        store.positions.get_position(r.exchange, r.symbol).strategy = r.strategy

    # Ensure pipelines exist for data routes as well (no strategy attached)
    # Keys in `candles` include both trading and data routes; provide a pipeline (or None) for each
    for dr in getattr(router, 'data_routes', []) or []:
        key = jh.key(dr.exchange, dr.symbol)
        if key in candles_pipeline:
            continue
        if with_candles_pipeline and candles_pipeline_class is not None:
            kwargs = candles_pipeline_kwargs or {}
            candles_pipeline[key] = candles_pipeline_class(**kwargs)
        else:
            candles_pipeline[key] = None

    return candles_pipeline


def get_candles_from_pipeline(candles_pipeline: Optional[BaseCandlesPipeline], candles: np.ndarray, i: int, candles_step: int = -1) -> np.ndarray:
    if candles_pipeline is None:
        if candles_step == -1:
            return candles[i]
        else:
            return candles[i: i+candles_step]
    return candles_pipeline.get_candles(candles[i: i + candles_pipeline._batch_size], i, candles_step)


def _get_live_stats() -> dict:
    """Gather live execution stats for progress reporting."""
    stats = {}
    try:
        total_pnl = 0.0
        total_floating = 0.0
        total_margin = 0.0
        equity = 0.0
        session_num = None
        total_trades = 0

        for r in router.routes:
            e = store.exchanges.get_exchange(r.exchange)
            wallet = e.assets.get(jh.app_currency(), 0)
            pos = store.positions.get_position(r.exchange, r.symbol)

            floating = pos.pnl if pos and pos.is_open else 0.0
            margin = pos.margin_used if pos and pos.is_open else 0.0
            total_floating += floating
            total_margin += margin
            equity = wallet + total_floating

            # Get session number from strategy vars (hedge strategies)
            if r.strategy and hasattr(r.strategy, 'vars') and isinstance(r.strategy.vars, dict):
                sn = r.strategy.vars.get('session_number')
                if sn is not None:
                    session_num = sn

        # Count completed trades
        total_trades = store.closed_trades.count

        stats['equity'] = round(equity, 2)
        stats['floating_pnl'] = round(total_floating, 2)
        stats['margin_used'] = round(total_margin, 2)
        stats['trades'] = total_trades
        if session_num is not None:
            stats['session'] = session_num

        # Pipeline live stats (danger score, gate/abort counts)
        # Access raw pipeline state directly (avoid expensive get_stats() analytics)
        for r in router.routes:
            if r.strategy and hasattr(r.strategy, '_pipelines') and r.strategy._pipelines:
                try:
                    for p in r.strategy._pipelines.pipelines:
                        if hasattr(p, 'scorer'):
                            stats['pipeline_danger'] = round(p.scorer.current_score, 4)
                            ds = p._stats.danger_scores
                            if ds:
                                vals = [d[1] for d in ds]
                                stats['pipeline_danger_mean'] = round(sum(vals) / len(vals), 4)
                                # Last 60 danger scores for live mini-chart
                                stats['pipeline_danger_history'] = [
                                    [d[0], d[1]] for d in ds[-60:]
                                ]
                        if hasattr(p, '_stats'):
                            stats['pipeline_blocks'] = p._stats.entries_blocked
                            stats['pipeline_aborts'] = p._stats.aborts_triggered
                            stats['pipeline_cycles'] = p._stats.cycles_completed
                            # Recent decisions for live feed (last 5 new ones)
                            gd = p._stats.gate_decisions
                            ad = p._stats.abort_decisions
                            recent = []
                            for g in gd[-5:]:
                                recent.append({
                                    'type': 'gate',
                                    'ts': g['ts'],
                                    'danger': g['danger'],
                                    'threshold': g.get('threshold'),
                                    'decision': 'ALLOWED' if g['allowed'] else 'BLOCKED',
                                })
                            for a in ad[-5:]:
                                if a['action'] == 'abort':
                                    recent.append({
                                        'type': 'abort',
                                        'ts': a['ts'],
                                        'danger': a['danger'],
                                        'level': a.get('level'),
                                        'decision': 'ABORT',
                                    })
                            recent.sort(key=lambda x: x.get('ts', 0))
                            stats['pipeline_decisions'] = recent[-5:]
                        break
                except Exception:
                    pass
                break
    except Exception:
        pass

    # Stream recent logs (send new entries since last update)
    try:
        all_logs = store.logs.info
        last_sent = getattr(_get_live_stats, '_last_log_idx', 0)
        if len(all_logs) > last_sent:
            new_logs = all_logs[last_sent:]
            # Send last 20 new entries max per tick to avoid bloat
            stats['recent_logs'] = [
                {'timestamp': jh.timestamp_to_time(l['timestamp'])[:19] if l.get('timestamp') else '',
                 'type': l.get('type', ''),
                 'message': l.get('message', '')}
                for l in new_logs[-20:]
            ]
            _get_live_stats._last_log_idx = len(all_logs)
    except Exception:
        pass

    return stats


def _update_progress_bar(
        progressbar: Progressbar, run_silently: bool, candle_index: int, candle_step: int, last_update_time: float
) -> float:
    throttle_interval = 0.5
    current_time = time.time()
    if not run_silently and candle_index % candle_step == 0:
        progressbar.update()

        if last_update_time is None or (current_time - last_update_time) >= throttle_interval:
            sync_publish(
                "progressbar",
                {
                    "current": progressbar.current,
                    "estimated_remaining_seconds": progressbar.estimated_remaining_seconds,
                    "current_date": store.app.time,
                    **_get_live_stats(),
                },
            )
            # Update the last update time
            last_update_time = current_time

    # Return the last update time for future reference
    return last_update_time


def _finish_progress_bar(progressbar: Progressbar, run_silently: bool):
    if run_silently:
        return

    progressbar.finish()
    sync_publish(
        "progressbar",
        {
            "current": 100,
            "estimated_remaining_seconds": 0,
        },
    )


def _get_fixed_jumped_candle(
        previous_candle: np.ndarray, candle: np.ndarray
) -> np.ndarray:
    """
    A little workaround for the times that the price has jumped and the opening
    price of the current candle is not equal to the previous candle's close!

    :param previous_candle: np.ndarray
    :param candle: np.ndarray
    """
    if previous_candle[2] < candle[1]:
        candle[1] = previous_candle[2]
        candle[4] = min(previous_candle[2], candle[4])
    elif previous_candle[2] > candle[1]:
        candle[1] = previous_candle[2]
        candle[3] = max(previous_candle[2], candle[3])

    return candle


def _apply_gap_execution_prices(orders: list, candle: np.ndarray) -> list:
    """
    For forex/CFD: if a stop/limit order's price was gapped past by the candle open,
    adjust the execution price to the open (simulating slippage on weekend gaps).
    candle format: [timestamp, open, close, high, low, volume]

    Saves original price as _pre_gap_price so exchange order tracking can
    match against the originally submitted price.
    """
    open_price = candle[1]
    for order in orders:
        if not order.is_active:
            continue
        if order.type in (order_types.STOP, 'STOP'):
            if order.side == 'buy' and open_price > order.price:
                order._pre_gap_price = order.price
                order.price = open_price
            elif order.side == 'sell' and open_price < order.price:
                order._pre_gap_price = order.price
                order.price = open_price
        elif order.type in (order_types.LIMIT, 'LIMIT'):
            if order.side == 'buy' and open_price < order.price:
                order._pre_gap_price = order.price
                order.price = open_price
            elif order.side == 'sell' and open_price > order.price:
                order._pre_gap_price = order.price
                order.price = open_price
    return orders


def _check_ticket_tp_sl_triggers(real_candle: np.ndarray, exchange: str, symbol: str) -> None:
    """Check all open CFD tickets for TP/SL hits and close them.

    Called once per candle AFTER order execution, so that new hedges set TP/SL
    for the *next* candle (not the current one).
    """
    p = store.positions.get_position(exchange, symbol)
    if not p or not p.is_cfd_mode or not p._tickets:
        return

    mode = config['app'].get('ticket_tp_sl_mode', 'ohlc_walk')
    open_price = real_candle[1]
    close_price = real_candle[2]
    high = real_candle[3]
    low = real_candle[4]

    for ticket in list(p._tickets):
        if ticket.tp_price is None and ticket.sl_price is None:
            continue

        result = ticket_service.check_ticket_triggers(
            ticket, high, low, open_price, close_price, mode=mode
        )
        if result is None:
            continue

        fill_price = result['price']
        reason = result['reason']

        # Close the ticket
        close_result = p.close_ticket(ticket.id, fill_price)
        if close_result is None:
            continue

        pnl = close_result['pnl']
        if p.exchange:
            p.exchange.add_realized_pnl(pnl)

        from qengine.services import closed_trade_service
        closed_trade_service.record_ticket_close(
            p, close_result['ticket'], fill_price, pnl,
            meta={'exit_reason': f'{reason}_hit'}
        )

        # Fire strategy callback
        strategy = None
        for r in router.routes:
            if r.exchange == exchange and r.symbol == symbol:
                strategy = r.strategy
                break

        if strategy is not None:
            if reason == 'tp':
                strategy.on_ticket_tp_hit(ticket, fill_price)
            else:
                strategy.on_ticket_sl_hit(ticket, fill_price)

            # Callback may have closed remaining tickets (e.g., martingale cycle end).
            # No point checking already-closed tickets from the snapshot.
            if not p._tickets:
                break


def _simulate_price_change_effect(real_candle: np.ndarray, exchange: str, symbol: str) -> None:
    current_temp_candle = real_candle.copy()
    executed_order = False

    # Weekend gap handling: check if there's a time gap > 2 days from prev candle
    # If so, stop/limit orders that gapped should execute at open price (slippage)
    e = store.exchanges.get_exchange(exchange)
    _is_cfd_exchange = isinstance(e, CFDExchange)

    executing_orders = _get_executing_orders(exchange, symbol, real_candle)
    if _is_cfd_exchange and len(executing_orders) > 0 and config['app'].get('cost_model', True):
        executing_orders = _apply_gap_execution_prices(executing_orders, real_candle)
    if len(executing_orders) > 1:
        # extend the candle shape from (6,) to (1,6)
        executing_orders = _sort_execution_orders(executing_orders, current_temp_candle[None, :])

    while True:
        if len(executing_orders) == 0:
            executed_order = False
        else:
            for index, order in enumerate(executing_orders):
                if index == len(executing_orders) - 1 and not order.is_active:
                    executed_order = False

                if not order.is_active:
                    continue

                if candle_service.candle_includes_price(current_temp_candle, order.price):
                    storable_temp_candle, current_temp_candle = candle_service.split_candle(current_temp_candle, order.price)
                    _update_all_routes_a_partial_candle(exchange, symbol, storable_temp_candle)

                    p = store.positions.get_position(exchange, symbol)
                    p.current_price = storable_temp_candle[2]

                    executed_order = True

                    order_service.execute_order(order)
                    executing_orders = _get_executing_orders(exchange, symbol, current_temp_candle)
                    if len(executing_orders) > 1:
                        # extend the candle shape from (6,) to (1,6)
                        executing_orders = _sort_execution_orders(executing_orders, current_temp_candle[None, :])

                    # break from the for loop, we'll try again inside the while
                    # loop with the new current_temp_candle
                    break
                else:
                    executed_order = False

        if not executed_order:
            # add/update the real_candle to the store so we can move on
            candle_service.add_candle(
                real_candle, exchange, symbol, '1m',
                with_execution=False,
                with_generation=False
            )
            p = store.positions.get_position(exchange, symbol)
            if p:
                p.current_price = real_candle[2]
            break

    _check_ticket_tp_sl_triggers(real_candle, exchange, symbol)
    _check_for_liquidations(real_candle, exchange, symbol)
    _check_for_margin_call(exchange, symbol)


def _update_session_stats(had_margin_error: bool = False) -> None:
    """Track per-session stats: max/min floating PnL, peak margin used, peak equity %, margin blocks."""
    for r in router.routes:
        strategy = r.strategy
        if strategy is None:
            continue
        # Get current session number from strategy vars (hedge strategies set this)
        session_num = None
        if hasattr(strategy, 'vars') and isinstance(strategy.vars, dict):
            session_num = strategy.vars.get('session_number')
        if session_num is None:
            continue

        # Get current position state
        pos = store.positions.get_position(r.exchange, r.symbol)
        if pos is None or not pos.is_open:
            continue

        floating = pos.pnl
        margin = pos.margin_used

        # Get equity for equity usage %
        e = store.exchanges.get_exchange(r.exchange)
        wallet = e.assets.get(jh.app_currency(), 0)
        equity = wallet + floating
        equity_pct = (margin / equity * 100) if equity > 0 else 0

        stats = store.app.session_stats
        if session_num not in stats:
            stats[session_num] = {
                'max_float': 0.0,
                'min_float': 0.0,
                'peak_margin': 0.0,
                'peak_equity_pct': 0.0,
                'margin_block_leg': None,
            }

        s = stats[session_num]
        if floating > s['max_float']:
            s['max_float'] = round(floating, 2)
        if floating < s['min_float']:
            s['min_float'] = round(floating, 2)
        if margin > s['peak_margin']:
            s['peak_margin'] = round(margin, 2)
        if equity_pct > s['peak_equity_pct']:
            s['peak_equity_pct'] = round(equity_pct, 1)

        # If a margin error occurred this candle, record which leg triggered it
        if had_margin_error and s['margin_block_leg'] is None:
            level = strategy.vars.get('level', 0) if hasattr(strategy, 'vars') else 0
            s['margin_block_leg'] = level


def _check_for_margin_call(exchange: str, symbol: str) -> None:
    """
    Check if a forex/CFD position should be stopped out due to insufficient margin.

    In real forex trading, brokers enforce:
    - Margin Call Level: when equity drops to ~100% of used margin (warning)
    - Stop-Out Level: when equity drops to ~50% of used margin (force close)

    Equity = wallet_balance + unrealized_pnl
    Margin Level = (Equity / Used Margin) * 100
    Stop-out triggers when Margin Level < stop_out_level (default 50%)
    """
    e = store.exchanges.get_exchange(exchange)
    if not isinstance(e, CFDExchange):
        return

    p: Position = store.positions.get_position(exchange, symbol)
    if not p or not p.is_open:
        return

    # Calculate equity (balance + unrealized PnL across all positions)
    equity = e.wallet_balance
    total_used_margin = 0
    for key, pos in store.positions.storage.items():
        if pos.is_open:
            equity += pos.pnl
            # Use margin_used which accounts for gross exposure in CFD mode,
            # not total_cost which uses net qty (near-zero for hedged positions)
            total_used_margin += pos.margin_used

    if total_used_margin <= 0:
        return

    margin_level = (equity / total_used_margin) * 100

    # Stop-out at 50% margin level (industry standard)
    stop_out_level = e._bt_cost_settings.get('stop_out_level', 50.0)
    if margin_level < stop_out_level:
        closing_order_side = jh.closing_side(p.type)

        logger.info(
            f'MARGIN CALL: {symbol} force-closed. Margin level: {round(margin_level, 1)}% '
            f'(equity: {round(equity, 2)}, used margin: {round(total_used_margin, 2)})'
        )

        order = Order({
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': exchange,
            'side': closing_order_side,
            'type': order_types.MARKET,
            'reduce_only': True,
            'qty': jh.prepare_qty(p.qty, closing_order_side),
            'price': p.current_price
        })

        store.orders.add_order(order)
        store.app.total_liquidations += 1

        order_service.execute_order(order)


def _check_for_liquidations(candle: np.ndarray, exchange: str, symbol: str) -> None:
    p: Position = store.positions.get_position(exchange, symbol)

    if not p:
        return

    # for now, we only support the isolated mode:
    if p.mode != 'isolated':
        return

    if candle_service.candle_includes_price(candle, p.liquidation_price):
        closing_order_side = jh.closing_side(p.type)

        # create the market order that is used as the liquidation order
        order = Order({
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': exchange,
            'side': closing_order_side,
            'type': order_types.MARKET,
            'reduce_only': True,
            'qty': jh.prepare_qty(p.qty, closing_order_side),
            'price': p.bankruptcy_price
        })

        store.orders.add_order(order)

        store.app.total_liquidations += 1

        logger.info(f'{p.symbol} liquidated at {p.liquidation_price}')

        order_service.execute_order(order)


def _generate_full_report(session_id: str, result: dict):
    """Generate an HTML full report for the backtest session."""
    import os
    import math
    os.makedirs('./storage/full-reports', exist_ok=True)
    path = f'storage/full-reports/{session_id}.html'

    metrics = result.get('metrics') or {}
    trades_list = result.get('trades', [])
    sessions_list = result.get('sessions', [])

    def _fmt(v):
        """Format metric value for display."""
        if v is None:
            return '-'
        if isinstance(v, bool):
            return 'Yes' if v else 'No'
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                return '-'
            return f'{v:,.4f}' if abs(v) < 1 else f'{v:,.2f}'
        return str(v)

    def _label(k):
        return k.replace('_', ' ').title()

    # Separate session-level metrics from trade-level metrics
    session_metric_keys = [
        'total_sessions', 'session_win_rate', 'total_losing_sessions',
        'avg_session_win', 'avg_session_loss',
        'ev_per_session', 'avg_legs_per_session', 'max_legs_in_session',
        'sessions_with_1_leg', 'max_consecutive_session_wins', 'max_consecutive_session_losses',
        'total_busts', 'worst_bust_pnl',
    ]
    summary_keys = [
        'starting_balance', 'finishing_balance', 'net_profit', 'net_profit_percentage',
        'profit_factor', 'max_drawdown', 'sharpe_ratio', 'sortino_ratio',
        'worst_floating_pnl', 'peak_margin_used', 'peak_equity_usage_pct',
        'margin_closeouts', 'account_blown',
    ]
    trade_keys = [
        'total', 'total_winning_trades', 'total_losing_trades', 'win_rate',
        'average_win', 'average_loss', 'expectancy', 'largest_winning_trade',
        'largest_losing_trade', 'winning_streak', 'losing_streak', 'fee',
        'gross_profit', 'gross_loss', 'annual_return', 'calmar_ratio',
        'omega_ratio', 'serenity_index', 'kelly_criterion',
        'var_95', 'cvar_95', 'total_pips', 'avg_pips_per_trade',
    ]

    has_sessions = any(k in metrics for k in session_metric_keys)

    # Build summary metrics table
    summary_rows = ''
    for k in summary_keys:
        if k in metrics:
            summary_rows += f'<tr><td>{_label(k)}</td><td>{_fmt(metrics[k])}</td></tr>\n'

    # Build session metrics table (if hedge sessions exist)
    session_rows = ''
    if has_sessions:
        for k in session_metric_keys:
            if k in metrics:
                v = metrics[k]
                # Highlight session win rate
                style = ''
                if k == 'session_win_rate':
                    wr = v if isinstance(v, (int, float)) else 0
                    color = '#4ade80' if wr > 0.5 else '#facc15' if wr > 0.3 else '#f87171'
                    style = f' style="color:{color};font-weight:600"'
                session_rows += f'<tr><td>{_label(k)}</td><td{style}>{_fmt(v)}</td></tr>\n'

    # Build per-trade metrics table
    trade_rows = ''
    for k in trade_keys:
        if k in metrics:
            trade_rows += f'<tr><td>{_label(k)}</td><td>{_fmt(metrics[k])}</td></tr>\n'
    # Any remaining metrics not in the above lists
    shown_keys = set(summary_keys + session_metric_keys + trade_keys)
    for k, v in metrics.items():
        if k not in shown_keys:
            trade_rows += f'<tr><td>{_label(k)}</td><td>{_fmt(v)}</td></tr>\n'

    # Build sessions/trades section
    sessions_html = ''
    if sessions_list:
        total_trades = sum(s.get('trade_count', len(s.get('trades', []))) for s in sessions_list)
        winning = sum(1 for s in sessions_list if s.get('total_pnl', 0) > 0)
        losing = len(sessions_list) - winning
        sessions_html += (
            f'<h2>Sessions ({len(sessions_list)}) &mdash; {total_trades} Trades '
            f'<span style="color:#4ade80;font-size:14px">{winning}W</span> / '
            f'<span style="color:#f87171;font-size:14px">{losing}L</span></h2>\n'
        )

        for s in sessions_list:
            spnl = s.get('total_pnl', 0)
            sfee = s.get('total_fee', 0)
            scolor = '#4ade80' if spnl >= 0 else '#f87171'
            outcome = s.get('outcome', '')
            levels = s.get('levels', 0)
            session_label = s.get('session', '?')
            opened = jh.timestamp_to_time(int(s['opened_at']))[:19] if s.get('opened_at') else ''
            closed = jh.timestamp_to_time(int(s['closed_at']))[:19] if s.get('closed_at') else ''
            max_float = s.get('max_float', 0)
            min_float = s.get('min_float', 0)

            outcome_color = '#4ade80' if outcome == 'tp_hit' else '#f87171' if outcome in ('bust', 'liquidation') else '#facc15'

            sessions_html += (
                f'<div class="session">'
                f'<div class="session-header">'
                f'<span class="session-label">#{session_label}</span>'
                f'<span class="tag" style="color:{outcome_color}">{outcome}</span>'
                f'<span class="tag">L{levels}</span>'
                f'<span style="color:{scolor};font-weight:600;font-size:14px">{round(spnl, 2)}</span>'
            )
            if sfee:
                sessions_html += f'<span class="dim">fee: {round(sfee, 4)}</span>'
            if min_float:
                sessions_html += f'<span class="dim">float: {round(min_float, 2)} / {round(max_float, 2)}</span>'
            # Pipeline info
            pipeline = s.get('pipeline')
            if pipeline:
                danger = pipeline.get('danger_at_entry')
                if danger is not None:
                    dcolor = '#4ade80' if danger < 0.5 else '#facc15' if danger < 0.75 else '#f87171'
                    sessions_html += f'<span style="color:{dcolor}" class="dim">danger: {round(danger, 3)}</span>'
            sessions_html += f'<span class="dim">{opened}</span>'
            sessions_html += '</div>\n'

            # Trades table for this session
            sessions_html += (
                '<table class="trades-table"><tr>'
                '<th>#</th><th>Type</th><th>Level</th><th>Entry</th><th>Exit</th>'
                '<th>Qty</th><th>PnL</th><th>PnL %</th><th>Opened</th></tr>\n'
            )
            for ti, t in enumerate(s.get('trades', [])):
                pnl = t.get('pnl', t.get('PNL', 0)) or 0
                pnl_pct = t.get('pnl_percentage', t.get('PNL_percentage', 0)) or 0
                meta = t.get('meta', {})
                level = meta.get('level', '')
                color = '#4ade80' if pnl >= 0 else '#f87171'
                t_opened = jh.timestamp_to_time(int(t['opened_at']))[11:19] if t.get('opened_at') else ''
                sessions_html += (
                    f'<tr><td>{ti+1}</td>'
                    f'<td>{t.get("type", "")}</td>'
                    f'<td>{level}</td>'
                    f'<td>{round(t.get("entry_price", 0), 5)}</td>'
                    f'<td>{round(t.get("exit_price", 0), 5)}</td>'
                    f'<td>{round(abs(t.get("qty", 0)), 1)}</td>'
                    f'<td style="color:{color}">{round(pnl, 2)}</td>'
                    f'<td style="color:{color}">{round(pnl_pct, 2)}%</td>'
                    f'<td>{t_opened}</td></tr>\n'
                )
            sessions_html += '</table></div>\n'
    else:
        # Fallback: flat trades table
        sessions_html += f'<h2>Trades ({len(trades_list)})</h2>\n'
        sessions_html += (
            '<table><tr><th>#</th><th>Symbol</th><th>Type</th><th>Entry</th>'
            '<th>Exit</th><th>Qty</th><th>PnL</th><th>PnL %</th></tr>\n'
        )
        for i, t in enumerate(trades_list):
            pnl = t.get('pnl', 0) or 0
            pnl_pct = t.get('pnl_percentage', 0) or 0
            color = '#4ade80' if pnl >= 0 else '#f87171'
            sessions_html += (
                f'<tr><td>{i+1}</td><td>{t.get("symbol", "")}</td>'
                f'<td>{t.get("type", "")}</td>'
                f'<td>{t.get("entry_price", "")}</td>'
                f'<td>{t.get("exit_price", "")}</td>'
                f'<td>{t.get("qty", "")}</td>'
                f'<td style="color:{color}">{round(pnl, 2)}</td>'
                f'<td style="color:{color}">{round(pnl_pct, 2)}%</td></tr>\n'
            )
        sessions_html += '</table>\n'

    # Build metrics HTML sections
    metrics_html = f'<h2>Summary</h2>\n<table class="metrics">{summary_rows}</table>\n'
    if session_rows:
        metrics_html += f'<h2>Session Metrics</h2>\n<table class="metrics">{session_rows}</table>\n'
    metrics_html += f'<details><summary style="cursor:pointer;color:#818cf8;margin:12px 0">Per-Trade Metrics</summary>\n<table class="metrics">{trade_rows}</table></details>\n'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Backtest Report - {session_id[:8]}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1117; color: #e2e8f0; margin: 0; padding: 20px; max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #818cf8; margin-bottom: 4px; }}
h2 {{ color: #818cf8; margin-top: 24px; }}
table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
th, td {{ padding: 6px 10px; border: 1px solid #2a2d3a; text-align: left; font-size: 13px; }}
th {{ background: #1a1d2e; color: #94a3b8; }}
tr:nth-child(even) {{ background: #131620; }}
.metrics {{ max-width: 500px; }}
.metrics td:first-child {{ color: #94a3b8; width: 60%; }}
.metrics td:last-child {{ font-family: 'SF Mono', 'Fira Code', monospace; text-align: right; }}
.session {{ background: #161926; border: 1px solid #2a2d3a; border-radius: 8px; margin: 10px 0; padding: 10px 12px; }}
.session-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; flex-wrap: wrap; }}
.session-label {{ font-weight: 700; color: #818cf8; font-size: 14px; min-width: 50px; }}
.tag {{ background: #1e2235; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
.dim {{ color: #64748b; font-size: 12px; }}
.trades-table {{ font-size: 12px; }}
.trades-table th {{ font-size: 11px; padding: 4px 8px; }}
.trades-table td {{ padding: 3px 8px; }}
details > summary {{ font-size: 14px; }}
</style>
</head><body>
<h1>Backtest Report</h1>
<p class="dim">Session: {session_id}</p>
{metrics_html}
{sessions_html}
</body></html>"""

    with open(path, 'w') as f:
        f.write(html)


def _generate_outputs(
        candles: dict,
        generate_tradingview: bool = False,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_hyperparameters: bool = False,
        generate_logs: bool = False,
):
    result = {}
    if generate_hyperparameters:
        result["hyperparameters"] = stats.hyperparameters(router.routes)
    result["metrics"] = report.portfolio_metrics()
    result["trades"] = report.trades()
    # Include hedge session grouping if any trades have session metadata
    sessions = report.hedge_sessions()
    if sessions:
        result["sessions"] = sessions
    # generate logs in json, csv and tradingview's pine-editor format
    logs_path = store_logs(generate_json, generate_tradingview, generate_csv)
    if generate_json:
        result["json"] = logs_path["json"]
    if generate_tradingview:
        result["tradingview"] = logs_path["tradingview"]
    if generate_csv:
        result["csv"] = logs_path["csv"]
    if generate_equity_curve:
        result["equity_curve"] = charts.equity_curve(benchmark)
        result["floating_pnl_curve"] = charts.floating_pnl_curve()
        result["margin_usage_curve"] = charts.margin_usage_curve()
    if generate_logs:
        result["logs_file"] = f"storage/logs/backtest-mode/{jh.get_session_id()}.txt"

    # Always include in-memory logs in result (strategy + market + order events)
    result["logs"] = [
        {
            'timestamp': log.get('timestamp', 0),
            'message': log.get('message', ''),
            'type': log.get('type', 'info'),
        }
        for log in store.logs.info
    ]

    # Collect pipeline stats from strategies (if any pipelines attached)
    pipeline_stats = {}
    _stack_hp_logs = {}  # route → HP log from PipelineStack (works for ALL pipelines)
    for r in router.routes:
        if getattr(r.strategy, '_pipelines', None):
            stack = r.strategy._pipelines
            stack_stats = stack.get_stats()
            route_key = f"{r.exchange}-{r.symbol}"
            # Capture HP log from stack (framework-level, pipeline-agnostic)
            _stack_hp_logs[route_key] = getattr(stack, '_cycle_hp_log', [])
            # Flatten PipelineStack nesting: {pipeline_name: stats} → stats
            # For single pipeline (common case), use its stats directly
            # For multiple, merge all pipeline stats into one dict
            merged = {}
            for pname, pstats in stack_stats.items():
                merged.update(pstats)
                merged['pipeline_name'] = pname
                # Include architecture metadata for the frontend
                for p in stack.pipelines:
                    if p.name == pname:
                        try:
                            merged['_architecture'] = p.architecture()
                        except Exception:
                            pass
                        break
            pipeline_stats[route_key] = merged
    if pipeline_stats:
        result["pipeline_stats"] = pipeline_stats

        # Enrich sessions with pipeline context (danger, abort info, HP per session)
        if sessions:
            for route_key, ps in pipeline_stats.items():
                cycles = ps.get('cycle_outcomes', [])
                cycle_map = {c['cycle']: c for c in cycles}
                # Framework-level HP log (PipelineStack captures strategy.hp for ALL pipelines)
                stack_hp = _stack_hp_logs.get(route_key, [])
                stack_hp_map = {h['cycle']: h for h in stack_hp}
                # Pipeline-specific HP log (IslandPilot's evolved genes)
                pipeline_hp = ps.get('cycle_hp_log', [])
                pipeline_hp_map = {h['cycle']: h for h in pipeline_hp} if pipeline_hp else {}
                for s in sessions:
                    sn = s.get('session')
                    if not isinstance(sn, int):
                        continue
                    # Pipeline danger/abort context (from PipelineStats)
                    if sn in cycle_map:
                        c = cycle_map[sn]
                        s['pipeline'] = {
                            'danger_at_entry': c.get('danger_at_entry'),
                            'danger_at_exit': c.get('danger_at_exit'),
                            'max_danger': c.get('max_danger'),
                            'min_danger': c.get('min_danger'),
                            'avg_danger': c.get('avg_danger'),
                            'abort_checks': c.get('abort_checks', 0),
                            'abort_triggers': c.get('abort_triggers', 0),
                            'gate_blocks_before_entry': c.get('gate_blocks_before_entry', 0),
                        }
                    # Always attach HP from PipelineStack (works for ANY pipeline)
                    if sn in stack_hp_map:
                        if 'pipeline' not in s:
                            s['pipeline'] = {}
                        s['pipeline']['hp'] = stack_hp_map[sn].get('hp')
                    # Overlay evolved genes from IslandPilot (if present)
                    if sn in pipeline_hp_map:
                        if 'pipeline' not in s:
                            s['pipeline'] = {}
                        hp_entry = pipeline_hp_map[sn]
                        s['pipeline']['regime'] = hp_entry.get('regime')
                        s['pipeline']['confidence'] = hp_entry.get('confidence')
                        if hp_entry.get('genes'):
                            s['pipeline']['genes'] = hp_entry['genes']

    return result


def _skip_simulator(
        candles: dict,
        run_silently: bool,
        hyperparameters: dict = None,
        generate_tradingview: bool = False,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_hyperparameters: bool = False,
        generate_logs: bool = False,
        with_candles_pipeline: bool = True,
        candles_pipeline_class = None,
        candles_pipeline_kwargs: dict = None,
) -> dict:
    # In case generating logs is specifically demanded, the debug mode must be enabled.
    if generate_logs:
        config["app"]["debug_mode"] = True

    begin_time_track = time.time()

    key = f"{config['app']['considering_candles'][0][0]}-{config['app']['considering_candles'][0][1]}"
    first_candles_set = candles[key]['candles']

    length = _simulation_minutes_length(candles)
    _prepare_times_before_simulation(candles)
    candles_pipelines = _prepare_routes(hyperparameters, with_candles_pipeline, candles_pipeline_class, candles_pipeline_kwargs)

    # add initial balance
    save_daily_portfolio_balance(is_initial=True)

    # Log backtest start
    route_info = ', '.join([f"{r.symbol} {r.timeframe} ({r.strategy_name})" for r in router.routes])
    store.logs.add(f'Backtest started (fast mode): {route_info}', 'market')

    cost_model_enabled = config['app'].get('cost_model', True)
    skip_market_hours = config['app'].get('skip_market_hours', False)

    candles_step = _calculate_minimum_candle_step()
    progressbar = Progressbar(length, step=candles_step)
    last_update_time = None
    margin_error_msg = None
    _prev_market_open = {}
    for i in range(0, length, candles_step):
        _simulate_new_candles(candles, candles_pipelines, i, candles_step)

        # Check overnight swap for each 1m candle in this batch
        if cost_model_enabled:
            for ci in range(i, min(i + candles_step, length)):
                ts = first_candles_set[ci][0]
                if _market_hours.is_rollover_time(ts):
                    for r in router.routes:
                        p = store.positions.get_position(r.exchange, r.symbol)
                        if p and p.is_open:
                            e = store.exchanges.get_exchange(r.exchange)
                            if isinstance(e, CFDExchange):
                                e.charge_overnight_swap(r.symbol, p.qty, p.type)

        last_update_time = _update_progress_bar(progressbar, run_silently, i, candles_step,
                                                last_update_time=last_update_time)

        # Determine current timestamp for market hours check (use last candle in batch)
        current_timestamp = first_candles_set[min(i + candles_step - 1, length - 1)][0]

        margin_error = None
        for r in router.routes:
            # Skip strategy execution if market is closed for this symbol
            if not skip_market_hours:
                e = store.exchanges.get_exchange(r.exchange)
                if isinstance(e, CFDExchange):
                    is_open = _market_hours.is_market_open(r.symbol, current_timestamp)
                    sym_key = f"{r.exchange}-{r.symbol}"
                    was_open = _prev_market_open.get(sym_key)
                    if was_open is not None and is_open != was_open:
                        state_txt = 'OPENED' if is_open else 'CLOSED'
                        store.logs.add(
                            f'Market {state_txt} for {r.symbol} at {jh.timestamp_to_time(current_timestamp)[:19]}',
                            'market'
                        )
                    _prev_market_open[sym_key] = is_open
                    if not is_open:
                        order_service.update_active_orders(r.exchange, r.symbol)
                        continue

            count = TIMEFRAME_TO_ONE_MINUTES[r.timeframe]
            try:
                if r.timeframe == timeframes.MINUTE_1:
                    r.strategy._execute()
                elif (i + candles_step) % count == 0:
                    if jh.is_debuggable("trading_candles"):
                        candle_service.print_candle(
                            candle_service.get_current_candle(r.exchange, r.symbol, r.timeframe),
                            False, r.symbol,
                        )
                    r.strategy._execute()

                order_service.update_active_orders(r.exchange, r.symbol)
            except exceptions.InsufficientMargin as e:
                margin_error = e
                break

        if margin_error is not None:
            margin_error_msg = str(margin_error)
            store.logs.add(f'MARGIN CALL: Backtest stopped early — {margin_error_msg}', 'market')
            logger.info(f'Backtest stopped early: {margin_error_msg}')
            if not run_silently:
                sync_publish('notification', {
                    'message': f'Insufficient margin — backtest stopped early. {margin_error_msg}',
                    'type': 'error'
                })
            break

        # now check to see if there's any MARKET orders waiting to be executed
        order_service.execute_simulated_market_orders()

        # Track per-session stats
        _update_session_stats(margin_error is not None)

        if i != 0 and i % 1440 == 0:
            save_daily_portfolio_balance()

    _finish_progress_bar(progressbar, run_silently)

    execution_duration = 0
    if not run_silently:
        # print executed time for the backtest session
        finish_time_track = time.time()
        execution_duration = round(finish_time_track - begin_time_track, 2)

    for r in router.routes:
        r.strategy._terminate()
        order_service.execute_simulated_market_orders()

    # now that backtest simulation is finished, add finishing balance
    save_daily_portfolio_balance()

    # set the ending time for the backtest session
    store.app.ending_time = store.app.time + 60_000

    # Log backtest completion summary
    total_trades = len(store.closed_trades.trades) if store.closed_trades.trades else 0
    store.logs.add(f'Backtest completed (fast mode): {total_trades} trades in {execution_duration}s', 'market')

    result = _generate_outputs(
        candles,
        generate_tradingview=generate_tradingview,
        generate_csv=generate_csv,
        generate_json=generate_json,
        generate_equity_curve=generate_equity_curve,
        benchmark=benchmark,
        generate_hyperparameters=generate_hyperparameters,
        generate_logs=generate_logs,
    )
    result['execution_duration'] = execution_duration
    if margin_error_msg:
        result['alert'] = f'Insufficient margin — backtest stopped early. {margin_error_msg}'
    return result


def _calculate_minimum_candle_step():
    """
    Calculates the minimum step for update candles that will allow simple updates on the simulator.
    """
    # config["app"]["considering_timeframes"] use '1m' also even if not required by the user so take only what the user
    # is requested.
    consider_time_frames = [
        TIMEFRAME_TO_ONE_MINUTES[route["timeframe"]]
        for route in router.all_formatted_routes
    ]
    return np.gcd.reduce(consider_time_frames)

timeframe_to_one_minutes = {
    timeframes.MINUTE_1: 1,
    timeframes.MINUTE_3: 3,
    timeframes.MINUTE_5: 5,
    timeframes.MINUTE_15: 15,
    timeframes.MINUTE_30: 30,
    timeframes.MINUTE_45: 45,
    timeframes.HOUR_1: 60,
    timeframes.HOUR_2: 60 * 2,
    timeframes.HOUR_3: 60 * 3,
    timeframes.HOUR_4: 60 * 4,
    timeframes.HOUR_6: 60 * 6,
    timeframes.HOUR_8: 60 * 8,
    timeframes.HOUR_12: 60 * 12,
    timeframes.DAY_1: 60 * 24,
    timeframes.DAY_3: 60 * 24 * 3,
    timeframes.WEEK_1: 60 * 24 * 7,
    timeframes.MONTH_1: 60 * 24 * 30,
}
def _simulate_new_candles(candles: dict, candles_pipelines: Dict[str, BaseCandlesPipeline], candle_index: int, candles_step: int) -> None:
    i = candle_index
    # add candles
    for j in candles:
        candles_pipeline = candles_pipelines[j]
        short_candles = get_candles_from_pipeline(candles_pipeline, candles[j]['candles'], i, candles_step)
        # Clamp to remaining array length at the tail end of the data
        remaining = len(candles[j]['candles']) - i
        if len(short_candles) > remaining:
            short_candles = short_candles[:remaining]
        candles[j]['candles'][i:i+candles_step] = short_candles
        if i != 0:
            previous_short_candles = candles[j]["candles"][i - 1]
            # work the same, the fix needs to be done only on the gap of 1m edge candles.
            short_candles[0] = _get_fixed_jumped_candle(
                previous_short_candles, short_candles[0]
            )
        exchange = candles[j]["exchange"]
        symbol = candles[j]["symbol"]

        _simulate_price_change_effect_multiple_candles(
            short_candles, exchange, symbol
        )

        # generate and add candles for bigger timeframes
        for timeframe in config["app"]["considering_timeframes"]:
            # for 1m, no work is needed
            if timeframe == "1m":
                continue

            count = TIMEFRAME_TO_ONE_MINUTES[timeframe]

            end_idx = i + candles_step
            if (end_idx) % count == 0 and end_idx >= count and end_idx <= len(candles[j]["candles"]):
                generated_candle = candle_service.generate_candle_from_one_minutes(
                    timeframe,
                    candles[j]["candles"][
                    end_idx - count: end_idx],
                )

                candle_service.add_candle(
                    generated_candle,
                    exchange,
                    symbol,
                    timeframe,
                    with_execution=False,
                    with_generation=False,
                )


def _simulate_price_change_effect_multiple_candles(
        short_timeframes_candles: np.ndarray, exchange: str, symbol: str
) -> None:
    real_candle = np.array(
        [
            short_timeframes_candles[0][0],
            short_timeframes_candles[0][1],
            short_timeframes_candles[-1][2],
            short_timeframes_candles[:, 3].max(),
            short_timeframes_candles[:, 4].min(),
            short_timeframes_candles[:, 5].sum(),
        ]
    )
    executing_orders = _get_executing_orders(exchange, symbol, real_candle)
    if len(executing_orders) > 0:
        if len(executing_orders) > 1:
            executing_orders = _sort_execution_orders(executing_orders, short_timeframes_candles)

        for i in range(len(short_timeframes_candles)):
            current_temp_candle = short_timeframes_candles[i].copy()
            if i > 0:
                current_temp_candle[3] = max(current_temp_candle[3], short_timeframes_candles[i-1, 2])
                current_temp_candle[4] = min(current_temp_candle[4], short_timeframes_candles[i-1, 2])
            is_executed_order = False

            while True:
                if len(executing_orders) == 0:
                    is_executed_order = False
                else:
                    for index, order in enumerate(executing_orders):
                        if index == len(executing_orders) - 1 and not order.is_active:
                            is_executed_order = False
                        if not order.is_active:
                            continue

                        if candle_service.candle_includes_price(current_temp_candle, order.price):
                            storable_temp_candle, current_temp_candle = candle_service.split_candle(
                                current_temp_candle, order.price
                            )
                            _update_all_routes_a_partial_candle(
                                exchange,
                                symbol,
                                storable_temp_candle,
                            )
                            p = store.positions.get_position(exchange, symbol)
                            p.current_price = storable_temp_candle[2]

                            is_executed_order = True

                            store.app.time = storable_temp_candle[0] + 60_000
                            order_service.execute_order(order)
                            executing_orders = _get_executing_orders(
                                exchange, symbol, real_candle
                            )

                            # break from the for loop, we'll try again inside the while
                            # loop with the new current_temp_candle
                            break
                        else:
                            is_executed_order = False

                if not is_executed_order:
                    # add/update the real_candle to the store so we can move on
                    candle_service.add_candle(
                        short_timeframes_candles[i].copy(),
                        exchange,
                        symbol,
                        "1m",
                        with_execution=False,
                        with_generation=False,
                    )
                    p = store.positions.get_position(exchange, symbol)
                    if p:
                        p.current_price = current_temp_candle[2]
                    break

    candle_service.add_multiple_1m_candles(
        short_timeframes_candles,
        exchange,
        symbol,
    )
    store.app.time = real_candle[0] + (60_000 * len(short_timeframes_candles))
    _check_for_liquidations(real_candle, exchange, symbol)
    _check_for_margin_call(exchange, symbol)

    p = store.positions.get_position(exchange, symbol)
    if p:
        p.current_price = short_timeframes_candles[-1, 2]


def _update_all_routes_a_partial_candle(
        exchange: str,
        symbol: str,
        storable_temp_candle: np.ndarray,
) -> None:
    """
    This function get called when an order is getting executed you need to update the other timeframe how their last
    candles looks like
    """
    candle_service.add_candle(
        storable_temp_candle,
        exchange,
        symbol,
        "1m",
        with_execution=False,
        with_generation=False,
    )

    for route in router.all_formatted_routes:
        timeframe = route['timeframe']
        if route['exchange'] != exchange or route['symbol'] != symbol:
            continue
        if timeframe == '1m':
            continue
        tf_minutes = TIMEFRAME_TO_ONE_MINUTES[timeframe]
        number_of_needed_candles = int(storable_temp_candle[0] % (tf_minutes * 60_000) // 60000) + 1
        candles_1m = candle_service.get_candles(exchange, symbol, '1m')[-number_of_needed_candles:]
        generated_candle = candle_service.generate_candle_from_one_minutes(
            timeframe,
            candles_1m,
            accept_forming_candles=True
        )
        candle_service.add_candle(
            generated_candle,
            exchange,
            symbol,
            timeframe,
            with_execution=False,
            with_generation=False,
        )


def _execute_routes(candle_index: int, candles_step: int) -> None:
    # now that all new generated candles are ready, execute
    for r in router.routes:
        count = TIMEFRAME_TO_ONE_MINUTES[r.timeframe]
        # 1m timeframe
        if r.timeframe == timeframes.MINUTE_1:
            r.strategy._execute()
        elif (candle_index + candles_step) % count == 0:
            # print candle
            if jh.is_debuggable("trading_candles"):
                candle_service.print_candle(
                    candle_service.get_current_candle(
                        r.exchange, r.symbol, r.timeframe
                    ),
                    False,
                    r.symbol,
                )
            r.strategy._execute()

        order_service.update_active_orders(r.exchange, r.symbol)


def _get_executing_orders(exchange, symbol, real_candle):
    orders = store.orders.get_active_orders(exchange, symbol)
    return [
        order
        for order in orders
        if order.is_active and candle_service.candle_includes_price(real_candle, order.price)
    ]


def _sort_execution_orders(orders: List[Order], short_candles: np.ndarray):
    remaining_orders = set(orders)
    sorted_orders = []
    
    for candle in short_candles:
        open_price, close_price, low, high = candle[1], candle[2], candle[4], candle[3]

        # Did not use candle_includes_price() for performance, keeping it vectorization-friendly
        included_orders = [order for order in remaining_orders if low <= order.price <= high]

        if len(included_orders) == 1:
            sorted_orders.append(included_orders[0])
            remaining_orders.remove(included_orders[0])
        elif len(included_orders) > 1:
            # in case that the orders are above
            on_open, above_open, below_open = [], [], []
            for order in included_orders:
                if order.price == open_price:
                    on_open.append(order)
                elif order.price > open_price:
                    above_open.append(order)
                else:
                    below_open.append(order)
            sorted_orders += on_open
            remaining_orders.difference_update(on_open)

            is_red = open_price > close_price
            if is_red:
                # heuristic that first the price goes up and then down, so this is the order execution sort
                above_open.sort(key=lambda o: o.price)
                below_open.sort(key=lambda o: o.price, reverse=True)
                sorted_orders += above_open + below_open
                remaining_orders.difference_update(above_open + below_open)
            else:
                below_open.sort(key=lambda o: o.price, reverse=True)
                above_open.sort(key=lambda o: o.price)
                sorted_orders += below_open + above_open
                remaining_orders.difference_update(below_open + above_open)

        if len(sorted_orders) == len(orders):
            break

    return sorted_orders
