import os
from typing import Union, List, Dict, Any

import arrow
import numpy as np
import pandas as pd

import qengine.helpers as jh
from qengine.modes.import_candles_mode.drivers.interface import CandleExchange


class CSVImport(CandleExchange):
    """
    Import candles from local CSV or Parquet files.
    Supports: MetaTrader export, TradingView export, custom formats.

    Expected CSV columns (configurable):
        timestamp (or date/datetime), open, high, low, close, volume

    Usage:
        Set CSV_DATA_DIR environment variable to the directory containing CSV files.
        Files should be named as: {EXCHANGE}_{SYMBOL}_{TIMEFRAME}.csv
        Example: OANDA_EUR-USD_1m.csv
    """

    def __init__(self, name: str = 'CSV', data_dir: str = None) -> None:
        super().__init__(
            name=name,
            count=5000,
            rate_limit_per_second=1000,  # local files, no rate limit
            backup_exchange_class=None,
        )

        if data_dir is None:
            data_dir = os.environ.get('CSV_DATA_DIR', 'storage/csv')
        self.data_dir = data_dir

        # Column mapping (configurable for different CSV formats)
        self.column_map = {
            'timestamp': 'timestamp',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume',
        }

    def set_column_map(self, mapping: dict) -> None:
        """Set custom column mapping for non-standard CSV formats."""
        self.column_map.update(mapping)

    def _find_file(self, symbol: str, timeframe: str = '1m') -> str:
        """Find the CSV/Parquet file for the given symbol."""
        # Try various naming patterns
        patterns = [
            f'{self.name}_{symbol}_{timeframe}.csv',
            f'{symbol}_{timeframe}.csv',
            f'{symbol}.csv',
            f'{self.name}_{symbol}_{timeframe}.parquet',
            f'{symbol}_{timeframe}.parquet',
            f'{symbol}.parquet',
        ]

        for pattern in patterns:
            path = os.path.join(self.data_dir, pattern)
            if os.path.exists(path):
                return path

        raise FileNotFoundError(
            f'No CSV/Parquet file found for {symbol} in {self.data_dir}. '
            f'Expected file names: {", ".join(patterns[:3])}'
        )

    def _read_file(self, filepath: str) -> pd.DataFrame:
        """Read CSV or Parquet file."""
        if filepath.endswith('.parquet'):
            return pd.read_parquet(filepath)
        return pd.read_csv(filepath)

    def _parse_timestamp(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse various timestamp formats."""
        ts_col = self.column_map['timestamp']

        # Check common column names if the configured one doesn't exist
        possible_names = [ts_col, 'timestamp', 'date', 'datetime', 'time', 'Date', 'Time', 'Datetime']
        found_col = None
        for name in possible_names:
            if name in df.columns:
                found_col = name
                break

        if found_col is None:
            raise ValueError(f'Could not find timestamp column in CSV. Available columns: {list(df.columns)}')

        col = df[found_col]

        # If already numeric (unix timestamp)
        if pd.api.types.is_numeric_dtype(col):
            values = col.values
            # If in seconds (< 10 billion), convert to milliseconds
            if values[0] < 1e12:
                df['_timestamp_ms'] = (values * 1000).astype(int)
            else:
                df['_timestamp_ms'] = values.astype(int)
        else:
            # Parse as datetime string
            df['_timestamp_ms'] = pd.to_datetime(col).astype(np.int64) // 10**6

        return df

    def fetch(self, symbol: str, start_timestamp: int, timeframe: str = '1m') -> Union[List[Dict[str, Any]], None]:
        filepath = self._find_file(symbol, timeframe)
        df = self._read_file(filepath)
        df = self._parse_timestamp(df)

        end_timestamp = start_timestamp + (self.count - 1) * 60000 * jh.timeframe_to_one_minutes(timeframe)

        # Filter by timestamp range
        mask = (df['_timestamp_ms'] >= start_timestamp) & (df['_timestamp_ms'] <= end_timestamp)
        df = df[mask].sort_values('_timestamp_ms')

        candles = []
        for _, row in df.iterrows():
            candles.append({
                'id': jh.generate_unique_id(),
                'exchange': self.name,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(row['_timestamp_ms']),
                'open': float(row.get(self.column_map['open'], row.get('open', row.get('Open', 0)))),
                'close': float(row.get(self.column_map['close'], row.get('close', row.get('Close', 0)))),
                'high': float(row.get(self.column_map['high'], row.get('high', row.get('High', 0)))),
                'low': float(row.get(self.column_map['low'], row.get('low', row.get('Low', 0)))),
                'volume': int(row.get(self.column_map['volume'], row.get('volume', row.get('Volume', 0)))),
            })

        return candles

    def get_starting_time(self, symbol: str) -> int:
        """Read the first timestamp from the file."""
        filepath = self._find_file(symbol)
        df = self._read_file(filepath)
        df = self._parse_timestamp(df)
        return int(df['_timestamp_ms'].min())

    def get_available_symbols(self) -> list:
        """List available symbols from files in the data directory."""
        if not os.path.exists(self.data_dir):
            return []

        symbols = set()
        for f in os.listdir(self.data_dir):
            if f.endswith(('.csv', '.parquet')):
                parts = f.replace('.csv', '').replace('.parquet', '').split('_')
                # Try to find a symbol pattern (XXX-YYY)
                for part in parts:
                    if '-' in part and len(part.split('-')) == 2:
                        symbols.add(part)

        return sorted(symbols)
