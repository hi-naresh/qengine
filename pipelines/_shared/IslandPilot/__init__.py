"""
IslandPilot — adaptive regime-aware pipeline for the Surefire strategy family.

Combines hierarchical regime detection (GMM tree), per-regime genetic parameter
evolution (island model), hysteresis-based inference, and adaptive position sizing
into a single Pipeline that wraps any strategy without modifying its code.
"""

import os
from typing import Any, Dict, List, Optional

import numpy as np

from qengine.framework.base import Pipeline, OrderIntent
from qengine.framework.components.feature_selector import FeaturePool
from qengine.framework.components.regime_tree import RegimeTree
from qengine.framework.components.island_evolver import IslandEvolver, SIZING_CURVE_MAP
from qengine.framework.components.regime_inferencer import RegimeInferencer
from qengine.framework.components.adaptive_sizer import AdaptiveSizer

from .config import DEFAULT_CONFIG, merge_config

# Path to shipped model artifacts (populated after research training)
_MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')


def _load_pretrained() -> dict:
    """Load pre-trained models from the models/ directory if available.

    Returns dict with keys 'regime_tree', 'evolver', 'inferencer' (or empty).
    """
    result = {}
    tree_path = os.path.join(_MODELS_DIR, 'regime_tree.pkl')
    if os.path.exists(tree_path):
        result['regime_tree'] = RegimeTree.load(tree_path)

        evolver_path = os.path.join(_MODELS_DIR, 'island_genomes.json')
        if os.path.exists(evolver_path):
            result['evolver'] = IslandEvolver.load(evolver_path)

        inferencer_path = os.path.join(_MODELS_DIR, 'inferencer_state.json')
        if os.path.exists(inferencer_path):
            result['inferencer'] = RegimeInferencer.load(
                inferencer_path, result['regime_tree']
            )
    return result


