# QEngine Backtester — Known Weaknesses and Limitations

This document catalogs known weaknesses, limitations, and gaps in the QEngine backtester. It exists to support honest methodology reporting in research output and to guide future engineering work. Each weakness is rated by severity and scoped to research impact where relevant.

## Severity Legend

- **High**: Can materially bias backtest results or invalidate live-trading claims.
- **Medium**: Creates unrealistic conditions that may overstate strategy edge but are commonly accepted in research.
- **Low**: Minor realism gap; unlikely to affect research conclusions.

---

## 1. Execution Realism Weaknesses

### 1.1 Bar-level granularity (no tick data)
- **Severity**: Medium
- **Description**: QEngine operates at 1-minute candle minimum. Real markets quote at tick level (often sub-millisecond updates).
- **Impact**: Intrabar fills are approximated via OHLC walk rather than exact tick sequence. Orders triggering inside a 1-minute window cannot be ordered exactly in time.
- **Mitigation**: Order-priority heuristic (open-to-close direction) provides reasonable approximation. For martingale and multi-minute strategies this is acceptable; for HFT or scalping strategies it is inadequate.
- **Where**: `backtest_mode.py:651-763`, `split_candle()`, `candle_includes_price()`.

### 1.2 No explicit latency model
- **Severity**: Medium
- **Description**: Orders are assumed to fill at the end of the candle in which they are triggered (`store.app.time = first_candles_set[i][0] + 60_000`).
- **Impact**: Real live trading has 50–500 ms network latency plus broker processing. Strategies sensitive to microstructure (arbitrage, high-frequency entries) will overperform in backtest.
- **Mitigation**: None currently. Users should pad signals with conservative entry thresholds.
- **Where**: `backtest_mode.py:653`.

### 1.3 No depth-of-book / liquidity modeling
- **Severity**: Medium (High for large-size strategies)
- **Description**: Backtester assumes infinite liquidity at the trigger price. Large orders will always fill at the modeled price.
- **Impact**: In real markets, large orders may walk the book, receive partial fills, or be rejected. Strategies that assume clean entries/exits at large sizes will understate real slippage.
- **Mitigation**: Partial-fill infrastructure exists (`execute_order_partially`) but is not automatically invoked based on size. Users must manually model size-dependent fills.
- **Where**: `order_service.py:148-176`.

### 1.4 Exit orders do not apply entry slippage
- **Severity**: Low
- **Description**: Slippage is applied to entry orders but not explicitly to TP/SL exits. Exit fills occur at the trigger price; spread cost is captured naturally in final PnL.
- **Impact**: Exit execution is slightly more optimistic than entry execution. The PnL accounting is correct on average because spread is already baked into entry fills.
- **Mitigation**: Acceptable given the spread-as-fill-shift model. Document clearly in strategy reports.
- **Where**: `CFDExchange.py:113-124`, `backtest_mode.py:1111-1172`.

### 1.5 Limit order queue position not modeled
- **Severity**: Low
- **Description**: Limit orders fill whenever price crosses the limit. No modeling of queue position, cancellation-replacement priority, or partial-fill probability at the touch.
- **Impact**: Limit-order strategies overestimate fill rates. In real markets, many limit orders at the best bid/offer never fill because of queue position.
- **Mitigation**: None. Strategies relying heavily on passive limit fills should be validated against live paper-trading data.

---

## 2. Data Pipeline Weaknesses

### 2.1 Survivorship bias not tracked
- **Severity**: Medium (mostly relevant for equities, low for forex/CFD)
- **Description**: Delisted, acquired, or bankrupt symbols are not automatically included in historical data. For forex pairs this is not an issue (major pairs persist); for equities research it would be significant.
- **Impact**: Strategies tested on current-universe tickers overstate returns.
- **Mitigation**: Current research focus is EUR-USD forex, so this does not affect dissertation results. Document as a limitation if extending to equities.

### 2.2 Single-source data (OANDA EUR-USD only)
- **Severity**: Low
- **Description**: Primary dataset is OANDA EUR-USD 1m/5m from 2006-01-02 to 2025-12-30. No cross-validation against other data vendors (Dukascopy, TrueFX, Refinitiv).
- **Impact**: Any OANDA-specific data artifacts (e.g., quote timing, spread handling) cannot be detected.
- **Mitigation**: Cross-validate key findings against a secondary source before final publication.

### 2.3 No volume calibration
- **Severity**: Low
- **Description**: Forex tick volume from OANDA is tick count, not actual traded volume. Volume-based indicators (OBV, VWAP) are therefore approximations.
- **Impact**: Any strategy using volume as a primary signal has a weak foundation.
- **Mitigation**: Avoid volume-based signals in forex; use price-action and volatility-based indicators.

---

## 3. Model and Analytics Weaknesses

### 3.1 Commission model is simplified
- **Severity**: Low
- **Description**: Per-instrument fixed commission plus a configurable fee rate. Does not model tiered commission structures, volume rebates, or broker-specific fee schedules.
- **Impact**: Per-trade cost may differ slightly from a specific broker. For OANDA (spread-only, no commission) this is accurate.
- **Where**: `order_service.py:68-70`, `CFDExchange.py:129-150`.

### 3.2 Overnight swap is a flat daily charge
- **Severity**: Low
- **Description**: Swap is charged at a flat rate at 5pm NY rollover. Does not model triple-swap Wednesdays, broker-specific swap curves, or variable swap by direction.
- **Impact**: Long-hold strategies may slightly misestimate carry cost.
- **Where**: `backtest_mode.py:656-668`.

### 3.3 No slippage for partial fills
- **Severity**: Low
- **Description**: Partial fills occur at a single fill price; no modeling of walking through liquidity levels.
- **Impact**: Large partial-fill scenarios are optimistic.

