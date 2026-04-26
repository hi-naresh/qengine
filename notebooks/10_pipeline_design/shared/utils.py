"""Pipeline-research helpers shared across pivots."""
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

ISLANDPILOT_MODELS = os.path.join(_ROOT, 'pipelines', '_shared', 'IslandPilot', 'models')


def load_pipeline_artifacts() -> dict:
    """Load trained IslandPilot artifacts as a dict.

    Returns keys: 'island_genomes' (list[dict] | None), 'feature_selector' (dict | None),
    'leaf_date_ranges' (dict | None). Missing files return None for that key rather
    than raising — pivots may run before all artifacts exist.
    """
    out = {}
    files = {
        'island_genomes': 'island_genomes.json',
        'feature_selector': 'feature_selector.json',
        'leaf_date_ranges': 'leaf_date_ranges.json',
    }
    for key, name in files.items():
        path = os.path.join(ISLANDPILOT_MODELS, name)
        if os.path.exists(path):
            with open(path) as f:
                out[key] = json.load(f)
        else:
            out[key] = None
    return out


def simulator_fitness(spread_pips: float, n_levels: int, sf: float, win_rate: float, n_cycles: int = 5000, seed: int = 0) -> dict:
    """Minimal cycle simulator: no spread shift, no margin, IID Bernoulli wins/busts.

    This is the surrogate Pivot 06 contrasts against. It deliberately omits
    cost realism so genomes evolved on it produce extreme HPs.

    Returns: {'total_pnl': float, 'avg_win': float, 'avg_bust': float,
              'bust_rate': float, 'n_busts': int}
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    base_unit = 1.0
    total_units = sum(sf ** k for k in range(n_levels))
    avg_win_units = base_unit
    avg_bust_units = -total_units
    n_busts = 0
    pnl = 0.0
    for _ in range(n_cycles):
        if rng.random() < win_rate:
            pnl += avg_win_units
        else:
            pnl += avg_bust_units
            n_busts += 1
    return {
        'total_pnl': pnl,
        'avg_win': avg_win_units,
        'avg_bust': avg_bust_units,
        'bust_rate': n_busts / n_cycles,
        'n_busts': n_busts,
    }


def engine_fitness(hp: dict, start_date: str = '2024-01-01', end_date: str = '2024-06-30') -> dict:
    """Thin wrapper around notebooks/shared/utils.py:run_backtest().

    Default range is a 6-month slice so pivot scripts complete in 1-2 minutes.
    Returns dict with: 'total_pnl', 'n_sessions', 'n_busts', 'bust_rate'.
    """
    from notebooks.shared.utils import run_backtest, load_candles, sessions_to_df
    candles = load_candles(start_date=start_date, end_date=end_date)
    r = run_backtest(hp, candles=candles)
    df = sessions_to_df(r.get('sessions', []))
    if df.empty:
        return {'total_pnl': 0.0, 'n_sessions': 0, 'n_busts': 0, 'bust_rate': 0.0}
    return {
        'total_pnl': float(df['pnl'].sum()),
        'n_sessions': int(len(df)),
        'n_busts': int(df['is_bust'].sum()),
        'bust_rate': float(df['is_bust'].mean()),
    }


def summarize_genome(genome: dict) -> str:
    """Pretty-print a genome grouped by HP family."""
    if 'genes' in genome:
        genes = genome['genes']
    else:
        genes = genome
    lines = []
    groupings = {
        'General': ['signal_mode', 'direction_bias', 'sizing_curve', 'sizing_factor', 'base_size_mode', 'base_size_value', 'max_levels'],
        'Grid/Hedge': ['hedge_mode', 'hedge_value'],
        'Take Profit': ['tp_mode', 'tp_value'],
        'Filters': [k for k in genes if k.startswith('filter_')],
        'Risk Management': ['abort_mode', 'abort_level', 'abort_aggressiveness'],
    }
    for group, keys in groupings.items():
        present = [(k, genes[k]) for k in keys if k in genes]
        if not present:
            continue
        lines.append(f'  [{group}]')
        for k, v in present:
            lines.append(f'    {k} = {v}')
    other = sorted(k for k in genes if not any(k in keys for keys in groupings.values()))
    if other:
        lines.append('  [Other]')
        for k in other:
            lines.append(f'    {k} = {genes[k]}')
    return '\n'.join(lines)
