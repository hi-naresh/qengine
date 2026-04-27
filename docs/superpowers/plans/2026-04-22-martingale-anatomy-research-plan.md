# Martingale Anatomy Research — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Study each structural component of the grid-hedged Martingale separately using the real qengine backtester (EUR-USD ≤ 2024-12-31), finding novel insights not in academic literature.

**Architecture:** Dual-track — math spine (01, 03) + empirical anatomy (02, 04) converge at abort theory (06), then HP interactions (07), broker mechanics (08), synthesis (09). Shared utility module provides backtest boilerplate for all scripts.

**Tech Stack:** Python 3 (conda), qengine backtester, numpy, matplotlib (Agg), pandas, scipy

---

## Task 1: Expose sessions from backtest + shared utils

**Files:**
- Modify: `qengine/research/backtest.py`
- Create: `notebooks/shared/__init__.py`
- Create: `notebooks/shared/utils.py`

- [ ] **Step 1: Add sessions to backtest result**

In `qengine/research/backtest.py`, find the line `result["trades"] = report.trades()` and add one line after it:

```python
    # Always include trades if available (needed for trade-shuffling Monte Carlo)
    if 'trades' in backtest_result:
        result['trades'] = backtest_result['trades']
    result['sessions'] = report.hedge_sessions()   # ← ADD THIS LINE
    if 'pipeline_stats' in backtest_result:
```

- [ ] **Step 2: Create shared package**

```bash
mkdir -p /Users/naresh/Documents/Research/qengine/notebooks/shared
touch /Users/naresh/Documents/Research/qengine/notebooks/shared/__init__.py
```

- [ ] **Step 3: Write `notebooks/shared/utils.py`**

```python
"""Shared utilities for all martingale anatomy research scripts."""
import os
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from qengine.research.candles import get_candles
from qengine.research.backtest import backtest

EXCHANGE = 'OANDA'
SYMBOL = 'EUR-USD'
TIMEFRAME = '5m'
DATA_END = '2024-12-31'

BUST_REASONS = {
    'abort', 'terminate', 'max_level_bust', 'sl_hit',
    'margin_call', 'margin_bust', 'max_level_sl',
}

BASE_CONFIG = {
    'starting_balance': 10_000,
    'fee': 0.0,
    'type': 'cfd',
    'exchange': 'OANDA',
    'warm_up_candles': 210,
}

BASE_ROUTES = [{
    'exchange': EXCHANGE,
    'strategy': 'Martingale',
    'symbol': SYMBOL,
    'timeframe': TIMEFRAME,
}]


def load_candles(start_date='2006-01-02', end_date=DATA_END):
    """Load EUR-USD candles. Always use end_date <= 2024-12-31."""
    assert end_date <= DATA_END, f"No 2025+ data allowed. Got {end_date}"
    warmup, candles = get_candles(
        exchange=EXCHANGE, symbol=SYMBOL, timeframe=TIMEFRAME,
        start_date=start_date, finish_date=end_date,
    )
    if warmup.ndim == 2 and len(warmup) > 0:
        return np.concatenate([warmup, candles], axis=0)
    return candles


def make_candles_dict(candles):
    key = f'{EXCHANGE}-{SYMBOL}'
    return {key: {'exchange': EXCHANGE, 'symbol': SYMBOL, 'candles': candles}}


def run_backtest(hp: dict, candles=None, start_date='2006-01-02',
                 balance=10_000) -> dict:
    """Run a single backtest, return result with result['sessions']."""
    if candles is None:
        candles = load_candles(start_date=start_date)
    cfg = {**BASE_CONFIG, 'starting_balance': balance}
    return backtest(
        config=cfg,
        routes=BASE_ROUTES,
        data_routes=[],
        candles=make_candles_dict(candles),
        hyperparameters=hp,
        generate_equity_curve=False,
    )


def sessions_to_df(sessions: list):
    """Convert result['sessions'] to a pandas DataFrame."""
    import pandas as pd
    rows = []
    for s in sessions:
        if not isinstance(s.get('session'), int):
            continue
        rows.append({
            'session': s['session'],
            'levels': s.get('levels', 0),
            'pnl': s.get('total_pnl', 0),
            'is_bust': s.get('outcome', '') in BUST_REASONS,
            'outcome': s.get('outcome', ''),
            'peak_margin': s.get('peak_margin', 0),
            'peak_equity_pct': s.get('peak_equity_pct', 0),
            'opened_at': s.get('opened_at'),
            'closed_at': s.get('closed_at'),
            'trade_count': s.get('trade_count', 0),
        })
    return pd.DataFrame(rows)


def save_fig(fig, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved: {path}')


CANONICAL_HP = {
    'preset': 'custom',
    'signal_mode': 'random',
    'direction_bias': 'both',
    'sizing_curve': 'geometric',
    'sizing_factor': 2.0,
    'base_size_mode': 'pct_equity',
    'base_size_value': 0.5,
    'max_levels': 6,
    'hedge_mode': 'fixed_pips',
    'hedge_value': 20.0,
    'tp_mode': 'fixed_pips',
    'tp_value': 20.0,
}
```

- [ ] **Step 4: Verify import works**

```bash
/Users/naresh/miniconda3/bin/python3 -c "import sys; sys.path.insert(0,'.');from notebooks.shared.utils import run_backtest, CANONICAL_HP; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add qengine/research/backtest.py notebooks/shared/
git commit -m "research: expose sessions from backtest + shared research utils"
```

---

## Task 2: 01_finite_capital — N-to-1 ratio

**Files:**
- Create: `notebooks/01_finite_capital/01_n_to_1_ratio.py`
- Create: `notebooks/01_finite_capital/results/` (auto-created by script)

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
How many wins does 1 bust erase?
Sweeps (sizing_factor, max_levels) and computes N = |avg_bust_pnl| / avg_win_pnl.
Novel target: is N stable across configs, or does it vary exploitably?
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, save_fig, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

SIZING_FACTORS = [1.3, 1.5, 2.0, 2.5, 3.0]
MAX_LEVELS     = [3, 4, 5, 6, 8]

print('Loading candles...')
candles = load_candles()

records = []
total = len(SIZING_FACTORS) * len(MAX_LEVELS)
i = 0
for sf in SIZING_FACTORS:
    for ml in MAX_LEVELS:
        i += 1
        hp = {**CANONICAL_HP, 'sizing_factor': sf, 'max_levels': ml}
        r = run_backtest(hp, candles=candles)
        df = sessions_to_df(r.get('sessions', []))
        if df.empty:
            continue
        wins  = df[~df['is_bust']]
        busts = df[df['is_bust']]
        if wins.empty or busts.empty:
            continue
        avg_win  = wins['pnl'].mean()
        avg_bust = busts['pnl'].mean()
        n_ratio  = abs(avg_bust) / avg_win if avg_win > 0 else np.nan
        records.append({
            'sizing_factor': sf, 'max_levels': ml,
            'avg_win': round(avg_win, 2),
            'avg_bust': round(avg_bust, 2),
            'n_ratio': round(n_ratio, 1),
            'n_sessions': len(df),
            'n_busts': len(busts),
            'win_rate': round(len(wins)/len(df), 4),
        })
        print(f'  [{i}/{total}] sf={sf} ml={ml}: N={n_ratio:.1f}  '
              f'busts={len(busts)} win_rate={len(wins)/len(df):.3f}')

results = pd.DataFrame(records)
results.to_csv(os.path.join(RESULTS, 'n_to_1_ratio.csv'), index=False)

# Heatmap of N
pivot = results.pivot(index='sizing_factor', columns='max_levels', values='n_ratio')
fig, ax = plt.subplots(figsize=(8, 5))
im = ax.imshow(pivot.values, aspect='auto', cmap='YlOrRd')
ax.set_xticks(range(len(pivot.columns))); ax.set_xticklabels(pivot.columns)
ax.set_yticks(range(len(pivot.index)));  ax.set_yticklabels(pivot.index)
ax.set_xlabel('max_levels'); ax.set_ylabel('sizing_factor')
ax.set_title('N-to-1 ratio: wins erased by 1 bust')
for r in range(pivot.shape[0]):
    for c in range(pivot.shape[1]):
        v = pivot.values[r, c]
        if not np.isnan(v):
            ax.text(c, r, f'{v:.0f}', ha='center', va='center', fontsize=9)
plt.colorbar(im, ax=ax)
save_fig(fig, os.path.join(RESULTS, 'n_to_1_heatmap.png'))

print('\nResults:')
print(results.to_string(index=False))
print(f'\nN ratio range: {results["n_ratio"].min():.1f} – {results["n_ratio"].max():.1f}')
print('Check observed.md if range > 3x across configs (exploitable variation)')
```

- [ ] **Step 2: Run and verify**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/01_finite_capital/01_n_to_1_ratio.py 2>&1 | tail -20
```
Expected: CSV saved, heatmap saved, N ratio values printed. If N varies >3x across configs, log to `observed.md`.

- [ ] **Step 3: Commit**

```bash
git add notebooks/01_finite_capital/01_n_to_1_ratio.py notebooks/01_finite_capital/results/
git commit -m "research(01): N-to-1 ratio sweep across sizing_factor × max_levels"
```

---

## Task 3: 01_finite_capital — break-even formula

