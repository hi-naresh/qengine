import json
import threading
from typing import List, Callable

import requests

from qengine.enums import brokers
from qengine.live_drivers.base import ForexLiveDriver
from qengine.modes.import_candles_mode.drivers.IG.ig_utils import symbol_to_epic, DEFAULT_EPIC_MAP
from qengine.services import logger


class IGMarketsLiveDriverBase(ForexLiveDriver):
    """
    IG Markets REST API driver for live/paper trading.

    Authentication uses CST + X-SECURITY-TOKEN from /session endpoint.
    Demo: https://demo-api.ig.com/gateway/deal
    Live: https://api.ig.com/gateway/deal
    """

    def __init__(self, name: str, is_demo: bool = False):
        super().__init__(name=name, is_demo=is_demo)
        if is_demo:
            self._base_url = 'https://demo-api.ig.com/gateway/deal'
        else:
            self._base_url = 'https://api.ig.com/gateway/deal'

        self._ig_api_key: str = ''
        self._username: str = ''
        self._password: str = ''
        self._cst: str = ''
        self._security_token: str = ''
        self._deal_reference_prefix = 'TE_'
        self._currency = 'USD'
        self._ls_endpoint: str = ''  # Lightstreamer endpoint from session
        self._instrument_cache: dict = {}  # epic -> instrument data
        self._last_auth_attempt: float = 0  # timestamp of last auth attempt
        self._auth_cooldown: float = 10  # seconds between re-auth attempts
        self._rate_limited_until: float = 0  # backoff until this timestamp
        self._rate_limit_backoff: float = 5  # seconds to back off on 403

    def configure(self, api_key: str, account_id: str = None, **kwargs) -> None:
        super().configure(api_key, account_id, **kwargs)
        self._ig_api_key = api_key
        self._username = kwargs.get('username', '')
        self._password = kwargs.get('password', '')
        if 'currency' in kwargs:
            self._currency = kwargs['currency']

    def _authenticate(self) -> None:
        """Authenticate and get CST + security token, then switch to CFD account."""
        import time
        self._last_auth_attempt = time.time()
        resp = requests.post(
            f'{self._base_url}/session',
            headers={
                'X-IG-API-KEY': self._ig_api_key,
                'Content-Type': 'application/json',
                'Version': '2',
            },
            json={
                'identifier': self._username,
                'password': self._password,
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._cst = resp.headers.get('CST', '')
        self._security_token = resp.headers.get('X-SECURITY-TOKEN', '')
        self._ls_endpoint = resp.json().get('lightstreamerEndpoint', '')
        self._connected = True

        # Switch to the correct account (CFD, not spread bet)
        target_account_id = self._resolve_cfd_account_id()
        if target_account_id:
            current = resp.json().get('currentAccountId', '')
            if current != target_account_id:
                self._switch_account(target_account_id)

    def _resolve_cfd_account_id(self) -> str:
        """Find the CFD account ID. Uses configured account_id, or auto-detects from account list."""
        if self._account_id:
            return self._account_id

        # Fetch accounts and find the CFD one
        try:
            resp = self._safe_request(
                'get',
                f'{self._base_url}/accounts',
                headers=self._headers(),
            )
            resp.raise_for_status()
            accounts = resp.json().get('accounts', [])
            for acct in accounts:
                acct_type = acct.get('accountType', '').upper()
                if acct_type == 'CFD':
                    account_id = acct.get('accountId', '')
                    logger.info(f'IG auto-detected CFD account: {account_id}')
                    return account_id
            # Log available accounts if no CFD found
            acct_types = [(a.get('accountId'), a.get('accountType')) for a in accounts]
            logger.info(f'IG no CFD account found. Available accounts: {acct_types}')
        except Exception as e:
            logger.error(f'IG failed to fetch accounts for CFD detection: {e}')
        return ''

    def _switch_account(self, account_id: str) -> None:
        """Switch active IG account (e.g. from spread bet to CFD)."""
        resp = requests.put(
            f'{self._base_url}/session',
            headers={
                'X-IG-API-KEY': self._ig_api_key,
                'CST': self._cst,
                'X-SECURITY-TOKEN': self._security_token,
                'Content-Type': 'application/json',
                'Version': '1',
            },
            json={'accountId': account_id},
            timeout=30,
        )
        resp.raise_for_status()
        # Update tokens from switch response
        new_cst = resp.headers.get('CST', '')
        new_token = resp.headers.get('X-SECURITY-TOKEN', '')
        if new_cst:
            self._cst = new_cst
        if new_token:
            self._security_token = new_token
        logger.info(f'IG switched to account {account_id}')

    def _headers(self) -> dict:
        if not self._connected:
            self._authenticate()
        return {
            'X-IG-API-KEY': self._ig_api_key,
            'CST': self._cst,
            'X-SECURITY-TOKEN': self._security_token,
            'Content-Type': 'application/json',
        }

    def _safe_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make request with rate-limit awareness and auto-reauth on 401."""
        import time
        kwargs.setdefault('timeout', 30)

        # If rate-limited, don't make the request — raise so callers back off
        now = time.time()
        if now < self._rate_limited_until:
            raise Exception(f'IG rate limited, backing off until {self._rate_limited_until - now:.0f}s remaining')

        resp = getattr(requests, method)(url, **kwargs)

        if resp.status_code == 403:
            # 403 = rate limit (not auth failure). Back off globally.
            self._rate_limited_until = now + self._rate_limit_backoff
            self._rate_limit_backoff = min(self._rate_limit_backoff * 1.5, 30)
            raise Exception(f'IG 403 rate limited on {method.upper()} {url.split("/")[-1]}')

        if resp.status_code == 401:
            # 401 = genuine auth failure. Re-authenticate.
            if now - self._last_auth_attempt < self._auth_cooldown:
                raise Exception('IG auth expired, cooldown active')
            self._connected = False
            self._authenticate()
            kwargs['headers'] = self._headers()
            resp = getattr(requests, method)(url, **kwargs)

        # Reset backoff on success
        if resp.status_code == 200:
            self._rate_limit_backoff = 5

        return resp

    def _get_instrument_currency(self, epic: str) -> str:
        """Get the tradeable currency for an instrument."""
        cached = self._instrument_cache.get(epic)
        if cached:
            return cached.get('currency', self._currency)
        return self._currency

    # ── Order Submission ──

    def _submit_market_order(self, symbol: str, qty: float, current_price: float, side: str, reduce_only: bool) -> str:
        epic = symbol_to_epic(symbol)
        direction = 'BUY' if side == 'buy' else 'SELL'
        size = abs(qty)

        payload = {
            'epic': epic,
            'expiry': '-',
            'direction': direction,
            'size': size,
            'orderType': 'MARKET',
            'currencyCode': self._get_instrument_currency(epic),
            'forceOpen': not reduce_only,
            'guaranteedStop': False,
        }

        logger.info(f'IG market order payload: {payload}')
        resp = self._safe_request(
            'post',
            f'{self._base_url}/positions/otc',
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        deal_ref = data.get('dealReference', '')
        logger.info(f'IG market order: {epic} {direction} {size} -> ref {deal_ref}')

        # Confirm the deal
        deal_id = self._confirm_deal(deal_ref)
        return deal_id or deal_ref

    def _submit_limit_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> str:
        epic = symbol_to_epic(symbol)
        direction = 'BUY' if side == 'buy' else 'SELL'
        size = abs(qty)

        payload = {
            'epic': epic,
            'expiry': '-',
            'direction': direction,
            'size': size,
            'level': price,
            'type': 'LIMIT',
            'currencyCode': self._get_instrument_currency(epic),
            'forceOpen': not reduce_only,
            'guaranteedStop': False,
            'timeInForce': 'GOOD_TILL_CANCELLED',
        }

        resp = self._safe_request(
            'post',
            f'{self._base_url}/workingorders/otc',
            headers={**self._headers(), 'Version': '2'},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        deal_ref = data.get('dealReference', '')
        logger.info(f'IG limit order: {epic} {direction} {size}@{price} -> ref {deal_ref}')
        deal_id = self._confirm_deal(deal_ref)
        return deal_id or deal_ref

    def _submit_stop_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> str:
        epic = symbol_to_epic(symbol)
        direction = 'BUY' if side == 'buy' else 'SELL'
        size = abs(qty)

        payload = {
            'epic': epic,
            'expiry': '-',
            'direction': direction,
            'size': size,
            'level': price,
            'type': 'STOP',
            'currencyCode': self._get_instrument_currency(epic),
            'forceOpen': not reduce_only,
            'guaranteedStop': False,
            'timeInForce': 'GOOD_TILL_CANCELLED',
        }

        resp = self._safe_request(
            'post',
            f'{self._base_url}/workingorders/otc',
            headers={**self._headers(), 'Version': '2'},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        deal_ref = data.get('dealReference', '')
        logger.info(f'IG stop order: {epic} {direction} {size}@{price} -> ref {deal_ref}')
        deal_id = self._confirm_deal(deal_ref)
        return deal_id or deal_ref

    def _confirm_deal(self, deal_reference: str) -> str:
        """Confirm a deal and return the deal ID. Raises on rejection.
        Retries once on UNKNOWN reason (transient IG issue)."""
        import time
        for attempt in range(2):
            resp = self._safe_request(
                'get',
                f'{self._base_url}/confirms/{deal_reference}',
                headers=self._headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                deal_status = data.get('dealStatus', '')
                reason = data.get('reason', '')
                deal_id = data.get('dealId', deal_reference)
                if deal_status == 'REJECTED':
                    if reason == 'UNKNOWN' and attempt == 0:
                        logger.info(f'IG deal UNKNOWN on first check, retrying in 1s (ref={deal_reference})')
                        time.sleep(1)
                        continue
                    logger.error(f'IG deal rejected: {reason} ref={deal_reference} '
                                 f'epic={data.get("epic")} dir={data.get("direction")} '
                                 f'size={data.get("size")} level={data.get("level")}')
                    raise Exception(f'IG deal rejected: {reason} (ref={deal_reference}, dealId={deal_id})')
                logger.info(f'IG deal confirmed: {deal_id} status={deal_status} reason={reason}')
                return deal_id
            logger.error(f'IG deal confirm failed: status={resp.status_code} ref={deal_reference}')
            if attempt == 0:
                time.sleep(1)
                continue
            return deal_reference
        return deal_reference

    # ── Order Cancellation ──

    def _cancel_order_on_exchange(self, symbol: str, exchange_order_id: str) -> None:
        # IG requires POST with _method=DELETE header for working order cancellation
        resp = self._safe_request(
            'post',
            f'{self._base_url}/workingorders/otc/{exchange_order_id}',
            headers={**self._headers(), '_method': 'DELETE', 'Version': '2'},
            json={},
        )
        if resp.status_code not in (200, 404):
            resp.raise_for_status()
        logger.info(f'IG order {exchange_order_id} cancelled')

    def _cancel_all_orders_on_exchange(self, symbol: str) -> None:
        epic = symbol_to_epic(symbol)
        orders = self.get_open_orders()
        for o in orders:
            if o.get('epic') == epic:
                self._cancel_order_on_exchange(symbol, o['id'])

    # ── Streaming (IG Lightstreamer) ──

    def start_price_stream(self, symbols: List[str], callback: Callable) -> None:
        """Stream prices via IG's Lightstreamer (real-time, no API rate limit cost)."""
        import time

        epics = {symbol_to_epic(s): s for s in symbols}
        # schema fields: BID, OFFER, UPDATE_TIME, MARKET_STATE
        schema = 'BID OFFER UPDATE_TIME MARKET_STATE'

        def _stream():
            while True:
                try:
                    self._run_lightstreamer(epics, schema, callback)
                except Exception as e:
                    logger.info(f'IG stream error: {e}, reconnecting in 5s...')
                time.sleep(5)

        thread = threading.Thread(target=_stream, daemon=True)
        thread.start()

    def _run_lightstreamer(self, epics: dict, schema: str, callback: Callable) -> None:
        """Connect to IG Lightstreamer and stream price updates.

        Uses raw HTTP streaming protocol (no external LS library needed).
        Runs until disconnect/error, then returns so caller can reconnect.
        """
        import time

        # Get Lightstreamer endpoint from IG session
        if not self._connected:
            self._authenticate()
        ls_endpoint = self._ls_endpoint
        if not ls_endpoint:
            raise Exception('No Lightstreamer endpoint from IG session')

        # Use a no-proxy session (IG LS control address may not work through proxies)
        sess = requests.Session()
        sess.trust_env = False

        # Step 1: Create Lightstreamer session
        resp = sess.post(
            f'{ls_endpoint}/lightstreamer/create_session.txt',
            data={
                'LS_op2': 'create',
                'LS_cid': 'mgQkwtwdysogQz2BJ4Ji kOj2Bg',
                'LS_adapter_set': 'DEFAULT',
                'LS_user': self._account_id or '',
                'LS_password': f'CST-{self._cst}|XST-{self._security_token}',
            },
            stream=True,
            timeout=15,
        )

        session_id = None
        control_addr = None
        lines_iter = resp.iter_lines(decode_unicode=True)
        for line in lines_iter:
            if line.startswith('SessionId:'):
                session_id = line.split(':')[1].strip()
            elif line.startswith('ControlAddress:'):
                control_addr = line.split(':', 1)[1].strip()
            elif line == '':
                break

        if not session_id:
            resp.close()
            raise Exception('Failed to create Lightstreamer session')

        logger.info(f'IG Lightstreamer connected: session={session_id}')

        # Step 2: Subscribe to price data via control address
        control_url = f'https://{control_addr}/lightstreamer/control.txt'
        for idx, (epic, symbol) in enumerate(epics.items(), 1):
            sub_resp = sess.post(
                control_url,
                data={
                    'LS_session': session_id,
                    'LS_op': 'add',
                    'LS_table': str(idx),
                    'LS_id': f'MARKET:{epic}',
                    'LS_schema': schema,
                    'LS_mode': 'MERGE',
                },
                timeout=15,
            )
            result = sub_resp.text.strip()
            if result != 'OK':
                logger.error(f'IG Lightstreamer subscribe failed for {symbol}: {result}')
            else:
                logger.info(f'IG Lightstreamer subscribed: {symbol} ({epic})')

        # Build table->symbol map and last-known prices for partial updates
        table_to_symbol = {str(idx): symbol for idx, (epic, symbol) in enumerate(epics.items(), 1)}
        last_prices = {}  # symbol -> {'bid': float, 'ask': float}

        # Step 3: Read streaming data
        for line in lines_iter:
            if not line or line == 'PROBE':
                continue
            if 'Preamble' in line:
                continue

            # Parse: "table,item|BID|OFFER|UPDATE_TIME|MARKET_STATE"
            try:
                header, fields = line.split('|', 1)
                table = header.split(',')[0]
                symbol = table_to_symbol.get(table)
                if not symbol:
                    continue

                parts = fields.split('|')
                bid_str = parts[0] if len(parts) > 0 and parts[0] else None
                offer_str = parts[1] if len(parts) > 1 and parts[1] else None

                # Update last known prices (IG sends partial updates)
                if symbol not in last_prices:
                    last_prices[symbol] = {'bid': 0.0, 'ask': 0.0}
                if bid_str:
                    last_prices[symbol]['bid'] = float(bid_str)
                if offer_str:
                    last_prices[symbol]['ask'] = float(offer_str)

                bid = last_prices[symbol]['bid']
                ask = last_prices[symbol]['ask']
                if bid > 0 and ask > 0:
                    callback({
                        'symbol': symbol,
                        'bid': bid,
                        'ask': ask,
                        'price': (bid + ask) / 2,
                    })
            except (ValueError, IndexError):
                continue

        resp.close()
        logger.info('IG Lightstreamer stream ended')

    # ── Account Info ──

    def get_account_summary(self) -> dict:
        resp = self._safe_request(
            'get',
            f'{self._base_url}/accounts',
            headers=self._headers(),
        )
        resp.raise_for_status()
        accounts = resp.json().get('accounts', [])
        if not accounts:
            return {}

        # Find the CFD account, fall back to configured account_id, then first account
        acct = accounts[0]
        for a in accounts:
            if self._account_id and a.get('accountId') == self._account_id:
                acct = a
                break
            if a.get('accountType', '').upper() == 'CFD':
                acct = a
                break

        balance_info = acct.get('balance', {})
        return {
            'balance': float(balance_info.get('balance', 0)),
            'unrealized_pnl': float(balance_info.get('profitLoss', 0)),
            'margin_available': float(balance_info.get('available', 0)),
            'currency': acct.get('currency', 'USD'),
        }

    def get_open_positions(self) -> List[dict]:
        # Build reverse epic->symbol map
        epic_to_sym = {v: k for k, v in DEFAULT_EPIC_MAP.items()}

        resp = self._safe_request(
            'get',
            f'{self._base_url}/positions',
            headers={**self._headers(), 'Version': '2'},
        )
        resp.raise_for_status()
        positions = []
        for pos_data in resp.json().get('positions', []):
            market = pos_data.get('market', {})
            position = pos_data.get('position', {})
            epic = market.get('epic', '')
            symbol = epic_to_sym.get(epic, market.get('instrumentName', ''))
            direction = position.get('direction', '')
            size = float(position.get('size', 0))
            # Convert IG direction+size to signed units for position sync
            long_units = size if direction == 'BUY' else 0
            short_units = -size if direction == 'SELL' else 0
            positions.append({
                'symbol': symbol,
                'epic': epic,
                'direction': direction,
                'size': size,
                'level': float(position.get('level', 0)),
                'deal_id': position.get('dealId', ''),
                'long_units': long_units,
                'short_units': short_units,
            })
        return positions

    def get_open_orders(self) -> List[dict]:
        resp = self._safe_request(
            'get',
            f'{self._base_url}/workingorders',
            headers={**self._headers(), 'Version': '2'},
        )
        resp.raise_for_status()
        orders = []
        for wo in resp.json().get('workingOrders', []):
            order_data = wo.get('workingOrderData', {})
            market = wo.get('marketData', {})
            orders.append({
                'id': order_data.get('dealId', ''),
                'epic': market.get('epic', ''),
                'direction': order_data.get('direction', ''),
                'size': float(order_data.get('orderSize', 0)),
                'level': float(order_data.get('orderLevel', 0)),
                'type': order_data.get('orderType', ''),
            })
        return orders

    def set_trade_tp_sl(self, trade_id: str, take_profit: float = None, stop_loss: float = None) -> None:
        """Set or update TP/SL on an IG position via PUT /positions/otc/{dealId}."""
        payload = {'trailingStop': False}
        if take_profit is not None:
            payload['limitLevel'] = take_profit
        if stop_loss is not None:
            payload['stopLevel'] = stop_loss

        if len(payload) == 1:  # only trailingStop, nothing to set
            return

        resp = self._safe_request(
            'put',
            f'{self._base_url}/positions/otc/{trade_id}',
            headers={**self._headers(), 'Version': '2'},
            json=payload,
        )
        if resp.status_code == 200:
            logger.info(f'IG trade {trade_id}: set TP={take_profit}, SL={stop_loss}')
        else:
            logger.error(f'IG set_trade_tp_sl failed: {resp.status_code} {resp.text} (dealId={trade_id})')

    def cancel_trade_tp_sl(self, trade_id: str) -> None:
        """Remove TP and SL from an IG position by setting levels to None."""
        resp = self._safe_request(
            'put',
            f'{self._base_url}/positions/otc/{trade_id}',
            headers={**self._headers(), 'Version': '2'},
            json={'limitLevel': None, 'stopLevel': None, 'trailingStop': False},
        )
        if resp.status_code == 200:
            logger.info(f'IG trade {trade_id}: cleared TP/SL')
        else:
            logger.error(f'IG cancel_trade_tp_sl failed: {resp.status_code} {resp.text} (dealId={trade_id})')

    def _fetch_precisions(self) -> None:
        """Fetch instrument precisions from IG Markets API and store them."""
        from qengine.store import store
        from qengine.routes import router

        if self.name not in store.exchanges.storage:
            return
        exchange = store.exchanges.storage[self.name]
        if not hasattr(exchange, 'vars'):
            return

        exchange.vars['precisions'] = {}

        # Get unique symbols from routes
        symbols = set()
        for r in router.routes:
            if r.exchange == self.name:
                symbols.add(r.symbol)

        for symbol in symbols:
            epic = symbol_to_epic(symbol)
            try:
                resp = self._safe_request(
                    'get',
                    f'{self._base_url}/markets/{epic}',
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    snapshot = data.get('snapshot', {})
                    instrument = data.get('instrument', {})
                    decimals = snapshot.get('decimalPlacesFactor', 5)
                    lot_size = float(instrument.get('lotSize', 1))
                    # Min deal size from marginDepositBands or default to lot_size
                    bands = instrument.get('marginDepositBands', [])
                    min_size = float(bands[0].get('min', 0)) if bands else lot_size
                    if min_size <= 0:
                        min_size = lot_size

                    # Cache instrument currency for order submission
                    # IG 'currencies' array: code='$.' is display, name='USD' is ISO code
                    currencies = instrument.get('currencies', [])
                    inst_currency = currencies[0].get('name', 'USD') if currencies else 'USD'
                    self._instrument_cache[epic] = {'currency': inst_currency}

                    exchange.vars['precisions'][symbol] = {
                        'price_precision': decimals,
                        'qty_precision': 2,
                        'min_qty': min_size,
                        'lot_size': lot_size,
                    }
                    logger.info(f'IG precision for {symbol} ({epic}): decimals={decimals}, min_size={min_size}, lot_size={lot_size}, currency={inst_currency}')
                else:
                    # Fallback defaults for forex
                    exchange.vars['precisions'][symbol] = {
                        'price_precision': 5,
                        'qty_precision': 2,
                        'min_qty': 0.1,
                    }
                    logger.info(f'IG could not fetch market info for {symbol} ({epic}), using defaults')
            except Exception as e:
                exchange.vars['precisions'][symbol] = {
                    'price_precision': 5,
                    'qty_precision': 2,
                    'min_qty': 0.1,
                }
                logger.info(f'IG precision fetch error for {symbol}: {e}, using defaults')


class IGMarketsLiveDriver(IGMarketsLiveDriverBase):
    def __init__(self):
        super().__init__(name=brokers.IG_MARKETS, is_demo=False)


class IGMarketsDemoDriver(IGMarketsLiveDriverBase):
    def __init__(self):
        super().__init__(name=brokers.IG_MARKETS_DEMO, is_demo=True)
