import os
import json
import threading
from typing import List, Callable

import requests

from qengine.enums import brokers
from qengine.live_drivers.base import ForexLiveDriver
from qengine.modes.import_candles_mode.drivers.OANDA.oanda_utils import (
    symbol_to_instrument,
    instrument_to_symbol,
)
from qengine.services import logger


class OandaLiveDriverBase(ForexLiveDriver):
    """
    OANDA v20 REST + Streaming API driver for live/paper trading.

    Endpoints:
    - REST: https://api-fxtrade.oanda.com/v3  (live)
    - REST: https://api-fxpractice.oanda.com/v3  (demo)
    - Stream: https://stream-fxtrade.oanda.com/v3  (live)
    - Stream: https://stream-fxpractice.oanda.com/v3  (demo)
    """

    def __init__(self, name: str, is_demo: bool = False):
        super().__init__(name=name, is_demo=is_demo)
        if is_demo:
            self._rest_url = 'https://api-fxpractice.oanda.com/v3'
            self._stream_url = 'https://stream-fxpractice.oanda.com/v3'
        else:
            self._rest_url = 'https://api-fxtrade.oanda.com/v3'
            self._stream_url = 'https://stream-fxtrade.oanda.com/v3'

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self._api_key}',
            'Content-Type': 'application/json',
        }

    # ── Order Submission ──

    def _submit_market_order(self, symbol: str, qty: float, current_price: float, side: str, reduce_only: bool) -> str:
        instrument = symbol_to_instrument(symbol)
        units = abs(qty) if side == 'buy' else -abs(qty)

        payload = {
            'order': {
                'type': 'MARKET',
                'instrument': instrument,
                'units': str(units),
                'timeInForce': 'FOK',
                'positionFill': 'REDUCE_ONLY' if reduce_only else 'DEFAULT',
            }
        }

        resp = requests.post(
            f'{self._rest_url}/accounts/{self._account_id}/orders',
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        order_id = data.get('orderCreateTransaction', {}).get('id', '')
        if 'orderFillTransaction' in data:
            order_id = data['orderFillTransaction'].get('orderID', order_id)

        logger.info(f'OANDA market order submitted: {instrument} {units} units -> ID {order_id}')
        return str(order_id)

    def _submit_limit_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> str:
        instrument = symbol_to_instrument(symbol)
        units = abs(qty) if side == 'buy' else -abs(qty)

        payload = {
            'order': {
                'type': 'LIMIT',
                'instrument': instrument,
                'units': str(units),
                'price': str(price),
                'timeInForce': 'GTC',
                'positionFill': 'REDUCE_ONLY' if reduce_only else 'DEFAULT',
            }
        }

        resp = requests.post(
            f'{self._rest_url}/accounts/{self._account_id}/orders',
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        order_id = data.get('orderCreateTransaction', {}).get('id', '')
        logger.info(f'OANDA limit order submitted: {instrument} {units}@{price} -> ID {order_id}')
        return str(order_id)

    def _submit_stop_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> str:
        instrument = symbol_to_instrument(symbol)
        units = abs(qty) if side == 'buy' else -abs(qty)

        payload = {
            'order': {
                'type': 'STOP',
                'instrument': instrument,
                'units': str(units),
                'price': str(price),
                'timeInForce': 'GTC',
                'positionFill': 'REDUCE_ONLY' if reduce_only else 'DEFAULT',
            }
        }

        resp = requests.post(
            f'{self._rest_url}/accounts/{self._account_id}/orders',
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        order_id = data.get('orderCreateTransaction', {}).get('id', '')
        logger.info(f'OANDA stop order submitted: {instrument} {units}@{price} -> ID {order_id}')
        return str(order_id)

    # ── Order Cancellation ──

    def _cancel_order_on_exchange(self, symbol: str, exchange_order_id: str) -> None:
        resp = requests.put(
            f'{self._rest_url}/accounts/{self._account_id}/orders/{exchange_order_id}/cancel',
            headers=self._headers(),
            timeout=30,
        )
        if resp.status_code != 404:
            resp.raise_for_status()
        logger.info(f'OANDA order {exchange_order_id} cancelled')

    def _cancel_all_orders_on_exchange(self, symbol: str) -> None:
        instrument = symbol_to_instrument(symbol)
        # Get pending orders for this instrument
        resp = requests.get(
            f'{self._rest_url}/accounts/{self._account_id}/pendingOrders',
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        orders = resp.json().get('orders', [])
        for order in orders:
            if order.get('instrument') == instrument:
                self._cancel_order_on_exchange(symbol, order['id'])

    # ── Streaming ──

    def start_price_stream(self, symbols: List[str], callback: Callable) -> None:
        instruments = ','.join(symbol_to_instrument(s) for s in symbols)

        def _stream():
            resp = requests.get(
                f'{self._stream_url}/accounts/{self._account_id}/pricing/stream',
                headers=self._headers(),
                params={'instruments': instruments},
                stream=True,
                timeout=60,
            )
            for line in resp.iter_lines():
                if line:
                    data = json.loads(line)
                    if data.get('type') == 'PRICE':
                        symbol = instrument_to_symbol(data['instrument'])
                        bid = float(data['bids'][0]['price'])
                        ask = float(data['asks'][0]['price'])
                        mid = (bid + ask) / 2
                        callback({
                            'symbol': symbol,
                            'bid': bid,
                            'ask': ask,
                            'price': mid,
                            'time': data.get('time'),
                        })

        thread = threading.Thread(target=_stream, daemon=True)
        thread.start()

    # ── Account Info ──

    def get_account_summary(self) -> dict:
        resp = requests.get(
            f'{self._rest_url}/accounts/{self._account_id}/summary',
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        acct = resp.json().get('account', {})
        return {
            'balance': float(acct.get('balance', 0)),
            'unrealized_pnl': float(acct.get('unrealizedPL', 0)),
            'margin_used': float(acct.get('marginUsed', 0)),
            'margin_available': float(acct.get('marginAvailable', 0)),
            'nav': float(acct.get('NAV', 0)),
            'open_trade_count': int(acct.get('openTradeCount', 0)),
            'currency': acct.get('currency', 'USD'),
        }

    def get_open_positions(self) -> List[dict]:
        resp = requests.get(
            f'{self._rest_url}/accounts/{self._account_id}/openPositions',
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        positions = []
        for pos in resp.json().get('positions', []):
            symbol = instrument_to_symbol(pos['instrument'])
            long_units = float(pos.get('long', {}).get('units', 0))
            short_units = float(pos.get('short', {}).get('units', 0))
            positions.append({
                'symbol': symbol,
                'long_units': long_units,
                'short_units': short_units,
                'unrealized_pnl': float(pos.get('unrealizedPL', 0)),
            })
        return positions

    def get_open_orders(self) -> List[dict]:
        resp = requests.get(
            f'{self._rest_url}/accounts/{self._account_id}/pendingOrders',
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        orders = []
        for o in resp.json().get('orders', []):
            orders.append({
                'id': o['id'],
                'symbol': instrument_to_symbol(o.get('instrument', '')),
                'type': o.get('type', ''),
                'units': float(o.get('units', 0)),
                'price': float(o.get('price', 0)),
                'time_in_force': o.get('timeInForce', ''),
            })
        return orders

    def _fetch_precisions(self) -> None:
        resp = requests.get(
            f'{self._rest_url}/accounts/{self._account_id}/instruments',
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        # Store precision info for use by the framework
        instruments = resp.json().get('instruments', [])
        from qengine.store import store
        if self.name not in store.exchanges.storage:
            return
        exchange = store.exchanges.storage[self.name]
        if not hasattr(exchange, 'vars'):
            return
        exchange.vars['precisions'] = {}
        for inst in instruments:
            symbol = instrument_to_symbol(inst['name'])
            exchange.vars['precisions'][symbol] = {
                'price_precision': inst.get('displayPrecision', 5),
                'qty_precision': 0,
                'min_qty': float(inst.get('minimumTradeSize', 1)),
            }


class OandaLiveDriver(OandaLiveDriverBase):
    def __init__(self):
        super().__init__(name=brokers.OANDA, is_demo=False)


class OandaDemoDriver(OandaLiveDriverBase):
    def __init__(self):
        super().__init__(name=brokers.OANDA_DEMO, is_demo=True)
