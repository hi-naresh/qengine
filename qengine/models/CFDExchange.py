import random

import numpy as np
from numba import njit

import qengine.helpers as jh
import qengine.services.logger as logger
from qengine.enums import sides
from qengine.exceptions import InsufficientMargin
from qengine.models.Order import Order
from qengine.models.Exchange import Exchange
from qengine.store import store
from qengine.core.instruments import instrument_registry


class CFDExchange(Exchange):
    """
    Exchange model for forex and CFD trading.
    Key differences from crypto futures:
    - Spread-based fees (not fixed fee rate)
    - Overnight swap charges
    - Leverage is per-instrument (via margin_rate)
    - P&L in account currency
    """

    def __init__(
            self,
            name: str,
            starting_balance: float,
            fee_rate: float,
            default_leverage: int = 30
    ):
        super().__init__(name, starting_balance, fee_rate, 'cfd')

        self.default_leverage = default_leverage

        # spread config per symbol (in price units, not pips)
        self._spread_config = {}
        # swap rates per symbol: (swap_long_per_day, swap_short_per_day) in account currency per lot
        self._swap_rates = {}
        # accumulated overnight charges
        self._overnight_charges = 0.0
        # accumulated spread+commission costs
        self._total_spread_cost = 0.0

        # Backtest cost/randomness settings (set by exchange_service)
        self._bt_cost_settings = {}

        # live-trading only
        self._available_margin = 0
        self._wallet_balance = 0
        self._started_balance = 0

    @property
    def started_balance(self) -> float:
        if jh.is_livetrading():
            return self._started_balance
        return self.starting_assets[jh.app_currency()]

    @property
    def wallet_balance(self) -> float:
        if jh.is_live() and self._wallet_balance > 0:
            return self._wallet_balance
        return self.assets[self.settlement_currency]

    @property
    def available_margin(self) -> float:
        if jh.is_live() and self._available_margin > 0:
            return self._available_margin

        margin = self.wallet_balance
        total_margin_used = 0

        for asset in self.assets:
            if asset == self.settlement_currency:
                continue

            position = store.positions.get_position(self.name, f"{asset}-{self.settlement_currency}")
            if position and position.is_open:
                # Use margin_used which accounts for gross exposure in CFD mode
                total_margin_used += position.margin_used
                total_margin_used -= position.pnl

            # pending orders margin
            sum_buy_orders = (self.buy_orders[asset][:][:, 0] * self.buy_orders[asset][:][:, 1]).sum()
            sum_sell_orders = (self.sell_orders[asset][:][:, 0] * self.sell_orders[asset][:][:, 1]).sum()

            total_margin_used += max(
                abs(sum_buy_orders) / self.default_leverage,
                abs(sum_sell_orders) / self.default_leverage
            )

        margin -= total_margin_used
        return margin

    def set_spread(self, symbol: str, spread: float) -> None:
        self._spread_config[symbol] = spread

    def get_spread(self, symbol: str) -> float:
        if symbol in self._spread_config:
            base_spread = self._spread_config[symbol]
        else:
            pip_size = instrument_registry.get_pip_size(symbol)
            base_spread = pip_size * 2  # default 2 pips

        # Apply randomness during backtesting
        randomness = self._bt_cost_settings.get('spread_randomness', 0.0)
        if randomness > 0 and not jh.is_livetrading():
            factor = 1.0 + random.uniform(-randomness, randomness)
            return max(0.0, base_spread * factor)
        return base_spread

    def get_slippage(self, symbol: str) -> float:
        """Return slippage in price units for the current trade (backtest only)."""
        slippage_pips = self._bt_cost_settings.get('slippage_pips', 0.0)
        if slippage_pips <= 0:
            return 0.0
        pip_size = instrument_registry.get_pip_size(symbol)
        base_slippage = pip_size * slippage_pips
        randomness = self._bt_cost_settings.get('slippage_randomness', 0.0)
        if randomness > 0:
            factor = random.uniform(1.0 - randomness, 1.0 + randomness)
            return max(0.0, base_slippage * factor)
        return base_slippage

    def set_swap_rates(self, symbol: str, swap_long: float, swap_short: float) -> None:
        self._swap_rates[symbol] = (swap_long, swap_short)

    def charge_spread(self, symbol: str, qty: float) -> float:
        if jh.is_livetrading():
            return 0.0

        spread = self.get_spread(symbol)
        # qty is already in units (not lots), so no contract_size multiplier
        spread_cost = spread * abs(qty)

        # Add per-lot commission if configured (convert to per-unit)
        commission_per_lot = self._bt_cost_settings.get('commission_per_lot', 0.0)
        if commission_per_lot > 0:
            contract_size = instrument_registry.get_contract_size(symbol)
            lots = abs(qty) / contract_size if contract_size > 0 else abs(qty)
            spread_cost += commission_per_lot * lots

        self._total_spread_cost += spread_cost
        old_balance = self.assets[self.settlement_currency]
        self.assets[self.settlement_currency] -= spread_cost
        if spread_cost != 0:
            logger.info(
                f'Charged {round(spread_cost, 2)} as spread+commission for {symbol}. '
                f'Balance changed from {round(old_balance, 2)} to {round(self.assets[self.settlement_currency], 2)}'
            )
        return spread_cost

    def charge_overnight_swap(self, symbol: str, qty: float, position_type: str) -> float:
        if jh.is_livetrading():
            return 0.0

        # Check if swap is disabled in backtest settings
        if not self._bt_cost_settings.get('swap_enabled', True):
            return 0.0

        swap_rates = self._swap_rates.get(symbol, (0.0, 0.0))
        rate = swap_rates[0] if position_type == 'long' else swap_rates[1]
        if rate == 0.0:
            return 0.0

        # Swap rate is per-lot annual (e.g., -$5/lot/night = cost, +$3/lot/night = credit).
        # Negative rate → charge (deduct), Positive rate → credit (add).
        # Forex swaps are charged per trading day (~252/year). Wednesday nights
        # incur 3x to cover the weekend (Sat+Sun settlement).
        contract_size = instrument_registry.get_contract_size(symbol)
        lots = abs(qty) / contract_size if contract_size > 0 else abs(qty)
        # Determine day-of-week for triple-Wednesday swap
        try:
            import arrow
            dow = arrow.Arrow.fromtimestamp(jh.now_to_timestamp() / 1000).weekday()
        except Exception:
            dow = 2  # default to non-Wednesday
        multiplier = 3 if dow == 2 else 1  # Wednesday = 3x (covers Sat+Sun)
        swap_amount = rate * lots * multiplier / 252  # per trading day
        self.assets[self.settlement_currency] += swap_amount  # add (negative subtracts)
        self._overnight_charges += abs(swap_amount)  # track total magnitude
        action = 'Charged' if swap_amount < 0 else 'Credited'
        swap_msg = (
            f'{action} {round(abs(swap_amount), 4)} overnight swap for {symbol} ({position_type}). '
            f'Total overnight charges: {round(self._overnight_charges, 2)}'
        )
        if jh.is_backtesting():
            from qengine.store import store
            store.logs.add(swap_msg, 'market')
        logger.info(swap_msg)
        return swap_amount

    def charge_fee(self, amount: float) -> None:
        if jh.is_livetrading():
            return

        fee_amount = abs(amount) * self.fee_rate
        new_balance = self.assets[self.settlement_currency] - fee_amount
        if fee_amount != 0:
            logger.info(
                f'Charged {round(fee_amount, 2)} as fee. Balance for {self.settlement_currency} on '
                f'{self.name} changed from {round(self.assets[self.settlement_currency], 2)} to {round(new_balance, 2)}'
            )
        self.assets[self.settlement_currency] = new_balance

    def add_realized_pnl(self, realized_pnl: float) -> None:
        if jh.is_livetrading():
            return

        new_balance = self.assets[self.settlement_currency] + realized_pnl
        logger.info(
            f'Added realized PNL of {round(realized_pnl, 2)}. Balance for {self.settlement_currency} on '
            f'{self.name} changed from {round(self.assets[self.settlement_currency], 2)} to {round(new_balance, 2)}'
        )
        self.assets[self.settlement_currency] = new_balance

    def on_order_submission(self, order: Order) -> None:
        if jh.is_livetrading():
            return

        base_asset = jh.base_asset(order.symbol)

        if not order.reduce_only:
            effective_order_size = abs(order.qty * order.price) / self.default_leverage
            if effective_order_size > self.available_margin:
                raise InsufficientMargin(
                    f'Cannot submit order worth ${round(order.qty * order.price)} '
                    f'when available margin is ${round(self.available_margin)}. '
                    f'Current leverage: {self.default_leverage}x'
                )

        self.available_assets[base_asset] += order.qty

        if not order.reduce_only:
            if order.side == sides.BUY:
                self.buy_orders[base_asset].append(np.array([order.qty, order.price]))
            else:
                self.sell_orders[base_asset].append(np.array([order.qty, order.price]))

    def on_order_execution(self, order: Order) -> None:
        if jh.is_livetrading():
            return

        base_asset = jh.base_asset(order.symbol)

        if not order.reduce_only:
            # Use original price for matching (before gap adjustment may have changed it)
            match_price = getattr(order, '_pre_gap_price', order.price)
            order_array = np.array([order.qty, match_price])
            if order.side == sides.BUY:
                item_index = np.where(np.all(self.buy_orders[base_asset].array == order_array, axis=1))[0]
                if len(item_index) > 0:
                    self.buy_orders[base_asset].delete(item_index[0], axis=0)
            else:
                item_index = np.where(np.all(self.sell_orders[base_asset].array == order_array, axis=1))[0]
                if len(item_index) > 0:
                    self.sell_orders[base_asset].delete(item_index[0], axis=0)

    def on_order_cancellation(self, order: Order) -> None:
        if jh.is_livetrading():
            return

        base_asset = jh.base_asset(order.symbol)
        self.available_assets[base_asset] -= order.qty

        if not order.reduce_only:
            order_array = np.array([order.qty, order.price])
            if order.side == sides.BUY:
                index = _find_order_index(self.buy_orders[base_asset].array, order_array)
                if index != -1:
                    self.buy_orders[base_asset].delete(index, axis=0)
            else:
                index = _find_order_index(self.sell_orders[base_asset].array, order_array)
                if index != -1:
                    self.sell_orders[base_asset].delete(index, axis=0)

    def update_from_stream(self, data: dict) -> None:
        """Update balance/margin from broker API. Works in both live and paper mode."""
        if not jh.is_live():
            raise Exception('This method is only for live/paper trading')
        self._available_margin = data['available_margin']
        self._wallet_balance = data['wallet_balance']
        if self._started_balance == 0:
            self._started_balance = self._wallet_balance


@njit(cache=True)
def _find_order_index(orders, order_array):
    for i in range(len(orders)):
        if np.all(orders[i] == order_array):
            return i
    return -1