**Files:**
- Create: `notebooks/01_finite_capital/02_break_even_formula.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Minimum win rate for positive expectancy.
EV = p*avg_win + (1-p)*avg_bust = 0  →  p_min = |avg_bust| / (avg_win + |avg_bust|)
Novel target: margin of safety = actual_win_rate - p_min. Is it stable?
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from notebooks.shared.utils import sessions_to_df, save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')

# Load N-to-1 data from Task 2
csv = os.path.join(RESULTS, 'n_to_1_ratio.csv')
if not os.path.exists(csv):
    print('Run 01_n_to_1_ratio.py first.')
    sys.exit(1)

df = pd.read_csv(csv)

# Break-even win rate: p_min = |avg_bust| / (avg_win + |avg_bust|)
df['p_min'] = df['avg_bust'].abs() / (df['avg_win'] + df['avg_bust'].abs())
df['margin_of_safety'] = df['win_rate'] - df['p_min']
df['is_viable'] = df['margin_of_safety'] > 0

print('Break-even analysis:')
print(df[['sizing_factor','max_levels','win_rate','p_min','margin_of_safety','is_viable']].to_string(index=False))

# Save
df.to_csv(os.path.join(RESULTS, 'break_even.csv'), index=False)

# Plot: margin of safety heatmap
pivot = df.pivot(index='sizing_factor', columns='max_levels', values='margin_of_safety')
fig, ax = plt.subplots(figsize=(8, 5))
im = ax.imshow(pivot.values, aspect='auto', cmap='RdYlGn', vmin=-0.1, vmax=0.2)
ax.set_xticks(range(len(pivot.columns))); ax.set_xticklabels(pivot.columns)
ax.set_yticks(range(len(pivot.index)));  ax.set_yticklabels(pivot.index)
ax.set_xlabel('max_levels'); ax.set_ylabel('sizing_factor')
ax.set_title('Margin of safety = actual_win_rate - break_even_win_rate')
for r in range(pivot.shape[0]):
    for c in range(pivot.shape[1]):
        v = pivot.values[r, c]
        if not np.isnan(v):
            ax.text(c, r, f'{v:.3f}', ha='center', va='center', fontsize=8)
plt.colorbar(im, ax=ax)
save_fig(fig, os.path.join(RESULTS, 'break_even_safety_margin.png'))

# Key insight: which configs are above breakeven?
viable = df[df['is_viable']]
print(f'\nViable configs (margin_of_safety > 0): {len(viable)}/{len(df)}')
print('Log to anomalies.md any configs with p_min > actual win_rate (structurally losing).')
```

- [ ] **Step 2: Run**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/01_finite_capital/02_break_even_formula.py
```
Expected: table printed, heatmap saved showing which configs have positive margin of safety.

- [ ] **Step 3: Commit**

```bash
git add notebooks/01_finite_capital/02_break_even_formula.py
git commit -m "research(01): break-even win rate and margin of safety per config"
```

---

## Task 4: 01_finite_capital — capital boundary

**Files:**
- Create: `notebooks/01_finite_capital/03_capital_boundary.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
At what starting equity does the config become structurally ruin-prone?
Run same HP at 5 equity levels. Find where bust_rate inflects.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, save_fig, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

EQUITY_LEVELS = [1_000, 2_500, 5_000, 10_000, 25_000]
# Test two representative configs: aggressive (sf=2, ml=8) and conservative (sf=1.5, ml=4)
CONFIGS = [
    {'label': 'aggressive', 'sizing_factor': 2.0, 'max_levels': 8},
    {'label': 'conservative', 'sizing_factor': 1.5, 'max_levels': 4},
]

print('Loading candles...')
candles = load_candles()

records = []
for cfg in CONFIGS:
    for eq in EQUITY_LEVELS:
        hp = {**CANONICAL_HP, **cfg}
        hp.pop('label', None)
        r = run_backtest(hp, candles=candles, balance=eq)
        df = sessions_to_df(r.get('sessions', []))
        if df.empty:
            continue
        bust_rate = df['is_bust'].mean()
        metrics   = r.get('metrics', {})
        records.append({
            'config': cfg['label'],
            'equity': eq,
            'bust_rate': round(bust_rate, 4),
            'win_rate':  round(1 - bust_rate, 4),
            'n_sessions': len(df),
            'net_pct': metrics.get('net_profit_percentage', 0),
        })
        print(f"  {cfg['label']} equity={eq:,}: bust_rate={bust_rate:.3f}")

df_r = pd.DataFrame(records)
df_r.to_csv(os.path.join(RESULTS, 'capital_boundary.csv'), index=False)

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
for ax, cfg_label in zip(axes, [c['label'] for c in CONFIGS]):
    sub = df_r[df_r['config'] == cfg_label]
    ax.plot(sub['equity'], sub['bust_rate'], 'o-', color='crimson')
    ax.set_xscale('log')
    ax.set_xlabel('Starting equity ($)')
    ax.set_ylabel('Bust rate')
    ax.set_title(f'{cfg_label} — bust rate vs equity')
    ax.grid(True, alpha=0.3)
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'capital_boundary.png'))

print('\nCapital boundary results:')
print(df_r.to_string(index=False))
print('\nNote: if bust_rate increases sharply below a threshold equity, log that threshold to observed.md')
```

- [ ] **Step 2: Run**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/01_finite_capital/03_capital_boundary.py
```
Expected: 10 rows, plots saved. Log any equity threshold where bust_rate jumps >2x to `observed.md`.

- [ ] **Step 3: Commit**

```bash
git add notebooks/01_finite_capital/03_capital_boundary.py
git commit -m "research(01): capital boundary — bust rate vs starting equity"
```

---

## Task 5: 02_bust_anatomy — extract all busts

**Files:**
- Create: `notebooks/02_bust_anatomy/01_bust_extraction.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Run full backtest, extract every bust session with complete state snapshot.
Saves bust database for all downstream anatomy scripts.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

print('Loading candles (full 2006–2024)...')
candles = load_candles()

hp = {**CANONICAL_HP, 'max_levels': 8}  # allow deeper levels so we capture full bust depth

print('Running full backtest...')
r = run_backtest(hp, candles=candles)
sessions = r.get('sessions', [])
print(f'Total sessions: {len(sessions)}')

df = sessions_to_df(sessions)
busts = df[df['is_bust']].copy()
wins  = df[~df['is_bust']].copy()

print(f'Busts: {len(busts)} ({len(busts)/len(df)*100:.2f}%)')
print(f'Wins:  {len(wins)}')
print(f'Avg bust PnL: ${busts["pnl"].mean():.2f}')
print(f'Avg win  PnL: ${wins["pnl"].mean():.2f}')
print(f'Bust level distribution:\n{busts["levels"].value_counts().sort_index()}')

df.to_csv(os.path.join(RESULTS, 'all_sessions.csv'), index=False)
busts.to_csv(os.path.join(RESULTS, 'bust_database.csv'), index=False)
print(f'\nSaved: all_sessions.csv ({len(df)} rows), bust_database.csv ({len(busts)} rows)')

metrics = r.get('metrics', {})
print(f'\nBacktest metrics: {metrics}')
```

- [ ] **Step 2: Run**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/02_bust_anatomy/01_bust_extraction.py
```
Expected: bust_database.csv saved, bust count and level distribution printed.

- [ ] **Step 3: Commit**

```bash
git add notebooks/02_bust_anatomy/01_bust_extraction.py
git commit -m "research(02): bust extraction — full 2006-2024 backtest, bust database"
```

---

## Task 6: 02_bust_anatomy — cause of death per level

**Files:**
- Create: `notebooks/02_bust_anatomy/02_level_cause_of_death.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
At which level do busts actually terminate?
Is it always max_levels (theoretical), or earlier (broker forced close)?
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
CSV = os.path.join(RESULTS, 'bust_database.csv')
if not os.path.exists(CSV):
    print('Run 01_bust_extraction.py first.')
    sys.exit(1)

busts = pd.read_csv(CSV)
all_s = pd.read_csv(os.path.join(RESULTS, 'all_sessions.csv'))

print(f'Total busts: {len(busts)}')
print(f'\nBust exit reasons:')
print(busts['outcome'].value_counts())

print(f'\nLevel reached at bust:')
print(busts['levels'].value_counts().sort_index())

# Were busts at max_levels (8) or earlier?
at_max = (busts['levels'] == 8).sum()
below_max = (busts['levels'] < 8).sum()
print(f'\nAt max_levels (8): {at_max} ({at_max/len(busts)*100:.1f}%)')
print(f'Below max_levels:  {below_max} ({below_max/len(busts)*100:.1f}%)')
if below_max > 0:
    print('** ANOMALY: busts occurring before max level — broker forcing close **')
    print('  Log to observed.md: implicit forced close at level < max_levels')

# Peak margin at bust
print(f'\nPeak margin at bust (peak_equity_pct):')
print(busts['peak_equity_pct'].describe())

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
axes[0].bar(busts['levels'].value_counts().sort_index().index,
            busts['levels'].value_counts().sort_index().values, color='crimson')
axes[0].set_xlabel('Level reached'); axes[0].set_ylabel('Count')
axes[0].set_title('Bust level distribution')

axes[1].hist(busts['peak_equity_pct'].dropna(), bins=20, color='orange', edgecolor='black')
axes[1].set_xlabel('Peak equity usage %'); axes[1].set_ylabel('Count')
axes[1].set_title('Broker margin usage at time of bust')
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'level_cause_of_death.png'))
```

- [ ] **Step 2: Run**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/02_bust_anatomy/02_level_cause_of_death.py
```
Expected: level distribution printed, early-bust anomaly flagged if any occur below max_levels.

- [ ] **Step 3: Commit**

```bash
git add notebooks/02_bust_anatomy/02_level_cause_of_death.py
git commit -m "research(02): level cause-of-death — where do busts actually terminate?"
```

---

