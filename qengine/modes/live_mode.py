"""
Live Trading Mode.
Manages the live trading loop for CFD brokers (OANDA, IG Markets, IBKR):
price streaming, strategy execution, order management, and position tracking.
"""
import time
import threading
import numpy as np
import simplejson as json
from typing import List, Dict

import qengine.helpers as jh
from qengine.config import config, set_config
from qengine.routes import router
from qengine.store import store
from qengine.services import logger, order_service, candle_service
from qengine.services import position_service, exchange_service
from qengine.services.redis import sync_publish, is_process_active, sync_redis
from qengine.services.validators import validate_routes
from qengine.services.failure import register_custom_exception_handler
from qengine.repositories import live_session_repository
from qengine.enums import live_session_statuses, live_session_modes, timeframes
from qengine.constants import TIMEFRAME_TO_ONE_MINUTES
from qengine.modes.utils import save_daily_portfolio_balance

# Redis key prefixes for cross-process data sharing
_REDIS_LOG_KEY = 'qengine:live:logs:'
_REDIS_ORDERS_KEY = 'qengine:live:orders:'
_REDIS_POSITIONS_KEY = 'qengine:live:positions:'
_REDIS_STATE_KEY = 'qengine:live:state:'
_REDIS_REPORT_KEY = 'qengine:live:report:'
_REDIS_MAX_LOGS = 2000  # cap log entries per session

# Module-level state for account sync and backoff
_last_account_data: Dict[str, dict] = {}
_sync_backoff: Dict[str, dict] = {}  # {exchange: {interval: int, failures: int, last_logged: bool}}


def run(
    client_id: str,
    debug_mode: bool,
    exchange: str,
    exchange_api_key_id: str,
    notification_api_key_id: str,
    user_config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    trading_mode: str,
    hyperparameters: dict = None,
    user_id: str = None,
) -> None:
    """Main entry point for forex live/paper trading."""
    # Demo brokers route orders to the broker's practice API, so they must
    # run as 'livetrade' internally to avoid double-execution of market orders
    # (the Sandbox/simulated path is no longer used).
    config['app']['trading_mode'] = 'livetrade'
    config['app']['debug_mode'] = debug_mode

    # Clear @lru_cache on mode helpers so they reflect the new trading_mode
    _clear_mode_caches()

    # Ensure notifications config has required structure
    _ensure_notifications_config(user_config)

    register_custom_exception_handler()

    try:
        is_paper = trading_mode == live_session_modes.PAPERTRADE
        _log(client_id, f'Initializing {"paper" if is_paper else "live"} trading session')
        _log(client_id, f'Exchange: {exchange}, trading_mode: {trading_mode}')

        # Configure
        _log(client_id, 'Setting config...')
        set_config(user_config)

        # Add exchange to routes
        for r in routes:
            r['exchange'] = exchange
        for r in data_routes:
            r['exchange'] = exchange

        _log(client_id, f'Routes: {routes}')

        router.initiate(routes, data_routes)
        store.reset()
        store.app.set_session_id(client_id)
        validate_routes(router)
        store.candles.init_storage(5000)
        exchange_service.initialize_exchanges_state()
        order_service.initialize_orders_state()
        position_service.initialize_positions_state()
        _log(client_id, 'Store and state initialized')

        # Get the live driver for price streaming and (in live mode) order execution
        _log(client_id, f'Loading live driver for {exchange}...')
        driver = _get_live_driver(exchange, exchange_api_key_id, user_id=user_id)
        _log(client_id, f'Driver loaded: {type(driver).__name__}, is_demo={getattr(driver, "_is_demo", "?")}')
        _log(client_id, f'REST URL: {getattr(driver, "_rest_url", "?")}')

        from qengine.services.api import api
        # Always use the real driver for order routing.
        # For demo brokers, the driver already points to the practice/sandbox API
        # (e.g. OANDA Demo -> api-fxpractice.oanda.com), so orders are safe
        # and positions will be visible on the broker's demo platform.
        api.drivers[exchange] = driver
        if is_paper:
            _log(client_id, f'Demo mode: {type(driver).__name__} registered for orders (practice API)')
        else:
            _log(client_id, f'Live mode: {type(driver).__name__} registered for orders')

        # Sync account balance from broker into the exchange model
        _log(client_id, 'Syncing account balance from broker...')
        _sync_account_balance(exchange, driver, client_id)

        # Fetch instrument precisions from broker
        try:
            driver._fetch_precisions()
            _log(client_id, 'Instrument precisions fetched')
        except Exception as e:
            _log(client_id, f'Could not fetch precisions: {e}', 'warning')

        # Initialize strategies (after exchange + positions are set up)
        for r in router.routes:
            _log(client_id, f'Initializing strategy {r.strategy_name} on {r.symbol} {r.timeframe}...')
            StrategyClass = jh.get_strategy_class(r.strategy_name)
            r.strategy = StrategyClass()
            r.strategy.name = r.strategy_name
            r.strategy.exchange = r.exchange
            r.strategy.symbol = r.symbol
            r.strategy.timeframe = r.timeframe

            # Inject hyperparameters from DNA or explicit override (like backtest does)
            if len(r.strategy.dna()) > 0 and hyperparameters is None:
                hp = jh.dna_to_hp(r.strategy.hyperparameters(), r.strategy.dna())
                r.strategy.hp = hp
            elif hyperparameters is not None:
                r.strategy.hp = hyperparameters

            # Critical: initialize broker and position references
            # (also sets hp from defaults if not already set above)
            r.strategy._init_objects()

            # Attach pipelines if configured
            pipeline_configs = config.get('app', {}).get('pipelines')
            if pipeline_configs:
                from qengine.framework import create_pipelines
                r.strategy._pipelines = create_pipelines(pipeline_configs)
                _log(client_id, f'Attached {len(r.strategy._pipelines.pipelines)} pipeline(s) to {r.strategy_name}')

            # Link position back to strategy (needed by closed_trade_service)
            p = store.positions.get_position(r.exchange, r.symbol)
            if p:
                p.strategy = r.strategy
            _log(client_id, f'Strategy {r.strategy_name} initialized (broker={r.strategy.broker is not None}, position={p is not None})')

            # Log hyperparameters so we know what config the strategy is running with
            if r.strategy.hp:
                _log(client_id, f'Strategy {r.strategy_name} hyperparameters: {r.strategy.hp}')

        live_session_repository.update_live_session_status(client_id, live_session_statuses.RUNNING)

        mode_label = 'demo' if is_paper else 'live'
        _log(client_id, f'Started {mode_label} trading on {exchange}')

        _run_live_mode(client_id, driver, exchange)

    except Exception as e:
        error_msg = str(e)
        import traceback
        tb = traceback.format_exc()
        _log(client_id, f'ERROR: {error_msg}', 'error')

        live_session_repository.store_live_session_exception(client_id, error_msg, tb)
        live_session_repository.update_live_session_status(client_id, live_session_statuses.ERROR)

        sync_publish('error', {
            'id': client_id,
            'message': error_msg,
        })
    finally:
        # Capture final state before marking as stopped
        try:
            _publish_state(client_id)
        except Exception:
            pass
        live_session_repository.update_live_session_status(client_id, live_session_statuses.STOPPED)
        _log(client_id, 'Trading session ended')