### 3.4 Statistical metrics assume i.i.d. returns
- **Severity**: Medium
- **Description**: Sharpe, Sortino, and related metrics assume independent, identically distributed returns. Trading returns exhibit autocorrelation, volatility clustering, and fat tails.
- **Impact**: Reported Sharpe ratios are likely biased upward for strategies with serial correlation.
- **Mitigation**: Complementary metrics included (Ulcer Index, Serenity Index, bootstrap confidence intervals in some notebooks). Use bootstrapped or block-resampled metrics for publication.

---

## 4. Live-Trading Integration Weaknesses

### 4.1 CFD tickets are in-memory only
- **Severity**: High (for live trading robustness)
- **Description**: CFDTicket objects live in Python process memory. No persistence layer, no crash recovery, no broker-side sync.
- **Impact**: If the live-trading process crashes or restarts, ticket state is lost. OANDA trade IDs are tracked but reconstruction logic is partial.
- **Mitigation**: Documented in `docs/issues/TODO.md`. Workaround: do not restart live-trading process during an open session.
- **Where**: `Position.py` `_tickets`.

### 4.2 Narrow broker ecosystem
- **Severity**: Medium
- **Description**: Two live drivers (OANDA, IG Markets). MetaTrader supports 100+ brokers; Interactive Brokers via TWS API would extend reach significantly but is not implemented.
- **Impact**: Users must trade with OANDA or IG. No cross-broker arbitrage.

### 4.3 Rate-limit handling is reactive
- **Severity**: Low
- **Description**: IG Markets rate-limit (60 req/min on demo) is handled via post-hoc error recovery rather than proactive throttling.
- **Impact**: Occasional 403 responses under high-frequency order flow. Not a research-result concern.
- **Where**: `IGMarketsDriver.py`.

### 4.4 No order-book staleness detection
- **Severity**: Medium
- **Description**: Lightstreamer price feed can lag during high volatility. No explicit staleness check before submitting orders.
- **Impact**: Orders may be submitted against stale prices during fast markets, leading to rejection or unexpected fills.
- **Mitigation**: Users should monitor live trading during high-impact news.

---

## 5. Architecture and Code Quality Weaknesses

### 5.1 Formal API documentation sparse
- **Severity**: Low
- **Description**: Inline docstrings exist but no Sphinx/autodoc-generated API reference. Strategy-author tutorial documentation is incomplete.
- **Impact**: Slows onboarding for new users. Does not affect research validity.
- **Mitigation**: `docs/ARCHITECTURE.md` and `docs/STRATEGY.md` cover basics.

### 5.2 Some test coverage is integration-level, not unit-level
- **Severity**: Low
- **Description**: 81 test files exist, but some areas (metrics edge cases, pipeline components) rely on end-to-end integration tests rather than fast unit tests.
- **Impact**: Test suite runs slowly; harder to isolate regressions.

### 5.3 Frontend and backend versioning not strictly coupled
- **Severity**: Low
- **Description**: `frontend/` (Vue dashboard) and Python backend are versioned together but no API schema contract is enforced.
- **Impact**: Frontend regressions can occur silently when backend endpoints change.

### 5.4 Research notebooks are not all reproducible
- **Severity**: Low
- **Description**: Some notebooks in `notebooks/` hard-code date ranges or parameters. Not all produce deterministic outputs.
- **Impact**: Replicating older research requires care.
- **Mitigation**: Core pipeline (`phase2/run_pipeline.py`, `phase4/`) is reproducible. Ad-hoc exploration notebooks are not guaranteed.

---

## 6. Research-Context Weaknesses

### 6.1 Single-asset focus
- **Severity**: Medium
- **Description**: Research primarily validated on EUR-USD. Multi-instrument results are preliminary.
- **Impact**: Findings may not generalize to other currency pairs, equities, or crypto.
- **Mitigation**: Planned next phase: multi-instrument diversification testing.

### 6.2 Spread assumption fixed at 2 pips
- **Severity**: Medium
- **Description**: OANDA EUR-USD spread is modeled at a fixed 2 pips. Real spreads vary by session (tighter in London/NY overlap, wider in Asia).
- **Impact**: Strategies that concentrate entries in low-liquidity sessions will be modeled as more profitable than reality.
- **Mitigation**: Session-aware spread modeling is a future improvement.

### 6.3 Martingale-specific metrics may be over-fit to this research
- **Severity**: Low (scope issue, not a bug)
- **Description**: Wilson-Banzhaf index, analytical ruin, and depth-barrier detection are designed for the martingale research context. Their general applicability to other strategy classes is untested.
- **Mitigation**: Clearly scope these metrics to martingale strategies in documentation.

---

## Summary Table

| Category | High | Medium | Low | Total |
|---|---|---|---|---|
| Execution realism | 0 | 3 | 2 | 5 |
| Data pipeline | 0 | 1 | 2 | 3 |
| Model/analytics | 0 | 1 | 3 | 4 |
| Live trading | 1 | 2 | 1 | 4 |
| Code quality | 0 | 0 | 4 | 4 |
| Research context | 0 | 2 | 1 | 3 |
| **Total** | **1** | **9** | **13** | **23** |

## Recommended Disclosures for Publication

For dissertation or peer-reviewed submission, the following weaknesses must be acknowledged in the methodology section:

1. 1-minute bar granularity (no tick data) — §1.1
2. Implicit latency model — §1.2
3. Infinite-liquidity assumption — §1.3
4. OANDA-only data source — §2.2
5. Fixed 2-pip EUR-USD spread assumption — §6.2
6. i.i.d. return assumption in Sharpe/Sortino — §3.4
7. Single-asset validation — §6.1

These disclosures protect research credibility and pre-empt reviewer objections.