## Task 7: 02_bust_anatomy — path patterns

**Files:**
- Create: `notebooks/02_bust_anatomy/03_bust_path_patterns.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Characterize the time-between-levels in bust paths vs win paths.
Fast escalation (choppy) vs slow escalation (normal)?
Not prediction — pure characterization of structural sub-types.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from notebooks.shared.utils import save_fig, run_backtest, load_candles, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
CSV = os.path.join(RESULTS, 'bust_database.csv')
ALL_CSV = os.path.join(RESULTS, 'all_sessions.csv')

all_s = pd.read_csv(ALL_CSV)
busts = pd.read_csv(CSV)
wins  = all_s[~all_s['is_bust']]

# Proxy for escalation speed: PnL per level (more negative = faster loss)
all_s['pnl_per_level'] = all_s['pnl'] / (all_s['levels'] + 1)
bust_rows = all_s[all_s['is_bust']]
win_rows  = all_s[~all_s['is_bust']]

print('PnL per level at bust vs win:')
print(f'  Bust: mean={bust_rows["pnl_per_level"].mean():.2f}  std={bust_rows["pnl_per_level"].std():.2f}')
print(f'  Win:  mean={win_rows["pnl_per_level"].mean():.2f}  std={win_rows["pnl_per_level"].std():.2f}')

# Trade count (legs) distribution: more legs = more time spent
print('\nLegs in bust sessions:')
print(bust_rows['trade_count'].describe())
print('\nLegs in win sessions:')
print(win_rows['trade_count'].describe())

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
axes[0].hist(bust_rows['trade_count'].dropna(), bins=15, alpha=0.7, label='Bust', color='crimson')
axes[0].hist(win_rows['trade_count'].clip(upper=20).dropna(), bins=15, alpha=0.7, label='Win', color='green')
axes[0].set_xlabel('Legs (trade count)'); axes[0].set_title('Legs per session: bust vs win')
axes[0].legend()

axes[1].hist(bust_rows['peak_equity_pct'].dropna(), bins=15, alpha=0.7, label='Bust', color='crimson')
axes[1].hist(win_rows['peak_equity_pct'].dropna(), bins=15, alpha=0.7, label='Win', color='green')
axes[1].set_xlabel('Peak equity usage %'); axes[1].set_title('Peak equity usage: bust vs win')
axes[1].legend()
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'bust_path_patterns.png'))
print(f'\nSaved: bust_path_patterns.png')
```

- [ ] **Step 2: Run**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/02_bust_anatomy/03_bust_path_patterns.py
```
Expected: distributions printed, histogram saved.

- [ ] **Step 3: Commit**

```bash
git add notebooks/02_bust_anatomy/03_bust_path_patterns.py
git commit -m "research(02): bust path patterns — fast vs slow escalation characterization"
```

---

## Task 8: 03_margin_mechanics — trajectory formula

**Files:**
- Create: `notebooks/03_margin_mechanics/01_margin_trajectory.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Derive the theoretical margin consumption at each level.
Formula: margin_at_level_N = sum(lot_N * price * margin_rate) for all open tickets.
Lot at level n = base_lots * sizing_factor^n  (geometric).
Compare theory vs empirical peak_margin from backtester.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

# OANDA margin rate for EUR-USD: 3.33% (30:1 leverage)
MARGIN_RATE = 1 / 30
PRICE = 1.10        # approximate EUR-USD price
LOT_SIZE = 100_000  # standard lot in units

def theoretical_margin(sizing_factor, max_levels, base_pct_equity, equity):
    """Compute cumulative margin used at each level (geometric sizing)."""
    base_lots = (base_pct_equity / 100 * equity) / (PRICE * LOT_SIZE)
    margins = []
    total = 0
    for n in range(max_levels + 1):
        lot_n = base_lots * (sizing_factor ** n)
        margin_n = lot_n * PRICE * LOT_SIZE * MARGIN_RATE
        total += margin_n
        margins.append({'level': n, 'lots': lot_n, 'margin_this': margin_n, 'margin_total': total,
                         'equity_pct': total / equity * 100})
    return pd.DataFrame(margins)

configs = [
    {'sf': 1.5, 'ml': 6, 'label': 'sf=1.5, ml=6'},
    {'sf': 2.0, 'ml': 6, 'label': 'sf=2.0, ml=6'},
    {'sf': 2.0, 'ml': 8, 'label': 'sf=2.0, ml=8'},
    {'sf': 2.5, 'ml': 5, 'label': 'sf=2.5, ml=5'},
]
EQUITY = 10_000
BASE_PCT = 0.5

fig, ax = plt.subplots(figsize=(10, 6))
for cfg in configs:
    df = theoretical_margin(cfg['sf'], cfg['ml'], BASE_PCT, EQUITY)
    ax.plot(df['level'], df['equity_pct'], marker='o', label=cfg['label'])
    print(f"\n{cfg['label']}:")
    print(df[['level','lots','margin_total','equity_pct']].to_string(index=False))

ax.axhline(100, color='red', linestyle='--', label='100% equity (margin call)')
ax.axhline(50, color='orange', linestyle='--', alpha=0.5, label='50% equity')
ax.set_xlabel('Level'); ax.set_ylabel('Cumulative margin used (% equity)')
ax.set_title('Theoretical margin consumption by level\n(30:1 leverage, 0.5% base, €10k)')
ax.legend(); ax.grid(True, alpha=0.3)
save_fig(fig, os.path.join(RESULTS, 'margin_trajectory.png'))

# Also compare against empirical from bust anatomy
bust_csv = os.path.join('notebooks', '02_bust_anatomy', 'results', 'bust_database.csv')
if os.path.exists(bust_csv):
    busts = pd.read_csv(bust_csv)
    print(f'\nEmpirical peak_equity_pct at bust (all levels):')
    print(busts.groupby('levels')['peak_equity_pct'].describe())
```

- [ ] **Step 2: Run**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/03_margin_mechanics/01_margin_trajectory.py
```
Expected: margin trajectory table per config printed, plot saved. Note: if empirical bust margin < 100%, that's implicit forced close.

- [ ] **Step 3: Commit**

```bash
git add notebooks/03_margin_mechanics/01_margin_trajectory.py
git commit -m "research(03): margin trajectory — theoretical formula vs empirical peak"
```

---

## Task 9: 03_margin_mechanics — implicit forced close

**Files:**
- Create: `notebooks/03_margin_mechanics/02_implicit_forced_close.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
When does the broker force-close before theoretical max_levels?
Run backtests at equity levels where margin should be tight.
Compare max level REACHED vs max level CONFIGURED.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, save_fig, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

candles = load_candles()
records = []

# Sweep equity + sizing to find where broker closes early
for equity in [1_000, 2_000, 5_000, 10_000]:
    for sf in [1.5, 2.0, 2.5]:
        hp = {**CANONICAL_HP, 'sizing_factor': sf, 'max_levels': 8}
        r = run_backtest(hp, candles=candles, balance=equity)
        df = sessions_to_df(r.get('sessions', []))
        if df.empty:
            continue
        busts = df[df['is_bust']]
        if busts.empty:
            continue
        avg_bust_level = busts['levels'].mean()
        margin_call_busts = busts[busts['outcome'].isin(['margin_call', 'margin_bust'])].shape[0]
        records.append({
            'equity': equity, 'sizing_factor': sf,
            'n_busts': len(busts),
            'avg_bust_level': round(avg_bust_level, 2),
            'max_bust_level': int(busts['levels'].max()),
            'margin_call_count': margin_call_busts,
            'margin_call_pct': round(margin_call_busts / len(busts) * 100, 1),
        })
        print(f'  equity={equity:,} sf={sf}: avg_bust_level={avg_bust_level:.1f}  '
              f'margin_calls={margin_call_busts}/{len(busts)}')

df_r = pd.DataFrame(records)
df_r.to_csv(os.path.join(RESULTS, 'implicit_forced_close.csv'), index=False)

# Key finding: if max_bust_level < 8 in many configs, broker is closing early
print('\n')
print(df_r[['equity','sizing_factor','avg_bust_level','max_bust_level','margin_call_pct']].to_string(index=False))

forced_early = df_r[df_r['max_bust_level'] < 8]
if not forced_early.empty:
    print(f'\n** FINDING: {len(forced_early)} configs show broker closing before max_levels=8 **')
    print('Log to observed.md: implicit forced close at level < configured max_levels')
```

- [ ] **Step 2: Run**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/03_margin_mechanics/02_implicit_forced_close.py
```
Expected: table showing whether broker closes early. If max_bust_level < configured max, log to `observed.md`.

- [ ] **Step 3: Commit**

```bash
git add notebooks/03_margin_mechanics/02_implicit_forced_close.py
git commit -m "research(03): implicit forced close — broker vs theoretical max levels"
```

---

## Task 10: 03_margin_mechanics — margin cushion map

**Files:**
- Create: `notebooks/03_margin_mechanics/03_margin_cushion_map.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
2D heatmap: at which (sizing_factor, max_levels) does cumulative margin
exceed 100% equity at OANDA 30:1, given 0.5% base size and $10k?
This defines the structurally infeasible region for pipeline gene bounds.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

MARGIN_RATE = 1 / 30
PRICE = 1.10
LOT_SIZE = 100_000
EQUITY = 10_000
BASE_PCT = 0.5

SFS = np.round(np.arange(1.2, 3.1, 0.1), 1)
MLS = list(range(2, 13))

data = np.zeros((len(SFS), len(MLS)))
level_at_100 = np.full((len(SFS), len(MLS)), np.nan)

