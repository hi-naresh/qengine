from abc import ABC, abstractmethod
from time import sleep
from typing import List, Dict, Union, Optional
# import os
# import joblib
# import csv
import numpy as np
import qengine.helpers as jh
import qengine.services.logger as logger
from qengine import exceptions
from qengine.enums import sides, order_submitted_via, order_types
from qengine.models import ClosedTrade, Order, Route, FuturesExchange, SpotExchange, ForexCFDExchange, Position
from qengine.candle_pipelines import BaseCandlesPipeline
from qengine.services import metrics
from qengine.services.broker import Broker
from qengine.services import order_service, candle_service
from qengine.repositories import order_repository
from qengine.store import store
from qengine.services.cache import cached
from qengine.services import notifier
from qengine.services.color import generate_unique_hex_color


class Strategy(ABC):
    """
    The parent strategy class which every strategy must extend. It is the heart of the framework!
    """

    def __init__(self) -> None:
        self.id = jh.generate_unique_id()
        self.name = None
        self.symbol = None
        self.exchange = None
        self.timeframe = None
        self.hp = None

        self.index = 0
        self.last_trade_index = 0
        self.vars = {}

        # Hedge mode: when True, bypasses ConflictingRules for should_long+should_short
        self.hedge_mode: bool = False

        self.increased_count = 0
        self.reduced_count = 0

        # Variables used for accepting orders from user. Each variable also has a
        # similar one   starting with _ which is used as a temp placeholder to
        # later compare with the current one to detect if user has submitted
        # any new orders. If so, we cancel old ones and submit the new ones.
        self.buy = None
        self._buy = None
        self.sell = None
        self._sell = None
        self.stop_loss = None
        self._stop_loss = None
        self.take_profit = None
        self._take_profit = None

        self.trade: ClosedTrade | None = None
        self.trades_count = 0

        # chart variables
        self._executed_orders = []
        self._add_line_to_candle_chart_values = {}
        self._add_extra_line_chart_values = {}
        self._add_horizontal_line_to_candle_chart_values = {}
        self._add_horizontal_line_to_extra_chart_values = {}
        # Optional label injected by strategy before each order fires.
        # Shows as prefix on the chart marker, e.g. 'S1·O2'
        self.chart_label: str = ''

        # # Variables used for ML calculations
        # self.ml_mode = "gather" # "gather" or "deploy"

        # self._ml_data_points = []  # Stores complete data points with features and labels
        # self._current_ml_point = None  # Tracks the currently open data point
        # self._ml_model = None  # Cached loaded model (loaded once on first prediction)
        # self._ml_scaler = None  # Cached loaded scaler (loaded once on first prediction)

        self._is_executing = False
        self._is_initiated = False
        self._is_handling_updated_order = False

        self.position: Position | None = None
        self.broker = None

        self._cached_methods = {}
        self._cached_metrics = {}
        self._current_route_index = None

        # Add cached price
        self._cached_price = None

    def candles_pipeline(self) -> Optional[BaseCandlesPipeline]:
        return None

    # def record_features(self, features_dict: dict) -> None:
    #     """
    #     Record multiple features (inputs) for ML training at once.
    #     These will be the independent variables used to predict outcomes.

    #     Args:
    #         features_dict: Dictionary of {feature_name: value} pairs
    #                       (e.g., {'rsi_value': 50, 'macd_crossover': True})
    #     """
    #     # If we don't have an open data point, create one
    #     if self._current_ml_point is None:
    #         current_time = int(self.current_candle[0] / 1000)
    #         self._current_ml_point = {
    #             'time': current_time,
    #             'features': {},
    #             'label': None  # Will be set later when trade completes
    #         }

    #     # Add all features to this data point at once
    #     self._current_ml_point['features'].update(features_dict)

    # def record_label(self, name: str, value) -> None:
    #     """
    #     Record a label (output) for ML training.
    #     These are the target variables that the model should predict.

    #     Args:
    #         name: Descriptive name of the label (e.g., 'trade_profit', 'win_loss')
    #         value: The actual outcome value
    #     """
    #     # Set the label for the current open data point
    #     if self._current_ml_point is not None:
    #         self._current_ml_point['label'] = {
    #             'name': name,
    #             'value': value
    #         }

    #         # Move this completed data point to our storage and clear the current point
    #         self._ml_data_points.append(self._current_ml_point)
    #         self._current_ml_point = None
    #     else:
    #         jh.debug(f"record_label('{name}') called with no open data point — did you forget to call record_features() first?")

    # def export_ml_data(self, directory: str = None) -> bool:
    #     """
    #     Export all recorded features and labels to CSV files.
    #     Returns True if export was successful, False otherwise.

    #     Args:
    #         directory: Optional output directory. Defaults to strategy location.
    #     """
    #     import os
    #     import sys
    #     import csv

    #     try:
    #         # Determine output directory
    #         if directory is None:
    #             try:
    #                 module = sys.modules[self.__class__.__module__]
    #                 directory = os.path.dirname(os.path.abspath(module.__file__))
    #             except Exception as e:
    #                 jh.debug(f"Could not determine strategy path, using cwd: {e}")
    #                 directory = os.getcwd()

    #         # Create ml_data subdirectory
    #         try:
    #             ml_dir = os.path.join(directory, "ml_data")
    #             os.makedirs(ml_dir, exist_ok=True)
    #         except Exception as e:
    #             jh.debug(f"Failed to create ml_data directory: {e}")
    #             return False

    #         # Export data points
    #         if self._ml_data_points:
    #             try:
    #                 data_path = os.path.join(ml_dir, f"{self.name}_data.csv")
    #                 with open(data_path, 'w', newline='') as f:
    #                     writer = csv.writer(f)

    #                     # Write header: time, label_name, label_value, feature1, feature2, ...
    #                     headers = ['time', 'label_name', 'label_value']
    #                     # Get all unique feature names across all data points
    #                     all_features = set()
    #                     for point in self._ml_data_points:
    #                         all_features.update(point['features'].keys())
    #                     headers.extend(sorted(all_features))

    #                     writer.writerow(headers)

    #                     # Write data rows
    #                     for point in self._ml_data_points:
    #                         if point['label'] is None:
    #                             continue  # Skip points without labels

    #                         row = [
    #                             point['time'],
    #                             point['label']['name'],
    #                             str(point['label']['value'])
    #                         ]

    #                         # Add all feature values (in consistent order)
    #                         for feature_name in sorted(all_features):
    #                             row.append(str(point['features'].get(feature_name, '')))

    #                         writer.writerow(row)

    #             except Exception as e:
    #                 jh.debug(f"Failed to export ML data: {e}")
    #                 return False

    #         return True

    #     except Exception as e:
    #         jh.debug(f"Unexpected error during ML data export: {e}")
    #         return False

    # def get_ml_prediction(self) -> dict:
    #     """
    #     Get ML prediction using the most recently recorded features.

    #     Returns:
    #         Dictionary containing:
    #         - 'prediction': bool (True/False prediction)
    #         - 'probability': float (0-1 probability of positive class)

    #     Raises:
    #         ValueError: If no features have been recorded or model not trained
    #         FileNotFoundError: If model files are missing (with detailed path info)
    #     """
    #     import joblib
    #     import numpy as np
    #     import os
    #     import sys

    #     # Check if we have features to predict with
    #     if self._current_ml_point is None or not self._current_ml_point['features']:
    #         raise ValueError("No features recorded for prediction. Call record_features() first.")

    #     # Resolve strategy directory reliably via the module registry
    #     try:
    #         module = sys.modules[self.__class__.__module__]
    #         strategy_dir = os.path.dirname(os.path.abspath(module.__file__))
    #     except Exception as e:
    #         raise FileNotFoundError(
    #             f"Could not determine strategy directory from module '{self.__class__.__module__}': {e}"
    #         )

    #     # Load model and scaler once and cache them for the lifetime of this strategy instance
    #     if self._ml_model is None or self._ml_scaler is None:
    #         model_path = os.path.join(strategy_dir, "svm_model.pkl")
    #         scaler_path = os.path.join(strategy_dir, "scaler.pkl")

    #         # Check what files actually exist (for helpful error messages)
    #         existing_files = [f for f in os.listdir(strategy_dir) if not f.startswith('.')]
    #         jh.debug(f"[ML] Loading model from: {strategy_dir}")

    #         if not os.path.exists(model_path):
    #             raise FileNotFoundError(
    #                 f"Model file NOT FOUND at: {model_path}\n"
    #                 f"Current directory: {os.getcwd()}\n"
    #                 f"Files in strategy dir ({strategy_dir}): {existing_files}"
    #             )
    #         if not os.path.exists(scaler_path):
    #             raise FileNotFoundError(
    #                 f"Scaler file NOT FOUND at: {scaler_path}\n"
    #                 f"Current directory: {os.getcwd()}\n"
    #                 f"Files in strategy dir ({strategy_dir}): {existing_files}"
    #             )

    #         try:
    #             self._ml_model = joblib.load(model_path)
    #             self._ml_scaler = joblib.load(scaler_path)
    #             jh.debug("[ML] Model and scaler loaded and cached successfully")
    #         except Exception as e:
    #             raise FileNotFoundError(
    #                 f"Failed to load model files from {strategy_dir}\n"
    #                 f"Error: {str(e)}\n"
    #                 f"Files in directory ({strategy_dir}): {existing_files}"
    #             )

    #     svm_model = self._ml_model
    #     scaler = self._ml_scaler

    #     # Get current features
    #     current_features = self._current_ml_point['features']

    #     # Create feature array from current features
    #     # We'll use the same order as when training (alphabetical)
    #     sorted_features = sorted(current_features.keys())
    #     feature_array = np.array([
    #         current_features[feature] for feature in sorted_features
    #     ]).reshape(1, -1)

    #     # Scale and predict
    #     try:
    #         feature_array_scaled = scaler.transform(feature_array)
    #         prediction = svm_model.predict(feature_array_scaled)[0]
    #         probabilities = svm_model.predict_proba(feature_array_scaled)[0]

    #         return {
    #             'prediction': bool(prediction),
    #             'probability': float(probabilities[1])
    #         }
    #     except Exception as e:
    #         raise ValueError(f"Prediction failed: {e}. Check feature consistency with training data.")

    def add_line_to_candle_chart(self, title: str, value: float, color=None) -> None:
        # validate value's type
        if not isinstance(value, (int, float)):
            raise ValueError(f"Invalid value type: {type(value)}. The value must be either int or float; you're passing {value}")

        if title not in self._add_line_to_candle_chart_values:
            self._add_line_to_candle_chart_values[title] = {
                'data': [],
                'color': color if color is not None else generate_unique_hex_color(),
            }
        self._add_line_to_candle_chart_values[title]['data'].append({
            'time': int(self.current_candle[0] / 1000),
            'value': value,
            'color': color if color is not None else (self._add_line_to_candle_chart_values[title]['color'])
        })

    def add_horizontal_line_to_candle_chart(self, title: str, value: float, color=None, line_width=1.5, line_style='solid') -> None:
        # validate value's type
        if not isinstance(value, (int, float)):
            raise ValueError(f"Invalid value type: {type(value)}. The value must be either int or float; you're passing {value}")

        if line_style == 'solid':
            lineStyle = 0
        elif line_style == 'dotted':
            lineStyle = 1
        else:
            raise ValueError(f"Invalid line_style: {line_style}")

        if title in self._add_horizontal_line_to_candle_chart_values:
            self._add_horizontal_line_to_candle_chart_values[title].update({
                'price': value,
                'color': color if color is not None else self._add_horizontal_line_to_candle_chart_values[title]['color'],
                'lineWidth': line_width,
                'lineStyle': lineStyle,
            })
        else:
            self._add_horizontal_line_to_candle_chart_values[title] = {
                'title': title,
                'price': value,
                'color': color if color is not None else generate_unique_hex_color(),
                'lineWidth': line_width,
                'lineStyle': lineStyle,
            }

    def add_horizontal_line_to_extra_chart(self, chart_name: str, title: str, value: float, color=None, line_width=1.5, line_style='solid') -> None:
        # validate value's type
        if not isinstance(value, (int, float)):
            raise ValueError(f"Invalid value type: {type(value)}. The value must be either int or float; you're passing {value}")

        if line_style == 'solid':
            lineStyle = 0
        elif line_style == 'dotted':
            lineStyle = 1
        else:
            raise ValueError(f"Invalid line_style: {line_style}")

        if chart_name not in self._add_horizontal_line_to_extra_chart_values:
            self._add_horizontal_line_to_extra_chart_values[chart_name] = {}

        self._add_horizontal_line_to_extra_chart_values[chart_name][title] = {
            'price': value,
            'color': color if color is not None else generate_unique_hex_color(),
            'lineWidth': line_width,
            'lineStyle': lineStyle,
            'title': title
        }

    def add_extra_line_chart(self, chart_name: str, title: str, value: float, color=None) -> None:
        # validate value's type
        if not isinstance(value, (int, float)):
            raise ValueError(f"Invalid value type: {type(value)}. The value must be either int or float; you're passing {value}")

        if chart_name not in self._add_extra_line_chart_values:
            self._add_extra_line_chart_values[chart_name] = {}

        if title not in self._add_extra_line_chart_values[chart_name]:
            self._add_extra_line_chart_values[chart_name][title] = {
                'data': [],
                'color': color if color is not None else generate_unique_hex_color(),
            }

        self._add_extra_line_chart_values[chart_name][title]['data'].append({
            'time': int(self.current_candle[0] / 1000),
            'value': value,
            'color': color if color is not None else (self._add_extra_line_chart_values[chart_name][title]['color'])
        })

    def _init_objects(self) -> None:
        """
        This method gets called after right creating the Strategy object. It
        is just a workaround as a part of not being able to set them inside
        self.__init__() for the purpose of removing __init__() methods from strategies.
        """
        self.position = store.positions.get_position(self.exchange, self.symbol)
        self.broker = Broker(self.position, self.exchange, self.symbol, self.timeframe)

        if self.hp is None and len(self.hyperparameters()) > 0:
            self.hp = {}
            for dna in self.hyperparameters():
                self.hp[dna['name']] = dna['default']

    @property
    def _price_precision(self) -> int:
        """
        used when live trading because few exchanges require numbers to have a specific precision
        """
        return store.exchanges.get_exchange(self.exchange).vars['precisions'][self.symbol]['price_precision']

    @property
    def _qty_precision(self) -> int:
        """
        used when live trading because few exchanges require numbers to have a specific precision
        """
        return store.exchanges.get_exchange(self.exchange).vars['precisions'][self.symbol]['qty_precision']

    def _broadcast(self, msg: str) -> None:
        """Broadcasts the event to all OTHER strategies

        Arguments:
            msg {str} -- [the message to broadcast]
        """
        from qengine.routes import router

        for r in router.routes:
            # skip self
            if r.strategy.id == self.id:
                continue

            if msg == 'route-open-position':
                r.strategy.on_route_open_position(self)
            elif msg == 'route-close-position':
                r.strategy.on_route_close_position(self)
            elif msg == 'route-increased-position':
                r.strategy.on_route_increased_position(self)
            elif msg == 'route-reduced-position':
                r.strategy.on_route_reduced_position(self)
            elif msg == 'route-canceled':
                r.strategy.on_route_canceled(self)

            r.strategy._detect_and_handle_entry_and_exit_modifications()

    def _handle_executed_order_for_chart(self, order: Order):
        position_type = ''
        if self.position.is_long:
            position_type = 'LONG'
        elif self.position.is_short:
            position_type = 'SHORT'
        elif self.position.is_close and self.position.previous_qty > 0:
            position_type = 'LONG'
        elif self.position.is_close and self.position.previous_qty < 0:
            position_type = 'SHORT'

        prefix = f'{self.chart_label} ' if self.chart_label else ''
        # store.app.time (and thus order.executed_at) is candle_open + 60_000,
        # so subtract 60s to align the marker with the candle that was being processed.
        marker_time = (order.executed_at - 60_000) if order.executed_at else self.current_candle[0]
        self._executed_orders.append({
            'time': int(marker_time / 1000),
            'position': 'aboveBar' if order.side == sides.SELL else 'belowBar',
            'color': '#e91e63' if order.side == sides.SELL else '#2196F3',
            'shape': 'arrowDown' if order.side == sides.SELL else 'arrowUp',
            'text': f'{prefix}{order.side.upper()} • {position_type}',
            'order_id': order.id,
        })

    def _on_updated_position(self, order: Order) -> None:
        """
        Handles the after-effect of the executed order to execute strategy
        events. Note that it assumes that the position has already
        been affected by the executed order.
        """
        # in live-mode, sometimes order-update effects and new execution has overlaps, so:
        self._is_handling_updated_order = True

        self._handle_executed_order_for_chart(order)

        # CFD mode: determine effect from ticket changes
        if self.position.is_cfd_mode:
            if order.reduce_only:
                if self.position.ticket_count == 0:
                    effect = 'closing_position'
                else:
                    effect = 'ticket_closed'
            elif self.position.ticket_count == 1:
                effect = 'opening_position'
            else:
                effect = 'ticket_opened'
        else:
            # Standard mode: determine effect from qty changes
            before_qty = self.position.previous_qty
            after_qty = self.position.qty

            if abs(before_qty) <= abs(self.position._min_qty) < abs(after_qty):
                effect = 'opening_position'
            elif abs(before_qty) > abs(self.position._min_qty) >= abs(after_qty):
                effect = 'closing_position'
            elif abs(after_qty) > abs(before_qty):
                effect = 'increased_position'
            else:
                effect = 'reduced_position'

        if effect == 'opening_position':
            after_qty = self.position.qty
            txt = f"OPENED {self.position.type} position for {self.symbol}: qty: {after_qty}, entry_price: {self.position.entry_price}"
            if jh.is_backtesting():
                store.logs.add(txt, 'position')
            if jh.is_debuggable('position_opened'):
                logger.info(txt)
            if jh.is_live() and jh.get_config('env.notifications.events.updated_position'):
                notifier.notify(txt)
            self._on_open_position(order)
        elif effect == 'closing_position':
            pnl_txt = ''
            if store.closed_trades.trades:
                last_trade = store.closed_trades.trades[-1]
                pnl_txt = f', PnL: {getattr(last_trade, "pnl", "N/A")}'
            txt = f"CLOSED Position for {self.symbol}{pnl_txt}"
            if jh.is_backtesting():
                store.logs.add(txt, 'position')
            if jh.is_debuggable('position_closed'):
                logger.info(txt)
            if jh.is_live() and jh.get_config('env.notifications.events.updated_position'):
                notifier.notify(txt)
            self._on_close_position(order)
        elif effect == 'ticket_opened':
            txt = f"CFD ticket #{self.position.ticket_count} opened for {self.symbol}, net qty: {self.position.qty}"
            if jh.is_backtesting():
                store.logs.add(txt, 'position')
            if jh.is_debuggable('position_opened'):
                logger.info(txt)
            self.on_ticket_opened(order)
        elif effect == 'ticket_closed':
            txt = f"CFD ticket closed for {self.symbol}, {self.position.ticket_count} remaining"
            if jh.is_backtesting():
                store.logs.add(txt, 'position')
            if jh.is_debuggable('position_closed'):
                logger.info(txt)
            self.on_ticket_closed(order)
        elif effect == 'increased_position':
            after_qty = self.position.qty
            txt = f"INCREASED Position size to {after_qty}"
            if jh.is_backtesting():
                store.logs.add(txt, 'position')
            if jh.is_debuggable('position_increased'):
                logger.info(txt)
            if jh.is_live() and jh.get_config('env.notifications.events.updated_position'):
                notifier.notify(txt)
            self._on_increased_position(order)
        else:  # reduced_position
            after_qty = self.position.qty
            txt = f"REDUCED Position size to {after_qty}"
            if jh.is_backtesting():
                store.logs.add(txt, 'position')
            if jh.is_debuggable('position_reduced'):
                logger.info(txt)
            if jh.is_live() and jh.get_config('env.notifications.events.updated_position'):
                notifier.notify(txt)
            self._on_reduced_position(order)

        self._is_handling_updated_order = False

    def filters(self) -> list:
        return []

    def hyperparameters(self) -> list:
        return []

    def dna(self) -> str:
        return ''

    def _execute_long(self) -> None:
        self.go_long()

        # validation
        if self.buy is None:
            raise exceptions.InvalidStrategy('You forgot to set self.buy. example (qty, price)')
        elif type(self.buy) not in [tuple, list]:
            raise exceptions.InvalidStrategy(
                f'self.buy must be either a list or a tuple. example: (qty, price). You set: {type(self.buy)}')

        self._prepare_buy()

        if self.take_profit is not None:
            if self.exchange_type == 'spot':
                raise exceptions.InvalidStrategy(
                    "Setting self.take_profit in the go_long() method is not supported for spot trading (it's only supported in futures trading). "
                    "Try setting it in self.on_open_position() instead."
                )

            # validate
            self._validate_take_profit()

            self._prepare_take_profit()

        if self.stop_loss is not None:
            if self.exchange_type == 'spot':
                raise exceptions.InvalidStrategy(
                    "Setting self.stop_loss in the go_long() method is not supported for spot trading (it's only supported in futures trading). "
                    "Try setting it in self.on_open_position() instead."
                )

            # validate
            self._validate_stop_loss()

            self._prepare_stop_loss()

        # filters
        if not self._execute_filters():
            return

        self._submit_buy_orders()

    def _submit_buy_orders(self) -> None:
        if jh.is_livetrading():
            price_to_compare = jh.round_price_for_live_mode(
                self.price,
                store.exchanges.get_exchange(self.exchange).vars['precisions'][self.symbol]['price_precision']
            )
        else:
            price_to_compare = self.price

        for o in self._buy:
            # MARKET order
            if jh.is_price_near(o[1], price_to_compare):
                self.broker.buy_at_market(o[0])
            # STOP order
            elif o[1] > price_to_compare:
                self.broker.start_profit_at(sides.BUY, o[0], o[1])
            # LIMIT order
            elif o[1] < price_to_compare:
                self.broker.buy_at(o[0], o[1])
            else:
                raise ValueError(f'Invalid order price: o[1]:{o[1]}, self.price:{self.price}')

    def _submit_sell_orders(self) -> None:
        if jh.is_livetrading():
            price_to_compare = jh.round_price_for_live_mode(
                self.price,
                store.exchanges.get_exchange(self.exchange).vars['precisions'][self.symbol]['price_precision']
            )
        else:
            price_to_compare = self.price

        for o in self._sell:
            # MARKET order
            if jh.is_price_near(o[1], price_to_compare):
                self.broker.sell_at_market(o[0])
            # STOP order
            elif o[1] < price_to_compare:
                self.broker.start_profit_at(sides.SELL, o[0], o[1])
            # LIMIT order
            elif o[1] > price_to_compare:
                self.broker.sell_at(o[0], o[1])
            else:
                raise ValueError(f'Invalid order price: o[1]:{o[1]}, self.price:{self.price}')

    def _execute_short(self) -> None:
        self.go_short()

        # validation
        if self.sell is None:
            raise exceptions.InvalidStrategy('You forgot to set self.sell. example (qty, price)')
        elif type(self.sell) not in [tuple, list]:
            raise exceptions.InvalidStrategy(
                f'self.sell must be either a list or a tuple. example: (qty, price). You set {type(self.sell)}'
            )

        self._prepare_sell()

        if self.take_profit is not None:
            self._validate_take_profit()
            self._prepare_take_profit()

        if self.stop_loss is not None:
            self._validate_stop_loss()
            self._prepare_stop_loss()

        # filters
        if not self._execute_filters():
            return

        self._submit_sell_orders()

    def _prepare_buy(self, make_copies: bool = True) -> None:
        try:
            self.buy = self._get_formatted_order(self.buy)
        except ValueError:
            raise exceptions.InvalidShape(
                'The format of self.buy is invalid. \n'
                f'It must be either (qty, price) or [(qty, price), (qty, price)] for multiple points; but {self.buy} was given'
            )

        if make_copies:
            self._buy = self.buy.copy()

    def _prepare_sell(self, make_copies: bool = True) -> None:
        try:
            self.sell = self._get_formatted_order(self.sell)
        except ValueError:
            raise exceptions.InvalidShape(
                'The format of self.sell is invalid. \n'
                f'It must be either (qty, price) or [(qty, price), (qty, price)] for multiple points; but {self.sell} was given'
            )

        if make_copies:
            self._sell = self.sell.copy()

    def _prepare_stop_loss(self, make_copies: bool = True) -> None:
        try:
            self.stop_loss = self._get_formatted_order(self.stop_loss)
        except ValueError:
            raise exceptions.InvalidShape(
                'The format of self.stop_loss is invalid. \n'
                f'It must be either (qty, price) or [(qty, price), (qty, price)] for multiple points; but {self.stop_loss} was given'
            )

        if make_copies:
            self._stop_loss = self.stop_loss.copy()

    def _prepare_take_profit(self, make_copies: bool = True) -> None:
        try:
            self.take_profit = self._get_formatted_order(self.take_profit)
        except ValueError:
            raise exceptions.InvalidShape(
                'The format of self.take_profit is invalid. \n'
                f'It must be either (qty, price) or [(qty, price), (qty, price)] for multiple points; but {self.take_profit} was given'
            )

        if make_copies:
            self._take_profit = self.take_profit.copy()

    def _validate_stop_loss(self) -> None:
        if self.stop_loss is None:
            raise exceptions.InvalidStrategy('You forgot to set self.stop_loss. example (qty, price)')
        elif type(self.stop_loss) not in [tuple, list, np.ndarray]:
            raise exceptions.InvalidStrategy(
                f'self.stop_loss must be either a list or a tuple. example: (qty, price). You set {type(self.stop_loss)}')

    def _validate_take_profit(self) -> None:
        if self.take_profit is None:
            raise exceptions.InvalidStrategy('You forgot to set self.take_profit. example (qty, price)')
        elif type(self.take_profit) not in [tuple, list, np.ndarray]:
            raise exceptions.InvalidStrategy(
                f'self.take_profit must be either a list or a tuple. example: (qty, price). You set {type(self.take_profit)}')

    def _execute_filters(self) -> bool:
        for f in self.filters():
            try:
                passed = f()
            except TypeError:
                raise exceptions.InvalidStrategy(
                    "Invalid filter format. You need to pass filter methods WITHOUT calling them "
                    "(no parentheses must be present at the end)"
                    "\n\n"
                    "\u274C " + "Incorrect Example:\n"
                                "return [\n"
                                "    self.filter_1()\n"
                                "]\n\n"
                                "\u2705 " + "Correct Example:\n"
                                            "return [\n"
                                            "    self.filter_1\n"
                                            "]\n"
                )

            if not passed:
                logger.info(f.__name__)
                self._reset()
                return False

        return True

    @abstractmethod
    def go_long(self) -> None:
        pass

    def go_short(self) -> None:
        pass

    def _execute_cancel(self) -> None:
        """
        cancels everything so that the strategy can keep looking for new trades.
        """
        # validation
        if self.position.is_open:
            raise Exception('cannot cancel orders when position is still open. there must be a bug somewhere.')

        logger.info(f'cancel all remaining orders of {self.symbol} to prepare for a fresh start...')

        self.broker.cancel_all_orders()

        self._reset()

        self._broadcast('route-canceled')

        self.on_cancel()

        if not jh.is_unit_testing() and not jh.is_live():
            store.orders.storage[f'{self.exchange}-{self.symbol}'].clear()

    def _reset(self) -> None:
        self.buy = None
        self._buy = None
        self.sell = None
        self._sell = None
        self.stop_loss = None
        self._stop_loss = None
        self.take_profit = None
        self._take_profit = None

        store.orders.reset_trade_orders(self.exchange, self.symbol)

        self.increased_count = 0
        self.reduced_count = 0

    def on_cancel(self) -> None:
        """
        what should happen after all active orders have been cancelled
        """
        pass

    @abstractmethod
    def should_long(self) -> bool:
        pass

    def should_short(self) -> bool:
        return False

    def should_cancel_entry(self) -> bool:
        """
        Whether to cancel the active  entry orders or not. By default, it will cancel the
        entry orders when a new candle is formed and the position is still not open.
        """
        return True

    def before(self) -> None:
        """
        Get's executed BEFORE executing the strategy's logic
        """
        pass

    def after(self) -> None:
        """
        Get's executed AFTER executing the strategy's logic
        """
        pass

    def _update_position(self) -> None:
        self._wait_until_executing_orders_are_fully_handled()

        # after _wait_until_executing_orders_are_fully_handled, the position might have closed, so:
        if self.position.is_close:
            return

        self.update_position()

        self._detect_and_handle_entry_and_exit_modifications()

    def _detect_and_handle_entry_and_exit_modifications(self) -> None:
        if self.position.is_close:
            return

        try:
            # if self.buy has been modified
            if self.is_long:
                # prepare format
                self._prepare_buy(make_copies=False)

                # if entry has been modified
                if not np.array_equal(self.buy, self._buy):
                    self._buy = self.buy.copy()

                    # cancel orders
                    for o in self.entry_orders:
                        if o.is_active or o.is_queued:
                            self.broker.cancel_order(o.id)

                    self._submit_buy_orders()

            # if self.sell has been modified
            elif self.is_short:
                # prepare format
                self._prepare_sell(make_copies=False)

                # if entry has been modified
                if not np.array_equal(self.sell, self._sell):
                    self._sell = self.sell.copy()

                    # cancel orders
                    for o in self.entry_orders:
                        if o.is_active or o.is_queued:
                            self.broker.cancel_order(o.id)

                    self._submit_sell_orders()

            # if self.stop_loss has been modified
            if self.position.is_open and self.stop_loss is not None:
                self._validate_stop_loss()
                self._prepare_stop_loss(False)

                # if stop_loss has been modified
                if not np.array_equal(self.stop_loss, self._stop_loss):
                    # prepare format
                    self._stop_loss = self.stop_loss.copy()

                    # if there's only one order in self._stop_loss, then it could be a liquidation order, store its price
                    if len(self._stop_loss) == 1:
                        temp_current_price = self.price
                    else:
                        temp_current_price = None

                    # CANCEL previous orders
                    for o in self.active_exit_orders:
                        if o.is_stop_loss and (o.is_active or o.is_queued):
                            self.broker.cancel_order(o.id)

                    # SUBMIT new orders
                    for o in self._stop_loss:
                        # sometimes while submitting orders, the position gets closed (in live mode). Hence, check again
                        # to see if the position is still open. If it's closed, no further submitting is required.
                        if self.position.is_close:
                            logger.info(
                                "Position got closed while submitting stop-loss orders. Hence, skipping further submissions"
                            )
                            break

                        # see if we need to override the stop-loss price to be the current price to ensure a MARKET order
                        if temp_current_price == o[1]:
                            order_price = self.price
                        else:
                            order_price = o[1]

                        submitted_order: Order = self.broker.reduce_position_at(o[0], order_price, self.price)
                        if submitted_order:
                            submitted_order.submitted_via = order_submitted_via.STOP_LOSS

                        # if self.take_profit has been modified

            # if self.take_profit has been modified
            if self.position.is_open and self.take_profit is not None:
                self._validate_take_profit()
                self._prepare_take_profit(False)

                # if _take_profit has been modified
                if not np.array_equal(self.take_profit, self._take_profit):
                    self._take_profit = self.take_profit.copy()

                    # if there's only one order in self._stop_loss, then it could be a liquidation order, store its price
                    if len(self._take_profit) == 1:
                        temp_current_price = self.price
                    else:
                        temp_current_price = None

                    # CANCEL previous orders
                    for o in self.active_exit_orders:
                        if o.is_take_profit and (o.is_active or o.is_queued):
                            self.broker.cancel_order(o.id)

                    # SUBMIT new orders
                    for o in self._take_profit:
                        # sometimes while submitting orders, the position gets closed (in live mode). Hence, check again
                        # to see if the position is still open. If it's closed, no further submitting is required.
                        if self.position.is_close:
                            logger.info(
                                "Position got closed while submitting take-profit orders. Hence, skipping further submissions"
                            )
                            break

                        # see if we need to override the take-profit price to be the current price to ensure a MARKET order
                        if temp_current_price == o[1]:
                            order_price = self.price
                        else:
                            order_price = o[1]

                        submitted_order: Order = self.broker.reduce_position_at(o[0], order_price, self.price)
                        if submitted_order:
                            submitted_order.submitted_via = order_submitted_via.TAKE_PROFIT
    
        except TypeError:
            raise exceptions.InvalidStrategy(
                'Something odd is going on within your strategy causing a TypeError exception. '
                'Try running it with the debug mode enabled in a backtest to see what was going on near the end, and fix it.'
            )
        except:
            raise

        # validations: stop-loss and take-profit should not be the same
        if (
                self.position.is_open
                and (self.stop_loss is not None and self.take_profit is not None)
                and np.array_equal(self.stop_loss, self.take_profit)
                and len(self.stop_loss) > 0
        ):
            raise exceptions.InvalidStrategy(
                'stop-loss and take-profit should not be exactly the same. Just use either one of them and it will do.')

    def update_position(self) -> None:
        pass

    def _wait_until_executing_orders_are_fully_handled(self):
        if self._is_handling_updated_order:
            logger.info(
                "Stopped strategy execution at this time because we're still handling the result "
                "of an executed order. Trying again in 3 seconds..."
            )
            sleep(3)

    def _check(self) -> None:
        """
        Based on the newly updated info, check if we should take action or not
        """
        if not self._is_initiated:
            self._is_initiated = True

        self._wait_until_executing_orders_are_fully_handled()

        if jh.is_live() and jh.is_debuggable('strategy_execution'):
            logger.info(f'Executing  {self.name}-{self.exchange}-{self.symbol}-{self.timeframe}')

        # should cancel entry?
        if len(self.entry_orders) and self.is_close and self.should_cancel_entry():
            self._execute_cancel()

            # make sure order cancellation response is received via WS
            if jh.is_live():
                # sleep a little until cancel is received via WS
                sleep(0.1)
                # just in case, sleep some more if necessary
                for _ in range(20):
                    if store.orders.count_active_orders(self.exchange, self.symbol) == 0:
                        break

                    logger.info('sleeping 0.2 more seconds until cancellation is over...')
                    sleep(0.2)

                # If it's still not cancelled, something is wrong. Handle cancellation failure
                if store.orders.count_active_orders(self.exchange, self.symbol) != 0:
                    raise exceptions.ExchangeNotResponding(
                        'The exchange did not respond as expected for order cancellation'
                    )

        # update position
        if self.position.is_open:
            self._update_position()

            # sleep for 1 second if a MARKET order has been submitted but not executed yet (live trading only)
            if jh.is_livetrading():
                waiting_counter = 0
                waiting_seconds = 1
                while self._have_any_pending_market_exit_orders():
                    if jh.is_debugging():
                        logger.info(f'Waiting {waiting_seconds} second for pending market exit orders to be handled...')
                    waiting_counter += 1
                    if waiting_counter > 22:
                        raise exceptions.ExchangeNotResponding(
                            'The exchange did not respond as expected for order execution'
                        )
                    else:
                        sleep(1)

        self._simulate_market_order_execution()

        # should_long and should_short
        # In CFD mode: also check for entry while position is open (adding tickets)
        can_check_entry = self.position.is_close and self.entry_orders == []
        if self.position.is_cfd_mode and self.position.is_open:
            can_check_entry = True

        if can_check_entry:
            if self.position.is_close:
                self._reset()

            should_short = self.should_short()
            # validate that should_short is not True if the exchange_type is spot
            if self.exchange_type == 'spot' and should_short:
                raise exceptions.InvalidStrategy(
                    'should_short cannot be True if the exchange type is "spot".'
                )

            should_long = self.should_long()

            # should_short and should_long cannot both be True unless hedge_mode is enabled
            if should_short and should_long:
                if not self.hedge_mode:
                    raise exceptions.ConflictingRules(
                        'should_short and should_long should not be true at the same time. '
                        'If you want true hedging, set self.hedge_mode = True in your strategy.'
                    )
                # Hedge mode: execute BOTH legs — go_long then go_short
                self._execute_long()
                self._execute_short()
            elif should_long:
                self._execute_long()
            elif should_short:
                self._execute_short()

    def _have_any_pending_market_exit_orders(self) -> bool:
        return any(o.is_active and o.type == order_types.MARKET for o in self.exit_orders)

    @staticmethod
    def _simulate_market_order_execution() -> None:
        """
        Simulate market order execution in backtest mode
        """
        if jh.is_backtesting() or jh.is_unit_testing() or jh.is_paper_trading():
            if not store.orders.to_execute:
                return

            for o in store.orders.to_execute:
                order_service.execute_order(o)
                
                # Update order in database for paper trading
                if jh.is_paper_trading():
                    order_repository.store_or_update(o)

            store.orders.to_execute = []

    def _on_open_position(self, order: Order) -> None:
        self.increased_count = 1

        self._broadcast('route-open-position')

        if self.stop_loss is not None:
            for o in self._stop_loss:
                # validation: make sure stop-loss will exit with profit, if not, close the position
                if self.is_long and o[1] >= self.position.entry_price:
                    submitted_order: Order = self.broker.sell_at_market(o[0])
                    logger.info(
                        'The stop-loss is above entry-price for long position, so it will be replaced with a market order instead')
                elif self.is_short and o[1] <= self.position.entry_price:
                    submitted_order: Order = self.broker.buy_at_market(o[0])
                    logger.info(
                        'The stop-loss is below entry-price for a short position, so it will be replaced with a market order instead')
                else:
                    submitted_order: Order = self.broker.reduce_position_at(o[0], o[1], self.price)

                if submitted_order:
                    submitted_order.submitted_via = order_submitted_via.STOP_LOSS

        if self.take_profit is not None:
            for o in self._take_profit:
                # validation: make sure take-profit will exit with profit, if not, close the position
                if self.is_long and o[1] <= self.position.entry_price:
                    submitted_order: Order = self.broker.sell_at_market(o[0])
                    logger.info(
                        'The take-profit is below entry-price for long position, so it will be replaced with a market order instead')
                elif self.is_short and o[1] >= self.position.entry_price:
                    submitted_order: Order = self.broker.buy_at_market(o[0])
                    logger.info(
                        'The take-profit is above entry-price for a short position, so it will be replaced with a market order instead')
                else:
                    submitted_order: Order = self.broker.reduce_position_at(o[0], o[1], self.price)

                if submitted_order:
                    submitted_order.submitted_via = order_submitted_via.TAKE_PROFIT

        self.on_open_position(order)
        self._detect_and_handle_entry_and_exit_modifications()

    def on_open_position(self, order) -> None:
        """
        What should happen after the open position order has been executed
        """
        pass

    def on_close_position(self, order: Order, closed_trade: ClosedTrade) -> None:
        """
        What should happen after the close position order has been executed. The closed_trade is trade that has been closed.

        Arguments:
            order: Order -- the order that has been executed
            closed_trade: ClosedTrade -- the trade that has been closed
        """
        pass

    def _on_close_position(self, order: Order) -> None:
        self.last_trade_index = self.index

        if not store.closed_trades.trades:
            return

        # get the last closed trade
        closed_trade = store.closed_trades.trades[-1]

        self._broadcast('route-close-position')
        self._execute_cancel()

        # call the on_close_position event
        self.on_close_position(order, closed_trade)

        self._detect_and_handle_entry_and_exit_modifications()

    def _on_increased_position(self, order: Order) -> None:
        self.increased_count += 1

        self._broadcast('route-increased-position')

        self.on_increased_position(order)

        self._detect_and_handle_entry_and_exit_modifications()

    def on_increased_position(self, order) -> None:
        """
        What should happen after the order (if any) increasing the
        size of the position is executed. Overwrite it if needed.
        And leave it be if your strategy doesn't require it
        """
        pass

    def _on_reduced_position(self, order: Order) -> None:
        """
        prepares for on_reduced_position() is implemented by user
        """
        self.reduced_count += 1

        self._broadcast('route-reduced-position')

        self.on_reduced_position(order)

        self._detect_and_handle_entry_and_exit_modifications()

    def on_reduced_position(self, order) -> None:
        """
        What should happen after the order (if any) reducing the size of the position is executed.
        """
        pass

    def on_ticket_opened(self, order) -> None:
        """Called in CFD mode when a new ticket is opened while other tickets exist."""
        pass

    def on_ticket_closed(self, order) -> None:
        """Called in CFD mode when a ticket is closed but other tickets remain open."""
        pass

    def close_all_tickets(self, exit_price: float = None, meta: dict = None) -> None:
        """Close all CFD tickets at the given price (or current price).
        Settles all tickets, records per-ticket trades, fires close callback.

        In live trading, also submits market close orders to the broker so that
        real positions are actually closed (not just internal state).

        Args:
            exit_price: Price to close at (defaults to current price).
            meta: Optional dict merged into each trade's meta (e.g. session, level, exit_reason).
        """
        if not self.position.is_cfd_mode or not self.position._tickets:
            return
        price = exit_price or self.price

        # In live trading, compute gross long/short qty BEFORE clearing tickets
        # so we can submit broker close orders afterwards.
        if jh.is_livetrading():
            long_qty = sum(t.qty for t in self.position._tickets if t.type == 'long')
            short_qty = sum(t.qty for t in self.position._tickets if t.type == 'short')

        from qengine.services import closed_trade_service
        results = self.position.close_all_tickets(price)
        total_pnl = sum(r['pnl'] for r in results)
        if self.position.exchange:
            self.position.exchange.add_realized_pnl(total_pnl)
        for i, r in enumerate(results):
            ticket_meta = dict(meta) if meta else {}
            ticket_meta['leg_index'] = i
            closed_trade_service.record_ticket_close(self.position, r['ticket'], price, r['pnl'], meta=ticket_meta)
        self.trades_count += len(results)
        # Reset position state
        self.position.entry_price = None
        self.position.exit_price = price
        self.position.closed_at = jh.now_to_timestamp()
        # Cancel any pending orders
        self._execute_cancel()

        # In live trading, submit close orders directly to the broker's REST API.
        # We use _submit_market_order() to bypass the internal order execution flow
        # (tickets are already cleared above, so no double callbacks or double PnL).
        if jh.is_livetrading():
            from qengine.services.api import api
            driver = api.drivers.get(self.exchange)
            if driver:
                try:
                    if long_qty > 0:
                        driver._submit_market_order(self.symbol, long_qty, price, 'sell', reduce_only=True)
                        logger.info(f'CFD live: submitted broker SELL {long_qty} to close long tickets')
                    if short_qty > 0:
                        driver._submit_market_order(self.symbol, short_qty, price, 'buy', reduce_only=True)
                        logger.info(f'CFD live: submitted broker BUY {short_qty} to close short tickets')
                except Exception as e:
                    logger.error(f'CFD live: failed to submit broker close order: {e}')

        # Fire close callback
        if store.closed_trades.trades:
            closed_trade = store.closed_trades.trades[-1]
            self.on_close_position(None, closed_trade)

    def close_ticket(self, ticket_id: str, exit_price: float = None, meta: dict = None) -> None:
        """Close a specific CFD ticket by ID.

        In live trading, also submits a market close order to the broker.

        Args:
            ticket_id: ID of the ticket to close.
            exit_price: Price to close at (defaults to current price).
            meta: Optional dict merged into the trade's meta.
        """
        if not self.position.is_cfd_mode:
            return
        # Capture ticket info before closing (needed for broker order in live mode)
        ticket_obj = self.position.get_ticket(ticket_id)
        if ticket_obj is None:
            return

        price = exit_price or self.price
        from qengine.services import closed_trade_service
        result = self.position.close_ticket(ticket_id, price)
        if result is None:
            return
        ticket = result['ticket']
        pnl = result['pnl']
        if self.position.exchange:
            self.position.exchange.add_realized_pnl(pnl)
        closed_trade_service.record_ticket_close(self.position, ticket, price, pnl, meta=meta)
        self.trades_count += 1

        # In live trading, submit close order to broker
        if jh.is_livetrading():
            from qengine.services.api import api
            driver = api.drivers.get(self.exchange)
            if driver:
                try:
                    close_side = 'sell' if ticket.type == 'long' else 'buy'
                    driver._submit_market_order(self.symbol, ticket.qty, price, close_side, reduce_only=True)
                    logger.info(f'CFD live: submitted broker {close_side.upper()} {ticket.qty} to close ticket {ticket.id[:8]}')
                except Exception as e:
                    logger.error(f'CFD live: failed to submit broker close for ticket {ticket.id[:8]}: {e}')

        # If all tickets closed, fire close callback
        if self.position.ticket_count == 0:
            self.position.entry_price = None
            self.position.exit_price = price
            self.position.closed_at = jh.now_to_timestamp()
            self._execute_cancel()
            if store.closed_trades.trades:
                closed_trade = store.closed_trades.trades[-1]
                self.on_close_position(None, closed_trade)

    def on_route_open_position(self, strategy) -> None:
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def on_route_close_position(self, strategy) -> None:
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def on_route_increased_position(self, strategy) -> None:
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def on_route_reduced_position(self, strategy) -> None:
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def on_route_canceled(self, strategy) -> None:
        """used when trading multiple routes that related

        Arguments:
            strategy {Strategy} -- the strategy that has fired (and not listening to) the event
        """
        pass

    def _execute(self) -> None:
        """
        Handles the execution permission for the strategy.
        """
        # make sure we don't execute this strategy more than once at the same time.
        if self._is_executing:
            return

        self._is_executing = True

        try:
            # Cache the current price at the start of execution
            self._cached_price = self.close

            self.before()
            self._check()
            self.after()
            self._clear_cached_methods()

            self.index += 1
        finally:
            # Always reset execution state so strategy isn't permanently stuck
            self._cached_price = None
            self._is_executing = False

    def _terminate(self) -> None:
        """
        Optional for executing code after completion of a backTest.
        This block will not execute in live use as a live
        QEngine is never ending.
        """
        if not jh.should_execute_silently() or jh.is_debugging():
            logger.info(f"Terminating {self.symbol}...")

        self.before_terminate()

        self._detect_and_handle_entry_and_exit_modifications()

        # fake execution of market orders in backtest simulation
        if not jh.is_live():
            if store.orders.to_execute:
                for o in store.orders.to_execute:
                    order_service.execute_order(o)
                store.orders.to_execute = []

        if jh.is_live():
            self.terminate()
            return

        if self.position.is_open:
            store.app.total_open_trades += 1
            store.app.total_open_pl += self.position.pnl
            logger.info(
                f"Closed open {self.exchange}-{self.symbol} position at {self.position.current_price} with PNL: {round(self.position.pnl, 4)}({round(self.position.pnl_percentage, 2)}%) because we reached the end of the backtest session."
            )
            if self.position.is_cfd_mode and self.position._tickets:
                # Close all CFD tickets at current price
                self.close_all_tickets(self.position.current_price)
            else:
                # first cancel all active orders so the balances would go back to the original state
                if self.exchange_type == 'spot':
                    self.broker.cancel_all_orders()
                # fake a closing (market) order so that the calculations would be correct
                self.broker.reduce_position_at(self.position.qty, self.position.current_price, self.price)
            self.terminate()
            return

        if len(self.entry_orders):
            self._execute_cancel()
            logger.info('Canceled open-position orders because we reached the end of the backtest session.')

        self.terminate()

    def before_terminate(self):
        pass

    def terminate(self):
        pass

    def watch_list(self) -> list:
        """
        returns an array containing an array of key-value items that should
        be logged when backTested, and monitored while liveTraded

        Returns:
            [array[{"key": v, "value": v}]] -- an array of dictionary objects
        """
        return []

    def _clear_cached_methods(self) -> None:
        for m in self._cached_methods.values():
            m.cache_clear()

    @property
    def current_candle(self) -> np.ndarray:
        """
        Returns current trading candle

        :return: np.ndarray
        """
        return candle_service.get_current_candle(self.exchange, self.symbol, self.timeframe).copy()

    @property
    def open(self) -> float:
        """
        Returns the opening price of the current candle for this strategy.
        Just as a helper to use when writing super simple strategies.
        Returns:
            [float] -- the current trading candle's OPEN price
        """
        return self.current_candle[1]

    @property
    def close(self) -> float:
        """
        Returns the closing price of the current candle for this strategy.
        Just as a helper to use when writing super simple strategies.
        Returns:
            [float] -- the current trading candle's CLOSE price
        """
        return self.current_candle[2]

    @property
    def price(self) -> float:
        """
        Same as self.close, except in livetrade, this is rounded as the exchanges require it.
        During strategy execution cycles, returns cached price to ensure consistency.

        Returns:
            [float] -- the current trading candle's current(close) price
        """
        # Return cached price if we're executing
        if self._is_executing and self._cached_price is not None:
            return self._cached_price
            
        return self.close

    @property
    def high(self) -> float:
        """
        Returns the highest price of the current candle for this strategy.
        Just as a helper to use when writing super simple strategies.
        Returns:
            [float] -- the current trading candle's HIGH price
        """
        return self.current_candle[3]

    @property
    def low(self) -> float:
        """
        Returns the lowest price of the current candle for this strategy.
        Just as a helper to use when writing super simple strategies.
        Returns:
            [float] -- the current trading candle's LOW price
        """
        return self.current_candle[4]
    
    @property
    def volume(self) -> float:
        """
        Returns the volume of the current candle for this strategy.
        Just as a helper to use when writing super simple strategies.
        Returns:
           [float] -- the volume of the current candle
        """
        return self.current_candle[5]

    @property
    def candles(self) -> np.ndarray:
        """
        Returns candles for current trading route

        :return: np.ndarray
        """
        return candle_service.get_candles(self.exchange, self.symbol, self.timeframe)

    def get_candles(self, exchange: str, symbol: str, timeframe: str) -> np.ndarray:
        """
        Get candles by passing exchange, symbol, and timeframe

        :param exchange: str
        :param symbol: str
        :param timeframe: str

        :return: np.ndarray
        """
        return candle_service.get_candles(exchange, symbol, timeframe)

    @property
    def metrics(self) -> dict:
        """
        Returns all the metrics of the strategy.
        """
        if self.trades_count not in self._cached_metrics:
            self._cached_metrics[self.trades_count] = metrics.trades(
                store.closed_trades.trades, store.app.daily_balance, final=False
            )
        return self._cached_metrics[self.trades_count]

    @property
    def time(self) -> int:
        """returns the current time"""
        return store.app.time

    @property
    def balance(self) -> float:
        """the current capital in the trading exchange"""
        return self.position.exchange.wallet_balance

    @property
    def capital(self) -> float:
        raise NotImplementedError('The alias "self.capital" has been removed. Please use "self.balance" instead.')

    @property
    def available_margin(self) -> float:
        """Current available margin considering leverage"""
        return self.position.exchange.available_margin

    @property
    def leveraged_available_margin(self) -> float:
        """Current available margin considering leverage"""
        return self.leverage * self.available_margin

    @property
    def fee_rate(self) -> float:
        return store.exchanges.get_exchange(self.exchange).fee_rate

    @property
    def is_long(self) -> bool:
        return self.position.type == 'long'

    @property
    def is_short(self) -> bool:
        return self.position.type == 'short'

    @property
    def is_open(self) -> bool:
        return self.position.is_open

    @property
    def is_close(self) -> bool:
        return self.position.is_close

    @property
    def average_stop_loss(self) -> float:
        if self._stop_loss is None:
            raise exceptions.InvalidStrategy('You cannot access self.average_stop_loss before setting self.stop_loss')

        arr = self._stop_loss
        return (np.abs(arr[:, 0] * arr[:, 1])).sum() / np.abs(arr[:, 0]).sum()

    @property
    def average_take_profit(self) -> float:
        if self._take_profit is None:
            raise exceptions.InvalidStrategy(
                'You cannot access self.average_take_profit before setting self.take_profit')

        arr = self._take_profit
        return (np.abs(arr[:, 0] * arr[:, 1])).sum() / np.abs(arr[:, 0]).sum()

    def _get_formatted_order(self, var, round_for_live_mode=True) -> Union[list, np.ndarray]:
        if type(var) is np.ndarray:
            return var

        # just to make sure we also support None
        if var is None or var == []:
            return []

        # create a copy in the placeholders variables so we can detect future modifications
        # also, make it list of orders even if there's only one, to make it easier to loop
        if type(var[0]) not in [list, tuple]:
            var = [var]

        # create numpy array from list
        arr = np.array(var, dtype=float)

        # validate that the price (second column) is not less or equal to zero
        if arr[:, 1].min() <= 0:
            raise exceptions.InvalidStrategy(f'Order price must be greater than zero: \nSubmitted order: {var}\nCurrent price: {self.price}\nCurrent time: {jh.timestamp_to_time(self.time)}')

        if jh.is_livetrading() and round_for_live_mode:
            # in livetrade mode, we'll need them rounded
            current_exchange = store.exchanges.get_exchange(self.exchange)

            # skip rounding if the exchange doesn't have values for 'precisions'
            if 'precisions' not in current_exchange.vars:
                return arr

            price_precision = current_exchange.vars['precisions'][self.symbol]['price_precision']
            qty_precision = current_exchange.vars['precisions'][self.symbol]['qty_precision']

            prices = jh.round_price_for_live_mode(arr[:, 1], price_precision)
            qtys = jh.round_qty_for_live_mode(arr[:, 0], qty_precision)

            arr[:, 0] = qtys
            arr[:, 1] = prices

        return arr

    @property
    def average_entry_price(self) -> float:
        if self.is_long:
            arr = self._buy
        elif self.is_short:
            arr = self._sell
        elif self.has_long_entry_orders:
            arr = self._get_formatted_order(self.buy)
        elif self.has_short_entry_orders:
            arr = self._get_formatted_order(self.sell)
        else:
            return None

        # if type of arr is not np.ndarray, then it's not ready yet. Return None
        if type(arr) is not np.ndarray:
            arr = None

        if arr is None and self.position.is_open:
            return self.position.entry_price
        elif arr is None:
            return None

        return (np.abs(arr[:, 0] * arr[:, 1])).sum() / np.abs(arr[:, 0]).sum()

    @property
    def has_long_entry_orders(self) -> bool:
        # if no order has been submitted yet, but self.buy is not None, then we are calling
        # this property inside a filter.
        if self.entry_orders == [] and self.buy is not None:
            return True

        return self.entry_orders != [] and self.entry_orders[0].side == 'buy'

    @property
    def has_short_entry_orders(self) -> bool:
        # if no order has been submitted yet, but self.sell is not None, then we are calling
        # this property inside a filter.
        if self.entry_orders == [] and self.sell is not None:
            return True
        return self.entry_orders != [] and self.entry_orders[0].side == 'sell'

    def liquidate(self) -> None:
        """
        closes open position with a MARKET order
        """
        if self.position.is_close:
            return

        if self.position.pnl > 0:
            self.take_profit = self.position.qty, self.price
        else:
            self.stop_loss = self.position.qty, self.price

    @property
    def shared_vars(self) -> dict:
        return store.vars

    @property
    def routes(self) -> List[Route]:
        from qengine.routes import router
        return router.routes
    
    @property
    def data_routes(self) -> List[Route]:
        from qengine.routes import router
        return router.data_routes

    @property
    def current_route_index(self) -> int:
        if self._current_route_index is None:
            for i, r in enumerate(self.routes):
                if r.exchange == self.exchange and r.symbol == self.symbol and r.timeframe == self.timeframe:
                    self._current_route_index = i
                    break
            else:
                self._current_route_index = -1
        return self._current_route_index

    @property
    def leverage(self) -> int:
        if type(self.position.exchange) is SpotExchange:
            return 1
        elif type(self.position.exchange) is FuturesExchange:
            return self.position.exchange.futures_leverage
        elif type(self.position.exchange) is ForexCFDExchange:
            return self.position.exchange.default_leverage
        else:
            raise ValueError(f'exchange type not supported: "{self.position.exchange}"')

    @property
    def mark_price(self) -> float:
        return self.position.mark_price

    @property
    def funding_rate(self) -> float:
        return self.position.funding_rate

    @property
    def next_funding_timestamp(self) -> int:
        return self.position.next_funding_timestamp

    @property
    def liquidation_price(self) -> float:
        return self.position.liquidation_price

    @staticmethod
    def log(msg: str, log_type: str = 'info', send_notification: bool = False, webhook: str = None) -> None:
        msg = str(msg)

        # Always log to in-memory store for backtest results with 'strategy' type
        if jh.is_backtesting():
            store.logs.add(msg, 'strategy')

        if log_type == 'info':
            logger.info(msg, send_notification=jh.is_live() and send_notification, webhook=webhook)
        elif log_type == 'error':
            logger.error(msg, send_notification=jh.is_live() and send_notification)
        else:
            raise ValueError(f'log_type should be either "info" or "error". You passed {log_type}')

    @property
    def all_positions(self) -> Dict[str, Position]:
        positions_dict = {}
        for r in self.routes:
            positions_dict[r.symbol] = r.strategy.position
        return positions_dict

    @property
    def portfolio_value(self) -> float:
        total_position_values = 0

        # in spot mode, self.balance does not include open order's value, so:
        if self.is_spot_trading:
            # Add value of active entry orders
            entry_orders_value = 0
            for o in self.entry_orders:
                if o.is_active:
                    entry_orders_value += o.value

            # Add value of all positions
            positions_value = 0
            for key, p in self.all_positions.items():
                positions_value += p.value

            total_position_values = entry_orders_value + positions_value

        # in futures and cfd mode, it's simpler:
        elif self.is_futures_trading or self.is_cfd_trading:
            for key, p in self.all_positions.items():
                total_position_values += p.pnl

        # For spot/futures, PnL is scaled by leverage; for CFD, PnL is already in actual dollars
        if self.is_cfd_trading:
            return total_position_values + self.balance
        return (total_position_values * self.leverage) + self.balance

    @property
    def trades(self) -> List[ClosedTrade]:
        """
        Returns all the closed trades for this strategy.
        """
        return store.closed_trades.trades

    @property
    def orders(self) -> List[Order]:
        """
        Returns all the orders submitted by for this strategy.
        """
        return store.orders.get_orders(self.exchange, self.symbol)

    @property
    def entry_orders(self):
        """
        Returns all the entry orders for this position.
        """
        return order_service.get_entry_orders(self.exchange, self.symbol)

    @property
    def exit_orders(self):
        """
        Returns all the exit orders for this position.
        """
        return order_service.get_exit_orders(self.exchange, self.symbol)

    @property
    def active_exit_orders(self):
        """
        Returns all the exit orders for this position.
        """
        return order_service.get_active_exit_orders(self.exchange, self.symbol)

    @property
    def exchange_type(self):
        return store.exchanges.get_exchange(self.exchange).type

    @property
    def is_spot_trading(self) -> bool:
        return self.exchange_type == 'spot'

    @property
    def is_futures_trading(self) -> bool:
        return self.exchange_type == 'futures'

    @property
    @property
    def is_cfd_trading(self) -> bool:
        return self.exchange_type == 'cfd'

    @property
    def is_forex_cfd_trading(self) -> bool:
        """Alias for is_cfd_trading (backwards compatibility)."""
        return self.is_cfd_trading

    # ── Forex/CFD-specific properties ──

    @property
    def asset_class(self) -> str:
        """What asset class is this route trading?"""
        return jh.get_asset_class(self.symbol)

    @property
    def spread(self) -> float:
        """Current spread for this instrument (in price units)."""
        exchange = store.exchanges.get_exchange(self.exchange)
        if hasattr(exchange, 'get_spread'):
            return exchange.get_spread(self.symbol)
        return 0

    @property
    def pip_size(self) -> float:
        """Pip size for this instrument."""
        return jh.get_pip_size(self.symbol)

    @property
    def market_is_open(self) -> bool:
        """Is the market currently open for this instrument?"""
        from qengine.core.market_hours import market_hours
        return market_hours.is_market_open(self.symbol, self.time)

    @property
    def session(self) -> str:
        """Current forex session: 'tokyo', 'london', 'new_york', 'overlap', 'off'."""
        from qengine.core.market_hours import market_hours
        return market_hours.current_session(self.time)

    @property
    def minutes_to_close(self) -> Optional[int]:
        """Minutes until market/session close."""
        from qengine.core.market_hours import market_hours
        return market_hours.minutes_to_close(self.symbol, self.time)

    @property
    def swap_long(self) -> float:
        """Current overnight swap rate for long positions."""
        exchange = store.exchanges.get_exchange(self.exchange)
        if hasattr(exchange, '_swap_rates'):
            return exchange._swap_rates.get(self.symbol, (0, 0))[0]
        return 0

    @property
    def swap_short(self) -> float:
        """Current overnight swap rate for short positions."""
        exchange = store.exchanges.get_exchange(self.exchange)
        if hasattr(exchange, '_swap_rates'):
            return exchange._swap_rates.get(self.symbol, (0, 0))[1]
        return 0

    @property
    def contract_size(self) -> float:
        """Contract size (e.g., 100000 for forex standard lot)."""
        from qengine.core.instruments import instrument_registry
        return instrument_registry.get_contract_size(self.symbol)

    def pips_to_price(self, pips: float) -> float:
        """Convert pips to price distance."""
        return pips * self.pip_size

    def price_to_pips(self, price_distance: float) -> float:
        """Convert price distance to pips."""
        ps = self.pip_size
        if ps == 0:
            return 0
        return price_distance / ps

    def lot_size_for_risk(self, risk_pct: float, stop_pips: float) -> float:
        """Calculate lot size for a given risk % and stop distance in pips."""
        if stop_pips <= 0:
            return 0
        risk_amount = self.balance * (risk_pct / 100)
        pip_value = self.pip_size * self.contract_size
        if pip_value == 0:
            return 0
        return risk_amount / (stop_pips * pip_value)

    @property
    def daily_balances(self):
        return store.app.daily_balance

    @property
    def is_backtesting(self) -> bool:
        return jh.is_backtesting()

    @property
    def is_livetrading(self) -> bool:
        return jh.is_livetrading()

    @property
    def is_papertrading(self) -> bool:
        return jh.is_paper_trading()

    @property
    def is_live(self) -> bool:
        return jh.is_live()

    @property
    def min_qty(self) -> float:
        if not jh.is_live():
            raise ValueError('self.min_qty is only available in live modes')

        try:
            return store.exchanges.get_exchange(self.exchange).vars['precisions'][self.symbol]['min_qty']
        except KeyError:
            return None
