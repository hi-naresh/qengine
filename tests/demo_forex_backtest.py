#!/usr/bin/env python
"""
TradeEngine v2.0 Demo - Forex Backtest
Run this without PostgreSQL/Redis to see forex features in action.

Usage:
    python demo_forex_backtest.py
"""
import os
import sys

# Enable unit testing mode so strategies resolve from qengine.strategies.*
os.environ['PYTEST_CURRENT_TEST'] = 'demo'
# Force sys.path[0] to project root BEFORE any imports (ray overwrites sys.path[0])
_project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _project_root)
sys.path[0] = _project_root

import numpy as np
from qengine.config import config, reset_config
from qengine.enums import timeframes, brokers
from qengine.routes import router
from qengine.store import store
from qengine.services import exchange_service, order_service, position_service
from qengine.factories import range_candles
import qengine.helpers as jh


def main():
    print("=" * 60)
    print("  TradeEngine v2.0 - Forex Backtest Demo")
    print("=" * 60)

    # ── Step 1: Show broker info ──
    from qengine.info import broker_info
    print("\n--- Available Brokers ---")
    for key, info in broker_info.items():
        mode_str = []
        if info['modes'].get('backtesting'):
            mode_str.append('backtest')
        if info['modes'].get('live_trading'):
            mode_str.append('live')
        if info['modes'].get('paper_trading'):
            mode_str.append('paper')
        print(f"  {key:30s} | type={info['type']:12s} | modes={', '.join(mode_str)}")

    # ── Step 2: Show instrument registry ──
    from qengine.core.instruments import instrument_registry
    print("\n--- Registered Instruments ---")
    print(f"  {'Symbol':<10} | {'Pip Size':<10} | {'Contract':<12} | {'Class':<10} | {'Margin Rate'}")
    print(f"  {'-'*10} | {'-'*10} | {'-'*12} | {'-'*10} | {'-'*12}")
    for sym in ['EUR-USD', 'GBP-USD', 'USD-JPY', 'GBP-JPY', 'AUD-USD',
                'USD-CHF', 'NZD-USD', 'USD-CAD', 'XAU-USD', 'XAG-USD']:
        inst = instrument_registry.get(sym)
        if inst:
            print(f"  {sym:<10} | {inst.pip_size:<10} | {inst.contract_size:<12} | {inst.asset_class:<10} | {inst.margin_rate}")

    # ── Step 3: Show market hours / sessions ──
    from qengine.core.market_hours import market_hours
    now_ms = jh.now(force_fresh=True)
    session = market_hours.current_session(now_ms)
    is_open = market_hours.is_market_open('EUR-USD', now_ms)
    mins = market_hours.minutes_to_close('EUR-USD', now_ms)
    print(f"\n--- Current Market Status ---")
    print(f"  Session:           {session}")
    print(f"  EUR-USD open:      {is_open}")
    if mins is not None:
        print(f"  Minutes to close:  {mins}")

    # ── Step 4: Pip value calculations ──
    print("\n--- Pip Value per Standard Lot ---")
    for sym in ['EUR-USD', 'GBP-USD', 'USD-JPY', 'XAU-USD', 'XAG-USD']:
        pip = instrument_registry.get_pip_size(sym)
        cs = instrument_registry.get_contract_size(sym)
        pv = pip * cs
        unit = 'JPY' if 'JPY' in sym else 'USD'
        print(f"  {sym:<10} | pip_size={pip:<8} | pip_value={pv:>10.2f} {unit}")

    # ── Step 5: ForexCFD exchange model ──
    print("\n--- ForexCFD Exchange Model ---")
    # Fix sys.path[0] after ray (imported transitively) overwrites it
    sys.path[0] = os.path.dirname(os.path.abspath(__file__))
    reset_config()
    exchange_name = brokers.OANDA
    config['env']['exchanges'][exchange_name] = {
        'fee': 0,
        'type': 'cfd',
        'futures_leverage_mode': 'cross',
        'futures_leverage': 30,
        'balance': 10_000,
    }
    config['app']['trading_mode'] = 'backtest'

    routes = [{'symbol': 'EUR-USD', 'timeframe': timeframes.MINUTE_5, 'strategy': 'ForexMA'}]
    for r in routes:
        r['exchange'] = exchange_name

    router.initiate(routes, [])
    store.reset()
    store.app.set_session_id('demo-001')
    store.candles.init_storage(5000)
    exchange_service.initialize_exchanges_state()
    order_service.initialize_orders_state()
    position_service.initialize_positions_state()

    ex = store.exchanges.get_exchange(exchange_name)
    print(f"  Exchange:      {ex.name}")
    print(f"  Type:          {ex.type}")
    print(f"  Balance:       ${ex.wallet_balance:,.2f}")
    print(f"  Leverage:      {ex.default_leverage}x")
    print(f"  Spread (EUR-USD): {ex.get_spread('EUR-USD')} price units")
    spread = ex.get_spread('EUR-USD')
    cs = instrument_registry.get_contract_size('EUR-USD')
    print(f"  Spread cost (1 lot): ${spread * cs * 1.0:.2f}")

    # ── Step 6: Run a mini backtest ──
    print("\n--- Running Mini Backtest ---")
    sys.path[0] = _project_root  # ensure ray hasn't overwritten it
    key = jh.key(exchange_name, 'EUR-USD')
    candles = {
        key: {
            'exchange': exchange_name,
            'symbol': 'EUR-USD',
            'candles': range_candles(5 * 100),
        }
    }

    reset_config()
    config['env']['exchanges'][exchange_name] = {
        'fee': 0,
        'type': 'cfd',
        'futures_leverage_mode': 'cross',
        'futures_leverage': 30,
        'balance': 10_000,
    }
    config['app']['trading_mode'] = 'backtest'

    try:
        from qengine.modes import backtest_mode
        backtest_mode.run(
            'demo-001', False, {}, exchange_name,
            [{'symbol': 'EUR-USD', 'timeframe': timeframes.MINUTE_5, 'strategy': 'ForexMA'}],
            [], '2024-01-01', '2024-01-02', candles
        )

        p = store.positions.get_position(exchange_name, 'EUR-USD')
        ex = store.exchanges.get_exchange(exchange_name)
        print(f"  Strategy:      ForexMA (SMA crossover + session filter)")
        print(f"  Symbol:        EUR-USD")
        print(f"  Timeframe:     5m")
        print(f"  Bars:          100")
        print(f"  Position:      {'Open' if p.is_open else 'Closed'}")
        print(f"  Final balance: ${ex.wallet_balance:,.2f}")
        print(f"  Backtest completed successfully!")
    except Exception as e:
        print(f"  Note: {e}")
        print(f"  (Expected with synthetic candles - strategy may not generate signals)")

    # ── Step 7: Live driver registry ──
    print("\n--- Live Trading Drivers ---")
    from qengine.live_drivers import live_drivers
    for name, cls in live_drivers.items():
        d = cls()
        print(f"  {name:30s} | demo={str(d.is_demo):<5} | methods: market_order, limit_order, stop_order, stream, account")

    # ── Step 8: LLM engine ──
    print("\n--- LLM Strategy Engine ---")
    from qengine.services.llm_engine import llm_engine
    print(f"  Configured:    {llm_engine.is_configured}")
    print(f"  Provider:      {llm_engine.provider or 'not set (set GEMINI_API_KEY env var)'}")
    print(f"  Supported:     gemini (default), anthropic, openai")

    sample_code = '''
from qengine.strategies import Strategy
import qengine.indicators as ta

class DemoStrategy(Strategy):
    def should_long(self):
        return ta.rsi(self.candles, 14) < 30
    def go_long(self):
        qty = self.lot_size_for_risk(1.0, 50)
        self.buy = qty, self.price
        self.stop_loss = qty, self.price - self.pips_to_price(50)
        self.take_profit = qty, self.price + self.pips_to_price(100)
    def should_short(self):
        return ta.rsi(self.candles, 14) > 70
    def go_short(self):
        qty = self.lot_size_for_risk(1.0, 50)
        self.sell = qty, self.price
        self.stop_loss = qty, self.price + self.pips_to_price(50)
        self.take_profit = qty, self.price - self.pips_to_price(100)
    def should_cancel_entry(self):
        return False
'''
    result = llm_engine.validate_strategy(sample_code)
    print(f"  Code validation: {'PASS' if result['valid'] else 'FAIL'}")

    # ── Step 9: Example strategies ──
    print("\n--- Included Example Strategies ---")
    from qengine.strategies.ForexMA import ForexMA
    from qengine.strategies.ForexRSIReversal import ForexRSIReversal
    from qengine.strategies.GoldBreakout import GoldBreakout

    for cls, desc in [
        (ForexMA, 'EUR-USD SMA crossover with London/NY session filter'),
        (ForexRSIReversal, 'GBP-JPY RSI reversal with pip-based risk'),
        (GoldBreakout, 'XAU-USD Donchian breakout with ATR stops'),
    ]:
        s = cls()
        hp = s.hyperparameters()
        params = ', '.join(h['name'] for h in hp)
        print(f"  {cls.__name__:<20} | {desc}")
        print(f"  {'':20} | params: {params}")

    # ── Step 10: New REST API endpoints ──
    print("\n--- New REST API Endpoints ---")
    endpoints = [
        ('GET', '/broker/list', 'All available brokers'),
        ('GET', '/broker/backtesting', 'Backtesting-enabled brokers'),
        ('GET', '/broker/live-trading', 'Live trading brokers'),
        ('GET', '/broker/info/{id}', 'Broker details'),
        ('GET', '/broker/asset-classes', 'Supported asset classes'),
        ('GET', '/market-data/session', 'Current forex session'),
        ('GET', '/market-data/market-hours/{symbol}', 'Market open/close status'),
        ('GET', '/market-data/instrument/{symbol}', 'Instrument metadata'),
        ('GET', '/market-data/instruments', 'List all instruments'),
        ('GET', '/market-data/pip-value/{symbol}', 'Pip value calculator'),
        ('*',   '/settings/brokers', 'Broker credentials CRUD'),
        ('*',   '/settings/llm', 'LLM configuration CRUD'),
        ('POST', '/llm/generate', 'Generate strategy from description'),
        ('POST', '/llm/refine', 'Refine strategy with feedback'),
        ('POST', '/llm/validate', 'Validate strategy code'),
        ('POST', '/llm/configure', 'Configure LLM provider'),
        ('GET',  '/llm/status', 'LLM config status'),
    ]
    for method, path, desc in endpoints:
        print(f"  {method:<5} {path:<40} {desc}")

    print("\n" + "=" * 60)
    print("  Demo complete!")
    print("  See QUICKSTART.md for full API examples with curl.")
    print("  Run tests: python -m pytest tests/test_phase*.py -v")
    print("=" * 60)


if __name__ == '__main__':
    main()