def _clear_mode_caches():
    """Clear @lru_cache on mode detection helpers so they re-read config."""
    for fn_name in ('is_livetrading', 'is_paper_trading', 'is_live', 'is_backtesting'):
        fn = getattr(jh, fn_name, None)
        if fn and hasattr(fn, 'cache_clear'):
            fn.cache_clear()


def _ensure_notifications_config(user_config: dict):
    """Ensure notifications has the expected structure to prevent KeyErrors."""
    defaults = {
        'events': {
            'submitted_orders': False,
            'executed_orders': False,
            'cancelled_orders': False,
            'updated_position': False,
        }
    }
    if 'notifications' not in user_config or not user_config['notifications']:
        user_config['notifications'] = defaults
    elif 'events' not in user_config['notifications']:
        user_config['notifications']['events'] = defaults['events']
    # Also ensure it's in the global config
    if 'notifications' not in config['env'] or not config['env'].get('notifications'):
        config['env']['notifications'] = defaults
    elif 'events' not in config['env']['notifications']:
        config['env']['notifications']['events'] = defaults['events']


def _get_live_driver(exchange_name: str, api_key_id: str, user_id: str = None):
    """Instantiate and configure the appropriate live driver."""
    from qengine.live_drivers import live_drivers

    if exchange_name not in live_drivers:
        raise ValueError(f'No live driver found for {exchange_name}. Available: {list(live_drivers.keys())}')

    DriverClass = live_drivers[exchange_name]
    driver = DriverClass()

    # Load API credentials
    from qengine.services.env import ENV_VALUES
    import os

    broker_key_map = {
        'OANDA': {'api_key': 'OANDA_API_KEY', 'account_id': 'OANDA_ACCOUNT_ID'},
        'OANDA Demo': {'api_key': 'OANDA_API_KEY', 'account_id': 'OANDA_ACCOUNT_ID'},
        'IG Markets': {'api_key': 'IG_API_KEY', 'username': 'IG_USERNAME', 'password': 'IG_PASSWORD', 'account_id': 'IG_ACCOUNT_ID'},
        'IG Markets Demo': {'api_key': 'IG_API_KEY', 'username': 'IG_USERNAME', 'password': 'IG_PASSWORD', 'account_id': 'IG_ACCOUNT_ID'},
        'Interactive Brokers': {'api_key': None, 'account_id': 'IBKR_ACCOUNT_ID'},
        'Interactive Brokers Paper': {'api_key': None, 'account_id': 'IBKR_ACCOUNT_ID'},
    }

    creds = broker_key_map.get(exchange_name, {})
    def _env(key): return os.environ.get(key, ENV_VALUES.get(key, '')) if key else ''

    api_key = _env(creds.get('api_key', ''))
    account_id = _env(creds.get('account_id', ''))

    # Also try loading from DB-stored broker settings (set via UI)
    db_settings = {}
    try:
        from qengine.controllers.settings_controller import _get_settings_from_db, ADMIN_SETTINGS_ID
        from qengine.enums import brokers as broker_enums
        # Map exchange name to broker enum ID
        _name_to_id = {
            'OANDA': broker_enums.OANDA, 'OANDA Demo': broker_enums.OANDA_DEMO,
            'IG Markets': broker_enums.IG_MARKETS, 'IG Markets Demo': broker_enums.IG_MARKETS_DEMO,
            'Interactive Brokers': broker_enums.IBKR, 'Interactive Brokers Paper': broker_enums.IBKR_PAPER,
        }
        broker_id = _name_to_id.get(exchange_name)
        if broker_id:
            db_settings = _get_settings_from_db(ADMIN_SETTINGS_ID).get('brokers', {}).get(broker_id, {})
            if db_settings.get('api_key'):
                api_key = api_key or db_settings['api_key']
                account_id = account_id or db_settings.get('account_id', '')
    except Exception:
        db_settings = {}

    extra_kwargs = {}
    if 'IG' in exchange_name:
        extra_kwargs['username'] = _env(creds.get('username', '')) or db_settings.get('account_id', '')
        extra_kwargs['password'] = _env(creds.get('password', '')) or db_settings.get('api_secret', '')
        # IG account_id is the actual sub-account ID (CFD vs spread bet)
        ig_acct = _env(creds.get('account_id', '')) or db_settings.get('additional_fields', {}).get('ig_account_id', '')
        account_id = ig_acct  # override: account_id = IG sub-account, not username

    if hasattr(driver, 'configure'):
        driver.configure(api_key=api_key, account_id=account_id, **extra_kwargs)

    return driver


