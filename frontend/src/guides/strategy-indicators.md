## _section_guide
Import indicators with: import qengine.indicators as ta

All indicators take candles as the first argument. By default they return a scalar (latest value). Pass sequential=True to get the full array for all candles.

## categories
- Moving Averages | sma, ema, dema, tema, wma, vwma, kama, alma, jma, t3
- Momentum | rsi, macd, mom, apo, ppo, kst, tsi, stochastic, cci, rvi, williams
- Volatility | atr, natr, stddev, bollinger_bands, keltner, donchian
- Trend | adx, aroon, supertrend, ichimoku_cloud, trendline
- Volume | obv, adosc, mfi, kvo, vwap
- Utility | highestprice, lowestprice, correl, beta, heikin_ashi_candles

## usage_examples
```python
ta.ema(self.candles, 21)                    # scalar (latest value)
ta.ema(self.candles, 21, sequential=True)   # full array
ta.rsi(self.candles, 14)                    # RSI scalar
ta.atr(self.candles, 14)                    # ATR scalar
ta.macd(self.candles, 12, 26, 9)            # returns (macd, signal, hist)
ta.bollinger_bands(self.candles, 20)        # returns (upper, middle, lower)
ta.supertrend(self.candles, 10, 3.0)        # returns (trend, direction)
```