class IslandPilot(Pipeline):
    """Regime-aware adaptive pipeline with island-model evolution."""

    name = 'IslandPilot'

    def __init__(self, config: Optional[dict] = None):
        self.cfg = merge_config(config or {})

        # Components
        self.feature_pool = FeaturePool()
        self.regime_tree: Optional[RegimeTree] = None
        self.evolver: Optional[IslandEvolver] = None
        self.inferencer: Optional[RegimeInferencer] = None
        self.sizer = AdaptiveSizer(self.cfg['sizing'])

        # Runtime state
        self._active_regime: Optional[int] = None
        self._active_confidence: float = 0.0
        self._active_genome: Optional[dict] = None
        self._candle_count: int = 0
        self._feature_vector: Optional[np.ndarray] = None
        self._cycle_count: int = 0
        self._sibling_groups: Dict[str, List[str]] = {}

        # Auto-load pre-trained models if available
        self._load_pretrained_models()

    # ------------------------------------------------------------------
    # Pipeline hooks
    # ------------------------------------------------------------------

    def on_before(self, strategy) -> None:
        """Compute features, classify regime, apply genome to strategy."""
        self._candle_count += 1

        candles = getattr(strategy, 'candles', None)
        if candles is None or len(candles) < self.cfg['warmup']:
            return

        # Compute features for the latest candle
        try:
            features = self.feature_pool.compute(candles)
            self._feature_vector = features[-1]
        except Exception:
            self._feature_vector = None
            return

        if self._feature_vector is None:
            return

        # Classify regime
        if self.inferencer is not None:
            try:
                regime_id, confidence, _probs = self.inferencer.classify(
                    self._feature_vector
                )
                self._active_regime = regime_id
                self._active_confidence = confidence
            except Exception:
                self._active_regime = None
                self._active_confidence = 0.0
        elif self.regime_tree is not None:
            try:
                regime_id, confidence = self.regime_tree.classify_best(
                    self._feature_vector
                )
                self._active_regime = regime_id
                self._active_confidence = confidence
            except Exception:
                self._active_regime = None
                self._active_confidence = 0.0

        # Apply best genome for active regime
        if self._active_regime is not None and self.evolver is not None:
            regime_key = str(self._active_regime)
            try:
                genome_dict = self.evolver.get_best_genome(regime_key)
                self._active_genome = genome_dict.get('genes', genome_dict)
                self._apply_genome(strategy, self._active_genome)
            except (KeyError, Exception):
                self._active_genome = None
        else:
            self._active_genome = None

    def gate_entry(self, strategy) -> bool:
        """Block entry if no genome available, low confidence, or in grace period."""
        # During warmup, block
        if self._candle_count < self.cfg['warmup']:
            return False

        # No genome means the regime/evolver isn't ready
        if self._active_genome is None:
            return False

        # Low confidence
        min_conf = self.cfg['inference']['min_confidence']
        if self._active_confidence < min_conf:
            return False

        # Grace period after regime switch
        if self.inferencer is not None and self.inferencer.in_grace_period:
            return False

        return True

    def adjust_size(self, strategy, qty: float, side: str) -> float:
        """Scale position size using AdaptiveSizer."""
        if self._active_genome is None:
            return qty

        genome = self._active_genome
        base_pct = genome.get('base_size_pct', 1.0)
        confidence = self._active_confidence
        sensitivity = genome.get('confidence_sensitivity', 1.0)
        recovery_aggression = genome.get('recovery_aggression', 0.5)

        # Get drawdown from strategy if available
        drawdown_pct = 0.0
        if hasattr(strategy, 'portfolio') and hasattr(strategy.portfolio, 'max_drawdown'):
            drawdown_pct = abs(strategy.portfolio.max_drawdown)
        elif hasattr(strategy, 'drawdown_pct'):
            drawdown_pct = strategy.drawdown_pct

        # Get balance
        balance = 10000.0  # default
        if hasattr(strategy, 'portfolio') and hasattr(strategy.portfolio, 'equity'):
            balance = strategy.portfolio.equity
        elif hasattr(strategy, 'balance'):
            balance = strategy.balance

        return self.sizer.compute(
            base_pct=base_pct,
            confidence=confidence,
            sensitivity=sensitivity,
            drawdown_pct=drawdown_pct,
            recovery_aggression=recovery_aggression,
            balance=balance,
            qty=qty,
        )

    def filter_order(self, strategy, order_intent: OrderIntent) -> Optional[OrderIntent]:
        """Inject evolved TP/hedge params into orders if genome is active."""
        if self._active_genome is None:
            return order_intent

        genome = self._active_genome

        # For entry orders, we could adjust price based on genome params
        # but the main injection happens via _apply_genome in on_before.
        # Here we can override TP distance or hedge distance if the order
        # is a TP or SL type.
        if not order_intent.is_entry and order_intent.type == 'limit':
            # Potential TP order — genome may have tp_distance_atr_mult
            tp_mult = genome.get('tp_distance_atr_mult')
            if tp_mult is not None and self._feature_vector is not None:
                # We don't modify the actual price here; the strategy
                # uses hp dict which was already set in on_before.
                pass

        return order_intent

    def suggest_exit(self, strategy) -> Optional[dict]:
        """Abort based on danger proxy exceeding genome threshold."""
        if self._active_genome is None:
            return None

        danger = self._compute_danger(strategy)
        abort_threshold = self._active_genome.get('abort_aggressiveness', 0.5)

        if danger > abort_threshold:
            return {'action': 'close_all'}

        return None

    def on_cycle_end(self, pnl: float, strategy) -> None:
        """Record outcome for the evolver."""
        self._cycle_count += 1

        if self.evolver is not None and self._active_regime is not None:
            self.evolver.record_outcome(
                regime_id=str(self._active_regime),
                pnl=pnl,
                cycle=self._cycle_count,
                genome=self._active_genome,
            )

    # ------------------------------------------------------------------
    # Stats & persistence
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Comprehensive stats from all components."""
        stats: Dict[str, Any] = {
            'active_regime': self._active_regime,
            'active_confidence': self._active_confidence,
            'candle_count': self._candle_count,
            'cycle_count': self._cycle_count,
            'has_genome': self._active_genome is not None,
        }

        if self.regime_tree is not None:
            stats['n_leaves'] = self.regime_tree.n_leaves
            stats['leaf_ids'] = self.regime_tree.leaf_ids

        if self.inferencer is not None:
            stats['regime_counts'] = self.inferencer.get_regime_counts()
            stats['n_transitions'] = len(self.inferencer.get_transition_log())

        if self.evolver is not None:
            stats['fitness_summary'] = self.evolver.get_fitness_summary()
            stats['diversity'] = self.evolver.get_diversity_stats()
            stats['n_migrations'] = len(self.evolver.get_migration_log())

        stats['sizer'] = self.sizer.get_stats()

        return stats

    def save_state(self, path: str) -> None:
        """Persist all components to disk."""
        os.makedirs(path, exist_ok=True)

        if self.regime_tree is not None:
            self.regime_tree.save(os.path.join(path, 'regime_tree.pkl'))

        if self.evolver is not None:
            self.evolver.save(os.path.join(path, 'evolver.json'))

        if self.inferencer is not None:
            self.inferencer.save(os.path.join(path, 'inferencer.json'))

        self.sizer.save(os.path.join(path, 'sizer.json'))

        # Save runtime state
        import json
        runtime = {
            'candle_count': self._candle_count,
            'cycle_count': self._cycle_count,
            'active_regime': self._active_regime,
            'active_confidence': self._active_confidence,
            'sibling_groups': self._sibling_groups,
        }
        with open(os.path.join(path, 'runtime.json'), 'w') as f:
            json.dump(runtime, f, indent=2)

    def load_state(self, path: str) -> None:
        """Restore all components from disk."""
        import json

        tree_path = os.path.join(path, 'regime_tree.pkl')
        if os.path.exists(tree_path):
            self.regime_tree = RegimeTree.load(tree_path)

        evolver_path = os.path.join(path, 'evolver.json')
        if os.path.exists(evolver_path):
            self.evolver = IslandEvolver.load(evolver_path)

        inferencer_path = os.path.join(path, 'inferencer.json')
        if os.path.exists(inferencer_path) and self.regime_tree is not None:
            self.inferencer = RegimeInferencer.load(inferencer_path, self.regime_tree)

        sizer_path = os.path.join(path, 'sizer.json')
        if os.path.exists(sizer_path):
            self.sizer = AdaptiveSizer.load(sizer_path)

        runtime_path = os.path.join(path, 'runtime.json')
        if os.path.exists(runtime_path):
            with open(runtime_path) as f:
                runtime = json.load(f)
            self._candle_count = runtime.get('candle_count', 0)
            self._cycle_count = runtime.get('cycle_count', 0)
            self._active_regime = runtime.get('active_regime')
            self._active_confidence = runtime.get('active_confidence', 0.0)
            self._sibling_groups = runtime.get('sibling_groups', {})

    @classmethod
    def default_config(cls) -> dict:
        """Default configuration for this pipeline."""
        return merge_config({})

    @classmethod
    def architecture(cls) -> dict:
        """Return pipeline architecture metadata for the frontend."""
        return {
            'name': 'IslandPilot',
            'description': 'Regime-aware adaptive pipeline with island-model genetic evolution',
            'components': [
                {
                    'name': 'FeaturePool',
                    'role': 'Computes ~25 market features across 5 categories',
                    'type': 'feature_extractor',
                },
                {
                    'name': 'RegimeTree',
                    'role': 'Hierarchical GMM clustering for regime discovery',
                    'type': 'classifier',
                },
                {
                    'name': 'IslandEvolver',
                    'role': 'Per-regime genetic parameter optimization',
                    'type': 'optimizer',
                },
                {
                    'name': 'RegimeInferencer',
                    'role': 'Sticky regime classification with hysteresis',
                    'type': 'inferencer',
                },
                {
                    'name': 'AdaptiveSizer',
                    'role': 'Confidence and drawdown-based position sizing',
                    'type': 'sizer',
                },
            ],
            'hooks': [
                'on_before', 'gate_entry', 'adjust_size',
                'filter_order', 'suggest_exit', 'on_cycle_end',
            ],
            'state_space': {
                'regime_tree': 'pickle',
                'evolver': 'json',
                'inferencer': 'json',
                'sizer': 'json',
                'runtime': 'json',
            },
        }

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_pretrained_models(self) -> None:
        """Auto-load pre-trained models from models/ directory on init."""
        pretrained = _load_pretrained()
        if not pretrained:
            return

        self.regime_tree = pretrained.get('regime_tree')
        self.evolver = pretrained.get('evolver')
        self.inferencer = pretrained.get('inferencer')

        # If we have a tree but no inferencer, create one
        if self.regime_tree is not None and self.inferencer is None:
            self.inferencer = RegimeInferencer(
                self.regime_tree, self.cfg['inference']
            )

        # Build sibling groups for migration
        if self.regime_tree is not None:
            self._build_sibling_groups()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_genome(self, strategy, genome: dict) -> None:
        """Override strategy.hp dict with genome parameters."""
        if not hasattr(strategy, 'hp'):
            return

        hp = strategy.hp

        # Map genome keys to strategy hyperparameters
        mapping = {
            'max_levels': 'max_levels',
            'tp_distance_atr_mult': 'tp_distance_atr_mult',
            'hedge_distance_atr_mult': 'hedge_distance_atr_mult',
            'base_size_pct': 'base_size_pct',
        }

        for genome_key, hp_key in mapping.items():
            if genome_key in genome:
                hp[hp_key] = genome[genome_key]

        # Convert sizing_curve from int/string to the strategy's expected format
        sizing_curve = genome.get('sizing_curve')
        if sizing_curve is not None:
            if isinstance(sizing_curve, int):
                hp['sizing_curve'] = SIZING_CURVE_MAP.get(sizing_curve, 'geometric')
            else:
                hp['sizing_curve'] = sizing_curve

    def _compute_danger(self, strategy) -> float:
        """Simple volatility-based danger proxy in [0, 1]."""
        candles = getattr(strategy, 'candles', None)
        if candles is None or len(candles) < 20:
            return 0.0

        # Use recent close-to-close returns volatility
        closes = candles[-20:, 2]
        if closes[0] == 0:
            return 0.0

        returns = np.diff(closes) / (closes[:-1] + 1e-12)
        vol = np.std(returns)

        # Normalize: typical FX vol ~0.001-0.01, scale to [0, 1]
        # Use a sigmoid-like mapping
        danger = float(np.clip(vol / 0.01, 0.0, 1.0))
        return danger

    def _build_sibling_groups(self) -> Dict[str, List[str]]:
        """Build sibling groups from regime tree leaf map.

        Siblings are leaves that share the same macro cluster.
        """
        if self.regime_tree is None:
            return {}

        macro_to_leaves: Dict[int, List[str]] = {}
        for leaf_id, (macro_id, _sub_id) in self.regime_tree._leaf_map.items():
            macro_to_leaves.setdefault(macro_id, []).append(str(leaf_id))

        groups = {}
        for macro_id, leaves in macro_to_leaves.items():
            if len(leaves) > 1:
                groups[f'macro_{macro_id}'] = leaves

        self._sibling_groups = groups
        return groups