for i, sf in enumerate(SFS):
    for j, ml in enumerate(MLS):
        base_lots = (BASE_PCT / 100 * EQUITY) / (PRICE * LOT_SIZE)
        total_margin = 0
        safe_level = ml  # last level that fits within equity
        for n in range(ml + 1):
            lot_n = base_lots * (sf ** n)
            total_margin += lot_n * PRICE * LOT_SIZE * MARGIN_RATE
            if total_margin >= EQUITY and np.isnan(level_at_100[i, j]):
                level_at_100[i, j] = n
        pct = total_margin / EQUITY * 100
        data[i, j] = min(pct, 200)  # cap at 200% for display

fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# Heatmap: total margin at deepest level
im0 = axes[0].imshow(data, aspect='auto', cmap='RdYlGn_r', vmin=0, vmax=150)
axes[0].set_xticks(range(len(MLS))); axes[0].set_xticklabels(MLS)
axes[0].set_yticks(range(len(SFS))); axes[0].set_yticklabels([f'{s:.1f}' for s in SFS])
axes[0].set_xlabel('max_levels'); axes[0].set_ylabel('sizing_factor')
axes[0].set_title('Total margin at deepest level (% equity)\nRed = margin call territory')
plt.colorbar(im0, ax=axes[0])

# Heatmap: level at which margin hits 100%
im1 = axes[1].imshow(level_at_100, aspect='auto', cmap='RdYlGn', vmin=2, vmax=12)
axes[1].set_xticks(range(len(MLS))); axes[1].set_xticklabels(MLS)
axes[1].set_yticks(range(len(SFS))); axes[1].set_yticklabels([f'{s:.1f}' for s in SFS])
axes[1].set_xlabel('max_levels'); axes[1].set_ylabel('sizing_factor')
axes[1].set_title('Level at which broker forces close (margin = 100%)\nGreen = never hits 100%')
plt.colorbar(im1, ax=axes[1])

plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'margin_cushion_map.png'))

# Print infeasible region
infeasible = [(SFS[i], MLS[j]) for i in range(len(SFS)) for j in range(len(MLS))
              if not np.isnan(level_at_100[i, j]) and level_at_100[i, j] < MLS[j]]
print(f'Infeasible combos (broker closes before max_levels): {len(infeasible)}/{len(SFS)*len(MLS)}')
print('These define the FORBIDDEN region for IslandPilot gene bounds.')
print('Log specific boundary to 09_synthesis/02_pipeline_implications.md')
```

- [ ] **Step 2: Run**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/03_margin_mechanics/03_margin_cushion_map.py
```
Expected: two heatmaps saved, forbidden region count printed. This directly feeds IslandPilot gene bounds.

- [ ] **Step 3: Commit**

```bash
git add notebooks/03_margin_mechanics/03_margin_cushion_map.py
git commit -m "research(03): margin cushion map — infeasible HP region for gene bounds"
```

---

## Task 11: 04_cost_model — spread compounding

**Files:**
- Create: `notebooks/04_cost_model/01_spread_per_level.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Spread cost is NOT flat — it grows with position size.
At level N with geometric sizing, spread_cost_N = spread_pips * lot_N * pip_value.
Measure cumulative spread cost as % of avg_win across levels.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import run_backtest, run_backtest, load_candles, sessions_to_df, save_fig, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

# Theoretical: spread cost per level
SPREAD_PIPS = 2.0   # OANDA EUR-USD typical spread
PIP_VALUE   = 10.0  # $ per pip per standard lot (EUR-USD)
BASE_LOTS   = 0.01  # 0.5% of $10k at 30:1 = ~$50/lot → 0.05 lots; approx

SFS = [1.5, 2.0, 2.5]
MAX_LEVEL = 8

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

for sf in SFS:
    levels = list(range(MAX_LEVEL + 1))
    spread_costs = []
    cumulative = 0
    for n in levels:
        lot_n = BASE_LOTS * (sf ** n)
        cost  = SPREAD_PIPS * lot_n * PIP_VALUE  # spread paid on entry
        cumulative += cost
        spread_costs.append({'level': n, 'spread_cost': cost, 'cumulative': cumulative})
    df = pd.DataFrame(spread_costs)
    axes[0].plot(df['level'], df['spread_cost'], marker='o', label=f'sf={sf}')
    axes[1].plot(df['level'], df['cumulative'], marker='o', label=f'sf={sf}')

axes[0].set_xlabel('Level'); axes[0].set_ylabel('Spread cost at entry ($)')
axes[0].set_title('Spread cost per level entry (not flat — grows with lot size)')
axes[0].legend(); axes[0].grid(True, alpha=0.3)

axes[1].set_xlabel('Level'); axes[1].set_ylabel('Cumulative spread paid ($)')
axes[1].set_title('Cumulative spread cost across all levels')
axes[1].legend(); axes[1].grid(True, alpha=0.3)
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'spread_per_level.png'))

# Compare to avg win PnL from bust anatomy
all_csv = os.path.join('notebooks', '02_bust_anatomy', 'results', 'all_sessions.csv')
if os.path.exists(all_csv):
    sessions = pd.read_csv(all_csv)
    avg_win = sessions[~sessions['is_bust']]['pnl'].mean()
    print(f'Avg win PnL: ${avg_win:.2f}')
    for sf in SFS:
        cum_at_max = BASE_LOTS * PIP_VALUE * SPREAD_PIPS * sum(sf**n for n in range(MAX_LEVEL+1))
        print(f'sf={sf}: cumulative spread at level {MAX_LEVEL} = ${cum_at_max:.2f}  '
              f'({cum_at_max/avg_win*100:.1f}% of avg win)')
    print('\nIf cumulative spread > avg_win, strategy is structurally losing at deep levels.')
```

- [ ] **Step 2: Run**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/04_cost_model/01_spread_per_level.py
```
Expected: plots saved, cumulative spread vs avg win comparison printed.

- [ ] **Step 3: Commit**

```bash
git add notebooks/04_cost_model/01_spread_per_level.py
git commit -m "research(04): spread compounding per level — grows with lot size"
```

---

## Task 12: 04_cost_model — swap drag, effective grid distance, cost kills edge

**Files:**
- Create: `notebooks/04_cost_model/02_swap_drag.py`
- Create: `notebooks/04_cost_model/03_effective_grid_distance.py`
- Create: `notebooks/04_cost_model/04_cost_kills_edge.py`

- [ ] **Step 1: Write `02_swap_drag.py`**

```python
#!/usr/bin/env python3
"""Swap accumulates with hold time. Deeper levels = longer hold = more swap drag."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

# OANDA EUR-USD overnight swap (approximate, long position pays)
SWAP_PIPS_PER_DAY = -0.7   # negative = cost
PIP_VALUE = 10.0
BASE_LOTS = 0.01
SFS = [1.5, 2.0, 2.5]

# Assume levels are held progressively longer: level N held ~N days on avg
HOLD_DAYS_PER_LEVEL = {0: 0.5, 1: 1.0, 2: 1.5, 3: 2.5, 4: 4.0, 5: 6.0, 6: 8.0, 7: 12.0, 8: 18.0}

fig, ax = plt.subplots(figsize=(10, 5))
for sf in SFS:
    swap_costs = []
    for n, hold_days in HOLD_DAYS_PER_LEVEL.items():
        lot_n = BASE_LOTS * (sf ** n)
        swap  = abs(SWAP_PIPS_PER_DAY) * hold_days * lot_n * PIP_VALUE
        swap_costs.append({'level': n, 'swap_cost': swap})
    df = pd.DataFrame(swap_costs)
    ax.plot(df['level'], df['swap_cost'], marker='o', label=f'sf={sf}')

ax.set_xlabel('Level'); ax.set_ylabel('Swap cost ($)')
ax.set_title('Estimated swap drag by level\n(grows with both lot size AND hold time)')
ax.legend(); ax.grid(True, alpha=0.3)
save_fig(fig, os.path.join(RESULTS, 'swap_drag.png'))
print('Swap drag plot saved.')
print('Note: actual hold days need empirical measurement from bust_anatomy sessions.')
```

- [ ] **Step 2: Write `03_effective_grid_distance.py`**

```python
#!/usr/bin/env python3
"""
Effective hedge distance = configured_pips - spread_pips.
This shifts all ruin-probability math because the real grid is tighter than configured.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

SPREAD_PIPS = 2.0
CONFIGURED_HEDGES = np.arange(5, 55, 5)  # 5 to 50 pips
EFFECTIVE = CONFIGURED_HEDGES - SPREAD_PIPS
SHRINKAGE = (CONFIGURED_HEDGES - EFFECTIVE) / CONFIGURED_HEDGES * 100

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
axes[0].plot(CONFIGURED_HEDGES, EFFECTIVE, 'o-', color='steelblue')
axes[0].plot(CONFIGURED_HEDGES, CONFIGURED_HEDGES, '--', color='gray', label='No adjustment')
axes[0].set_xlabel('Configured hedge (pips)'); axes[0].set_ylabel('Effective hedge (pips)')
axes[0].set_title('Effective grid distance after spread'); axes[0].legend()

axes[1].plot(CONFIGURED_HEDGES, SHRINKAGE, 'o-', color='crimson')
axes[1].set_xlabel('Configured hedge (pips)'); axes[1].set_ylabel('Shrinkage (%)')
axes[1].set_title('% grid shrinkage from spread\n(largest at tight grids)')
axes[1].axhline(10, color='orange', linestyle='--', label='10% threshold')
axes[1].legend(); axes[1].grid(True, alpha=0.3)
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'effective_grid_distance.png'))

