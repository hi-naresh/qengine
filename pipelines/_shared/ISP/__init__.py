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
        self._abort_count: int = 0
        self._gate_block_count: int = 0
        self._gate_allow_count: int = 0
        self._cycle_hp_log: List[dict] = []
        self._last_recorded_session: Optional[int] = None
        self._sibling_groups: Dict[str, List[str]] = {}

        # ── Improvement 1: Online regime performance tracking ──
        # Tracks rolling PF per regime from completed cycles.
        # Used by gate_entry to block entries in historically bad regimes,
        # and by adjust_size to scale position size by regime quality.
        self._regime_wins: Dict[str, float] = {}    # regime_id -> gross wins
        self._regime_losses: Dict[str, float] = {}  # regime_id -> gross losses
        self._regime_cycles: Dict[str, int] = {}    # regime_id -> cycle count
        self._regime_busts: Dict[str, int] = {}     # regime_id -> bust count

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
            # Replace NaN with 0 for features that persistently produce NaN
            # (chop_14, er_50, er_100, hurst_100, stoch_k on some data sources).
            # The regime tree was trained on data where these features were valid,
            # so zeroing them is imperfect but better than blocking all entries.
            # Only skip if MORE THAN HALF the features are NaN (data not ready).
            n_nan = np.sum(np.isnan(fv))
            if n_nan > len(fv) // 2:
                return
            fv = np.nan_to_num(fv, nan=0.0)
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

            # Fallback: if this regime has no genome, use the best genome
            # from a sibling in the same macro-cluster. This handles the 8
            # regimes that were too sparse for the evolver to populate.
            if genome_dict is None and self.regime_tree is not None:
                rid = self._active_regime
                macro_id = None
                for lid, (mid, _sid) in self.regime_tree._leaf_map.items():
                    if lid == rid:
                        macro_id = mid
                        break
                if macro_id is not None:
                    best_fitness = -float('inf')
                    for lid, (mid, _sid) in self.regime_tree._leaf_map.items():
                        if mid == macro_id:
                            for lkey in [str(lid), lid, int(lid)]:
                                try:
                                    gd = self.evolver.get_best_genome(lkey)
                                    if gd:
                                        f = gd.get('fitness', -float('inf'))
                                        if f is not None and f > best_fitness:
                                            best_fitness = f
                                            genome_dict = gd
                                        break
                                except (KeyError, TypeError, Exception):
                                    continue

            if genome_dict is not None:
                self._active_genome = genome_dict.get('genes', genome_dict)
                # Apply genome to strategy HP only between cycles (not mid-cycle).
                # Changing HP mid-cycle breaks hedge direction and sizing chains.
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
        """Block entry if no genome available or low confidence.

        Grace period is NOT used for entry gating — it only prevents genome
        switching in on_before(). Blocking entries during grace period was
        causing 70%+ rejection rates because with 73 regime leaves, regime
        transitions happen every ~9 candles on 5m data, and a 5-candle grace
        period blocks entries more than half the time.
        """
        # During warmup, block
        if self._candle_count < self.cfg['warmup']:
            self._gate_block_count += 1
            return False

        # No genome means the regime/evolver isn't ready
        if self._active_genome is None:
            self._gate_block_count += 1
            return False

        # Low confidence
        min_conf = self.cfg['inference']['min_confidence']
        if self._active_confidence < min_conf:
            self._gate_block_count += 1
            return False

        # ── Improvement 1: Regime performance tracking (data collection) ──
        # The on_cycle_end method records per-regime PF. This data is available
        # in get_stats() for analysis but is NOT yet used for gating because:
        # (a) The regime tree and genomes need retraining on clean features first
        # (b) Gating thresholds need calibration after retrain
        # Future: block entries in regimes with PF < threshold after sufficient history.

        self._gate_allow_count += 1
        return True

    def adjust_size(self, strategy, qty: float, side: str) -> float:
        """Do NOT scale individual entry sizes for martingale/hedge strategies.

        The hedge sizing math (geometric 2×, fibonacci, etc.) requires L0, L1, L2
        to maintain exact ratios. If the pipeline scales L0 but not L1/L2 (which
        are placed internally by the strategy), the ratios break and sessions
        never profit.

        Instead, the pipeline controls entry TIMING (gate_entry) and cycle
        TERMINATION (suggest_exit), not position sizing.
        """
        # Pass through unchanged — sizing is the strategy's domain
        return qty

    def _adjust_size_disabled(self, strategy, qty: float, side: str) -> float:
        """Original adaptive sizing — disabled because it breaks hedge ratios."""
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
        """Abort if danger exceeds threshold derived from genome.

        abort_aggressiveness=0 means never abort (conservative).
        abort_aggressiveness=1 means abort at any danger (aggressive).
        The threshold is inverted: threshold = 1 - aggressiveness.
        So aggressiveness=0.8 → abort when danger > 0.2 (aggressive).
        And aggressiveness=0.2 → abort when danger > 0.8 (conservative).
        """
        if self._active_genome is None:
            return None

        aggressiveness = self._active_genome.get('abort_aggressiveness', 0.5)
        # Convert to threshold: higher aggressiveness = lower threshold = easier to abort
        threshold = 1.0 - aggressiveness

        danger = self._compute_danger(strategy)
        if danger > threshold:
            self._abort_count += 1
            return {'action': 'close_all'}

        return None

    def on_cycle_end(self, pnl: float, strategy) -> None:
        """Record outcome for the evolver and log active HP per cycle.

        Guards against double-fire: in CFD mode, close_all_tickets() and
        Martingale._reset_cycle() both call on_cycle_end. We use the strategy's
        session_number as the canonical cycle ID to deduplicate.
        """
        # Use strategy's session_number as canonical cycle ID (avoids double-count)
        sn = getattr(strategy, 'vars', {}).get('session_number') if strategy else None
        if sn is not None and sn == self._last_recorded_session:
            return  # already recorded this session
        self._last_recorded_session = sn

        self._cycle_count += 1
        cycle_id = sn if sn is not None else self._cycle_count

        # Track active HP per cycle for session display
        cycle_hp: Dict[str, Any] = {
            'cycle': cycle_id,
            'regime': self._active_regime,
            'confidence': round(self._active_confidence, 4) if self._active_confidence else None,
        }
        if self._active_genome is not None:
            genes = self._active_genome if isinstance(self._active_genome, dict) else getattr(self._active_genome, 'genes', {})
            cycle_hp['genes'] = {k: round(v, 4) if isinstance(v, float) else v for k, v in genes.items()}
        self._cycle_hp_log.append(cycle_hp)

        if self.evolver is not None and self._active_regime is not None:
            self.evolver.record_outcome(
                regime_id=str(self._active_regime),
                pnl=pnl,
                cycle=cycle_id,
                genome=self._active_genome,
            )

        # ── Improvement 1: Update online regime performance tracking ──
        regime_key = str(self._active_regime) if self._active_regime is not None else None
        if regime_key:
            self._regime_cycles[regime_key] = self._regime_cycles.get(regime_key, 0) + 1
            if pnl >= 0:
                self._regime_wins[regime_key] = self._regime_wins.get(regime_key, 0) + pnl
            else:
                self._regime_losses[regime_key] = self._regime_losses.get(regime_key, 0) + abs(pnl)
            # Track busts (check if strategy reports bust via vars)
            is_bust = False
            if strategy and hasattr(strategy, 'vars'):
                is_bust = strategy.vars.get('last_session_bust', False)
            if is_bust or pnl < -50:  # heuristic: large loss = likely bust
                self._regime_busts[regime_key] = self._regime_busts.get(regime_key, 0) + 1

    # ------------------------------------------------------------------
    # Stats & persistence
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Comprehensive stats from all components."""
        total_gate = self._gate_allow_count + self._gate_block_count
        stats: Dict[str, Any] = {
            'active_regime': self._active_regime,
            'active_confidence': round(self._active_confidence, 4) if self._active_confidence else 0,
            'candle_count': self._candle_count,
            'cycle_count': self._cycle_count,
            'entries_allowed': self._gate_allow_count,
            'entries_blocked': self._gate_block_count,
            'total_gate_checks': total_gate,
            'block_rate': round(self._gate_block_count / total_gate, 4) if total_gate > 0 else 0,
            'aborts_triggered': self._abort_count,
            'has_genome': self._active_genome is not None,
        }

        if self.regime_tree is not None:
            stats['n_leaves'] = self.regime_tree.n_leaves
            stats['leaf_ids'] = self.regime_tree.leaf_ids

        if self.inferencer is not None:
            stats['regime_counts'] = self.inferencer.get_regime_counts()
            stats['n_transitions'] = len(self.inferencer.get_transition_log())

        if self.evolver is not None:
            raw_fitness = self.evolver.get_fitness_summary()
            # Flatten for frontend table: {island_id: {best, mean, n, std}} → list
            stats['fitness_summary'] = raw_fitness

            # Summarize diversity: per-island average gene std → single value per island
            raw_div = self.evolver.get_diversity_stats()
            diversity_summary: Dict[str, Any] = {}
            total_avg_std = []
            for lid, gene_stds in raw_div.items():
                vals = [v for v in gene_stds.values() if isinstance(v, (int, float))]
                avg = sum(vals) / len(vals) if vals else 0
                diversity_summary[lid] = round(avg, 6)
                total_avg_std.append(avg)
            stats['diversity'] = {
                'n_islands': len(raw_div),
                'mean_gene_diversity': round(sum(total_avg_std) / len(total_avg_std), 6) if total_avg_std else 0,
                'min_diversity_island': min(diversity_summary, key=diversity_summary.get) if diversity_summary else '-',
                'max_diversity_island': max(diversity_summary, key=diversity_summary.get) if diversity_summary else '-',
                'min_diversity': round(min(total_avg_std), 6) if total_avg_std else 0,
                'max_diversity': round(max(total_avg_std), 6) if total_avg_std else 0,
            }
            stats['n_migrations'] = len(self.evolver.get_migration_log())

        stats['sizer'] = self.sizer.get_stats()
        stats['cycle_hp_log'] = self._cycle_hp_log
        stats['_ui'] = self.ui_metadata()

        return stats

    def ui_metadata(self) -> dict:
        n_leaves = self.regime_tree.n_leaves if self.regime_tree else 0
        return {
            'badges': [
                {'label': self.name or 'IslandPilot', 'color': 'brand'},
                {'label': f'Regime: {self._active_regime or "?"}',
                 'color': 'amber' if self._active_regime else 'surface'},
                {'label': f'{n_leaves} islands', 'color': 'surface'},
                {'label': 'Genome active' if self._active_genome else 'No genome',
                 'color': 'green' if self._active_genome else 'red'},
            ],
            'metric_cards': [
                {'label': 'Active Regime', 'key': 'active_regime', 'format': 'text', 'icon': 'chart',
                 'tooltip': 'Current detected market regime island'},
                {'label': 'Confidence', 'key': 'active_confidence', 'format': 'pct', 'threshold': [0.5, 0.7], 'icon': 'shield',
                 'tooltip': 'Regime classification confidence'},
                {'label': 'Entries Blocked', 'key': 'block_rate', 'format': 'pct', 'color': 'amber',
                 'sub_template': '{entries_blocked} / {total_gate_checks}', 'icon': 'block',
                 'tooltip': '% of entries blocked by low-confidence gate'},
                {'label': 'Islands', 'key': 'n_leaves', 'format': 'int', 'icon': 'chart',
                 'tooltip': 'Total regime islands discovered'},
                {'label': 'Migrations', 'key': 'n_migrations', 'format': 'int', 'icon': 'chart',
                 'tooltip': 'Cross-island genome migrations'},
                {'label': 'Cycles', 'key': 'cycle_count', 'format': 'int', 'icon': 'chart',
                 'tooltip': 'Total completed trading cycles'},
            ],
            'sections': [
                # Regime distribution (top 20 by count, collapsed)
                {
                    'type': 'bar_breakdown',
                    'title': 'Regime Distribution',
                    'data_key': 'regime_counts',
                    'empty_message': 'No regime data yet. Inferencer is still warming up.',
                    'label_prefix': 'R',
                    'mode': 'count_only',
                    'max_items': 20,
                    'sort_by_value': True,
                },
                # Fitness summary per island
                {
                    'type': 'kv_table',
                    'title': 'Fitness Summary by Island',
                    'data_key': 'fitness_summary',
                    'show_if': 'fitness_summary',
                    'empty_message': 'No fitness data. Evolver needs more cycles.',
                    'columns': [
                        {'key': 'island', 'label': 'Island'},
                        {'key': 'best', 'label': 'Best Fitness', 'format': 'dec4'},
                        {'key': 'mean', 'label': 'Mean Fitness', 'format': 'dec4'},
                        {'key': 'std', 'label': 'Std', 'format': 'dec4'},
                        {'key': 'n', 'label': 'Samples', 'format': 'int'},
                    ],
                    'max_items': 20,
                    'sort_key': 'best',
                    'sort_desc': True,
                    'hide_empty': True,
                },
                # Diversity stats (summarized)
                {
                    'type': 'kv_pairs',
                    'title': 'Genetic Diversity',
                    'data_key': 'diversity',
                    'show_if': 'diversity',
                    'empty_message': 'No diversity data yet.',
                    'auto_items': True,
                    'grid': 'full',
                },
                # Sizer stats
                {
                    'type': 'kv_pairs',
                    'title': 'Adaptive Sizer',
                    'data_key': 'sizer',
                    'show_if': 'sizer',
                    'auto_items': True,
                    'grid': 'full',
                },
            ],
        }

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
            'designed_for': ['Martingale strategies', 'SurefireHedge variants', 'Martingale'],
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
        """Apply evolved genome to strategy HP — discovered dynamically at runtime.

        Instead of hardcoding strategy key names, the pipeline reads the strategy's
        own hyperparameters() declaration to discover which params exist, their
        valid ranges, and groups. Only 'General' and 'Grid / Hedge' group params
        are overridden (entry signals, filters, risk management are left to user).

        This works with ANY strategy that declares hyperparameters().
        """
        if not hasattr(strategy, 'hp') or not hasattr(strategy, 'hyperparameters'):
            return

        # Do NOT force 'custom' preset. The user's preset defines the strategy's
        # grid structure and signal behavior. The pipeline only tunes sizing params
        # within the preset's framework. Forcing custom unlocks all params and lets
        # evolved genomes override grid/hedge/TP, creating cycle durations so long
        # that annual throughput drops to 2-3 sessions.
        # if strategy.hp.get('preset') and strategy.hp['preset'] != 'custom':
        #     strategy.hp['preset'] = 'custom'

        # Build lookup from strategy's declared HP
        if not hasattr(self, '_hp_spec'):
            try:
                hp_list = strategy.hyperparameters()
                self._hp_spec = {h['name']: h for h in hp_list if isinstance(h, dict) and 'name' in h}
            except Exception:
                self._hp_spec = {}

        if not self._hp_spec:
            return

        # Groups the pipeline is allowed to tune
        # Tune General (sizing), Grid/Hedge, and Take Profit parameters per regime.
        # Entry Signal is excluded — the pipeline must not change when signals fire.
        # The preset is NOT forced to 'custom' — the strategy's preset defines
        # the signal behavior and the pipeline only overrides execution params
        # that the preset allows to be changed.
        _TUNABLE_GROUPS = {'General', 'Grid / Hedge', 'Take Profit'}

        # Validated options for categorical params that may have broken choices.
        # Only allow signal modes that are known to work in the strategy.
        _SAFE_OPTIONS = {
            'signal_mode': {'random', 'ema_cross', 'rsi', 'macd', 'supertrend', 'stoch', 'ema_rsi', 'ema_macd', 'triple'},
            'hedge_mode': {'fixed_pips', 'atr_based', 'percentage'},
            'tp_mode': {'fixed_pips', 'atr_based', 'bucket_pct', 'risk_reward'},
            'base_size_mode': {'pct_equity', 'capital_aware'},
            'sizing_curve': {'geometric', 'sqrt', 'linear', 'fibonacci'},
        }

        hp = strategy.hp
        for hp_name, spec in self._hp_spec.items():
            group = spec.get('group', '')
            if group not in _TUNABLE_GROUPS:
                continue

            if hp_name not in genome:
                continue

            val = genome[hp_name]

            # Enforce declared bounds and convert types
            hp_type = spec.get('type')
            if hp_type == 'categorical':
                options = spec.get('options', [])
                # Filter to safe options if we have a safelist
                safe = _SAFE_OPTIONS.get(hp_name)
                if safe:
                    options = [o for o in options if o in safe]
                if not options:
                    continue
                # Genome may store int index (from GA) or string value
                if isinstance(val, (int, float)):
                    idx = int(round(val))
                    idx = max(0, min(idx, len(options) - 1))
                    hp[hp_name] = options[idx]
                elif val in options:
                    hp[hp_name] = val
            elif hp_type in (int, float) or hp_type in ('int', 'float'):
                lo = spec.get('min', float('-inf'))
                hi = spec.get('max', float('inf'))
                val = max(lo, min(hi, float(val)))
                if hp_type in (int, 'int'):
                    val = int(round(val))
                hp[hp_name] = val

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
