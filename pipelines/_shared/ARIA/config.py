"""
ARIA pipeline configuration defaults and HP schema utilities.
"""


def default_config() -> dict:
    """Default ARIA configuration shown in frontend / backtest UI."""
    return {
        # Layer 1 — MarketBrain
        'brain_warmup': 50,
        'brain_k_max': 5,

        # Layer 2 — CycleGate (Phase 2)
        'gate_enabled': False,         # disabled until Phase 2
        'gate_warmup_cycles': 30,
        'gate_learning_rate': 0.01,
        'gate_threshold': 0.0,

        # Layer 3 — HPEngine (Phase 2)
        'hp_engine_enabled': False,    # disabled until Phase 2
        'hp_warmup_cycles': 20,
        'hp_max_arms_per_group': 50,

        # Layer 4 — RiskShield
        'conformal_alpha': 0.1,
        'conformal_safety': 0.8,
        'fallback_level': 6,
        'max_ruin_prob': 0.5,

        # Layer 5 — Observer
        'max_sessions': 10_000,

        # Layer 6 — MetaEvaluator (Phase 3)
        'meta_enabled': False,         # disabled until Phase 3
        'meta_window': 100,
    }