print('Effective grid distance:')
for c, e, s in zip(CONFIGURED_HEDGES, EFFECTIVE, SHRINKAGE):
    print(f'  configured={c:.0f}  effective={e:.0f}  shrinkage={s:.1f}%')
print('\nKey: with 2-pip spread, a 10-pip grid is effectively 8 pips — 20% tighter.')
print('This directly shifts the P(win per level) upward or downward depending on direction.')
```

- [ ] **Step 3: Write `04_cost_kills_edge.py`**

```python
#!/usr/bin/env python3
"""
At what level does cumulative cost (spread + est. swap) exceed the strategy edge?
Edge = avg_win_pnl (from backtest). If cumulative cost at level N > edge, losing territory.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')

all_csv = os.path.join('notebooks', '02_bust_anatomy', 'results', 'all_sessions.csv')
if not os.path.exists(all_csv):
    print('Run 02_bust_anatomy/01_bust_extraction.py first.')
    import sys; sys.exit(1)

sessions = pd.read_csv(all_csv)
avg_win = sessions[~sessions['is_bust']]['pnl'].mean()
print(f'Average win PnL (edge): ${avg_win:.2f}')

SPREAD_PIPS = 2.0; SWAP_DAILY = 0.7; PIP_VALUE = 10.0; BASE_LOTS = 0.01
SFS = [1.5, 2.0, 2.5]
HOLD_DAYS = {0: 0.5, 1: 1.0, 2: 1.5, 3: 2.5, 4: 4.0, 5: 6.0, 6: 8.0, 7: 12.0, 8: 18.0}

fig, ax = plt.subplots(figsize=(10, 5))
for sf in SFS:
    cum = 0; records = []
    for n in range(9):
        lot_n = BASE_LOTS * (sf ** n)
        cost  = SPREAD_PIPS * lot_n * PIP_VALUE + SWAP_DAILY * HOLD_DAYS.get(n, n) * lot_n * PIP_VALUE
        cum  += cost
        records.append({'level': n, 'cumulative_cost': cum})
    df = pd.DataFrame(records)
    ax.plot(df['level'], df['cumulative_cost'], marker='o', label=f'sf={sf}')

ax.axhline(avg_win, color='green', linestyle='--', linewidth=2, label=f'avg_win=${avg_win:.2f}')
ax.set_xlabel('Level'); ax.set_ylabel('Cumulative cost ($)')
ax.set_title('Cumulative cost vs strategy edge\nCross = cost exceeds edge (losing territory)')
ax.legend(); ax.grid(True, alpha=0.3)
save_fig(fig, os.path.join(RESULTS, 'cost_kills_edge.png'))
print('Plot saved. If curves cross avg_win before level 6, log to anomalies.md.')
```

- [ ] **Step 4: Run all three**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/04_cost_model/02_swap_drag.py
/Users/naresh/miniconda3/bin/python3 notebooks/04_cost_model/03_effective_grid_distance.py
/Users/naresh/miniconda3/bin/python3 notebooks/04_cost_model/04_cost_kills_edge.py
```

- [ ] **Step 5: Commit**

```bash
git add notebooks/04_cost_model/
git commit -m "research(04): cost model — swap drag, effective grid distance, edge erosion"
```

---

## Task 13: 05_market_structure — holding time by structure

**Files:**
- Create: `notebooks/05_market_structure/01_holding_time_by_structure.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Does market structure (choppy vs trending) affect how long sessions stay open?
Use ATR as volatility proxy and Choppiness Index as structure proxy.
Measure session duration in bars vs ATR/choppiness at session entry.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, save_fig, CANONICAL_HP
import qengine.indicators as ta

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

print('Loading candles...')
candles = load_candles()

hp = {**CANONICAL_HP, 'max_levels': 8}
print('Running backtest...')
r = run_backtest(hp, candles=candles)
sessions = r.get('sessions', [])
df = sessions_to_df(sessions)
if df.empty:
    print('No sessions.'); sys.exit(1)

# Compute ATR on full candle array
atr_arr = ta.atr(candles, period=14, sequential=True)
# Choppiness Index: 100 * log10(sum(ATR1, N) / (High_N - Low_N)) / log10(N)
# Approximate using ATR14 / ATR50 ratio (simpler proxy)
atr_slow = ta.atr(candles, period=50, sequential=True)
chop_proxy = np.where(atr_slow > 0, atr_arr / atr_slow, np.nan)

# Map session open timestamps to candle index (approximate by index position)
# sessions have 'opened_at' as timestamp; use session number as rough index proxy
# Build per-session duration proxy: trade_count as duration proxy
df['duration_proxy'] = df['trade_count']  # more trades = longer session

# Separate by bust vs win and level depth
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
busts = df[df['is_bust']]
wins  = df[~df['is_bust']]

axes[0].hist(wins['trade_count'].clip(upper=20), bins=15, alpha=0.7, color='green', label='Win')
axes[0].hist(busts['trade_count'], bins=15, alpha=0.7, color='crimson', label='Bust')
axes[0].set_xlabel('Trade count (duration proxy)'); axes[0].set_title('Session duration: bust vs win')
axes[0].legend()

# By level reached
level_groups = df.groupby('levels')['trade_count'].mean()
axes[1].bar(level_groups.index, level_groups.values, color='steelblue')
axes[1].set_xlabel('Level reached'); axes[1].set_ylabel('Avg trade count')
axes[1].set_title('Average session duration by level depth')
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'holding_time_by_structure.png'))

print(f'Avg session duration: wins={wins["trade_count"].mean():.1f} trades, '
      f'busts={busts["trade_count"].mean():.1f} trades')
print('Longer bust sessions = more swap drag accumulated.')
```

- [ ] **Step 2: Run**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/05_market_structure/01_holding_time_by_structure.py
```

- [ ] **Step 3: Write `02_margin_consumption_rate.py` and `03_volatility_vs_hedge.py`**

```python
# 02_margin_consumption_rate.py
#!/usr/bin/env python3
"""Choppy market: multiple levels open simultaneously = high margin drain rate."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np
from notebooks.shared.utils import sessions_to_df

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

all_csv = os.path.join('notebooks', '02_bust_anatomy', 'results', 'all_sessions.csv')
if not os.path.exists(all_csv):
    print('Run 02_bust_anatomy/01_bust_extraction.py first.'); sys.exit(1)
df = pd.read_csv(all_csv)
busts = df[df['is_bust']]

