import os
import pytest
import arrow
import numpy as np

import qengine.helpers as jh
from qengine.enums import brokers, timeframes
from qengine.modes.import_candles_mode.drivers import drivers, driver_names
from qengine.modes.import_candles_mode.drivers.interface import CandleExchange


def _has_parquet_engine():
    try:
        import pyarrow
        return True
    except ImportError:
        pass
    try:
        import fastparquet
        return True
    except ImportError:
        return False


# ── 3.1 Driver Registry Tests ──

def test_all_brokers_registered():
    assert brokers.OANDA in drivers
    assert brokers.OANDA_DEMO in drivers
    assert brokers.IG_MARKETS in drivers
    assert brokers.IG_MARKETS_DEMO in drivers
    assert brokers.IBKR in drivers
    assert brokers.IBKR_PAPER in drivers


def test_driver_names_list():
    assert len(driver_names) == 6
    assert brokers.OANDA in driver_names


def test_all_drivers_are_candle_exchange_subclasses():
    for name, driver_cls in drivers.items():
        assert issubclass(driver_cls, CandleExchange), f'{name} driver is not a CandleExchange subclass'


# ── 3.2 OANDA Driver Tests ──

def test_oanda_driver_instantiation():
    from qengine.modes.import_candles_mode.drivers.OANDA.OandaForex import OandaForex
    driver = OandaForex()
    assert driver.name == brokers.OANDA
    assert driver.count == 5000
    assert 'oanda.com' in driver.base_url
    assert driver.practice is False


def test_oanda_demo_driver():
    from qengine.modes.import_candles_mode.drivers.OANDA.OandaForex import OandaDemoForex
    driver = OandaDemoForex()
    assert driver.name == brokers.OANDA_DEMO
    assert driver.practice is True
    assert 'practice' in driver.base_url


def test_oanda_utils_symbol_conversion():
    from qengine.modes.import_candles_mode.drivers.OANDA.oanda_utils import (
        symbol_to_instrument, instrument_to_symbol
    )
    assert symbol_to_instrument('EUR-USD') == 'EUR_USD'
    assert symbol_to_instrument('XAU-USD') == 'XAU_USD'
    assert instrument_to_symbol('EUR_USD') == 'EUR-USD'
    assert instrument_to_symbol('GBP_JPY') == 'GBP-JPY'


def test_oanda_utils_timeframe_conversion():
    from qengine.modes.import_candles_mode.drivers.OANDA.oanda_utils import timeframe_to_granularity
    assert timeframe_to_granularity(timeframes.MINUTE_1) == 'M1'
    assert timeframe_to_granularity(timeframes.MINUTE_5) == 'M5'
    assert timeframe_to_granularity(timeframes.MINUTE_15) == 'M15'
    assert timeframe_to_granularity(timeframes.MINUTE_30) == 'M30'
    assert timeframe_to_granularity(timeframes.HOUR_1) == 'H1'
    assert timeframe_to_granularity(timeframes.HOUR_4) == 'H4'
    assert timeframe_to_granularity(timeframes.DAY_1) == 'D'
    assert timeframe_to_granularity(timeframes.WEEK_1) == 'W'


# ── 3.3 IG Markets Driver Tests ──

def test_ig_driver_instantiation():
    from qengine.modes.import_candles_mode.drivers.IG.IGMarketsForex import IGMarketsForex
    driver = IGMarketsForex()
    assert driver.name == brokers.IG_MARKETS
    assert driver.count == 1000
    assert driver.demo is False


def test_ig_demo_driver():
    from qengine.modes.import_candles_mode.drivers.IG.IGMarketsForex import IGMarketsDemoForex
    driver = IGMarketsDemoForex()
    assert driver.name == brokers.IG_MARKETS_DEMO
    assert driver.demo is True
    assert 'demo' in driver.base_url


def test_ig_utils_symbol_to_epic():
    from qengine.modes.import_candles_mode.drivers.IG.ig_utils import symbol_to_epic
    assert symbol_to_epic('EUR-USD') == 'CS.D.EURUSD.CFD.IP'
    assert symbol_to_epic('GBP-USD') == 'CS.D.GBPUSD.CFD.IP'
    assert symbol_to_epic('XAU-USD') == 'CS.D.USCGC.TODAY.IP'
    assert symbol_to_epic('US30-USD') == 'IX.D.DOW.IFD.IP'
    # Unknown symbol returns the symbol itself
    assert symbol_to_epic('UNKNOWN-PAIR') == 'UNKNOWN-PAIR'


