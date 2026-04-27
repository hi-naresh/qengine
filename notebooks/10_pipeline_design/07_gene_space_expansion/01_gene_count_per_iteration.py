#!/usr/bin/env python3
"""Pivot 07 evidence: count tunable genes per iteration.

Iteration 1 evolved 14 strategy params over 3 tunable groups (General, Grid/Hedge,
Take Profit) plus 6 pipeline-level genes. Iteration 2 retired one legacy gene
(base_size_pct) and expanded the tunable groups to 7 (added Entry Signal, Filters,
Risk Management, Position Management).

This script reads the live _TUNABLE_GROUPS from IslandPilot's __init__.py and the
strategy's hyperparameters() spec, then counts how many strategy HPs fall into
each group — the Iteration 2 gene budget. Iteration 1's count is hard-coded from
DESIGN_RATIONALE.md since the historical __init__.py state isn't checked in.
"""
import os
import sys
import re
import json

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, ROOT)

ITERATION_1 = {
    'General': 7,
    'Grid / Hedge': 4,
    'Take Profit': 3,
    # legacy 6 pipeline-level genes including 1 inert (base_size_pct)
}
ITERATION_1_TOTAL = sum(ITERATION_1.values())  # = 14 strategy params

INIT_PY = os.path.join(ROOT, 'pipelines', '_shared', 'IslandPilot', '__init__.py')
with open(INIT_PY) as f:
    src = f.read()
m = re.search(r"_TUNABLE_GROUPS\s*=\s*{([^}]+)}", src)
if not m:
    sys.exit('ERROR: could not find _TUNABLE_GROUPS in __init__.py')
groups = [g.strip().strip("'").strip('"') for g in m.group(1).split(',') if g.strip()]
print(f'Iteration 2 _TUNABLE_GROUPS ({len(groups)} groups):')
for g in groups:
    print(f'  - {g}')

# Count strategy HPs per group from strategies/_admin/Martingale/__init__.py
STRAT_INIT = os.path.join(ROOT, 'strategies', '_admin', 'Martingale', '__init__.py')
with open(STRAT_INIT) as f:
    strat_src = f.read()

iter2_counts = {g: 0 for g in groups}
for m in re.finditer(r"\{[^{}]*'group'\s*:\s*([_A-Z][_A-Za-z]*)[^{}]*\}", strat_src):
    grp_var = m.group(1)
    grp_map = {'_G': 'General', '_E': 'Entry Signal', '_H': 'Grid / Hedge', '_T': 'Take Profit',
               '_F': 'Filters', '_R': 'Risk Management', '_P': 'Position Management'}
    grp_name = grp_map.get(grp_var)
    if grp_name and grp_name in iter2_counts:
        iter2_counts[grp_name] += 1

print('\nIteration 2 gene counts per tunable group:')
for g in groups:
    print(f'  {g}: {iter2_counts[g]}')
iter2_total = sum(iter2_counts.values())
print(f'  TOTAL: {iter2_total}')

print(f'\nIteration 1 total strategy genes (per DESIGN_RATIONALE.md): {ITERATION_1_TOTAL}')
print(f'Iteration 2 total strategy genes (live count): {iter2_total}')
print(f'Net expansion: +{iter2_total - ITERATION_1_TOTAL} genes, +{len(groups) - 3} groups')

out = os.path.join(RESULTS, 'gene_count_per_iteration.json')
with open(out, 'w') as f:
    json.dump({
        'iteration_1': {'groups': list(ITERATION_1.keys()), 'counts': ITERATION_1, 'total': ITERATION_1_TOTAL},
        'iteration_2': {'groups': groups, 'counts': iter2_counts, 'total': iter2_total},
    }, f, indent=2)
print(f'\nSaved {out}')