# Margin consumption rate = peak_equity_pct / trade_count (proxy for speed of margin usage)
df['margin_rate'] = df['peak_equity_pct'] / df['trade_count'].clip(lower=1)
print('Margin consumption rate (equity_pct per leg):')
print(f'  Busts: {df[df["is_bust"]]["margin_rate"].mean():.2f}')
print(f'  Wins:  {df[~df["is_bust"]]["margin_rate"].mean():.2f}')
print(f'\nFast-drain busts (margin_rate > 10): {(busts["margin_rate"] > 10).sum()} / {len(busts)}')
df.to_csv(os.path.join(RESULTS, 'margin_consumption_rate.csv'), index=False)
print('Saved margin_consumption_rate.csv')
```

```python
# 03_volatility_vs_hedge.py
#!/usr/bin/env python3
"""Wrong hedge distance in volatile regime: bust_rate by hedge_value setting."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, save_fig, CANONICAL_HP
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

candles = load_candles()
HEDGE_VALUES = [5, 10, 15, 20, 30, 40]
records = []
for hv in HEDGE_VALUES:
    hp = {**CANONICAL_HP, 'hedge_value': hv, 'tp_value': hv}
    r = run_backtest(hp, candles=candles)
    df = sessions_to_df(r.get('sessions', []))
    if df.empty: continue
    records.append({'hedge_pips': hv, 'bust_rate': df['is_bust'].mean(),
                    'avg_win': df[~df['is_bust']]['pnl'].mean() if (~df['is_bust']).any() else 0,
                    'n_sessions': len(df)})
    print(f'  hedge={hv}pips: bust_rate={df["is_bust"].mean():.4f}')

df_r = pd.DataFrame(records)
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(df_r['hedge_pips'], df_r['bust_rate'], 'o-', color='crimson')
ax.set_xlabel('Hedge distance (pips)'); ax.set_ylabel('Bust rate')
ax.set_title('Bust rate vs hedge distance\n(wrong distance in volatile market)')
ax.grid(True, alpha=0.3)
save_fig(fig, os.path.join(RESULTS, 'volatility_vs_hedge.png'))
print(df_r.to_string(index=False))
print('U-shape expected: too tight = false triggers, too wide = deep losses.')
```

- [ ] **Step 4: Run**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/05_market_structure/02_margin_consumption_rate.py
/Users/naresh/miniconda3/bin/python3 notebooks/05_market_structure/03_volatility_vs_hedge.py
```

- [ ] **Step 5: Commit**

```bash
git add notebooks/05_market_structure/
git commit -m "research(05): market structure — holding time, margin rate, hedge viability"
```

---

## Task 14: 06_abort_theory — abort vs no-abort EV sweep

**Files:**
- Create: `notebooks/06_abort_theory/01_abort_vs_no_abort.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Does aborting at level K improve long-run EV?
Run same HP with abort_mode=level_threshold at K=1..7, compare to no-abort baseline.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, save_fig, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

candles = load_candles()
records = []

# Baseline: no abort
hp_base = {**CANONICAL_HP, 'max_levels': 8, 'abort_mode': 'none'}
r = run_backtest(hp_base, candles=candles)
df_base = sessions_to_df(r.get('sessions', []))
base_pnl    = df_base['pnl'].sum()
base_busts  = df_base['is_bust'].sum()
base_bust_r = df_base['is_bust'].mean()
records.append({'abort_level': 0, 'label': 'no_abort', 'total_pnl': base_pnl,
                'bust_rate': base_bust_r, 'n_busts': base_busts})
print(f'Baseline (no abort): total_pnl=${base_pnl:.2f}  bust_rate={base_bust_r:.4f}')

# Abort at each level
for k in range(1, 9):
    hp = {**CANONICAL_HP, 'max_levels': 8, 'abort_mode': 'level_threshold', 'abort_level': k}
    r = run_backtest(hp, candles=candles)
    df = sessions_to_df(r.get('sessions', []))
    if df.empty: continue
    total_pnl  = df['pnl'].sum()
    bust_rate  = df['is_bust'].mean()
    aborts     = (df['outcome'] == 'abort').sum()
    records.append({'abort_level': k, 'label': f'abort@{k}', 'total_pnl': total_pnl,
                    'bust_rate': bust_rate, 'n_busts': df['is_bust'].sum(),
                    'n_aborts': aborts})
    print(f'abort@{k}: total_pnl=${total_pnl:.2f}  bust_rate={bust_rate:.4f}  aborts={aborts}')

df_r = pd.DataFrame(records)
df_r.to_csv(os.path.join(RESULTS, 'abort_vs_no_abort.csv'), index=False)

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
abort_rows = df_r[df_r['abort_level'] > 0]
axes[0].plot(abort_rows['abort_level'], abort_rows['bust_rate'], 'o-', color='crimson', label='Abort')
axes[0].axhline(base_bust_r, color='black', linestyle='--', label=f'No abort ({base_bust_r:.3f})')
axes[0].set_xlabel('Abort level'); axes[0].set_ylabel('Bust rate')
axes[0].set_title('Bust rate by abort level'); axes[0].legend()

axes[1].plot(abort_rows['abort_level'], abort_rows['total_pnl'], 'o-', color='steelblue', label='Abort')
axes[1].axhline(base_pnl, color='black', linestyle='--', label=f'No abort (${base_pnl:.0f})')
axes[1].set_xlabel('Abort level'); axes[1].set_ylabel('Total PnL ($)')
axes[1].set_title('Total PnL by abort level'); axes[1].legend()
plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'abort_vs_no_abort.png'))

# Key finding: is there an optimal K?
if len(abort_rows) > 0:
    best_pnl_row = abort_rows.loc[abort_rows['total_pnl'].idxmax()]
    print(f'\nBest abort level by PnL: K={best_pnl_row["abort_level"]} (${best_pnl_row["total_pnl"]:.2f})')
    best_bust_row = abort_rows.loc[abort_rows['bust_rate'].idxmin()]
    print(f'Best abort level by bust_rate: K={best_bust_row["abort_level"]} ({best_bust_row["bust_rate"]:.4f})')
    if best_pnl_row['abort_level'] != best_bust_row['abort_level']:
        print('** FINDING: PnL-optimal and bust-rate-optimal abort levels differ — log to observed.md **')
```

- [ ] **Step 2: Run**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/06_abort_theory/01_abort_vs_no_abort.py
```
Expected: EV curves printed and plotted. The optimal abort level is the key finding here.

- [ ] **Step 3: Commit**

```bash
git add notebooks/06_abort_theory/01_abort_vs_no_abort.py
git commit -m "research(06): abort EV sweep — optimal abort level vs no-abort baseline"
```

---

## Task 15: 06_abort_theory — point of no return + optimal abort

**Files:**
- Create: `notebooks/06_abort_theory/02_point_of_no_return.py`
- Create: `notebooks/06_abort_theory/03_optimal_abort_level.py`
- Create: `notebooks/06_abort_theory/04_partial_abort.py`

- [ ] **Step 1: Write `02_point_of_no_return.py`**

```python
#!/usr/bin/env python3
"""
Math: at what level is remaining EV negative regardless of outcome?
Point of no return = level where (cost to continue) > (expected recovery value).
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import numpy as np
import pandas as pd

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

csv = os.path.join(RESULTS, 'abort_vs_no_abort.csv')
bust_csv = os.path.join('notebooks', '02_bust_anatomy', 'results', 'bust_database.csv')
all_csv  = os.path.join('notebooks', '02_bust_anatomy', 'results', 'all_sessions.csv')

abort_df = pd.read_csv(csv) if os.path.exists(csv) else None
if os.path.exists(all_csv):
    sessions = pd.read_csv(all_csv)
    wins  = sessions[~sessions['is_bust']]
    busts = sessions[sessions['is_bust']]
    avg_win  = wins['pnl'].mean()
    avg_bust = busts['pnl'].mean()

    # By level: what's the conditional expectation of PnL given you're at level N?
    # At level N: prob of winning (reaching TP from here) vs busting
    # Use empirical: sessions that reached level N — what fraction eventually won?
    print('Conditional win rate given current level:')
    for lvl in range(0, 9):
        at_or_above = sessions[sessions['levels'] >= lvl]
        if at_or_above.empty: continue
        win_from_here = (~at_or_above['is_bust']).mean()
        exp_value = win_from_here * avg_win + (1 - win_from_here) * avg_bust
        print(f'  Level {lvl}: P(win | reached) = {win_from_here:.3f}  EV = ${exp_value:.2f}')
        if exp_value < 0:
            print(f'  ** POINT OF NO RETURN: level {lvl} has negative conditional EV **')
            print(f'     Log to observed.md')
            break
```

- [ ] **Step 2: Write `03_optimal_abort_level.py`**

```python
#!/usr/bin/env python3
"""
Fixed-level abort vs margin-state-aware abort: which produces better outcomes?
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
csv = os.path.join(RESULTS, 'abort_vs_no_abort.csv')
if not os.path.exists(csv):
    print('Run 01_abort_vs_no_abort.py first.'); import sys; sys.exit(1)

df = pd.read_csv(csv)
print('Abort level analysis:')
print(df[['label','total_pnl','bust_rate','n_busts']].to_string(index=False))

# Find the Pareto-optimal abort level (best bust_rate with least PnL sacrifice)
baseline = df[df['abort_level'] == 0].iloc[0]
abort_rows = df[df['abort_level'] > 0].copy()
abort_rows['pnl_sacrifice'] = baseline['total_pnl'] - abort_rows['total_pnl']
abort_rows['bust_reduction'] = baseline['bust_rate'] - abort_rows['bust_rate']
abort_rows['efficiency'] = abort_rows['bust_reduction'] / (abort_rows['pnl_sacrifice'].abs() + 1)

best = abort_rows.loc[abort_rows['efficiency'].idxmax()]
print(f'\nPareto-optimal abort level: K={best["abort_level"]}')
print(f'  Bust reduction: {best["bust_reduction"]:.4f} ({best["bust_reduction"]/baseline["bust_rate"]*100:.1f}%)')
print(f'  PnL sacrifice:  ${best["pnl_sacrifice"]:.2f}')
print(f'\nConclusion: fixed-level abort at K={best["abort_level"]} is the optimal static policy.')
print('Next: test if margin-aware dynamic abort can improve on this — see 07_hp_interactions/')
```

- [ ] **Step 3: Write `04_partial_abort.py`**

```python
#!/usr/bin/env python3
"""
Can closing only the worst-performing tickets (not all) outperform full abort?
Simulate: at level K, close only tickets with pnl < -threshold, keep best.
This is a heuristic test — full simulation requires engine changes.
Use N-to-1 math to estimate impact.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
import numpy as np

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
all_csv = os.path.join('notebooks', '02_bust_anatomy', 'results', 'all_sessions.csv')
if not os.path.exists(all_csv):
    print('Run bust anatomy first.'); import sys; sys.exit(1)

sessions = pd.read_csv(all_csv)
wins  = sessions[~sessions['is_bust']]
busts = sessions[sessions['is_bust']]

# Geometric sizing: at level N, losing ticket is lot_N * avg_loss
# Full abort at level K locks in sum of all tickets' losses
# Partial abort (keep L0 only): locks in sum of levels 1..K but keeps L0 running
# Estimate: if L0 keeps running with fresh context, it has p(win) = base win rate

BASE_WIN_RATE = len(wins) / len(sessions)
AVG_WIN = wins['pnl'].mean()
AVG_BUST = busts['pnl'].mean()

print('Partial abort analysis (theoretical):')
print(f'Base win rate: {BASE_WIN_RATE:.3f}')
print(f'Avg win: ${AVG_WIN:.2f}  Avg bust: ${AVG_BUST:.2f}')

for K in [3, 4, 5, 6]:
    # Full abort: realize full bust loss at level K
    # Partial: lose levels 1..K-1, keep L0 → L0 has p(win) chance
    # Geometric: level K loss ≈ 2^K * base_unit loss
    # Rough model: partial saves the L0 win if lucky
    ev_full_abort   = 0  # abort = 0 PnL, just stop
    ev_partial_keep = BASE_WIN_RATE * AVG_WIN + (1 - BASE_WIN_RATE) * (AVG_BUST * 0.7)
    print(f'  K={K}: EV(full_abort)=$0  EV(partial_keep_L0)=${ev_partial_keep:.2f}')

print('\nConclusion: partial abort can be positive EV if L0 ticket retains base win rate.')
print('Requires engine support to close individual tickets. Log to 09_synthesis/03_open_questions.md')
```

- [ ] **Step 4: Run all**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/06_abort_theory/02_point_of_no_return.py
/Users/naresh/miniconda3/bin/python3 notebooks/06_abort_theory/03_optimal_abort_level.py
/Users/naresh/miniconda3/bin/python3 notebooks/06_abort_theory/04_partial_abort.py
```

