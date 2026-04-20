"""
IGTSPRingPilot pipeline — default configuration and merge utility.

Baseline: island-model GA with RING topology migration (no regime structure).
Mirrors IslandPilot's composite fitness formula and tuning constraints
so that cross-pipeline comparisons isolate the regime-awareness contribution.

Reference:
    Chideme, K., Chen, C.-H., & Lin, J. C.-W. (2025).
    "Island genetic algorithm with diverse migration strategies for
     efficient group trading strategy portfolio optimization."
    Engineering Optimization. DOI: 10.1080/0305215X.2025.2592030
"""
import copy
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    # ── Island topology ──
    'n_islands': 8,              # number of parallel populations
    'population_size': 10,       # individuals per island
    'migration_interval': 5,     # migrate every N generations (paper value)
    'migration_topology': 'ring',

    # ── Evolution operators ──
    'evolution': {
        'elitism': 1,
        'crossover_rate': 0.7,
        'mutation_rate': 0.2,
        'mutation_sigma_pct': 0.1,
        'tournament_k': 3,
    },

    # ── Runtime batch evolution ──
    'evolve_every_n_cycles': 30,  # how often on_cycle_end triggers a GA step
    'min_cycles_per_genome': 1,    # minimum observations before genome is fitness-evaluated
    'cycle_buffer_size': 100,      # rolling cycle outcomes per genome

    # ── Fitness composition (matches IslandPilot for fair comparison) ──
    'fitness_weights': {
        'profit_factor': 0.4,
        'drawdown': 0.3,
        'bust': 0.2,
        'sessions': 0.1,
    },

    # ── Pipeline basics ──
    'warmup': 10,
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def merge_config(user_config: dict) -> dict:
    if not user_config:
        return copy.deepcopy(DEFAULT_CONFIG)
    return _deep_merge(DEFAULT_CONFIG, user_config)
