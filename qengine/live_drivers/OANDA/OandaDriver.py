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

    def _submit_market_order(self, symbol: str, qty: float, current_price: float, side: str, reduce_only: bool) -> dict:
        instrument = symbol_to_instrument(symbol)
        # OANDA requires integer units for standard FX pairs
        units = int(round(abs(qty))) if side == 'buy' else -int(round(abs(qty)))

        payload = {
            'order': {
                'type': 'MARKET',
                'instrument': instrument,
                'units': str(units),
                'timeInForce': 'FOK',
                'positionFill': 'REDUCE_ONLY' if reduce_only else 'DEFAULT',
            }
        }

        logger.info(f'OANDA submitting MARKET order: {instrument} {units} units, reduce_only={reduce_only}')

        resp = requests.post(
            f'{self._rest_url}/accounts/{self._account_id}/orders',
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        if resp.status_code >= 400:
            try:
                err_data = resp.json()
                logger.error(f'OANDA MARKET order HTTP {resp.status_code}: {err_data}')
            except Exception:
                logger.error(f'OANDA MARKET order HTTP {resp.status_code}: {resp.text}')
            resp.raise_for_status()
        data = resp.json()

        # Check for rejection (OANDA may return 201 with orderRejectTransaction)
        if 'orderRejectTransaction' in data:
            reason = data['orderRejectTransaction'].get('rejectReason', 'unknown')
            logger.error(f'OANDA MARKET order rejected: {reason} (full: {data["orderRejectTransaction"]})')
            raise RuntimeError(f'OANDA MARKET order rejected: {reason}')

        # Also check for orderCancelTransaction (order created then immediately cancelled)
        if 'orderCancelTransaction' in data and 'orderFillTransaction' not in data:
            reason = data['orderCancelTransaction'].get('reason', 'unknown')
            logger.error(f'OANDA MARKET order cancelled: {reason}')
            raise RuntimeError(f'OANDA MARKET order cancelled: {reason}')

        order_id = data.get('orderCreateTransaction', {}).get('id', '')
        fill_price = None
        if 'orderFillTransaction' in data:
            fill_tx = data['orderFillTransaction']
            order_id = fill_tx.get('orderID', order_id)
            fill_price = float(fill_tx.get('price', 0)) or None

        # Extract trade ID from fill (for per-trade TP/SL in hedging mode)
        trade_id = None
        if 'orderFillTransaction' in data:
            fill_tx = data['orderFillTransaction']
            if 'tradeOpened' in fill_tx:
                trade_id = str(fill_tx['tradeOpened'].get('tradeID', ''))
            elif 'tradesOpened' in fill_tx and fill_tx['tradesOpened']:
                trade_id = str(fill_tx['tradesOpened'][0].get('tradeID', ''))

        logger.info(f'OANDA market order filled: {instrument} {units} units @ {fill_price or current_price} -> ID {order_id}, trade {trade_id}')
        return {'order_id': str(order_id), 'fill_price': fill_price, 'trade_id': trade_id}

    def _submit_limit_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> str:
        instrument = symbol_to_instrument(symbol)
        # OANDA requires integer units for standard FX pairs
        units = int(round(abs(qty))) if side == 'buy' else -int(round(abs(qty)))

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
        # OANDA requires integer units for standard FX pairs
        units = int(round(abs(qty))) if side == 'buy' else -int(round(abs(qty)))

        payload = {
            'order': {
                'type': 'STOP',
                'instrument': instrument,
                'units': str(units),
                'price': str(round(price, 5)),
                'timeInForce': 'GTC',
                'positionFill': 'REDUCE_ONLY' if reduce_only else 'DEFAULT',
            }
        }

        logger.info(f'OANDA submitting STOP order: {instrument} {units} @ {round(price, 5)}, reduce_only={reduce_only}')

        resp = requests.post(
            f'{self._rest_url}/accounts/{self._account_id}/orders',
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        if resp.status_code >= 400:
            try:
                err_data = resp.json()
                logger.error(f'OANDA STOP order HTTP {resp.status_code}: {err_data}')
            except Exception:
                logger.error(f'OANDA STOP order HTTP {resp.status_code}: {resp.text}')
            resp.raise_for_status()
        data = resp.json()

        # Check for rejection (OANDA may return 201 with orderRejectTransaction)
        if 'orderRejectTransaction' in data:
            reason = data['orderRejectTransaction'].get('rejectReason', 'unknown')
            logger.error(f'OANDA STOP order rejected: {reason} (full: {data["orderRejectTransaction"]})')
            raise RuntimeError(f'OANDA STOP order rejected: {reason}')

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

    # ── Per-Trade TP/SL Management (OANDA hedging mode) ──

    def set_trade_tp_sl(self, trade_id: str, take_profit: float = None, stop_loss: float = None) -> None:
        """Set or update take-profit and/or stop-loss on an individual OANDA trade."""
        payload = {}
        if take_profit is not None:
            payload['takeProfit'] = {'price': str(take_profit), 'timeInForce': 'GTC'}
        if stop_loss is not None:
            payload['stopLoss'] = {'price': str(stop_loss), 'timeInForce': 'GTC'}

        if not payload:
            return

        resp = requests.put(
            f'{self._rest_url}/accounts/{self._account_id}/trades/{trade_id}/orders',
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        logger.info(f'OANDA trade {trade_id}: set TP={take_profit}, SL={stop_loss}')

    def cancel_trade_tp_sl(self, trade_id: str) -> None:
        """Remove TP and SL from an OANDA trade."""
        payload = {
            'takeProfit': {'timeInForce': 'GTC', 'price': '0'},
            'stopLoss': {'timeInForce': 'GTC', 'price': '0'},
        }
        # OANDA: to cancel, PUT with empty object or use the cancel endpoint
        # Actually OANDA doesn't support price=0. Use the individual order cancel approach.
        try:
            # Get trade details to find dependent order IDs
            resp = requests.get(
                f'{self._rest_url}/accounts/{self._account_id}/trades/{trade_id}',
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            trade = resp.json().get('trade', {})

            # Cancel TP order if exists
            tp_order_id = trade.get('takeProfitOrder', {}).get('id')
            if tp_order_id:
                self._cancel_order_on_exchange('', tp_order_id)

            # Cancel SL order if exists
            sl_order_id = trade.get('stopLossOrder', {}).get('id')
            if sl_order_id:
                self._cancel_order_on_exchange('', sl_order_id)

            logger.info(f'OANDA trade {trade_id}: cancelled TP/SL')
        except Exception as e:
            logger.info(f'OANDA: failed to cancel TP/SL on trade {trade_id}: {e}')

    def get_open_trades(self) -> List[dict]:
        """Get all open trades from OANDA (individual trade-level, not aggregated positions)."""
        resp = requests.get(
            f'{self._rest_url}/accounts/{self._account_id}/openTrades',
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        trades = []
        for t in resp.json().get('trades', []):
            trades.append({
                'trade_id': t['id'],
                'symbol': instrument_to_symbol(t['instrument']),
                'units': float(t.get('currentUnits', t.get('initialUnits', 0))),
                'price': float(t.get('price', 0)),
                'unrealized_pnl': float(t.get('unrealizedPL', 0)),
                'open_time': t.get('openTime'),
                'take_profit': float(t['takeProfitOrder']['price']) if 'takeProfitOrder' in t else None,
                'stop_loss': float(t['stopLossOrder']['price']) if 'stopLossOrder' in t else None,
                'state': t.get('state', 'OPEN'),
            })
        return trades

    def close_trade(self, trade_id: str, units: float = None) -> dict:
        """Close an individual OANDA trade (fully or partially)."""
        payload = {}
        if units is not None:
            payload['units'] = str(int(round(abs(units))))

        resp = requests.put(
            f'{self._rest_url}/accounts/{self._account_id}/trades/{trade_id}/close',
            headers=self._headers(),
            json=payload if payload else None,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        fill_price = None
        if 'orderFillTransaction' in data:
            fill_price = float(data['orderFillTransaction'].get('price', 0)) or None
        logger.info(f'OANDA trade {trade_id} closed at {fill_price}')
        return {'trade_id': trade_id, 'fill_price': fill_price}

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
