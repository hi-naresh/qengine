"""
ARIA pipeline configuration defaults and HP schema utilities.
"""


def default_config() -> dict:
    """Default ARIA configuration shown in frontend / backtest UI."""
    return {
        # Layer 1 — MarketBrain
        'brain_warmup': 50,
        'brain_k_max': 5,

        # Layer 2 — CycleGate
        'gate_enabled': True,
        'gate_warmup_cycles': 5,
        'gate_learning_rate': 0.05,
        'gate_threshold': 0.0,

        # Layer 3 — HPEngine
        'hp_engine_enabled': True,
        'hp_warmup_cycles': 5,
        'hp_max_arms_per_group': 25,
        'hp_stale_bars': 200,          # re-select HPs if no entry after 200 bars (~17 hours)

        # Layer 4 — RiskShield
        'conformal_alpha': 0.1,
        'conformal_safety': 0.8,
        'fallback_level': 6,
        'max_ruin_prob': 0.5,
        'max_cycle_bars': 300,           # ~1 day at 5m — TP hits avg at 164 bars, abort at 2x
        'danger_abort_threshold': 0.65,  # abort at L3+ when danger > 0.65 (L3+ is catastrophic)
        'stress_enabled': False,             # R(t) structural stress — disabled pending param research
        'stress_abort_threshold': 1.5,    # stress velocity above which to abort
        'stress_abort_min_level': 2,      # min depth before stress abort activates

        # Layer 5 — Observer
        'max_sessions': 10_000,

        # Layer 6 — MetaEvaluator
        'meta_enabled': True,
        'meta_window': 100,
        'meta_degradation_sigma': 1.0,
    }