def _enrich_order_from_broker(driver, order, client_id: str):
    """Try to get fill details for a filled order from the broker.

    For OANDA, queries the transaction history to get fill price and trade ID.
    This allows us to link the internal ticket to the OANDA trade for TP/SL management.
    """
    if not hasattr(driver, '_rest_url'):
        return

    try:
        import requests
        # Query OANDA for the order's fill transaction
        resp = requests.get(
            f'{driver._rest_url}/accounts/{driver._account_id}/orders/{order.exchange_id}',
            headers=driver._headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get('order', {})
            # If order has a fillingTransactionID, get the fill details
            fill_tx_id = data.get('fillingTransactionID')
            if fill_tx_id:
                tx_resp = requests.get(
                    f'{driver._rest_url}/accounts/{driver._account_id}/transactions/{fill_tx_id}',
                    headers=driver._headers(),
                    timeout=10,
                )
                if tx_resp.status_code == 200:
                    tx = tx_resp.json().get('transaction', {})
                    fill_price = float(tx.get('price', 0))
                    if fill_price:
                        order.price = fill_price
                    # Get trade ID from fill
                    if 'tradeOpened' in tx:
                        order.vars['trade_id'] = str(tx['tradeOpened'].get('tradeID', ''))
                    elif 'tradesOpened' in tx and tx['tradesOpened']:
                        order.vars['trade_id'] = str(tx['tradesOpened'][0].get('tradeID', ''))
                    _log(client_id,
                         f'Enriched order {order.exchange_id}: '
                         f'fill_price={fill_price}, trade_id={order.vars.get("trade_id")}')
    except Exception as e:
        _log(client_id, f'Could not enrich order {order.exchange_id}: {e}', 'warning')


def _sync_orders_with_broker(driver, exchange_name: str, client_id: str) -> int:
    """Poll broker for pending orders and detect fills.

    Compares qengine's internal active orders with the broker's pending orders.
    If an internal active order's exchange_id is no longer in the broker's pending
    list, it was filled — so we execute it internally to trigger position updates
    and strategy callbacks (on_close_position, etc.).

    Returns the number of orders that were detected as filled.
    """
    try:
        broker_pending = driver.get_open_orders()
    except Exception as e:
        _log(client_id, f'Order sync failed (will retry): {e}', 'warning')
        return 0

    # Build set of exchange order IDs that are still pending on the broker
    broker_pending_ids = {str(o['id']) for o in broker_pending}

    filled_count = 0

    for r in router.routes:
        active_orders = store.orders.get_active_orders(r.exchange, r.symbol)
        for order in active_orders:
            if not order.is_active:
                continue
            # Only check orders that were actually submitted to the broker
            if not getattr(order, 'exchange_id', None):
                continue
            # If the order's exchange_id is no longer pending on the broker, it was filled
            if str(order.exchange_id) not in broker_pending_ids:
                _log(client_id,
                     f'Order filled on broker: {order.symbol} {order.side} {order.type} '
                     f'qty={order.qty} price={order.price} (exchange_id={order.exchange_id})')
                try:
                    # Try to get fill details from broker (price, trade_id)
                    _enrich_order_from_broker(driver, order, client_id)
                    order_service.execute_order(order)
                    filled_count += 1
                except Exception as e:
                    _log(client_id, f'Error processing filled order {order.id}: {e}', 'error')

    return filled_count


def _sync_trades_with_broker(driver, exchange_name: str, client_id: str) -> int:
    """Detect per-trade TP/SL closures in OANDA hedging mode.

    Compares internal tickets (with exchange_trade_ids) against broker's open trades.
    If a ticket's trade_id is no longer open on the broker, the trade was closed
    (e.g., by per-trade TP/SL). Updates internal state accordingly.

    Returns count of trades detected as closed.
    """
    if not hasattr(driver, 'get_open_trades'):
        return 0

    try:
        broker_trades = driver.get_open_trades()
    except Exception as e:
        _log(client_id, f'Trade sync failed (will retry): {e}', 'warning')
        return 0

    broker_trade_ids = {str(t['trade_id']) for t in broker_trades}
    closed_count = 0

    for r in router.routes:
        p = store.positions.get_position(r.exchange, r.symbol)
        if not p or not p.is_open or not p.is_cfd_mode:
            continue

        tickets_to_close = []
        for ticket in p.tickets:
            if ticket.exchange_trade_id and str(ticket.exchange_trade_id) not in broker_trade_ids:
                tickets_to_close.append(ticket)

        if not tickets_to_close:
            continue

        # Some trades were closed by OANDA (per-trade TP/SL)
        for ticket in tickets_to_close:
            _log(client_id,
                 f'[Trade sync] Trade {ticket.exchange_trade_id} closed on broker '
                 f'(ticket {ticket.id[:8]}, {ticket.type} {ticket.qty:.0f})')

            # TODO: query broker transaction log for actual fill price instead of
            # using cached current_price, which may be stale by the poll interval.
            fill_price = p.current_price

            # Determine if this was a TP or SL closure based on ticket's stored levels
            exit_reason = None
            if ticket.tp_price is not None and ticket.sl_price is not None:
                # Both set — infer from fill price proximity
                tp_dist = abs(fill_price - ticket.tp_price)
                sl_dist = abs(fill_price - ticket.sl_price)
                exit_reason = 'tp_hit' if tp_dist <= sl_dist else 'sl_hit'
            elif ticket.tp_price is not None:
                exit_reason = 'tp_hit'
            elif ticket.sl_price is not None:
                exit_reason = 'sl_hit'

            result = p.close_ticket(ticket.id, fill_price)
            if result:
                pnl = result['pnl']
                if p.exchange and p.exchange.type in ('cfd',):
                    p.exchange.add_realized_pnl(pnl)
                from qengine.services import closed_trade_service
                closed_trade_service.record_ticket_close(
                    p, result['ticket'], fill_price, pnl,
                    meta={'exit_reason': exit_reason} if exit_reason else None,
                )
                closed_count += 1

                # Fire strategy callback
                if r.strategy is not None and exit_reason:
                    if exit_reason == 'tp_hit':
                        r.strategy.on_ticket_tp_hit(ticket, fill_price)
                    elif exit_reason == 'sl_hit':
                        r.strategy.on_ticket_sl_hit(ticket, fill_price)

    if closed_count > 0:
        _log(client_id, f'Trade sync: {closed_count} trade(s) closed by broker TP/SL')

    return closed_count


def _sync_positions_with_broker(driver, exchange_name: str, client_id: str):
    """Fallback safety: compare broker positions with internal state.

    If the broker shows flat but qengine thinks there's an open position,
    force-close the internal position to prevent stale state.
    """
    try:
        broker_positions = driver.get_open_positions()
    except Exception as e:
        _log(client_id, f'Position sync failed (will retry): {e}', 'warning')
        return

    # Build map of broker positions by symbol
    broker_pos_map = {}
    for bp in broker_positions:
        sym = bp['symbol']
        net_units = bp.get('long_units', 0) + bp.get('short_units', 0)
        broker_pos_map[sym] = net_units

    for r in router.routes:
        p = store.positions.get_position(r.exchange, r.symbol)
        if not p or not p.is_open:
            continue

        broker_qty = broker_pos_map.get(r.symbol, 0)
        if broker_qty == 0:
            # Broker is flat but we think we have a position — stale state
            _log(client_id,
                 f'[POSITION SYNC] Broker is FLAT for {r.symbol} but internal state shows '
                 f'{p.type} qty={p.qty}. Force-closing internal position.',
                 'warning')
            # Cancel any remaining active orders internally
            active_orders = store.orders.get_active_orders(r.exchange, r.symbol)
            for order in active_orders:
                if order.is_active:
                    try:
                        order_service.cancel_order(order, silent=True)
                    except Exception:
                        pass
            # Force-close the internal position
            try:
                from qengine.services.broker import Broker
                broker_svc = Broker(p, r.exchange, r.symbol, r.timeframe)
                # Create a synthetic close order at current price
                close_qty = abs(p.qty)
                close_side = 'sell' if p.qty > 0 else 'buy'
                close_order = order_service.create_order({
                    'id': jh.generate_unique_id(),
                    'exchange_id': '',
                    'symbol': r.symbol,
                    'exchange': r.exchange,
                    'side': close_side,
                    'type': 'MARKET',
                    'reduce_only': True,
                    'qty': jh.prepare_qty(close_qty, close_side),
                    'price': p.current_price,
                }, should_silent=True)
                order_service.execute_order(close_order)
                _log(client_id,
                     f'[POSITION SYNC] Internal position force-closed for {r.symbol}')
            except Exception as e:
                _log(client_id,
                     f'[POSITION SYNC] Failed to force-close {r.symbol}: {e}', 'error')


def _run_live_mode(client_id: str, driver, exchange_name: str):
    """Live/demo trading: execute strategies and submit orders to broker API."""
    _log(client_id, 'Orders will be submitted to broker API')

    symbols = [r.symbol for r in router.routes]
    _log(client_id, f'Symbols to stream: {symbols}')
    price_data = {}
    tick_count = [0]

    def on_price(tick: dict):
        """Callback receives a dict: {symbol, bid, ask, price, time}"""
        sym = tick['symbol']
        price_data[sym] = {
            'bid': tick['bid'],
            'ask': tick['ask'],
            'mid': tick['price'],
            'time': jh.now_to_timestamp(),
        }
        tick_count[0] += 1
        if tick_count[0] <= 3:
            _log(client_id, f'Tick #{tick_count[0]}: {sym} bid={tick["bid"]} ask={tick["ask"]} mid={tick["price"]}')

    # Start streaming
    _log(client_id, f'Starting price stream for {symbols}...')
    stream_thread = threading.Thread(
        target=lambda: driver.start_price_stream(symbols, on_price),
        daemon=True
    )
    stream_thread.start()
    time.sleep(3)

    _log(client_id, f'After 3s wait: got {tick_count[0]} ticks, symbols with data: {list(price_data.keys())}')

    # Candle builders for live mode
    candle_builders = {}
    for r in router.routes:
        candle_builders[f'{r.exchange}-{r.symbol}-{r.timeframe}'] = _CandleBuilder(r.timeframe)

    _seed_candles(symbols, exchange_name, candle_builders, client_id)

    # IG has strict rate limits (~60 req/min) so use longer intervals
    _is_ig = 'ig' in exchange_name.lower()

    # Account sync interval (every 30 seconds, with backoff on failure)
    last_account_sync = 0
    # Order sync interval — OANDA: 3s (low latency), IG: 10s (rate limit)
    last_order_sync = 0
    _ORDER_SYNC_INTERVAL_MS = 10_000 if _is_ig else 3_000
    # Trade sync interval — OANDA: 3s, IG: 10s
    last_trade_sync = 0
    _TRADE_SYNC_INTERVAL_MS = 10_000 if _is_ig else 3_000
    # Position sync interval (every 30 seconds — fallback safety net)
    last_position_sync = 0
    _POSITION_SYNC_INTERVAL_MS = 60_000 if _is_ig else 30_000

    last_execution = {}
    execution_count = [0]
    for r in router.routes:
        last_execution[f'{r.exchange}-{r.symbol}'] = 0

    _log(client_id, 'Entering main trading loop...')

    while is_process_active(client_id):
        time.sleep(1)

        now = jh.now_to_timestamp()

        # Periodically sync account balance from broker (backoff-aware interval)
        sync_interval = _get_sync_interval(exchange_name)
        if now - last_account_sync >= sync_interval:
            last_account_sync = now
            _sync_account_balance(exchange_name, driver, client_id)

        # Sync order fills from broker (detect TP/SL fills)
        force_execute = False
        if now - last_order_sync >= _ORDER_SYNC_INTERVAL_MS:
            last_order_sync = now
            filled = _sync_orders_with_broker(driver, exchange_name, client_id)
            if filled > 0:
                _log(client_id, f'Order sync: {filled} order(s) filled on broker')
                # Force immediate strategy execution so hedge orders are placed ASAP
                force_execute = True

        # Trade-level sync (detect per-trade TP/SL closures in hedging mode)
        if now - last_trade_sync >= _TRADE_SYNC_INTERVAL_MS:
            last_trade_sync = now
            trades_closed = _sync_trades_with_broker(driver, exchange_name, client_id)
            if trades_closed > 0:
                force_execute = True

        # Position sync fallback (detect stale internal state)
        if now - last_position_sync >= _POSITION_SYNC_INTERVAL_MS:
            last_position_sync = now
            _sync_positions_with_broker(driver, exchange_name, client_id)

        for r in router.routes:
            key = f'{r.exchange}-{r.symbol}'
            if r.symbol not in price_data:
                continue

            current_price = price_data[r.symbol]['mid']

            p = store.positions.get_position(r.exchange, r.symbol)
            if p:
                p.current_price = current_price

            # Feed price into candle builder
            cb_key = f'{r.exchange}-{r.symbol}-{r.timeframe}'
            builder = candle_builders[cb_key]
            new_candle = builder.update(current_price, now)

            _update_live_candle(r.exchange, r.symbol, r.timeframe, builder.current_candle())

            minutes = TIMEFRAME_TO_ONE_MINUTES.get(r.timeframe, 1)
            interval_ms = minutes * 60 * 1000

            # Between full strategy executions, run lightweight checks every tick (1s):
            # - before(): detect broker-side fills (TP/SL closures, hedge fills)
            # - update_position(): fallback price checks for strategies without broker orders
            if now - last_execution[key] < interval_ms and not force_execute:
                try:
                    r.strategy._cached_price = current_price
                    r.strategy.before()
                    if p and p.is_open and hasattr(r.strategy, 'update_position'):
                        r.strategy.update_position()
                    r.strategy._cached_price = None
                except Exception as e:
                    r.strategy._cached_price = None
                    _log(client_id, f'Tick check error: {e}', 'error')

            # Execute strategy on timeframe interval OR immediately after a fill is detected
            if now - last_execution[key] >= interval_ms or force_execute:
                last_execution[key] = now
                store.app.time = now

                if new_candle is not None:
                    _append_candle_to_store(r.exchange, r.symbol, r.timeframe, new_candle)

                execution_count[0] += 1
                try:
                    r.strategy._execute()
                    # Log first few ticks and then periodically
                    if execution_count[0] <= 3 or execution_count[0] % 60 == 0 or force_execute:
                        orders = store.orders.get_orders(r.exchange, r.symbol)
                        active = [o for o in orders if o.status == 'ACTIVE']
                        executed = [o for o in orders if o.status == 'EXECUTED']
                        _log(client_id, f'Strategy tick #{execution_count[0]}: {r.symbol} price={current_price}, orders={len(executed)} filled / {len(active)} pending, pos={p.type if p and p.is_open else "flat"} qty={p.qty if p else 0}')
                except Exception as e:
                    _log(client_id, f'Strategy error: {e}', 'error')
                    import traceback
                    _log(client_id, traceback.format_exc(), 'error')

        _publish_state(client_id)

    _graceful_shutdown(client_id, exchange_name, is_paper=False)
    _log(client_id, 'Trading stopped')


def _log(session_id: str, message: str, level: str = 'info'):
    """Store log entry in Redis (accessible cross-process)."""
    entry = {
        'time': jh.now_to_timestamp(),
        'message': message,
        'level': level,
    }
    try:
        key = f'{_REDIS_LOG_KEY}{session_id}'
        sync_redis.rpush(key, json.dumps(entry))
        # Trim to keep bounded
        sync_redis.ltrim(key, -_REDIS_MAX_LOGS, -1)
        # Expire after 24h so stale sessions auto-clean
        sync_redis.expire(key, 86400)
    except Exception:
        pass

    # Also log via qengine logger
    if level == 'error':
        logger.error(message)
    else:
        logger.info(message)


def _publish_state(client_id: str):
    """Publish comprehensive state to Redis for cross-process frontend access."""
    try:
        now_ts = jh.now_to_timestamp()

        # ── Positions ──
        positions = []
        total_unrealized_pnl = 0
        for key, pos in store.positions.storage.items():
            pnl = round(pos.pnl, 4) if pos.is_open else 0
            pnl_pct = round(pos.pnl_percentage, 2) if pos.is_open and pos.pnl_percentage else 0
            value = round(pos.value, 2) if pos.is_open and pos.value else 0
            leverage = int(pos.leverage) if pos.is_open else 0

            if pos.is_open:
                total_unrealized_pnl += pnl

            # Per-ticket details (CFD mode)
            tickets = []
            if pos.is_cfd_mode and pos._tickets:
                for t in pos._tickets:
                    t_pnl = t.pnl(pos.current_price) if pos.current_price else 0
                    pip_size = jh.get_pip_size(pos.symbol) if hasattr(jh, 'get_pip_size') else 0.0001
                    t_pips = (t_pnl / t.qty / pip_size) if t.qty and pip_size else 0
                    tickets.append({
                        'id': t.id[:8],
                        'type': t.type,
                        'qty': t.qty,
                        'entry_price': t.entry_price,
                        'pnl': round(t_pnl, 4),
                        'pips': round(t_pips, 1),
                        'trade_id': t.exchange_trade_id,
                        'opened_at': t.opened_at,
                    })

            positions.append({
                'symbol': pos.symbol,
                'exchange': pos.exchange_name,
                'type': pos.type if pos.is_open else 'close',
                'qty': pos.qty,
                'entry_price': pos.entry_price,
                'current_price': pos.current_price,
                'pnl': pnl,
                'pnl_percentage': pnl_pct,
                'value': value,
                'leverage': leverage,
                'opened_at': pos.opened_at,
                'tickets': tickets,
            })

        pos_key = f'{_REDIS_POSITIONS_KEY}{client_id}'
        sync_redis.set(pos_key, json.dumps(positions))
        sync_redis.expire(pos_key, 86400)

        # ── Orders ──
        all_orders = []
        for okey, order_list in store.orders.storage.items():
            for o in order_list:
                all_orders.append({
                    'id': str(o.id) if hasattr(o, 'id') else '',
                    'symbol': o.symbol,
                    'exchange': o.exchange if hasattr(o, 'exchange') else '',
                    'side': o.side,
                    'type': o.type,
                    'qty': o.qty,
                    'filled_qty': getattr(o, 'filled_qty', o.qty if o.is_executed else 0),
                    'price': o.price,
                    'status': o.status,
                    'reduce_only': getattr(o, 'reduce_only', False),
                    'created_at': o.created_at,
                    'executed_at': o.executed_at,
                    'canceled_at': getattr(o, 'canceled_at', None),
                })

        orders_key = f'{_REDIS_ORDERS_KEY}{client_id}'
        sync_redis.set(orders_key, json.dumps(all_orders))
        sync_redis.expire(orders_key, 86400)

        # ── Closed trades analysis ──
        closed_trades = store.closed_trades.trades
        realized_pnl = sum(t.pnl for t in closed_trades) if closed_trades else 0
        winning_trades = len([t for t in closed_trades if t.pnl > 0])
        losing_trades = len([t for t in closed_trades if t.pnl <= 0])
        total_trades = len(closed_trades)

        # ── Account / Exchange summary ──
        account = {}
        for ename, exch in store.exchanges.storage.items():
            try:
                balance = round(exch.wallet_balance, 2)
                avail_margin = round(exch.available_margin, 2)
                started_balance = round(getattr(exch, '_started_balance', 0), 2)
                margin_used = round(balance - avail_margin, 2)
                equity = round(balance + total_unrealized_pnl, 2)

                # Merge data from the driver's get_account_summary() if available
                broker_data = _last_account_data.get(ename, {})

                # Session duration
                session_duration = 0
                if store.app.starting_time:
                    session_duration = now_ts - store.app.starting_time

                # Position value: sum of open position values
                position_value = sum(
                    round(pos.value, 2) for pos in store.positions.storage.values()
                    if pos.is_open and pos.value
                )

                account = {
                    'exchange': ename,
                    'balance': balance,
                    'equity': equity,
                    'nav': round(broker_data.get('nav', equity), 2),
                    'available_margin': avail_margin,
                    'margin_used': margin_used,
                    'position_value': round(position_value, 2),
                    'unrealized_pnl': round(total_unrealized_pnl, 4),
                    'realized_pnl': round(realized_pnl, 4),
                    'started_balance': started_balance,
                    'type': getattr(exch, 'type', ''),
                    'leverage': getattr(exch, 'default_leverage', 1),
                    'currency': broker_data.get('currency', jh.app_currency()),
                    'account_id': broker_data.get('account_id', ''),
                    'open_trade_count': len([p for p in positions if p['type'] != 'close']),
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'losing_trades': losing_trades,
                    'session_duration': session_duration,
                }
            except Exception:
                pass

        # ── Closed Trades History ──
        closed_trades_list = []
        for ct in closed_trades:
            ct_dict = {
                'id': str(ct.id) if hasattr(ct, 'id') else '',
                'symbol': ct.symbol,
                'type': ct.type,
                'entry_price': ct.entry_price,
                'exit_price': ct.exit_price,
                'qty': ct.qty,
                'pnl': round(ct.pnl, 4),
                'pnl_percentage': round(ct.pnl_percentage, 2) if ct.pnl_percentage else 0,
                'opened_at': ct.opened_at,
                'closed_at': ct.closed_at,
            }
            # Include meta if available (session, level, exit_reason for surefire)
            if hasattr(ct, 'meta') and ct.meta:
                ct_dict['meta'] = ct.meta
            closed_trades_list.append(ct_dict)

        # ── Strategy info + session tracking ──
        strategies = []
        for r in router.routes:
            s = r.strategy
            if not s:
                continue
            p = store.positions.get_position(r.exchange, r.symbol)
            strat_info = {
                'name': r.strategy_name,
                'symbol': r.symbol,
                'timeframe': r.timeframe,
                'exchange': r.exchange,
                'has_position': p.is_open if p else False,
                'position_type': p.type if p and p.is_open else None,
                'position_qty': p.qty if p else 0,
                'position_pnl': round(p.pnl, 4) if p and p.is_open else 0,
                'hyperparameters': s.hp if s.hp else {},
            }
            # Include surefire session tracking if available
            if hasattr(s, 'vars') and 'sessions' in s.vars:
                strat_info['sessions'] = s.vars['sessions']
                # Derive direction from first leg or position
                direction = None
                legs = s.vars.get('legs', [])
                if legs:
                    first_side = legs[0].get('side') or legs[0].get('type')
                    direction = 'long' if first_side in ('buy', 'long') else 'short' if first_side in ('sell', 'short') else None
                strat_info['current_session'] = {
                    'session_number': s.vars.get('session_number', 0),
                    'level': s.vars.get('level', 0),
                    'cycle_active': s.vars.get('cycle_active', False),
                    'tp_price': s.vars.get('tp_price'),
                    'hedge_price': s.vars.get('hedge_trigger_price'),
                    'legs': legs,
                    'direction': direction,
                    'net_qty': round(p.qty, 2) if p else 0,
                    'ticket_count': p.ticket_count if p and hasattr(p, 'ticket_count') else 0,
                }
            # Include watch_list if available
            if hasattr(s, 'watch_list'):
                try:
                    strat_info['watch_list'] = s.watch_list()
                except Exception:
                    pass
            strategies.append(strat_info)

        # ── Aggregate state object ──
        total_orders = len(all_orders)
        executed_orders = len([o for o in all_orders if o['status'] == 'EXECUTED'])
        active_orders = len([o for o in all_orders if o['status'] == 'ACTIVE'])
        canceled_orders = len([o for o in all_orders if o['status'] == 'CANCELED'])
        open_positions = [p for p in positions if p['type'] != 'close']

        equity = account.get('equity', account.get('balance', 0) + total_unrealized_pnl)

        state = {
            'time': now_ts,
            'account': account,
            'equity': round(equity, 2),
            'unrealized_pnl': round(total_unrealized_pnl, 4),
            'realized_pnl': round(realized_pnl, 4),
            'positions': positions,
            'open_positions_count': len(open_positions),
            'orders_summary': {
                'total': total_orders,
                'active': active_orders,
                'executed': executed_orders,
                'canceled': canceled_orders,
            },
            'orders': all_orders,
            'closed_trades': closed_trades_list,
            'strategies': strategies,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
        }

        state_key = f'{_REDIS_STATE_KEY}{client_id}'
        sync_redis.set(state_key, json.dumps(state))
        sync_redis.expire(state_key, 86400)

        # pub/sub for real-time
        sync_publish('live-update', {
            'id': client_id,
            'positions': open_positions,
            'equity': round(equity, 2),
            'time': now_ts,
        })
    except Exception as e:
        import qengine.services.logger as logger
        logger.error(f'Error in _publish_state: {e}')


def get_live_logs(session_id: str, log_type: str = 'info', start_time: int = 0) -> list:
    """Get logs for a live session from Redis."""
    try:
        key = f'{_REDIS_LOG_KEY}{session_id}'
        raw_entries = sync_redis.lrange(key, 0, -1)
        logs = [json.loads(entry) for entry in raw_entries]
    except Exception:
        return []

    if start_time:
        logs = [l for l in logs if l['time'] > start_time]
    if log_type and log_type != 'all':
        logs = [l for l in logs if l['level'] == log_type]
    return logs


def get_live_orders(session_id: str) -> list:
    """Get orders for a live session from Redis."""
    try:
        key = f'{_REDIS_ORDERS_KEY}{session_id}'
        raw = sync_redis.get(key)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return []


def get_live_positions(session_id: str) -> list:
    """Get positions for a live session from Redis."""
    try:
        key = f'{_REDIS_POSITIONS_KEY}{session_id}'
        raw = sync_redis.get(key)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return []


def get_live_state(session_id: str) -> dict:
    """Get comprehensive live session state from Redis."""
    try:
        key = f'{_REDIS_STATE_KEY}{session_id}'
        raw = sync_redis.get(key)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {}


# ── Account Sync ──

def _sync_account_balance(exchange_name: str, driver, client_id: str) -> bool:
    """Fetch account summary from broker and update the exchange model.

    Returns True on success, False on failure.  Uses exponential backoff
    (30s -> 60s -> 120s -> 300s max) so failed syncs don't hammer the API.
    """
    global _last_account_data, _sync_backoff

    try:
        account = driver.get_account_summary()
        balance = account.get('balance', 0)
        margin_available = account.get('margin_available', balance)

        exchange_obj = store.exchanges.storage.get(exchange_name)
        if exchange_obj and hasattr(exchange_obj, 'update_from_stream'):
            exchange_obj.update_from_stream({
                'wallet_balance': balance,
                'available_margin': margin_available,
            })

        # Store the full account data for _publish_state
        _last_account_data[exchange_name] = account

        # Reset backoff on success
        _sync_backoff[exchange_name] = {'interval': 30_000, 'failures': 0, 'last_logged': False}

        _log(client_id, f'Account synced: balance={balance}, margin={margin_available}')
        return True
    except Exception as e:
        # Exponential backoff: only log on first failure and when backoff increases
        backoff = _sync_backoff.get(exchange_name, {'interval': 30_000, 'failures': 0, 'last_logged': False})
        backoff['failures'] += 1
        old_interval = backoff['interval']
        # Double interval on failure, cap at 300s (5 minutes)
        backoff['interval'] = min(old_interval * 2, 300_000)

        if not backoff['last_logged'] or backoff['interval'] != old_interval:
            _log(client_id, f'Account sync failed (attempt {backoff["failures"]}, next retry in {backoff["interval"] // 1000}s): {e}', 'warning')
            backoff['last_logged'] = True

        _sync_backoff[exchange_name] = backoff
        return False


def _get_sync_interval(exchange_name: str) -> int:
    """Return current sync interval in ms, respecting backoff state."""
    backoff = _sync_backoff.get(exchange_name)
    if backoff:
        return backoff['interval']
    return 30_000


# ── Graceful Shutdown & Session Report ──

def _graceful_shutdown(client_id: str, exchange_name: str, is_paper: bool) -> None:
    """Gracefully shut down a live/paper trading session.

    Cancels all active orders, closes all open positions, waits for fills,
    then computes and stores the session report.
    """
    from qengine.enums import order_statuses, sides
    from qengine.services.api import api

    _log(client_id, 'Shutting down gracefully...')

    # 1. Cancel all active orders (on broker AND internally)
    for r in router.routes:
        try:
            # Cancel on the broker side first
            if r.exchange in api.drivers:
                api.drivers[r.exchange].cancel_all_orders(r.symbol)
                _log(client_id, f'Cancelled all broker orders for {r.symbol}')
        except Exception as e:
            _log(client_id, f'Failed to cancel broker orders for {r.symbol}: {e}', 'warning')

    # Then cancel internally
    for okey, order_list in store.orders.storage.items():
        for order in order_list:
            if order.status == order_statuses.ACTIVE:
                try:
                    _log(client_id, f'Cancelling order {order.id} ({order.symbol} {order.side} {order.type} qty={order.qty})')
                    order_service.cancel_order(order)
                except Exception as e:
                    _log(client_id, f'Failed to cancel order {order.id}: {e}', 'warning')

    # 2. Close all open positions
    for pos_key, pos in store.positions.storage.items():
        if not pos.is_open:
            continue
        try:
            close_side = sides.SELL if pos.qty > 0 else sides.BUY
            close_qty = abs(pos.qty)
            current_price = pos.current_price
            _log(client_id, f'Closing position {pos.symbol}: {close_side} {close_qty} @ ~{current_price}')

            api.market_order(
                pos.exchange_name,
                pos.symbol,
                close_qty,
                current_price,
                close_side,
                reduce_only=True,
            )
        except Exception as e:
            _log(client_id, f'Failed to close position {pos.symbol}: {e}', 'warning')

    # 3. Wait for fills
    time.sleep(2)

    # 4. Compute and store the session report
    _compute_session_report(client_id)


def _compute_session_report(client_id: str) -> dict:
    """Compute post-session analysis and store in Redis.

    Stores total_trades, win/loss stats, PnL metrics, streak info,
    fee totals, holding periods, drawdown, and a full trades list.
    Returns the report dict.
    """
    trades = store.closed_trades.trades
    total_trades = len(trades)

    # Basic counts
    winning = [t for t in trades if t.pnl > 0]
    losing = [t for t in trades if t.pnl <= 0]
    winning_count = len(winning)
    losing_count = len(losing)
    win_rate = round((winning_count / total_trades * 100), 2) if total_trades > 0 else 0.0

    # PnL
    total_pnl = sum(t.pnl for t in trades)
    avg_win = round(sum(t.pnl for t in winning) / winning_count, 4) if winning_count > 0 else 0.0
    avg_loss = round(sum(t.pnl for t in losing) / losing_count, 4) if losing_count > 0 else 0.0
    largest_win = round(max((t.pnl for t in winning), default=0), 4)
    largest_loss = round(min((t.pnl for t in losing), default=0), 4)

    # Fees
    total_fees = sum(t.fee for t in trades)

    # Avg holding period (seconds)
    holding_periods = [t.holding_period for t in trades if t.holding_period is not None]
    avg_holding_period = round(sum(holding_periods) / len(holding_periods), 2) if holding_periods else 0.0

    # Streaks
    winning_streak = 0
    losing_streak = 0
    current_win = 0
    current_lose = 0
    for t in trades:
        if t.pnl > 0:
            current_win += 1
            current_lose = 0
            winning_streak = max(winning_streak, current_win)
        else:
            current_lose += 1
            current_win = 0
            losing_streak = max(losing_streak, current_lose)

    # Balance / drawdown tracking from closed trades
    exchange_obj = None
    started_balance = 0
    ending_balance = 0
    for ename, exch in store.exchanges.storage.items():
        exchange_obj = exch
        started_balance = round(getattr(exch, '_started_balance', 0), 2)
        ending_balance = round(exch.wallet_balance, 2)
        break

    total_pnl_pct = round((total_pnl / started_balance * 100), 2) if started_balance > 0 else 0.0

    # Simple max drawdown from cumulative PnL of closed trades
    max_drawdown = 0.0
    peak_equity = started_balance
    running_equity = started_balance
    for t in trades:
        running_equity += t.pnl
        if running_equity > peak_equity:
            peak_equity = running_equity
        dd = peak_equity - running_equity
        if dd > max_drawdown:
            max_drawdown = dd
    max_drawdown = round(max_drawdown, 4)

    # Session duration
    session_duration = 0
    if store.app.starting_time:
        session_duration = jh.now_to_timestamp() - store.app.starting_time

    # Build trades list
    trades_list = []
    for t in trades:
        try:
            trades_list.append(t.to_dict)
        except Exception:
            pass

    # Build hedge sessions from trade meta (if strategy uses session tracking)
    from qengine.services.report import hedge_sessions as _build_hedge_sessions
    sessions_list = _build_hedge_sessions()

    report = {
        'session_id': client_id,
        'total_trades': total_trades,
        'winning_trades': winning_count,
        'losing_trades': losing_count,
        'win_rate': win_rate,
        'total_pnl': round(total_pnl, 4),
        'total_pnl_pct': total_pnl_pct,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'largest_win': largest_win,
        'largest_loss': largest_loss,
        'winning_streak': winning_streak,
        'losing_streak': losing_streak,
        'total_fees': round(total_fees, 4),
        'avg_holding_period': avg_holding_period,
        'session_duration': session_duration,
        'starting_balance': started_balance,
        'ending_balance': ending_balance,
        'max_drawdown': max_drawdown,
        'trades': trades_list,
    }
    if sessions_list:
        report['sessions'] = sessions_list

    # Store in Redis with 7-day expiry
    try:
        report_key = f'{_REDIS_REPORT_KEY}{client_id}'
        sync_redis.set(report_key, json.dumps(report))
        sync_redis.expire(report_key, 7 * 86400)  # 7 days
        _log(client_id, f'Session report stored: {total_trades} trades, PnL={round(total_pnl, 2)}, win_rate={win_rate}%')
    except Exception as e:
        _log(client_id, f'Failed to store session report: {e}', 'warning')

    return report


def get_session_report(session_id: str) -> dict:
    """Retrieve a stored session report from Redis."""
    try:
        report_key = f'{_REDIS_REPORT_KEY}{session_id}'
        raw = sync_redis.get(report_key)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {}


# ── Candle Building from Tick Data ──

class _CandleBuilder:
    """Builds OHLCV candles from streaming tick prices."""

    def __init__(self, timeframe: str):
        self.timeframe = timeframe
        self._interval_ms = TIMEFRAME_TO_ONE_MINUTES.get(timeframe, 1) * 60 * 1000
        self._open = 0.0
        self._high = 0.0
        self._low = 0.0
        self._close = 0.0
        self._volume = 0.0
        self._candle_start = 0
        self._tick_count = 0

    def update(self, price: float, timestamp: int) -> np.ndarray:
        """Feed a tick. Returns a closed candle array if the period ended, else None."""
        if self._tick_count == 0:
            # First tick: start the candle
            self._candle_start = self._align_timestamp(timestamp)
            self._open = price
            self._high = price
            self._low = price
            self._close = price
            self._tick_count = 1
            return None

        # Check if we've crossed into a new candle period
        aligned = self._align_timestamp(timestamp)
        if aligned > self._candle_start:
            # Close current candle and return it
            closed = np.array([
                self._candle_start,
                self._open,
                self._close,
                self._high,
                self._low,
                self._volume,
            ])

            # Start new candle
            self._candle_start = aligned
            self._open = price
            self._high = price
            self._low = price
            self._close = price
            self._volume = 0.0
            self._tick_count = 1

            return closed

        # Same period: update OHLC
        self._high = max(self._high, price)
        self._low = min(self._low, price)
        self._close = price
        self._volume += 1
        self._tick_count += 1
        return None

    def current_candle(self) -> np.ndarray:
        """Get the in-progress candle (not yet closed)."""
        return np.array([
            self._candle_start,
            self._open,
            self._close,
            self._high,
            self._low,
            self._volume,
        ])

    def _align_timestamp(self, ts: int) -> int:
        """Align timestamp to the start of the candle period."""
        return (ts // self._interval_ms) * self._interval_ms


def _seed_candles(symbols: list, exchange_name: str, candle_builders: dict, client_id: str) -> None:
    """
    Seed the candle store with historical candles from the database so
    indicators have enough data from the very first strategy execution.
    If unavailable, logs a warning (candles will build from the live stream).
    """
    for r in router.routes:
        try:
            # Try to load 1m candles directly from the DB (bypasses day-floor
            # logic in get_candles_from_db which breaks same-day ranges).
            now_ts = jh.now_to_timestamp()
            tf_minutes = TIMEFRAME_TO_ONE_MINUTES.get(r.timeframe, 1)
            warmup_candles = 500
            start_ts = now_ts - (warmup_candles * tf_minutes * 60 * 1000)

            from qengine.services.candle_service import _get_candles_from_db
            candles = _get_candles_from_db(
                r.exchange, r.symbol, start_ts, now_ts
            )
            if candles is not None and len(candles) > 0:
                key = jh.key(r.exchange, r.symbol, r.timeframe)
                dna = store.candles.storage.get(key)
                if dna is not None:
                    for c in candles:
                        dna.append(c)
                _log(client_id, f'Seeded {len(candles)} candles for {r.symbol} {r.timeframe}')
                continue
        except Exception as e:
            _log(client_id, f'Could not load historical candles for {r.symbol}: {e}', 'warning')

        _log(client_id, f'No historical candles for {r.symbol} {r.timeframe} - will build from stream')


def _update_live_candle(exchange: str, symbol: str, timeframe: str, candle: np.ndarray) -> None:
    """Update the latest (in-progress) candle in the store."""
    try:
        key = jh.key(exchange, symbol, timeframe)
        dna = store.candles.storage.get(key)
        if dna is not None and len(dna) > 0:
            dna[-1] = candle
        elif dna is not None:
            # Empty store - append first candle
            dna.append(candle)
    except Exception:
        pass


def _append_candle_to_store(exchange: str, symbol: str, timeframe: str, candle: np.ndarray) -> None:
    """Append a closed candle to the store (DynamicNumpyArray)."""
    try:
        key = jh.key(exchange, symbol, timeframe)
        dna = store.candles.storage.get(key)
        if dna is not None:
            dna.append(candle)
    except Exception:
        pass
