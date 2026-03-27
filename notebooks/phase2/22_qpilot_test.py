#!/usr/bin/env python3
"""
Quick test: Run AutoPilot orchestrator in backtest mode.
Uses 2024-2025 with 90-day sessions (~7 sessions).

Bypasses full qengine.__init__ (which needs Redis + all controllers)
by stubbing Redis before importing.
"""
import os
import sys
import types

os.chdir('/Users/naresh/Documents/Research/qengine')
sys.path.insert(0, '.')

# ── Stub out Redis before any qengine imports ──
fake_redis_mod = types.ModuleType('qengine.services.redis')
fake_redis_mod.sync_publish = None
fake_redis_mod.sync_redis = None
fake_redis_mod.async_redis = None
fake_redis_mod.is_process_active = lambda x: True
sys.modules['qengine.services.redis'] = fake_redis_mod

fake_aioredis = types.ModuleType('aioredis')
sys.modules.setdefault('aioredis', fake_aioredis)

# Prevent qengine.__init__ from running (it imports all controllers)
fake_qengine = types.ModuleType('qengine')
fake_qengine.__path__ = [os.path.join(os.getcwd(), 'qengine')]
fake_qengine.__package__ = 'qengine'
sys.modules['qengine'] = fake_qengine

# Import the submodules we need
import qengine.helpers as jh
import qengine.config
import qengine.services
import qengine.services.logger

# Import autopilot
from qengine.autopilot import run

run(
    client_id='test-autopilot-001',
    debug_mode=False,
    user_config={
        'starting_balance': 10_000,
        'fee': 0,
        'type': 'cfd',
        'exchange': 'OANDA',
        'warm_up_candles': 500,
    },
    exchange='OANDA',
    routes=[{'exchange': 'OANDA', 'strategy': 'SurefirePilot', 'symbol': 'EUR-USD', 'timeframe': '5m'}],
    data_routes=[
        {'exchange': 'OANDA', 'symbol': 'EUR-USD', 'timeframe': '15m'},
        {'exchange': 'OANDA', 'symbol': 'EUR-USD', 'timeframe': '1h'},
        {'exchange': 'OANDA', 'symbol': 'EUR-USD', 'timeframe': '1D'},
    ],
    start_date='2024-01-01',
    finish_date='2025-06-30',
    execution_backend='backtest',
    session_duration_days=90,
    hyperparameters={
        'signal_mode': 'ema',
        'session_filter': 'london_ny',
        'pilot_enable_danger': True,
        'pilot_enable_gate': True,
        'pilot_enable_abort': True,
    },
)
