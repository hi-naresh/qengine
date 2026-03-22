import json
import threading
from typing import List, Callable

import requests

from qengine.enums import brokers
from qengine.live_drivers.base import ForexLiveDriver
from qengine.modes.import_candles_mode.drivers.IG.ig_utils import symbol_to_epic
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

    def configure(self, api_key: str, account_id: str = None, **kwargs) -> None:
        super().configure(api_key, account_id, **kwargs)
        self._ig_api_key = api_key
        self._username = kwargs.get('username', '')
        self._password = kwargs.get('password', '')
        if 'currency' in kwargs:
            self._currency = kwargs['currency']

    def _authenticate(self) -> None:
        """Authenticate and get CST + security token."""
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
        self._connected = True

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
        """Make request with auto-reauth on 401."""
        kwargs.setdefault('timeout', 30)
        resp = getattr(requests, method)(url, **kwargs)
        if resp.status_code == 401:
            self._authenticate()
            kwargs['headers'] = self._headers()
            resp = getattr(requests, method)(url, **kwargs)
        return resp

    # ── Order Submission ──

    def _submit_market_order(self, symbol: str, qty: float, current_price: float, side: str, reduce_only: bool) -> str:
        epic = symbol_to_epic(symbol)
        direction = 'BUY' if side == 'buy' else 'SELL'
        size = abs(qty)

        payload = {
            'epic': epic,
            'expiry': 'DFB',
            'direction': direction,
            'size': size,
            'orderType': 'MARKET',
            'currencyCode': self._currency,
            'forceOpen': not reduce_only,
            'guaranteedStop': False,
        }

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
            'expiry': 'DFB',
            'direction': direction,
            'size': size,
            'level': price,
            'type': 'LIMIT',
            'currencyCode': self._currency,
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
            'expiry': 'DFB',
            'direction': direction,
            'size': size,
            'level': price,
            'type': 'STOP',
            'currencyCode': self._currency,
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
        """Confirm a deal and return the deal ID."""
        resp = self._safe_request(
            'get',
            f'{self._base_url}/confirms/{deal_reference}',
            headers=self._headers(),
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get('dealId', deal_reference)
        return deal_reference

    # ── Order Cancellation ──

    def _cancel_order_on_exchange(self, symbol: str, exchange_order_id: str) -> None:
        resp = self._safe_request(
            'delete',
            f'{self._base_url}/workingorders/otc/{exchange_order_id}',
            headers=self._headers(),
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

    # ── Streaming (IG uses Lightstreamer) ──

    def start_price_stream(self, symbols: List[str], callback: Callable) -> None:
        """
        IG uses Lightstreamer for streaming. This is a simplified polling fallback.
        For production, integrate the lightstreamer_client library.
        """
        import time

        epics = {symbol_to_epic(s): s for s in symbols}

        def _poll():
            while True:
                try:
                    for epic, symbol in epics.items():
                        resp = self._safe_request(
                            'get',
                            f'{self._base_url}/markets/{epic}',
                            headers=self._headers(),
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            snapshot = data.get('snapshot', {})
                            bid = float(snapshot.get('bid', 0))
                            offer = float(snapshot.get('offer', 0))
                            callback({
                                'symbol': symbol,
                                'bid': bid,
                                'ask': offer,
                                'price': (bid + offer) / 2,
                            })
                except Exception as e:
                    logger.info(f'IG price poll error: {e}')
                time.sleep(1)

        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()

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
        acct = accounts[0]
        balance_info = acct.get('balance', {})
        return {
            'balance': float(balance_info.get('balance', 0)),
            'unrealized_pnl': float(balance_info.get('profitLoss', 0)),
            'margin_available': float(balance_info.get('available', 0)),
            'currency': acct.get('currency', 'USD'),
        }

    def get_open_positions(self) -> List[dict]:
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
            positions.append({
                'symbol': market.get('instrumentName', ''),
                'epic': market.get('epic', ''),
                'direction': position.get('direction', ''),
                'size': float(position.get('size', 0)),
                'level': float(position.get('level', 0)),
                'deal_id': position.get('dealId', ''),
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

    def _fetch_precisions(self) -> None:
        pass


class IGMarketsLiveDriver(IGMarketsLiveDriverBase):
    def __init__(self):
        super().__init__(name=brokers.IG_MARKETS, is_demo=False)


class IGMarketsDemoDriver(IGMarketsLiveDriverBase):
    def __init__(self):
        super().__init__(name=brokers.IG_MARKETS_DEMO, is_demo=True)