def test_ig_utils_timeframe_conversion():
    from qengine.modes.import_candles_mode.drivers.IG.ig_utils import timeframe_to_resolution
    assert timeframe_to_resolution(timeframes.MINUTE_1) == 'MINUTE'
    assert timeframe_to_resolution(timeframes.MINUTE_5) == 'MINUTE_5'
    assert timeframe_to_resolution(timeframes.HOUR_1) == 'HOUR'
    assert timeframe_to_resolution(timeframes.HOUR_4) == 'HOUR_4'
    assert timeframe_to_resolution(timeframes.DAY_1) == 'DAY'


# ── 3.4 IBKR Driver Tests ──

def test_ibkr_driver_instantiation():
    from qengine.modes.import_candles_mode.drivers.IBKR.IBKRForex import IBKRForex
    driver = IBKRForex()
    assert driver.name == brokers.IBKR
    assert driver.count == 5000
    assert driver.port == 7497


def test_ibkr_paper_driver():
    from qengine.modes.import_candles_mode.drivers.IBKR.IBKRForex import IBKRPaperForex
    driver = IBKRPaperForex()
    assert driver.name == brokers.IBKR_PAPER


def test_ibkr_utils_symbol_to_contract():
    from qengine.modes.import_candles_mode.drivers.IBKR.ibkr_utils import symbol_to_contract_params
    # Forex
    params = symbol_to_contract_params('EUR-USD')
    assert params['sec_type'] == 'CASH'
    assert params['symbol'] == 'EUR'
    assert params['currency'] == 'USD'
    assert params['exchange'] == 'IDEALPRO'

    # Gold
    params = symbol_to_contract_params('XAU-USD')
    assert params['sec_type'] == 'FUT'
    assert params['symbol'] == 'GC'
    assert params['exchange'] == 'COMEX'

    # Crude oil
    params = symbol_to_contract_params('WTI-USD')
    assert params['sec_type'] == 'FUT'
    assert params['symbol'] == 'CL'


def test_ibkr_utils_timeframe_conversion():
    from qengine.modes.import_candles_mode.drivers.IBKR.ibkr_utils import timeframe_to_bar_size
    assert timeframe_to_bar_size(timeframes.MINUTE_1) == '1 min'
    assert timeframe_to_bar_size(timeframes.MINUTE_5) == '5 mins'
    assert timeframe_to_bar_size(timeframes.HOUR_1) == '1 hour'
    assert timeframe_to_bar_size(timeframes.HOUR_4) == '4 hours'
    assert timeframe_to_bar_size(timeframes.DAY_1) == '1 day'


def test_ibkr_utils_duration():
    from qengine.modes.import_candles_mode.drivers.IBKR.ibkr_utils import timeframe_to_duration
    # 5000 1-minute candles = ~3.5 days
    duration = timeframe_to_duration(timeframes.MINUTE_1, 5000)
    assert 'D' in duration

    # 5000 1-hour candles = ~208 days
    duration = timeframe_to_duration(timeframes.HOUR_1, 5000)
    assert 'D' in duration


def test_ibkr_available_symbols():
    from qengine.modes.import_candles_mode.drivers.IBKR.IBKRForex import IBKRForex
    driver = IBKRForex()
    symbols = driver.get_available_symbols()
    assert 'EUR-USD' in symbols
    assert 'XAU-USD' in symbols


# ── 3.5 CSV Import Driver Tests ──

def test_csv_driver_instantiation():
    from qengine.modes.import_candles_mode.drivers.CSV.CSVImport import CSVImport
    driver = CSVImport(name='CSV', data_dir='/tmp/test_csv')
    assert driver.name == 'CSV'
    assert driver.data_dir == '/tmp/test_csv'


def test_csv_import_from_file(tmp_path):
    """Test importing candles from a CSV file."""
    from qengine.modes.import_candles_mode.drivers.CSV.CSVImport import CSVImport

    # Create a test CSV file
    csv_content = "timestamp,open,high,low,close,volume\n"
    base_ts = arrow.get('2024-01-02T00:00:00Z').int_timestamp * 1000
    for i in range(100):
        ts = base_ts + i * 60000
        price = 1.1000 + i * 0.0001
        csv_content += f"{ts},{price},{price + 0.0002},{price - 0.0001},{price + 0.0001},{1000 + i}\n"

    csv_file = tmp_path / "CSV_EUR-USD_1m.csv"
    csv_file.write_text(csv_content)

    driver = CSVImport(name='CSV', data_dir=str(tmp_path))

    # Fetch candles
    candles = driver.fetch('EUR-USD', base_ts, '1m')
    assert len(candles) == 100
    assert candles[0]['timestamp'] == base_ts
    assert candles[0]['exchange'] == 'CSV'
    assert candles[0]['symbol'] == 'EUR-USD'
    assert candles[0]['timeframe'] == '1m'
    assert candles[0]['open'] == 1.1000
    assert candles[0]['volume'] == 1000


