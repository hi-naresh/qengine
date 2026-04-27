# QEngine Backtester — Comparison with Industry Tools

This document provides an honest technical comparison of QEngine against widely-used backtesting platforms. It is intended as a reference for dissertation defense and methodology justification.

## Background

QEngine is a fork of [Jesse](https://github.com/jesse-ai/jesse), a mature open-source Python algorithmic trading framework. It has been extended for forex/CFD research with the following major additions:

- CFD hedging mode with per-trade TP/SL (independent tickets)
- OANDA v20 API live trading driver
- IG Markets REST + Lightstreamer live trading driver
- Weekend gap slippage modeling
- Martingale-specific analytical metrics (Wilson-Banzhaf index, analytical ruin probability)
- User/role system with JWT auth, data isolation, and quotas

Building a production-grade backtester from scratch is genuinely one of the hardest problems in quantitative finance. Hidden bugs in execution logic (look-ahead bias, unrealistic fills, survivorship bias) silently invalidate research results. For this reason, serious quantitative research projects almost universally fork or build on top of existing frameworks rather than start from zero. QEngine follows this standard approach.

## Feature Comparison Matrix

| Feature | QEngine | MetaTrader 5 | TradeStation | Backtrader | Zipline | QuantConnect |
|---|---|---|---|---|---|---|
| **Execution Realism** | | | | | | |
| Intrabar OHLC walk fills | Yes (`backtest_mode.py:1174`) | No (close-only) | Yes | No | No | Yes |
| Weekend gap slippage | Yes (`_apply_gap_execution_prices`) | No | No | No | No | No |
| Spread-as-fill-shift (correct model) | Yes (`order_service.py:104`) | Partial | Partial | Minimal | No | Yes |
| Partial fills | Yes (`execute_order_partially`) | Yes | Yes | Limited | No | Yes |
| Order-priority within a bar | Yes (open-to-close direction heuristic) | No | Yes | No | No | Yes |
| Stop-order gap slippage | Yes (explicit) | No | No | No | No | No |
| Explicit latency model | No (implicit, bar-end fills) | No | No | No | No | No |
| **Position & Risk Modeling** | | | | | | |
| Netting mode | Yes | Yes | Yes | Yes | Yes | Yes |
| Hedging mode (independent tickets) | Yes (`CFDTicket`) | Yes (live only) | Yes | No | No | No |
| Per-trade TP/SL | Yes | Live only | Yes | No | No | No |
| Margin / leverage | Yes (`margin_rate`, `CFDExchange.py:66`) | Yes | Yes | Limited | No | Yes |
| Margin call / stop-out simulation | Yes (50% level) | Yes | Yes | No | No | Partial |
| Overnight swap charges | Yes (rollover 5pm NY) | Yes | Yes | No | No | Partial |
| **Backtest ↔ Live Parity** | | | | | | |
| Same strategy code backtest + live | Yes (OANDA + IG) | No (MQL differs from tester) | Yes | No | No | Yes |
| Number of supported live brokers | 2 (OANDA, IG) | 100+ | 1 | 0 | 0 | Many |
| Streaming price feed integration | Yes (Lightstreamer, OANDA stream) | Yes | Yes | No | No | Yes |
| **Data & Instruments** | | | | | | |
| Tick data support | No (1m min) | Yes | Yes | Yes | No | Yes |
| Multi-timeframe resampling | Yes (`candle_service.generate_candle_from_one_minutes`) | Yes | Yes | Yes | Yes | Yes |
| Warmup candle isolation | Yes | Yes | Yes | Yes | Yes | Yes |
| Depth-of-book / L2 data | No | Partial | Yes | No | No | Yes |
| **Metrics & Analytics** | | | | | | |
| Standard metrics (Sharpe, Sortino, etc.) | Yes | Yes | Yes | Yes | Yes | Yes |
| Drawdown, Calmar, Ulcer, Serenity | Yes | Partial | Partial | Yes | Yes | Yes |
| Wilson-Banzhaf martingale index | Yes (`metrics.py:509`) | No | No | No | No | No |
| Analytical ruin probability | Yes (`metrics.py:821`) | No | No | No | No | No |
| Depth-barrier auto-detection | Yes | No | No | No | No | No |
| Markov transition matrix | Yes | No | No | No | No | No |
| d'Alembert / null-hypothesis baseline | Yes | No | No | No | No | No |
| **Quality & Validation** | | | | | | |
| Execution test suite | 81 test files | Closed source | Closed | Sparse | Yes | Yes |
| Determinism test | Yes (`test_backtest_determinism.py`) | No | No | No | Yes | Yes |
| PnL truth test | Yes (`test_pnl_truth.py`) | No | No | No | Yes | Yes |
| Open source | Yes | No | No | Yes | Yes | Partial |
| **Extensibility** | | | | | | |
| Custom indicators | Yes (170+, Rust backend) | Yes | Yes | Yes | Limited | Yes |
| Monte Carlo / scenario mode | Yes (`monte_carlo_mode/`) | No | Limited | No | No | Yes |
| Candle pipelines (noise injection) | Yes | No | No | No | No | Partial |
| Multi-user / role system | Yes (JWT, quotas) | No | No | No | No | Yes |

## Unique Contributions (Not Found in Other Platforms)

These features distinguish QEngine from all surveyed platforms and represent genuine research contributions:

1. **Wilson-Banzhaf martingale collapse index** (`metrics.py:509-872`): Covariance-based detector for martingale-style strategies, derived from Dimitrov & Shafer (2025). Used to rank strategies by risk of catastrophic drawdown.
2. **Analytical ruin probability** (`metrics.py:821-868`): Closed-form ruin probability and survival half-life for bust-prone strategies.
3. **Depth-barrier auto-detection**: Identifies the escalation depth at which session win rate collapses below 70%.
4. **Explicit weekend gap execution model** (`_apply_gap_execution_prices`, lines 1081-1108): Stop orders that gap past candle open execute at open price, with `_pre_gap_price` tracking. Rare in any backtester.
5. **CFD per-trade ticket system with live parity**: Each buy/sell creates an independent `CFDTicket` with its own TP/SL, mirrored exactly on OANDA and IG Markets live drivers.

## Summary Assessment

| Dimension | QEngine Rating | Notes |
|---|---|---|
| Execution realism | 7/10 | Strong intrabar fills, gap slippage, spread model; lacks tick data and DOM |
| Position/risk modeling | 8/10 | CFD tickets + margin call sim is better than Backtrader/Zipline |
| Live trading parity | 7/10 | Excellent on OANDA/IG but narrow broker ecosystem |
| Metrics | 9/10 | Standard metrics plus novel martingale analytics |
| Test coverage | 7/10 | 81 test files including determinism and PnL truth |
| Documentation | 6/10 | Code is self-documenting; formal API docs sparse |
| **Overall** | **6–7/10** | Research-grade; stronger than Backtrader/Zipline, weaker than institutional tools on tick data |

## Positioning Statement

> QEngine is a research-grade backtester built on the Jesse framework, extended with forex/CFD execution realism (per-trade TP/SL, weekend gap slippage, spread-as-fill-shift), full backtest-to-live parity on OANDA and IG Markets, and novel martingale-collapse analytics. It is not intended to replace institutional tools such as Bloomberg BQuant or Kinetick for tick-level or high-frequency research, but it compares favorably with open-source alternatives (Backtrader, Zipline) and is sufficient for rigorous PhD-level methodology in forex/CFD strategy research.

## References

- Jesse framework: https://github.com/jesse-ai/jesse
- Core execution logic: `/qengine/modes/backtest_mode.py` (2161 lines)
- Order matching: `/qengine/services/order_service.py` (331 lines)
- CFD model: `/qengine/models/CFDExchange.py` (316 lines) + `/qengine/models/Position.py` (390 lines)
- Metrics suite: `/qengine/services/metrics.py` (1345 lines)
- Live drivers: `/qengine/live_drivers/OANDA/OandaDriver.py`, `/qengine/live_drivers/IG/IGMarketsDriver.py`
- Test suite: `/tests/` (81 files)