- [ ] **Step 5: Commit**

```bash
git add notebooks/06_abort_theory/
git commit -m "research(06): abort theory — point of no return, optimal level, partial abort"
```

---

## Task 16: 07_hp_interactions — sizing × levels surface and heatmaps

**Files:**
- Create: `notebooks/07_hp_interactions/01_sizing_x_levels.py`
- Create: `notebooks/07_hp_interactions/02_hedge_x_tp.py`
- Create: `notebooks/07_hp_interactions/03_equity_sensitivity.py`
- Create: `notebooks/07_hp_interactions/04_interaction_heatmaps.py`

- [ ] **Step 1: Write `01_sizing_x_levels.py`**

```python
#!/usr/bin/env python3
"""
Safe region of (sizing_factor, max_levels) given $10k equity, 30:1 leverage.
Use margin cushion map + empirical bust_rate to draw the feasibility frontier.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, save_fig, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

candles = load_candles()
SFS = [1.3, 1.5, 1.7, 2.0, 2.5, 3.0]
MLS = [3, 4, 5, 6, 7, 8]

records = []
total = len(SFS) * len(MLS)
i = 0
for sf in SFS:
    for ml in MLS:
        i += 1
        hp = {**CANONICAL_HP, 'sizing_factor': sf, 'max_levels': ml}
        r = run_backtest(hp, candles=candles)
        df = sessions_to_df(r.get('sessions', []))
        if df.empty: continue
        bust_rate = df['is_bust'].mean()
        total_pnl = df['pnl'].sum()
        records.append({'sf': sf, 'ml': ml, 'bust_rate': bust_rate, 'total_pnl': total_pnl})
        print(f'[{i}/{total}] sf={sf} ml={ml}: bust_rate={bust_rate:.4f}')

df_r = pd.DataFrame(records)
df_r.to_csv(os.path.join(RESULTS, 'sizing_x_levels.csv'), index=False)

pivot = df_r.pivot(index='sf', columns='ml', values='bust_rate')
fig, ax = plt.subplots(figsize=(9, 6))
im = ax.imshow(pivot.values, aspect='auto', cmap='RdYlGn_r', vmin=0, vmax=0.05)
ax.set_xticks(range(len(pivot.columns))); ax.set_xticklabels(pivot.columns)
ax.set_yticks(range(len(pivot.index))); ax.set_yticklabels([f'{s:.1f}' for s in pivot.index])
ax.set_xlabel('max_levels'); ax.set_ylabel('sizing_factor')
ax.set_title('Bust rate: sizing_factor × max_levels\n(Green = safe, Red = high bust)')
for r in range(pivot.shape[0]):
    for c in range(pivot.shape[1]):
        v = pivot.values[r, c]
        if not np.isnan(v):
            ax.text(c, r, f'{v:.3f}', ha='center', va='center', fontsize=8)
plt.colorbar(im, ax=ax)
save_fig(fig, os.path.join(RESULTS, 'sizing_x_levels_heatmap.png'))
print('Saved. Safe region = green zone. Log boundary to 09_synthesis/02_pipeline_implications.md')
```

- [ ] **Step 2: Write `02_hedge_x_tp.py`**

```python
#!/usr/bin/env python3
"""Degenerate case: hedge == TP. Also test hedge > TP and hedge < TP."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd
from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df, CANONICAL_HP

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)
candles = load_candles()

configs = [
    {'hedge': 10, 'tp': 5,  'label': 'hedge > TP'},
    {'hedge': 10, 'tp': 10, 'label': 'hedge == TP (degenerate)'},
    {'hedge': 10, 'tp': 15, 'label': 'hedge < TP (1.5x)'},
    {'hedge': 10, 'tp': 20, 'label': 'hedge < TP (2x)'},
    {'hedge': 10, 'tp': 30, 'label': 'hedge < TP (3x)'},
]
records = []
for cfg in configs:
    hp = {**CANONICAL_HP, 'hedge_value': cfg['hedge'], 'tp_value': cfg['tp']}
    r = run_backtest(hp, candles=candles)
    df = sessions_to_df(r.get('sessions', []))
    if df.empty: continue
    records.append({'label': cfg['label'], 'hedge': cfg['hedge'], 'tp': cfg['tp'],
                    'bust_rate': df['is_bust'].mean(), 'total_pnl': df['pnl'].sum(),
                    'n_sessions': len(df)})
    print(f"{cfg['label']}: bust_rate={df['is_bust'].mean():.4f}  pnl=${df['pnl'].sum():.2f}")

pd.DataFrame(records).to_csv(os.path.join(RESULTS, 'hedge_x_tp.csv'), index=False)
print('\nIf hedge==TP shows anomalous bust_rate, log to anomalies.md')
```

- [ ] **Step 3: Write `03_equity_sensitivity.py`** (reuse capital boundary data)

```python
#!/usr/bin/env python3
"""Survivability sensitivity to starting equity — extend capital boundary analysis."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pandas as pd

cap_csv = os.path.join('notebooks', '01_finite_capital', 'results', 'capital_boundary.csv')
if not os.path.exists(cap_csv):
    print('Run 01_finite_capital/03_capital_boundary.py first.'); sys.exit(1)

df = pd.read_csv(cap_csv)
print('Equity sensitivity (from capital boundary data):')
print(df[['config','equity','bust_rate','net_pct']].to_string(index=False))

# Find inflection: where bust_rate increases sharply
for config in df['config'].unique():
    sub = df[df['config'] == config].sort_values('equity')
    sub = sub.copy()
    sub['bust_delta'] = sub['bust_rate'].diff()
    inflection = sub.loc[sub['bust_delta'].idxmax()]
    print(f"\n{config}: bust_rate inflects at equity=${inflection['equity']:,} "
          f"(Δbust_rate={inflection['bust_delta']:.4f})")
    print(f'  This is the minimum safe equity for this config.')
```

- [ ] **Step 4: Write `04_interaction_heatmaps.py`**

```python
#!/usr/bin/env python3
"""
Compile all pairwise interaction data into a unified figure for pipeline bounds.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

# Load sizing x levels
csv1 = os.path.join(RESULTS, 'sizing_x_levels.csv')
# Load hedge x tp
csv2 = os.path.join(RESULTS, 'hedge_x_tp.csv')
# Load capital boundary
csv3 = os.path.join('notebooks', '01_finite_capital', 'results', 'capital_boundary.csv')

fig, axes = plt.subplots(1, 3, figsize=(18, 5))
fig.suptitle('HP Interaction Maps — Pipeline Gene Bound Justification', fontsize=13)

if os.path.exists(csv1):
    df1 = pd.read_csv(csv1)
    pivot = df1.pivot(index='sf', columns='ml', values='bust_rate')
    axes[0].imshow(pivot.values, aspect='auto', cmap='RdYlGn_r')
    axes[0].set_title('sizing_factor × max_levels\n(bust rate)')
    axes[0].set_xlabel('max_levels')
    axes[0].set_ylabel('sizing_factor')

if os.path.exists(csv2):
    df2 = pd.read_csv(csv2)
    axes[1].bar(range(len(df2)), df2['bust_rate'], color='steelblue')
    axes[1].set_xticks(range(len(df2)))
    axes[1].set_xticklabels(df2['label'], rotation=15, ha='right', fontsize=8)
    axes[1].set_title('hedge × TP ratio\n(bust rate)')

if os.path.exists(csv3):
    df3 = pd.read_csv(csv3)
    for cfg in df3['config'].unique():
        sub = df3[df3['config'] == cfg]
        axes[2].plot(sub['equity'], sub['bust_rate'], 'o-', label=cfg)
    axes[2].set_xscale('log')
    axes[2].set_title('Equity sensitivity\n(bust rate vs capital)')
    axes[2].set_xlabel('Starting equity ($)')
    axes[2].legend()

plt.tight_layout()
save_fig(fig, os.path.join(RESULTS, 'interaction_heatmaps.png'))
print('Unified interaction heatmaps saved.')
print('Use these to update IslandPilot _BOUND_OVERRIDES in island_evolver.py')
```