def test_csv_import_timestamp_range(tmp_path):
    """Test that CSV driver correctly filters by timestamp range."""
    from qengine.modes.import_candles_mode.drivers.CSV.CSVImport import CSVImport

    csv_content = "timestamp,open,high,low,close,volume\n"
    base_ts = arrow.get('2024-01-02T00:00:00Z').int_timestamp * 1000
    for i in range(200):
        ts = base_ts + i * 60000
        csv_content += f"{ts},1.1,1.2,1.0,1.15,100\n"

    csv_file = tmp_path / "CSV_EUR-USD_1m.csv"
    csv_file.write_text(csv_content)

    driver = CSVImport(name='CSV', data_dir=str(tmp_path))

    # Fetch only first 50 candles
    candles = driver.fetch('EUR-USD', base_ts, '1m')
    # count=5000 but only 200 candles exist, all within range
    assert len(candles) == 200


def test_csv_get_starting_time(tmp_path):
    from qengine.modes.import_candles_mode.drivers.CSV.CSVImport import CSVImport

    base_ts = arrow.get('2024-01-02T00:00:00Z').int_timestamp * 1000
    csv_content = f"timestamp,open,high,low,close,volume\n{base_ts},1.1,1.2,1.0,1.15,100\n"

    csv_file = tmp_path / "CSV_EUR-USD_1m.csv"
    csv_file.write_text(csv_content)

    driver = CSVImport(name='CSV', data_dir=str(tmp_path))
    assert driver.get_starting_time('EUR-USD') == base_ts


def test_csv_get_available_symbols(tmp_path):
    from qengine.modes.import_candles_mode.drivers.CSV.CSVImport import CSVImport

    (tmp_path / "CSV_EUR-USD_1m.csv").write_text("timestamp,open,high,low,close,volume\n")
    (tmp_path / "CSV_GBP-JPY_1m.csv").write_text("timestamp,open,high,low,close,volume\n")
    (tmp_path / "notacsv.txt").write_text("hello")

    driver = CSVImport(name='CSV', data_dir=str(tmp_path))
    symbols = driver.get_available_symbols()
    assert 'EUR-USD' in symbols
    assert 'GBP-JPY' in symbols
    assert len(symbols) == 2


def test_csv_file_not_found(tmp_path):
    from qengine.modes.import_candles_mode.drivers.CSV.CSVImport import CSVImport

    driver = CSVImport(name='CSV', data_dir=str(tmp_path))
    with pytest.raises(FileNotFoundError):
        driver.fetch('NONEXISTENT-PAIR', 0, '1m')


@pytest.mark.skipif(
    not _has_parquet_engine(),
    reason="pyarrow or fastparquet not installed"
)
def test_csv_parquet_support(tmp_path):
    """Test that CSV driver can also read Parquet files."""
    import pandas as pd
    from qengine.modes.import_candles_mode.drivers.CSV.CSVImport import CSVImport

    base_ts = arrow.get('2024-01-02T00:00:00Z').int_timestamp * 1000
    data = {
        'timestamp': [base_ts + i * 60000 for i in range(50)],
        'open': [1.1 + i * 0.001 for i in range(50)],
        'high': [1.2 + i * 0.001 for i in range(50)],
        'low': [1.0 + i * 0.001 for i in range(50)],
        'close': [1.15 + i * 0.001 for i in range(50)],
        'volume': [100] * 50,
    }
    df = pd.DataFrame(data)
    parquet_file = tmp_path / "CSV_EUR-USD_1m.parquet"
    df.to_parquet(parquet_file)

    driver = CSVImport(name='CSV', data_dir=str(tmp_path))
    candles = driver.fetch('EUR-USD', base_ts, '1m')
    assert len(candles) == 50
    assert candles[0]['open'] == 1.1


def test_csv_custom_column_mapping(tmp_path):
    """Test that CSV driver supports custom column names."""
    from qengine.modes.import_candles_mode.drivers.CSV.CSVImport import CSVImport

    base_ts = arrow.get('2024-01-02T00:00:00Z').int_timestamp * 1000
    csv_content = f"Date,Open,High,Low,Close,Vol\n{base_ts},1.1,1.2,1.0,1.15,500\n"

    csv_file = tmp_path / "CSV_EUR-USD_1m.csv"
    csv_file.write_text(csv_content)

    driver = CSVImport(name='CSV', data_dir=str(tmp_path))
    driver.set_column_map({
        'timestamp': 'Date',
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Vol',
    })

    candles = driver.fetch('EUR-USD', base_ts, '1m')
    assert len(candles) == 1
    assert candles[0]['open'] == 1.1
    assert candles[0]['volume'] == 500
