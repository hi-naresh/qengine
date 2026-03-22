from typing import Union

import numpy as np
from numba import njit

from qengine.helpers import same_length, slice_candles


@njit
def _wad_numba(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    n = len(close)
    ad = np.zeros(n, dtype=np.float64)

    # The first element doesn't have a previous close, so set its adjustment to 0
    ad[0] = 0

    # Calculate the Acc/Dist component iteratively
    for i in range(1, n):
        if close[i] > close[i - 1]:
            ad[i] = close[i] - min(low[i], close[i - 1])
        elif close[i] < close[i - 1]:
            ad[i] = close[i] - max(high[i], close[i - 1])
        else:
            ad[i] = 0

    # Williams Accumulation/Distribution is the cumulative sum of these adjustments
    wad_values = np.cumsum(ad)
    return wad_values


def wad(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    WAD - Williams Accumulation/Distribution

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    # Candle columns: 0=timestamp, 1=open, 2=close, 3=high, 4=low, 5=volume
    res = _wad_numba(
        np.ascontiguousarray(candles[:, 3]),
        np.ascontiguousarray(candles[:, 4]),
        np.ascontiguousarray(candles[:, 2])
    )

    return same_length(candles, res) if sequential else res[-1]