- [ ] **Step 5: Run all**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/07_hp_interactions/01_sizing_x_levels.py
/Users/naresh/miniconda3/bin/python3 notebooks/07_hp_interactions/02_hedge_x_tp.py
/Users/naresh/miniconda3/bin/python3 notebooks/07_hp_interactions/03_equity_sensitivity.py
/Users/naresh/miniconda3/bin/python3 notebooks/07_hp_interactions/04_interaction_heatmaps.py
```

- [ ] **Step 6: Commit**

```bash
git add notebooks/07_hp_interactions/
git commit -m "research(07): HP interaction surfaces — sizing×levels, hedge×tp, equity sensitivity"
```

---

## Task 17: 08_broker_mechanics — lot rounding + margin closeout + generalized model

**Files:**
- Create: `notebooks/08_broker_mechanics/01_lot_rounding.py`
- Create: `notebooks/08_broker_mechanics/02_margin_closeout_model.py`
- Create: `notebooks/08_broker_mechanics/03_oanda_vs_generalized.py`

- [ ] **Step 1: Write `01_lot_rounding.py`**

```python
#!/usr/bin/env python3
"""
OANDA rounds positions to integer units. Does rounding cause systematic under/over-hedging?
At small equity, rounding error as % of intended position is non-negligible.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import numpy as np
import pandas as pd

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

PRICE = 1.10; EQUITY_LEVELS = [1_000, 2_500, 5_000, 10_000, 25_000]
SFS = [1.5, 2.0, 2.5]; BASE_PCT = 0.5

records = []
for eq in EQUITY_LEVELS:
    for sf in SFS:
        for level in range(9):
            target_notional = (BASE_PCT / 100 * eq)
            target_units_float = target_notional * (sf ** level) / PRICE
            rounded_units = int(round(target_units_float))
            rounding_error_pct = (rounded_units - target_units_float) / target_units_float * 100 if target_units_float > 0 else 0
            records.append({'equity': eq, 'sf': sf, 'level': level,
                            'target_units': target_units_float,
                            'rounded_units': rounded_units,
                            'error_pct': rounding_error_pct})

df = pd.DataFrame(records)
# Focus on cases where rounding error > 5%
significant = df[df['error_pct'].abs() > 5]
print(f'Rounding errors > 5%: {len(significant)} cases')
print(significant[['equity','sf','level','target_units','rounded_units','error_pct']].head(20).to_string(index=False))

# Summary: at low equity, what's the max rounding error?
for eq in EQUITY_LEVELS:
    sub = df[df['equity'] == eq]
    print(f'Equity ${eq:,}: max rounding error = {sub["error_pct"].abs().max():.1f}%')

df.to_csv(os.path.join(RESULTS, 'lot_rounding.csv'), index=False)
print('\nIf error > 10% at any level, strategy is systematically mis-hedging at that equity level.')
```

- [ ] **Step 2: Write `02_margin_closeout_model.py`**

```python
#!/usr/bin/env python3
"""
NAV-based vs equity-based margin closeout: OANDA uses NAV (Net Asset Value).
NAV = balance + unrealized_pnl. Equity-based = just balance.
At deep levels with negative unrealized, NAV falls faster than equity → earlier closeout.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from notebooks.shared.utils import save_fig

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

EQUITY = 10_000; MARGIN_RATE = 1/30; PRICE = 1.10; LOT_SIZE = 100_000
BASE_LOTS = 0.01; SF = 2.0; SPREAD = 20  # pips, adverse move at each hedge

fig, ax = plt.subplots(figsize=(10, 5))
for model, color, label in [('nav', 'crimson', 'NAV-based (OANDA)'), ('equity', 'steelblue', 'Equity-based')]:
    balance = EQUITY
    nav_history = []
    margin_used = 0
    unrealized = 0
    for n in range(9):
        lot_n = BASE_LOTS * (SF ** n)
        margin_n = lot_n * PRICE * LOT_SIZE * MARGIN_RATE
        margin_used += margin_n
        # Adverse move = hedge triggered, so unrealized on this ticket = -spread * lots
        unrealized -= SPREAD * 0.0001 * lot_n * LOT_SIZE
        nav = balance + unrealized
        check = nav if model == 'nav' else balance
        margin_pct = margin_used / check * 100
        nav_history.append({'level': n, 'nav': nav, 'margin_pct': margin_pct, 'forced': margin_pct >= 100})
        if margin_pct >= 100:
            print(f'{label}: forced close at level {n} (margin={margin_pct:.0f}%)')
            break
    levels = [x['level'] for x in nav_history]
    pcts   = [x['margin_pct'] for x in nav_history]
    ax.plot(levels, pcts, 'o-', color=color, label=label)

ax.axhline(100, color='red', linestyle='--', label='Closeout threshold (100%)')
ax.set_xlabel('Level'); ax.set_ylabel('Margin utilization %')
ax.set_title('NAV-based vs equity-based margin closeout\n(NAV closes earlier due to unrealized losses)')
ax.legend(); ax.grid(True, alpha=0.3)
save_fig(fig, os.path.join(RESULTS, 'margin_closeout_model.png'))
print('Key: NAV-based closeout at OANDA happens earlier than theory predicts.')
```

- [ ] **Step 3: Write `03_oanda_vs_generalized.py`**

```python
#!/usr/bin/env python3
"""
Generalized broker model: parameterized by (margin_rate, lot_unit, closeout_basis).
Instantiate with OANDA params and show how results change vs an idealized broker.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import numpy as np
import pandas as pd

RESULTS = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(RESULTS, exist_ok=True)

def broker_model(name, margin_rate, min_lot, lot_size, closeout_basis,
                 equity, base_pct, sf, max_levels, spread_pips):
    """Simulate margin trajectory for a parameterized broker."""
    records = []
    base_lots = (base_pct / 100 * equity) / (1.10 * lot_size)
    margin_used = 0; unrealized = 0; balance = equity
    for n in range(max_levels + 1):
        lot_n = max(min_lot, round(base_lots * (sf ** n) / min_lot) * min_lot)
        margin_n = lot_n * 1.10 * lot_size * margin_rate
        margin_used += margin_n
        unrealized -= spread_pips * 0.0001 * lot_n * lot_size
        nav = balance + unrealized
        check = nav if closeout_basis == 'nav' else balance
        margin_pct = margin_used / check * 100 if check > 0 else 999
        records.append({'broker': name, 'level': n, 'margin_pct': margin_pct,
                        'forced': margin_pct >= 100, 'lots': lot_n})
        if margin_pct >= 100:
            break
    return pd.DataFrame(records)

brokers = [
    dict(name='OANDA (real)', margin_rate=1/30, min_lot=1, lot_size=1,
         closeout_basis='nav', spread_pips=2),
    dict(name='Idealized (no spread, equity-based)', margin_rate=1/30, min_lot=0.001,
         lot_size=100_000, closeout_basis='equity', spread_pips=0),
    dict(name='High-leverage CFD (50:1)', margin_rate=1/50, min_lot=0.001,
         lot_size=100_000, closeout_basis='equity', spread_pips=1),
]

all_results = []
for b in brokers:
    df = broker_model(**b, equity=10_000, base_pct=0.5, sf=2.0, max_levels=8)
    all_results.append(df)
    max_safe_level = df[~df['forced']]['level'].max() if (~df['forced']).any() else -1
    print(f"{b['name']}: max safe level = {max_safe_level}")

combined = pd.concat(all_results)
combined.to_csv(os.path.join(RESULTS, 'oanda_vs_generalized.csv'), index=False)
print('\nSaved. OANDA real vs idealized broker shows structural gap in achievable levels.')
```

- [ ] **Step 4: Run all**

```bash
/Users/naresh/miniconda3/bin/python3 notebooks/08_broker_mechanics/01_lot_rounding.py
/Users/naresh/miniconda3/bin/python3 notebooks/08_broker_mechanics/02_margin_closeout_model.py
/Users/naresh/miniconda3/bin/python3 notebooks/08_broker_mechanics/03_oanda_vs_generalized.py
```

- [ ] **Step 5: Commit**

```bash
git add notebooks/08_broker_mechanics/
git commit -m "research(08): broker mechanics — lot rounding, NAV closeout, generalized model"
```

---

## Task 18: 09_synthesis — compile findings

**Files:**
- Write: `notebooks/09_synthesis/01_novel_findings.md`
- Write: `notebooks/09_synthesis/02_pipeline_implications.md`

- [ ] **Step 1: After all prior tasks complete, fill `01_novel_findings.md`**

Review all results CSVs and plots. For each finding that is NOT in `facts.md`, add an entry:

```markdown
## Finding 1: N-to-1 ratio varies N× across configurations
**Source:** `01_finite_capital/results/n_to_1_ratio.csv`
**What:** [fill with actual numbers from script output]
**Why novel:** Facts.md states N-to-1 exists "in abstract" but no paper derives it
as a function of (sizing_factor, max_levels).

## Finding 2: Broker closes before max_levels at [specific configs]
**Source:** `03_margin_mechanics/results/implicit_forced_close.csv`
**What:** [fill with actual threshold]
**Why novel:** All theory assumes you reach max_levels. OANDA NAV-based closeout
triggers early.

## Finding 3: Optimal abort level is not the same as point of no return
**Source:** `06_abort_theory/results/`
**What:** [fill with specific levels from output]
**Why novel:** Papers treat abort as binary (abort/no-abort). Optimal K exists
on a smooth EV curve.
```

- [ ] **Step 2: Fill `02_pipeline_implications.md`**

```markdown
## IslandPilot island_evolver.py — _BOUND_OVERRIDES update
**Source:** `07_hp_interactions/results/sizing_x_levels.csv` + `03_margin_mechanics/results/margin_cushion_map.png`
**Before:**
```python
'max_levels': (2, 6, int),
'sizing_factor': (1.2, 2.0, float),
```
**After:** [fill with empirically justified bounds from heatmap results]
**Why:** Safe region from bust rate + margin maps shows actual feasibility boundary.

## ARIA danger threshold calibration
**Source:** `06_abort_theory/results/abort_vs_no_abort.csv`
**Implication:** Set danger threshold at level K=[fill from optimal_abort_level output].
```

- [ ] **Step 3: Commit synthesis**

```bash
git add notebooks/09_synthesis/
git commit -m "research(09): synthesis — novel findings and pipeline implications"
```

---

## Task 19: Final verification

- [ ] **Step 1: Verify all result files exist**

```bash
find notebooks/ -name "*.csv" -o -name "*.png" | sort
```
Expected: at least 20+ output files across all directories.

- [ ] **Step 2: Verify no 2025 data was used**

```bash
grep -r "2025\|2026" notebooks/ --include="*.py" | grep -v "DATA_END\|assert\|#"
```
Expected: no hits (any hit means a script violated the data boundary).

- [ ] **Step 3: Final commit**

```bash
git add notebooks/
git commit -m "research: all anatomy scripts complete — ready for synthesis review"
```
