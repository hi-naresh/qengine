"""
Synthetic market data generator for the Strategy Playground.

Generates realistic 1-minute OHLCV candles for various market scenarios
that can be fed directly into the backtest simulator.
"""
import numpy as np
import time as time_module


def generate_scenario(
    scenario: str,
    duration_minutes: int = 360,
    symbol: str = 'EUR-USD',
    start_price: float = 1.1000,
    volatility: float = 0.0002,
    trend_strength: float = 0.00005,
    volume_base: float = 1000.0,
    seed: int = None,
) -> np.ndarray:
    """
    Generate synthetic 1-minute candle data for a given scenario.

    Returns numpy array of shape (duration_minutes, 6):
        [timestamp, open, close, high, low, volume]
    """
    if seed is not None:
        rng = np.random.default_rng(seed)
    else:
        rng = np.random.default_rng()

    generators = {
        'trending_up': _trending,
        'trending_down': _trending,
        'ranging': _ranging,
        'volatile': _volatile,
        'flash_crash': _flash_crash,
        'flash_spike': _flash_spike,
        'breakout_up': _breakout,
        'breakout_down': _breakout,
        'mean_revert': _mean_revert,
        'choppy': _choppy,
        'custom': _custom,
    }

    gen_func = generators.get(scenario, _ranging)

    # Use timestamps guaranteed to be during forex market open hours.
    # Start at a recent Tuesday 08:00 UTC (London session) so ALL candles
    # (including warmup) fall squarely during market-open hours.
    # Tuesday avoids Monday open gaps and Sunday close edge cases.
    import datetime
    now = datetime.datetime.utcnow()
    days_since_tuesday = (now.weekday() - 1) % 7
    if days_since_tuesday == 0 and now.hour < 8:
        days_since_tuesday = 7
    last_tuesday = now - datetime.timedelta(days=days_since_tuesday)
    market_start = last_tuesday.replace(hour=8, minute=0, second=0, microsecond=0)
    base_ts = int(market_start.timestamp()) * 1000
    base_ts = base_ts - (base_ts % 60_000)  # Align to minute

    kwargs = dict(
        rng=rng,
        duration=duration_minutes,
        start_price=start_price,
        volatility=volatility,
        trend_strength=trend_strength,
        volume_base=volume_base,
        base_ts=base_ts,
    )

    if scenario == 'trending_down':
        kwargs['direction'] = -1
    elif scenario == 'trending_up':
        kwargs['direction'] = 1
    elif scenario == 'breakout_down':
        kwargs['direction'] = -1
    elif scenario == 'breakout_up':
        kwargs['direction'] = 1

    return gen_func(**kwargs)


def _make_candles(prices: np.ndarray, base_ts: int, volume_base: float, rng) -> np.ndarray:
    """Convert a price series into OHLCV candles with realistic wicks.

    Wicks extend beyond the body by a realistic amount: ~50% of body size
    with a minimum of ~1 pip (0.0001 * price). This ensures stop/limit orders
    trigger when price reaches the level intra-candle, not just on close.
    """
    n = len(prices) - 1
    candles = np.zeros((n, 6))
    for i in range(n):
        o = prices[i]
        c = prices[i + 1]
        body = abs(o - c)
        mid = (o + c) / 2
        # Realistic wick: ~50% of body size, minimum ~1 pip
        wick_scale = max(body * 0.5, mid * 0.0001)
        h = max(o, c) + abs(rng.normal(0, wick_scale))
        l = min(o, c) - abs(rng.normal(0, wick_scale))
        v = volume_base * (0.5 + rng.random())
        candles[i] = [base_ts + i * 60_000, o, c, h, l, v]
    return candles


def _trending(rng, duration, start_price, volatility, trend_strength, volume_base, base_ts, direction=1):
    drift = direction * trend_strength
    returns = rng.normal(drift, volatility, duration)
    prices = start_price * np.cumprod(1 + returns)
    prices = np.insert(prices, 0, start_price)
    return _make_candles(prices, base_ts, volume_base, rng)


def _ranging(rng, duration, start_price, volatility, volume_base, base_ts, **_):
    vol = volatility * 0.6
    returns = rng.normal(0, vol, duration)
    prices = start_price * np.cumprod(1 + returns)
    # Add mean reversion to keep it in range
    mean_price = start_price
    for i in range(1, len(prices)):
        revert = (mean_price - prices[i]) * 0.02
        prices[i] += revert
    prices = np.insert(prices, 0, start_price)
    return _make_candles(prices, base_ts, volume_base, rng)


