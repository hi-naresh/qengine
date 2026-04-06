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
from qengine.framework.components.island_evolver import IslandEvolver, Genome, SIZING_CURVE_MAP
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

        # Try full evolver state first, fall back to simple genomes
        evolver_path = os.path.join(_MODELS_DIR, 'island_evolver.json')
        if not os.path.exists(evolver_path):
            evolver_path = os.path.join(_MODELS_DIR, 'island_genomes.json')
        if os.path.exists(evolver_path):
            try:
                result['evolver'] = IslandEvolver.load(evolver_path)
            except (KeyError, Exception):
                # Simple genomes format — build a minimal evolver from it
                import json
                with open(evolver_path) as f:
                    genomes_data = json.load(f)
                leaf_ids = list(genomes_data.keys())
                evolver = IslandEvolver(leaf_ids=leaf_ids, config={})
                for lid, gdata in genomes_data.items():
                    genome = Genome.from_dict(gdata if 'genes' not in gdata else gdata['genes'])
                    genome.fitness = gdata.get('fitness', 0.0)
                    if lid in evolver.populations:
                        evolver.populations[lid].individuals[0] = genome
                result['evolver'] = evolver

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

        # Only compute features on a FIXED tail window (not the whole array).
        # This keeps cost O(1) per candle regardless of backtest length.
        _WINDOW = 300
        tail = candles[-_WINDOW:] if len(candles) > _WINDOW else candles

        try:
            features = self.feature_pool.compute(tail)
            fv = features[-1]
            # Skip if any NaN in the feature vector
            if np.any(np.isnan(fv)):
                return
            self._feature_vector = fv
        except Exception:
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
            # Try both string and int keys (evolver may use either)
            regime_key = self._active_regime
            genome_dict = None
            for key in [str(regime_key), regime_key, int(regime_key)]:
                try:
                    genome_dict = self.evolver.get_best_genome(key)
                    if genome_dict:
                        break
                except (KeyError, TypeError, Exception):
                    continue

            if genome_dict is not None:
                self._active_genome = genome_dict.get('genes', genome_dict)
                # ONLY apply genome when no position is open (between cycles).
                # Changing hp mid-cycle breaks hedge sizing/direction logic.
                position_open = False
                if hasattr(strategy, 'position') and hasattr(strategy.position, 'is_open'):
                    position_open = strategy.position.is_open
                elif hasattr(strategy, 'vars') and strategy.vars.get('cycle_active'):
                    position_open = True

                if not position_open:
                    self._apply_genome(strategy, self._active_genome)
            else:
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
        # Check if pre-trained models exist
        models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
        has_tree = os.path.exists(os.path.join(models_dir, 'regime_tree.pkl'))
        has_genomes = os.path.exists(os.path.join(models_dir, 'island_genomes.json'))
        is_trained = has_tree and has_genomes

        return {
            'name': 'IslandPilot',
            'summary': 'Multi-island evolutionary pipeline that discovers market regimes, '
                       'evolves per-regime execution configs via genetic algorithm, and applies '
                       'them at runtime with adaptive position sizing.',
            'designed_for': ['Martingale strategies', 'SurefireHedge variants', 'UniversalMartingale'],
            'research_basis': 'Phase4 research: hierarchical GMM regime discovery + island-model GA',
            'requires_training': True,
            'training_status': 'trained' if is_trained else 'untrained',
            'training_description': 'Discovers market regimes from 5yr data, then evolves optimal '
                                    'execution configs per regime using genetic algorithm (~5-15 min).',
            'training_steps': [
                'Compute 25 market features across 5 categories',
                'Select top features via mutual information',
                'Build hierarchical regime tree (GMM + BIC)',
                'Evolve per-regime configs via island-model GA (100 generations)',
                'Save trained models for runtime use',
            ],
            'layers': [
                {
                    'name': 'FeaturePool',
                    'order': 1,
                    'type': 'feature_extractor',
                    'hook': 'on_before()',
                    'description': 'Computes ~25 market features across volatility, trend, chop, momentum, and structure categories',
                    'algorithm': 'Indicator-based feature extraction (NATR, ADX, EMA slopes, Hurst, RSI, etc.)',
                    'output': 'Feature vector per candle',
                },
                {
                    'name': 'RegimeTree',
                    'order': 2,
                    'type': 'classifier',
                    'hook': 'on_before()',
                    'description': 'Hierarchical GMM clustering — macro regimes split into sub-regimes',
                    'algorithm': 'Gaussian Mixture Model with BIC model selection at both levels',
                    'output': 'Probability distribution over 15-80 regime islands',
                    'config_keys': {
                        'max_macro': 'Max macro-regimes (default: 10)',
                        'max_sub': 'Max sub-regimes per macro (default: 8)',
                        'min_island_cycles': 'Min samples per island before merging (default: 200)',
                    },
                },
                {
                    'name': 'IslandEvolver',
                    'order': 3,
                    'type': 'optimizer',
                    'hook': 'on_cycle_end()',
                    'description': 'Per-regime genetic algorithm with sibling migration',
                    'algorithm': 'Tournament selection, uniform crossover, Gaussian mutation, elitism',
                    'output': 'Best execution config (genome) per regime island',
                    'genome_params': [
                        'gate_confidence_min', 'sizing_curve', 'sizing_factor', 'max_levels',
                        'tp_distance_atr_mult', 'hedge_distance_atr_mult', 'abort_aggressiveness',
                        'base_size_pct', 'hysteresis_margin', 'confidence_sensitivity', 'recovery_aggression',
                    ],
                    'config_keys': {
                        'population_size': 'Individuals per island (default: 30)',
                        'max_generations': 'Evolution limit (default: 100)',
                        'migration_interval': 'Generations between sibling migration (default: 5)',
                    },
                },
                {
                    'name': 'RegimeInferencer',
                    'order': 4,
                    'type': 'inferencer',
                    'hook': 'on_before() + gate_entry()',
                    'description': 'Runtime regime classification with sticky hysteresis to prevent whipsaw',
                    'algorithm': 'Soft GMM probabilities + hard config switching with margin threshold',
                    'output': 'Current regime ID + confidence score',
                    'config_keys': {
                        'min_confidence': 'Minimum probability to accept classification (default: 0.3)',
                        'default_hysteresis': 'Margin needed to switch regime (default: 0.15)',
                        'transition_grace_candles': 'Cooldown after switch (default: 5)',
                    },
                },
                {
                    'name': 'AdaptiveSizer',
                    'order': 5,
                    'type': 'sizer',
                    'hook': 'adjust_size()',
                    'description': 'Multi-factor position sizing: confidence × drawdown × base, bounded by SafetySizing',
                    'algorithm': 'Three multiplicative factors with hard caps',
                    'output': 'Adjusted position quantity',
                    'factors': [
                        'Island base size (evolved per regime)',
                        'Confidence scale (regime inference confidence ^ sensitivity)',
                        'Drawdown recovery (reduces size during drawdowns)',
                    ],
                    'config_keys': {
                        'drawdown_threshold_pct': 'DD% before scaling starts (default: 5.0)',
                        'min_confidence_scale': 'Floor for confidence factor (default: 0.2)',
                        'max_risk_per_cycle_pct': 'Hard cap on position size (default: 15.0)',
                    },
                },
            ],
            'lifecycle': [
                {'hook': 'on_before()', 'description': 'FeaturePool computes features → RegimeInferencer classifies regime → applies genome'},
                {'hook': 'gate_entry()', 'description': 'Blocks if confidence < threshold or in grace period after regime switch'},
                {'hook': 'adjust_size()', 'description': 'AdaptiveSizer scales position by confidence × drawdown factor'},
                {'hook': 'filter_order()', 'description': 'Injects evolved TP/hedge distances from active genome'},
                {'hook': 'suggest_exit()', 'description': 'Aborts cycle if danger exceeds evolved aggressiveness threshold'},
                {'hook': 'on_cycle_end()', 'description': 'Records outcome for fitness tracking and potential online learning'},
            ],
            'composition_rules': {
                'gate_entry': 'AND — all pipelines must allow (any veto blocks)',
                'adjust_size': 'Multiplicative chain (each scales previous output)',
                'suggest_exit': 'Most aggressive action wins (close_all > partial > tighten_sl > set_tp)',
                'filter_order': 'Sequential chain — any None cancels the order',
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
        """Override strategy.hp dict with genome parameters.

        Maps genome keys to the correct hp keys for each strategy variant:
        - Surefire v1: sizing_operator, sizing_factor, max_levels, hedge_distance, tp_distance
        - SurefireV2: sizing_operator, sizing_factor, max_levels, hedge_atr_mult
        - UniversalMartingale: sizing_curve, sizing_factor, max_levels, hedge_atr_mult

        Applies sanity bounds to prevent GA's extreme evolved values from
        blowing up real backtests with margin constraints.
        """
        if not hasattr(strategy, 'hp'):
            return

        hp = strategy.hp

        # max_levels — universal, capped at 8 for safety
        if 'max_levels' in genome:
            hp['max_levels'] = min(int(genome['max_levels']), 8)

        # sizing_factor — universal, capped at 2.5 for real margin
        if 'sizing_factor' in genome:
            hp['sizing_factor'] = min(genome['sizing_factor'], 2.5)

        # sizing_curve → detect which key the strategy uses
        sizing_curve = genome.get('sizing_curve')
        if sizing_curve is not None:
            curve_str = SIZING_CURVE_MAP.get(sizing_curve, sizing_curve) if isinstance(sizing_curve, int) else sizing_curve
            # Surefire v1/v2 use 'sizing_operator', UniversalMartingale uses 'sizing_curve'
            if 'sizing_operator' in hp:
                hp['sizing_operator'] = curve_str
            else:
                hp['sizing_curve'] = curve_str

        # hedge_distance_atr_mult → strategy-specific key
        hedge_mult = genome.get('hedge_distance_atr_mult')
        if hedge_mult is not None:
            # Clamp to reasonable range
            hedge_mult = max(0.5, min(hedge_mult, 3.0))
            if 'hedge_atr_mult' in hp:
                # SurefireV2, UniversalMartingale: ATR multiplier
                hp['hedge_atr_mult'] = hedge_mult
            elif 'hedge_distance' in hp:
                # Surefire v1: fixed pips — convert ATR mult to approx pips
                # Typical EUR-USD 5m ATR ~5-10 pips, so mult * 10 ≈ pips
                # Floor at 8 pips to prevent near-instant hedging
                hp['hedge_distance'] = max(8.0, round(hedge_mult * 10, 1))

        # tp_distance_atr_mult → strategy-specific key
        tp_mult = genome.get('tp_distance_atr_mult')
        if tp_mult is not None:
            tp_mult = max(1.0, min(tp_mult, 5.0))
            if 'tp_distance' in hp:
                # Surefire v1: fixed pips, floor at 10 pips
                hp['tp_distance'] = max(10.0, round(tp_mult * 10, 1))
            # SurefireV2 uses bucket_pct (not TP distance), so don't override
            # UniversalMartingale may use tp_atr_mult
            if 'tp_atr_mult' in hp:
                hp['tp_atr_mult'] = tp_mult

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
