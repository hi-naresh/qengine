import random as _random_module

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
        # accumulated slippage costs
        self._total_slippage_cost = 0.0

        # Backtest cost/randomness settings (set by exchange_service)
        self._bt_cost_settings = {}
        # Seeded RNG for deterministic backtest spread/slippage randomness
        self._rng = _random_module.Random(42)

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

    def get_spread(self, symbol: str, timestamp_ms: int = None) -> float:
        """Get spread for a symbol. Uses real per-candle spread from imported data
        when available, falls back to fixed/randomized spread from settings.

        Args:
            symbol: Trading pair (e.g. 'EUR-USD')
            timestamp_ms: Current candle timestamp. If provided and real spread
                         data exists for this candle, returns the actual broker spread.
        """
        # Try real spread data first (from OANDA bid/ask import)
        if timestamp_ms is not None and not jh.is_livetrading():
            from qengine.services import spread_data
            real_spread = spread_data.get_spread(self.name, symbol, timestamp_ms)
            if real_spread is not None:
                return real_spread

        # Fallback to configured fixed spread
        if symbol in self._spread_config:
            base_spread = self._spread_config[symbol]
        else:
            pip_size = instrument_registry.get_pip_size(symbol)
            base_spread = pip_size * 2  # default 2 pips

        # Apply randomness during backtesting
        randomness = self._bt_cost_settings.get('spread_randomness', 0.0)
        if randomness > 0 and not jh.is_livetrading():
            factor = 1.0 + self._rng.uniform(-randomness, randomness)
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
            factor = self._rng.uniform(1.0 - randomness, 1.0 + randomness)
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
        """Apply OANDA-style overnight financing charge.

        OANDA formula for FX: Charge = Size × (Rate / 365) × Conversion_Rate
        Where Rate = per-lot per-night rate (already includes benchmark + admin fee).

        Our stored rate is per standard lot (100,000 units) per night in account
        currency. Negative = trader pays. Wednesday night = 3x (FX T+2 settlement
        covers Saturday + Sunday).
        """
        if jh.is_livetrading():
            return 0.0

        if not self._bt_cost_settings.get('swap_enabled', True):
            return 0.0

        swap_rates = self._swap_rates.get(symbol, (0.0, 0.0))
        rate = swap_rates[0] if position_type == 'long' else swap_rates[1]
        if rate == 0.0:
            return 0.0

        # Convert qty to lots (1 lot = 100,000 units for FX)
        contract_size = instrument_registry.get_contract_size(symbol)
        lots = abs(qty) / contract_size if contract_size > 0 else abs(qty) / 100_000

        # Wednesday = 3x for FX (T+2 settlement covers Sat+Sun)
        # Day-of-week from timestamp using integer math (no datetime/arrow needed)
        # Unix epoch (1970-01-01) was a Thursday (day 3). Days since epoch mod 7:
        # 0=Thu, 1=Fri, 2=Sat, 3=Sun, 4=Mon, 5=Tue, 6=Wed
        days_since_epoch = int(jh.now_to_timestamp() // 86_400_000)
        dow = (days_since_epoch + 3) % 7  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
        multiplier = 3 if dow == 2 else 1  # Wednesday = index 2

        # Rate is per-lot per-night. Apply directly (no /365 needed since
        # rate is already the nightly charge, not an annual percentage).
        swap_amount = rate * lots * multiplier
        self.assets[self.settlement_currency] += swap_amount
        self._overnight_charges += abs(swap_amount)

        action = 'Charged' if swap_amount < 0 else 'Credited'
        swap_msg = (
            f'{action} {round(abs(swap_amount), 4)} overnight swap for {symbol} '
            f'({position_type}, {lots:.3f} lots, {multiplier}x). '
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
            # Block if order qty is below broker minimum.
            # Use broker-specific minimum from settings (injected via
            # _apply_backtest_cost_settings). Default 0 = no minimum.
            min_qty = self._bt_cost_settings.get('min_order_qty', 0)
            if abs(order.qty) < min_qty:
                raise InsufficientMargin(
                    f'Order qty {abs(order.qty):.2f} is below broker minimum of '
                    f'{min_qty} units for {order.symbol}.'
                )

            effective_order_size = abs(order.qty * order.price) / self.default_leverage
            avail = self.available_margin

            # Block if free margin insufficient
            if effective_order_size > avail:
                raise InsufficientMargin(
                    f'Cannot submit order worth ${round(order.qty * order.price)} '
                    f'when available margin is ${round(avail)}. '
                    f'Current leverage: {self.default_leverage}x'
                )

            # Block if margin level already at or below stop-out level (default 50%)
            equity = self.wallet_balance
            total_used_margin = 0
            for asset in self.assets:
                if asset == self.settlement_currency:
                    continue
                position = store.positions.get_position(self.name, f"{asset}-{self.settlement_currency}")
                if position and position.is_open:
                    equity += position.pnl
                    total_used_margin += position.margin_used

            if total_used_margin > 0:
                margin_level = (equity / total_used_margin) * 100
                stop_out_level = self._bt_cost_settings.get('stop_out_level', 50.0)
                if margin_level <= stop_out_level:
                    raise InsufficientMargin(
                        f'Margin level {round(margin_level, 1)}% is at or below '
                        f'stop-out level ({stop_out_level}%). Cannot open new trades.'
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
