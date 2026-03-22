import time
import arrow
from typing import Union, List, Dict, Any

import qengine.helpers as jh
from qengine.modes.import_candles_mode.drivers.interface import CandleExchange
from .ibkr_utils import timeframe_to_bar_size, timeframe_to_duration, symbol_to_contract_params


class IBKRMain(CandleExchange):
    """
    Interactive Brokers TWS API historical data driver.
    Uses ib_insync for connection to TWS or IB Gateway.
    Requires running TWS/IB Gateway instance.
    Rate limit: strict (~60 requests per 10 minutes)
    """

    def __init__(
            self,
            name: str,
            port: int = 7497,
            client_id: int = 1,
            backup_exchange_class=None,
    ) -> None:
        super().__init__(
            name=name,
            count=5000,
            rate_limit_per_second=0.1,  # IBKR is very strict
            backup_exchange_class=backup_exchange_class,
        )

        self.port = port
        self.client_id = client_id
        self._ib = None
        self._connected = False

    def _connect(self) -> None:
        """Connect to TWS/IB Gateway via ib_insync."""
        if self._connected and self._ib:
            return

        try:
            from ib_insync import IB
            self._ib = IB()

            import os
            from qengine.services.env import ENV_VALUES
            host = os.environ.get('IBKR_HOST', ENV_VALUES.get('IBKR_HOST', '127.0.0.1'))
            port = int(os.environ.get('IBKR_PORT', ENV_VALUES.get('IBKR_PORT', str(self.port))))
            client_id = int(os.environ.get('IBKR_CLIENT_ID', ENV_VALUES.get('IBKR_CLIENT_ID', str(self.client_id))))

            self._ib.connect(host, port, clientId=client_id)
            self._connected = True
        except ImportError:
            raise ImportError(
                'ib_insync is required for IBKR data import. '
                'Install it with: pip install ib_insync'
            )
        except Exception as e:
            raise ConnectionError(
                f'Could not connect to TWS/IB Gateway at port {self.port}. '
                f'Make sure TWS or IB Gateway is running. Error: {e}'
            )

    def _create_contract(self, symbol: str):
        """Create an ib_insync contract from symbol."""
        from ib_insync import Forex, Future, CFD, Contract

        params = symbol_to_contract_params(symbol)

        if params['sec_type'] == 'CASH':
            contract = Forex(params['symbol'] + params['currency'])
        elif params['sec_type'] == 'FUT':
            contract = Future(
                symbol=params['symbol'],
                exchange=params['exchange'],
                currency=params['currency'],
            )
        elif params['sec_type'] == 'CFD':
            contract = CFD(
                symbol=params['symbol'],
                exchange=params['exchange'],
                currency=params['currency'],
            )
        else:
            contract = Contract(
                symbol=params['symbol'],
                secType=params['sec_type'],
                exchange=params['exchange'],
                currency=params['currency'],
            )

        return contract

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[List[Dict[str, Any]], None]:
        self._connect()

        contract = self._create_contract(symbol)
        bar_size = timeframe_to_bar_size(timeframe)
        duration = timeframe_to_duration(timeframe, self.count)

        end_dt = arrow.get(start_timestamp / 1000).shift(
            minutes=self.count * jh.timeframe_to_one_minutes(timeframe)
        ).format('YYYYMMDD HH:mm:ss') + ' UTC'

        bars = self._ib.reqHistoricalData(
            contract,
            endDateTime=end_dt,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow='MIDPOINT',
            useRTH=False,
            formatDate=2,  # UTC format
        )

        candles = []
        for bar in bars:
            ts = int(bar.date.timestamp() * 1000) if hasattr(bar.date, 'timestamp') else arrow.get(str(bar.date)).int_timestamp * 1000
            candles.append({
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': ts,
                'open': float(bar.open),
                'close': float(bar.close),
                'high': float(bar.high),
                'low': float(bar.low),
                'volume': int(bar.volume) if bar.volume > 0 else 0,
            })

        return candles

    def get_starting_time(self, symbol: str) -> int:
        """IBKR typically has data from ~1998 for forex, varies for other instruments."""
        return arrow.get('2005-01-03').int_timestamp * 1000

    def get_available_symbols(self) -> list:
        """IBKR doesn't have a simple symbols list; return common forex/commodity symbols."""
        return [
            'EUR-USD', 'GBP-USD', 'USD-JPY', 'USD-CHF', 'AUD-USD', 'NZD-USD', 'USD-CAD',
            'EUR-GBP', 'EUR-JPY', 'GBP-JPY', 'EUR-CHF', 'AUD-JPY',
            'XAU-USD', 'XAG-USD',
        ]

    def _disconnect(self) -> None:
        if self._ib and self._connected:
            self._ib.disconnect()
            self._connected = False

    def __del__(self):
        self._disconnect()