def _volatile(rng, duration, start_price, volatility, volume_base, base_ts, **_):
    vol = volatility * 3.0
    returns = rng.normal(0, vol, duration)
    # Add occasional spikes
    spike_idx = rng.choice(duration, size=max(1, duration // 50), replace=False)
    returns[spike_idx] *= rng.uniform(3, 6, len(spike_idx)) * rng.choice([-1, 1], len(spike_idx))
    prices = start_price * np.cumprod(1 + returns)
    prices = np.insert(prices, 0, start_price)
    return _make_candles(prices, base_ts, volume_base * 1.5, rng)


def _flash_crash(rng, duration, start_price, volatility, volume_base, base_ts, **_):
    returns = rng.normal(0, volatility, duration)
    # Normal for first 60%, crash in middle 10%, recovery in remaining 30%
    crash_start = int(duration * 0.6)
    crash_end = int(duration * 0.7)
    recovery_end = int(duration * 0.85)

    # Crash phase: sharp decline
    crash_size = volatility * 40
    crash_returns = np.linspace(-crash_size, -crash_size * 0.3, crash_end - crash_start)
    crash_returns += rng.normal(0, volatility * 0.5, len(crash_returns))
    returns[crash_start:crash_end] = crash_returns

    # Recovery phase
    recovery_returns = np.linspace(crash_size * 0.5, volatility, recovery_end - crash_end)
    recovery_returns += rng.normal(0, volatility * 0.3, len(recovery_returns))
    returns[crash_end:recovery_end] = recovery_returns

    prices = start_price * np.cumprod(1 + returns)
    prices = np.insert(prices, 0, start_price)
    # Volume spikes during crash
    candles = _make_candles(prices, base_ts, volume_base, rng)
    candles[crash_start:crash_end, 5] *= rng.uniform(3, 8, crash_end - crash_start)
    return candles


def _flash_spike(rng, duration, start_price, volatility, volume_base, base_ts, **_):
    returns = rng.normal(0, volatility, duration)
    spike_start = int(duration * 0.6)
    spike_end = int(duration * 0.7)
    recovery_end = int(duration * 0.85)

    spike_size = volatility * 40
    spike_returns = np.linspace(spike_size, spike_size * 0.3, spike_end - spike_start)
    spike_returns += rng.normal(0, volatility * 0.5, len(spike_returns))
    returns[spike_start:spike_end] = spike_returns

    correction_returns = np.linspace(-spike_size * 0.5, -volatility, recovery_end - spike_end)
    correction_returns += rng.normal(0, volatility * 0.3, len(correction_returns))
    returns[spike_end:recovery_end] = correction_returns

    prices = start_price * np.cumprod(1 + returns)
    prices = np.insert(prices, 0, start_price)
    candles = _make_candles(prices, base_ts, volume_base, rng)
    candles[spike_start:spike_end, 5] *= rng.uniform(3, 8, spike_end - spike_start)
    return candles


def _breakout(rng, duration, start_price, volatility, volume_base, base_ts, direction=1, **_):
    returns = rng.normal(0, volatility * 0.4, duration)
    # Range-bound for first 70%
    range_end = int(duration * 0.7)
    mean_price = start_price
    prices_pre = [start_price]
    for i in range(range_end):
        new_p = prices_pre[-1] * (1 + returns[i])
        revert = (mean_price - new_p) * 0.03
        new_p += revert
        prices_pre.append(new_p)

    # Breakout phase with increasing momentum
    breakout_returns = rng.normal(direction * volatility * 2, volatility * 1.5, duration - range_end)
    # Accelerating breakout
    momentum = np.linspace(1, 3, len(breakout_returns))
    breakout_returns *= momentum
    returns[range_end:] = breakout_returns

    prices_post = [prices_pre[-1]]
    for r in breakout_returns:
        prices_post.append(prices_post[-1] * (1 + r))

    prices = np.array(prices_pre + prices_post[1:])
    candles = _make_candles(prices, base_ts, volume_base, rng)
    # Volume surge on breakout
    candles[range_end:, 5] *= rng.uniform(1.5, 4, duration - range_end)
    return candles


def _mean_revert(rng, duration, start_price, volatility, volume_base, base_ts, **_):
    """Price oscillates around start_price with strong mean reversion."""
    prices = [start_price]
    for _ in range(duration):
        shock = rng.normal(0, volatility * 1.5)
        revert = (start_price - prices[-1]) * 0.05
        prices.append(prices[-1] * (1 + shock + revert / start_price))
    prices = np.array(prices)
    return _make_candles(prices, base_ts, volume_base, rng)


def _choppy(rng, duration, start_price, volatility, volume_base, base_ts, **_):
    """Alternating micro-trends with frequent reversals."""
    prices = [start_price]
    segment_len = max(10, duration // 20)
    direction = 1
    for i in range(duration):
        if i % segment_len == 0:
            direction *= -1
        drift = direction * volatility * 0.8
        shock = rng.normal(drift, volatility * 1.2)
        prices.append(prices[-1] * (1 + shock))
    prices = np.array(prices)
    return _make_candles(prices, base_ts, volume_base, rng)


def _custom(rng, duration, start_price, volatility, trend_strength, volume_base, base_ts, **_):
    """Uses the user-provided volatility and trend_strength directly."""
    returns = rng.normal(trend_strength, volatility, duration)
    prices = start_price * np.cumprod(1 + returns)
    prices = np.insert(prices, 0, start_price)
    return _make_candles(prices, base_ts, volume_base, rng)


# ─── Available scenarios for the frontend dropdown ───
SCENARIOS = [
    {'id': 'trending_up', 'name': 'Trending Up', 'description': 'Steady upward trend with moderate pullbacks'},
    {'id': 'trending_down', 'name': 'Trending Down', 'description': 'Steady downward trend with moderate bounces'},
    {'id': 'ranging', 'name': 'Ranging / Sideways', 'description': 'Price oscillates in a tight range'},
    {'id': 'volatile', 'name': 'High Volatility', 'description': 'Large price swings with occasional spikes'},
    {'id': 'flash_crash', 'name': 'Flash Crash', 'description': 'Normal market then sudden crash and partial recovery'},
    {'id': 'flash_spike', 'name': 'Flash Spike', 'description': 'Normal market then sudden spike and correction'},
    {'id': 'breakout_up', 'name': 'Breakout Up', 'description': 'Consolidation followed by strong upward breakout'},
    {'id': 'breakout_down', 'name': 'Breakout Down', 'description': 'Consolidation followed by strong downward breakout'},
    {'id': 'mean_revert', 'name': 'Mean Reverting', 'description': 'Price consistently reverts to a central value'},
    {'id': 'choppy', 'name': 'Choppy', 'description': 'Frequent direction changes, whipsaw conditions'},
    {'id': 'custom', 'name': 'Custom', 'description': 'Set your own volatility and trend parameters'},
]
