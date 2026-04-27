#!/usr/bin/env python3
"""Pivot 06 evidence: a no-cost surrogate simulator and the full qengine
production engine return materially different fitness for the same genome.

Picks a representative canonical genome and evaluates it under both. The
surrogate ignores spread, swap, and margin — it produces the wrong sign of
the conclusion (positive total_pnl) where the engine produces the right sign
(negative). Genomes evolved on the surrogate optimise toward extreme HPs
that the engine refuses.

Reproducibility note: this is illustrative. Phase-4 evidence ran a full
GA on a 120-line simulator and found it produced unreproducible genomes
(notebooks/phase4/ — deleted). This script demonstrates the qualitative gap
on a single genome.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, ROOT)

# Import shared utils via path injection (10_pipeline_design has digit prefix)
sys.path.insert(0, os.path.join(HERE, '..', 'shared'))
import utils as pipeline_utils
from notebooks.shared.utils import CANONICAL_HP

# Surrogate: assumes anatomy-style win rate (97.4%), ignores cost
SURROGATE = pipeline_utils.simulator_fitness(
    spread_pips=0.0, n_levels=6, sf=2.0, win_rate=0.974, n_cycles=5000, seed=0,
)
print('Surrogate (no spread, IID Bernoulli):')
for k, v in SURROGATE.items():
    print(f'  {k}: {v}')

# Real engine: full qengine, real per-candle OANDA spread
print('\nRunning full engine fitness on canonical HP (6-month slice)...')
ENGINE = pipeline_utils.engine_fitness(CANONICAL_HP, start_date='2024-01-01', end_date='2024-06-30')
print('Engine (qengine, real spread):')
for k, v in ENGINE.items():
    print(f'  {k}: {v}')

# Sign comparison
import json
out = os.path.join(RESULTS, 'simulator_vs_engine.json')
with open(out, 'w') as f:
    json.dump({'surrogate': SURROGATE, 'engine': ENGINE}, f, indent=2)
print(f'\nSaved {out}')

surr_sign = '+' if SURROGATE['total_pnl'] > 0 else '-'
eng_sign = '+' if ENGINE['total_pnl'] > 0 else '-'
print(f'\nSurrogate total_pnl sign: {surr_sign}')
print(f'Engine    total_pnl sign: {eng_sign}')
if surr_sign != eng_sign:
    print('GAP: surrogate and engine disagree on the sign of fitness.')
    print('A GA optimising surrogate fitness will pull genomes toward configurations')
    print('the engine refuses. This was the Phase 4 finding that motivated the switch.')
else:
    print('NOTE: signs agree on this single genome, but the magnitudes differ; the')
    print('original Phase 4 evidence was on optimal-genome convergence, not single-genome agreement.')
