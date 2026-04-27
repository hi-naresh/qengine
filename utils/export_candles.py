"""One-time export: dump OANDA 1m candles to .npy for cloud training (no DB needed).

Run with the qengine conda environment:
    conda activate qengine
    python export_candles.py
"""
import sys, re, numpy as np
from datetime import datetime, timezone

sys.path.insert(0, '..')

from qengine.research.candles import get_candles
from qengine.exceptions import CandleNotFoundInDatabase

TRAIN_START = '2022-01-01'
TRAIN_END   = '2024-12-31'
OUT_FILE    = '../candles_oanda_eurusd_1m_2022_2024.npy'

def _to_ms(date_str):
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return int((dt - datetime(1970, 1, 1)).total_seconds() * 1000)

start_ts = _to_ms(TRAIN_START)
end_ts   = _to_ms(TRAIN_END) + 86_400_000 - 60_000

def _load(s, e):
    return get_candles(exchange='OANDA', symbol='EUR-USD', timeframe='1m',
                       start_date_timestamp=s, finish_date_timestamp=e)

try:
    warmup, candles = _load(start_ts, end_ts)
except CandleNotFoundInDatabase as ex:
    m = re.search(r'latest available candle is up to "([^"]+)"', str(ex))
    dt = datetime.fromisoformat(m.group(1))
    clamp_ts = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    print(f'Clamping end to {m.group(1)}')
    warmup, candles = _load(start_ts, clamp_ts)

if warmup is not None and hasattr(warmup, 'ndim') and warmup.ndim == 2 and len(warmup) > 0:
    candles = np.concatenate([warmup, candles], axis=0)

np.save(OUT_FILE, candles)
print(f'Saved {len(candles):,} candles → {OUT_FILE}  ({candles.nbytes / 1e6:.1f} MB)')
