"""
CoEvolGPPilot — a co-evolutionary, HMM-regime-aware genetic pipeline.

Implementation of the approach in
    Yang, S., Xin, J., Ye, Q., & Xia, H. (2025).
    *A Co-evolutionary Genetic Programming Framework for Market-Adaptive
    Formulaic Alpha Generation.* SSRN 5614908.

Adapted to evolve *strategy execution parameters* instead of formulaic alpha
factors (GP trees), but keeping the three distinguishing design elements:

    1. A 3-state HMM / GMM soft-gates regime-specific sub-populations.
    2. Runtime parameters are a **posterior-weighted aggregation** of the
       three best genomes — not a hard switch as in IslandPilot.
    3. Approximate per-state Shapley values feed back into each island's
       selection pressure.

The class is intentionally a drop-in replacement for IslandPilot so the PhD
dissertation can compare (a) hierarchical-GMM hard-switching vs flat-HMM
soft-gating and (b) tournament-only vs Shapley-scaled selection under
otherwise identical conditions (Martingale strategy, same fitness function).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

from qengine.framework.base import Pipeline, OrderIntent
from qengine.framework.components.feature_selector import FeaturePool
from qengine.framework.components.island_evolver import (
    IslandEvolver, Genome, GENE_BOUNDS,
)

from .config import DEFAULT_CONFIG, STATE_IDS, merge_config
from .hmm_regime import HMMRegimeModel, hmmlearn_available
from .shapley_feedback import ShapleyFeedback


# ---------------------------------------------------------------------------
# Paths to shipped artefacts
# ---------------------------------------------------------------------------

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_MODELS_DIR = os.path.join(_PKG_DIR, 'models')

_HMM_PATH = os.path.join(_MODELS_DIR, 'hmm.pkl')
_HMM_META_PATH = os.path.join(_MODELS_DIR, 'hmm_meta.json')
_EVOLVER_PATH = os.path.join(_MODELS_DIR, 'island_evolver.json')
_GENOMES_PATH = os.path.join(_MODELS_DIR, 'island_genomes.json')
_SHAPLEY_PATH = os.path.join(_MODELS_DIR, 'shapley.json')
_RUNTIME_PATH = os.path.join(_MODELS_DIR, 'runtime.json')


# ---------------------------------------------------------------------------
# Runtime-parameter aggregation
# ---------------------------------------------------------------------------

# Groups the pipeline may tune (same as IslandPilot for a fair comparison).
_TUNABLE_GROUPS = {'General', 'Grid / Hedge', 'Take Profit'}

# Safe categorical whitelist (lifted from IslandPilot to avoid evolving into
# broken signal/TP modes during experiments).
_SAFE_OPTIONS = {
    'signal_mode': {
        'random', 'ema_cross', 'rsi', 'macd', 'supertrend',
        'stoch', 'ema_rsi', 'ema_macd', 'triple',
    },
    'hedge_mode': {'fixed_pips', 'atr_based', 'percentage'},
    'tp_mode': {'fixed_pips', 'atr_based', 'bucket_pct', 'risk_reward'},
    'base_size_mode': {'pct_equity', 'capital_aware'},
    'sizing_curve': {'geometric', 'sqrt', 'linear', 'fibonacci'},
}


def _is_numeric(val) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def aggregate_genomes(posteriors: np.ndarray, best_per_state: Dict[str, dict]) -> dict:
    """Posterior-weighted aggregation of the best genome per state.

    * Numeric genes — weighted average.
    * Categorical genes — argmax-state value (discrete values cannot mix).
    * Missing genes — skipped.

    ``best_per_state`` keys must match the order implied by ``posteriors`` via
    ``STATE_IDS`` (i.e. posteriors[0] corresponds to STATE_IDS[0]).
    """
    p = np.asarray(posteriors, dtype=np.float64).ravel()
    if p.size != len(STATE_IDS):
        return {}
    s = p.sum()
    if s <= 0:
        return {}
    p = p / s

    # Collect the union of gene names across the three dictionaries
    all_genes: Dict[str, list] = {}
    for i, sid in enumerate(STATE_IDS):
        gd = best_per_state.get(sid) or {}
        genes = gd.get('genes', gd) if isinstance(gd, dict) else {}
        for name, val in genes.items():
            all_genes.setdefault(name, [None, None, None])
            all_genes[name][i] = val

    argmax_state = int(np.argmax(p))
    agg: Dict[str, Any] = {}
    for name, vals in all_genes.items():
        numeric_vals = [v for v in vals if _is_numeric(v)]
        if len(numeric_vals) == len(vals):
            # Fully numeric — weighted average with available posteriors
            weighted = 0.0
            w_total = 0.0
            for pi, v in zip(p, vals):
                if _is_numeric(v):
                    weighted += pi * float(v)
                    w_total += pi
            if w_total > 0:
                agg[name] = weighted / w_total
        else:
            # Categorical / mixed — pick the argmax state's value if present,
            # otherwise fall back to the first non-None value.
            pick = vals[argmax_state]
            if pick is None:
                for v in vals:
                    if v is not None:
                        pick = v
                        break
            if pick is not None:
                agg[name] = pick
    return agg


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class CoEvolGPPilot(Pipeline):
    """Co-evolutionary, HMM-regime-aware pipeline (Yang et al., 2025 adapted)."""

    name = 'CoEvolGPPilot'

    def __init__(self, config: Optional[dict] = None):
        self.cfg = merge_config(config or {})

        # Components
        self.feature_pool = FeaturePool()
        self.hmm: Optional[HMMRegimeModel] = None
        self.evolver: Optional[IslandEvolver] = None
        self.shapley = ShapleyFeedback(
            state_ids=list(STATE_IDS),
            update_interval=self.cfg['shapley']['update_interval'],
            min_samples_per_state=self.cfg['shapley']['min_samples_per_state'],
            pressure_min=self.cfg['shapley']['pressure_min'],
            pressure_max=self.cfg['shapley']['pressure_max'],
        )

        # Runtime state
        self._posteriors: np.ndarray = np.full(len(STATE_IDS), 1.0 / len(STATE_IDS))
        self._posterior_at_entry: Optional[np.ndarray] = None
        self._candle_count: int = 0
        self._cycle_count: int = 0
        self._gate_block_count: int = 0
        self._gate_allow_count: int = 0
        self._abort_count: int = 0
        self._active_genome: Optional[dict] = None
        self._cycle_hp_log: List[dict] = []
        self._last_recorded_session: Optional[int] = None
        self._hp_spec: Optional[Dict[str, dict]] = None
        self._feature_vector: Optional[np.ndarray] = None
        self._backend_note: str = (
            'hmmlearn' if hmmlearn_available() else 'sklearn_gmm_fallback'
        )

        # Auto-load shipped artefacts
        self._load_pretrained_models()

    # ------------------------------------------------------------------
    # Pipeline hooks
    # ------------------------------------------------------------------

    def on_before(self, strategy) -> None:
        """Compute features → posteriors → aggregated genome → apply."""
        self._candle_count += 1

        candles = getattr(strategy, 'candles', None)
        warmup = self.cfg.get('warmup', 50)
        if candles is None or len(candles) < warmup:
            return
        if self.hmm is None or self.evolver is None:
            return

        tail_window = self.cfg.get('window', 300)
        tail = candles[-tail_window:] if len(candles) > tail_window else candles

        # Features (top-K indices are stored on the HMM after training)
        try:
            feature_matrix = self.feature_pool.compute(tail)
            fv_full = feature_matrix[-1]
        except Exception:
            return

        idxs = self.hmm.feature_indices or list(range(fv_full.size))
        try:
            fv = fv_full[idxs]
        except Exception:
            return
        if np.sum(np.isnan(fv)) > fv.size // 2:
            return  # not enough valid features
        fv = np.nan_to_num(fv, nan=0.0)
        self._feature_vector = fv

        # Posterior over the 3 HMM states
        try:
            self._posteriors = self.hmm.posterior(fv)
        except Exception:
            return

        # Aggregate the best genome from each state
        best_per_state: Dict[str, dict] = {}
        for sid in STATE_IDS:
            try:
                best_per_state[sid] = self.evolver.get_best_genome(sid)
            except Exception:
                best_per_state[sid] = {}
        genome = aggregate_genomes(self._posteriors, best_per_state)
        if not genome:
            self._active_genome = None
            return
        self._active_genome = genome

        # Apply between cycles only — never mid-position
        position_open = False
        if hasattr(strategy, 'position') and hasattr(strategy.position, 'is_open'):
            position_open = bool(strategy.position.is_open)
        elif hasattr(strategy, 'vars') and strategy.vars.get('cycle_active'):
            position_open = True
        if not position_open and self.cfg['inference'].get('apply_between_cycles_only', True):
            self._apply_genome(strategy, genome)
        elif not self.cfg['inference'].get('apply_between_cycles_only', True):
            self._apply_genome(strategy, genome)

    def gate_entry(self, strategy) -> bool:
        warmup = self.cfg.get('warmup', 50)
        if self._candle_count < warmup:
            self._gate_block_count += 1
            return False
        if self._active_genome is None:
            self._gate_block_count += 1
            return False
        min_conf = float(self.cfg['inference'].get('min_posterior_confidence', 0.0))
        if min_conf > 0.0 and float(self._posteriors.max()) < min_conf:
            self._gate_block_count += 1
            return False
        self._gate_allow_count += 1
        return True

    def adjust_size(self, strategy, qty: float, side: str) -> float:
        # Same design decision as IslandPilot: don't scale individual entries
        # because it breaks hedge ratios. Pipeline controls timing + HP only.
        return qty

    def suggest_exit(self, strategy) -> Optional[dict]:
        # Abort on high volatility if the aggregated genome's
        # ``abort_aggressiveness`` gene is high.
        if not self._active_genome:
            return None
        aggr = float(self._active_genome.get('abort_aggressiveness', 0.0) or 0.0)
        if aggr <= 0.0:
            return None
        threshold = 1.0 - aggr
        danger = self._compute_danger(strategy)
        if danger > threshold:
            self._abort_count += 1
            return {'action': 'close_all'}
        return None

    def on_open_position(self, strategy) -> None:
        # Snapshot the posterior at entry so we can credit the outcome
        # proportionally to each state when the cycle closes.
        self._posterior_at_entry = np.array(self._posteriors, copy=True)

    def on_cycle_end(self, pnl: float, strategy) -> None:
        # Deduplicate on session_number like IslandPilot does
        sn = getattr(strategy, 'vars', {}).get('session_number') if strategy else None
        if sn is not None and sn == self._last_recorded_session:
            return
        self._last_recorded_session = sn

        self._cycle_count += 1
        cycle_id = sn if sn is not None else self._cycle_count

        p_at_entry = self._posterior_at_entry
        if p_at_entry is None:
            p_at_entry = self._posteriors

        # Shapley-style per-state credit
        try:
            self.shapley.record_cycle(pnl=pnl, posteriors=p_at_entry)
        except Exception:
            pass

        # Record outcome with each state weighted by posterior
        if self.evolver is not None:
            for sid, weight in zip(STATE_IDS, p_at_entry):
                if weight <= 0.0:
                    continue
                try:
                    self.evolver.record_outcome(
                        regime_id=sid,
                        pnl=float(pnl) * float(weight),
                        cycle=cycle_id,
                        genome=self._active_genome,
                        posterior_weight=float(weight),
                    )
                except Exception:
                    pass

        # Log HP snapshot
        hp_snap = None
        if self._active_genome:
            hp_snap = {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in self._active_genome.items()
            }
        self._cycle_hp_log.append({
            'cycle': cycle_id,
            'posteriors': [round(float(x), 4) for x in p_at_entry],
            'pnl': round(float(pnl), 4),
            'genes': hp_snap,
        })
        # Clear for next cycle
        self._posterior_at_entry = None

    # ------------------------------------------------------------------
    # Stats & persistence
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        total_gate = self._gate_allow_count + self._gate_block_count
        posteriors = [round(float(x), 4) for x in self._posteriors]
        argmax_state = STATE_IDS[int(np.argmax(self._posteriors))]

        stats: Dict[str, Any] = {
            'backend': self._backend_note,
            'active_state': argmax_state,
            'active_confidence': round(float(self._posteriors.max()), 4),
            'posteriors': {sid: posteriors[i] for i, sid in enumerate(STATE_IDS)},
            'candle_count': self._candle_count,
            'cycle_count': self._cycle_count,
            'entries_allowed': self._gate_allow_count,
            'entries_blocked': self._gate_block_count,
            'total_gate_checks': total_gate,
            'block_rate': round(self._gate_block_count / total_gate, 4) if total_gate else 0,
            'aborts_triggered': self._abort_count,
            'has_genome': self._active_genome is not None,
            'shapley': self.shapley.get_stats(),
        }

        if self.evolver is not None:
            stats['fitness_summary'] = self.evolver.get_fitness_summary()
            raw_div = self.evolver.get_diversity_stats()
            stats['diversity'] = {
                sid: {k: round(v, 6) for k, v in gene_stds.items()}
                for sid, gene_stds in raw_div.items()
            }

        stats['cycle_hp_log'] = self._cycle_hp_log[-200:]
        stats['_ui'] = self.ui_metadata()
        return stats

    def ui_metadata(self) -> dict:
        return {
            'badges': [
                {'label': self.name, 'color': 'brand'},
                {'label': f'Backend: {self._backend_note}', 'color': 'surface'},
                {'label': f'State: {STATE_IDS[int(np.argmax(self._posteriors))]}',
                 'color': 'amber' if self._active_genome else 'surface'},
                {'label': 'Genome active' if self._active_genome else 'No genome',
                 'color': 'green' if self._active_genome else 'red'},
            ],
            'metric_cards': [
                {'label': 'Posterior s0', 'key': 'posteriors.s0', 'format': 'pct'},
                {'label': 'Posterior s1', 'key': 'posteriors.s1', 'format': 'pct'},
                {'label': 'Posterior s2', 'key': 'posteriors.s2', 'format': 'pct'},
                {'label': 'Active State', 'key': 'active_state', 'format': 'text'},
                {'label': 'Cycles', 'key': 'cycle_count', 'format': 'int'},
                {'label': 'Shapley updates',
                 'key': 'shapley.history_len', 'format': 'int'},
            ],
            'sections': [
                {
                    'type': 'kv_table',
                    'title': 'Per-State Fitness',
                    'data_key': 'fitness_summary',
                    'empty_message': 'Evolver has not been trained yet.',
                    'columns': [
                        {'key': 'island', 'label': 'State'},
                        {'key': 'best', 'label': 'Best Fitness', 'format': 'dec4'},
                        {'key': 'mean', 'label': 'Mean Fitness', 'format': 'dec4'},
                        {'key': 'std', 'label': 'Std', 'format': 'dec4'},
                        {'key': 'n', 'label': 'Samples', 'format': 'int'},
                    ],
                },
                {
                    'type': 'kv_pairs',
                    'title': 'Shapley Pressure (per state)',
                    'data_key': 'shapley.pressure',
                    'auto_items': True,
                    'grid': 'full',
                },
                {
                    'type': 'kv_pairs',
                    'title': 'Shapley Phi (per state)',
                    'data_key': 'shapley.phi',
                    'auto_items': True,
                    'grid': 'full',
                },
            ],
        }

    def save_state(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)
        if self.hmm is not None:
            self.hmm.save(os.path.join(path, 'hmm.pkl'))
            self.hmm.save_metadata_json(os.path.join(path, 'hmm_meta.json'))
        if self.evolver is not None:
            self.evolver.save(os.path.join(path, 'island_evolver.json'))
        with open(os.path.join(path, 'shapley.json'), 'w') as f:
            json.dump(self.shapley.to_dict(), f, indent=2)
        runtime = {
            'candle_count': self._candle_count,
            'cycle_count': self._cycle_count,
            'posteriors': list(map(float, self._posteriors)),
            'backend': self._backend_note,
        }
        with open(os.path.join(path, 'runtime.json'), 'w') as f:
            json.dump(runtime, f, indent=2)

    def load_state(self, path: str) -> None:
        hmm_path = os.path.join(path, 'hmm.pkl')
        if os.path.exists(hmm_path):
            self.hmm = HMMRegimeModel.load(hmm_path)
            self._backend_note = self.hmm.backend
        evo_path = os.path.join(path, 'island_evolver.json')
        if os.path.exists(evo_path):
            self.evolver = IslandEvolver.load(evo_path)
        shap_path = os.path.join(path, 'shapley.json')
        if os.path.exists(shap_path):
            with open(shap_path) as f:
                self.shapley = ShapleyFeedback.from_dict(json.load(f))
        runtime_path = os.path.join(path, 'runtime.json')
        if os.path.exists(runtime_path):
            with open(runtime_path) as f:
                runtime = json.load(f)
            self._candle_count = int(runtime.get('candle_count', 0))
            self._cycle_count = int(runtime.get('cycle_count', 0))
            post = runtime.get('posteriors')
            if post and len(post) == len(STATE_IDS):
                self._posteriors = np.asarray(post, dtype=np.float64)

    # ------------------------------------------------------------------
    # Class metadata
    # ------------------------------------------------------------------

    @classmethod
    def default_config(cls) -> dict:
        return merge_config({})

    @classmethod
    def architecture(cls) -> dict:
        has_hmm = os.path.exists(_HMM_PATH)
        has_evo = os.path.exists(_EVOLVER_PATH) or os.path.exists(_GENOMES_PATH)
        is_trained = has_hmm and has_evo
        return {
            'name': 'CoEvolGPPilot',
            'summary': (
                'Co-evolutionary, HMM-regime-aware pipeline: 3-state HMM '
                'soft-gates three sub-populations whose best genomes are '
                'aggregated by posterior weight. Approximate Shapley values '
                'scale per-island selection pressure. (Yang et al., 2025.)'
            ),
            'designed_for': ['Martingale', 'SurefireHedge variants'],
            'research_basis': (
                'Yang, S., Xin, J., Ye, Q., & Xia, H. (2025). '
                'A Co-evolutionary Genetic Programming Framework for '
                'Market-Adaptive Formulaic Alpha Generation. SSRN 5614908.'
            ),
            'requires_training': True,
            'training_status': 'trained' if is_trained else 'untrained',
            'training_description': (
                'Fit 3-state HMM on top-K features, then run per-state GA '
                'for 5 generations against the real engine (~5-15 min).'
            ),
            'training_steps': [
                'Compute market features (FeaturePool)',
                'Select top-K by MI against cycle-outcome proxy',
                'Fit 3-state HMM / GMM',
                'Evolve one population per state',
                'Save artefacts to models/',
            ],
            'layers': [
                {
                    'name': 'FeaturePool',
                    'order': 1,
                    'type': 'feature_extractor',
                    'hook': 'on_before()',
                    'description': 'Computes ~25 market features across categories.',
                },
                {
                    'name': 'HMMRegimeModel',
                    'order': 2,
                    'type': 'classifier',
                    'hook': 'on_before()',
                    'description': (
                        '3-state HMM (Gaussian mixture emissions) returning '
                        'posterior probabilities per candle. Falls back to '
                        'sklearn GaussianMixture if hmmlearn is unavailable.'
                    ),
                },
                {
                    'name': 'IslandEvolver (3 islands)',
                    'order': 3,
                    'type': 'optimizer',
                    'hook': 'on_cycle_end()',
                    'description': (
                        'One GA population per state; outcomes credited by '
                        'posterior weight.'
                    ),
                },
                {
                    'name': 'ShapleyFeedback',
                    'order': 4,
                    'type': 'feedback',
                    'hook': 'on_cycle_end()',
                    'description': (
                        'Approximate per-state Shapley values scale each '
                        'island\'s selection pressure (tournament size, '
                        'mutation sigma).'
                    ),
                },
                {
                    'name': 'Aggregator',
                    'order': 5,
                    'type': 'applier',
                    'hook': 'on_before()',
                    'description': (
                        'Posterior-weighted aggregation of the 3 best genomes '
                        '— numeric genes averaged, categoricals argmax-picked.'
                    ),
                },
            ],
            'composition_rules': {
                'gate_entry': 'Warmup gate + optional min-posterior-confidence.',
                'suggest_exit': 'Volatility abort if abort_aggressiveness gene active.',
                'on_cycle_end': 'Posterior-weighted credit + Shapley update.',
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_pretrained_models(self) -> None:
        if os.path.exists(_HMM_PATH):
            try:
                self.hmm = HMMRegimeModel.load(_HMM_PATH)
                self._backend_note = self.hmm.backend
            except Exception as exc:  # pragma: no cover
                print(f'[CoEvolGPPilot] failed to load HMM: {exc}')

        if os.path.exists(_EVOLVER_PATH):
            try:
                self.evolver = IslandEvolver.load(_EVOLVER_PATH)
            except Exception as exc:  # pragma: no cover
                print(f'[CoEvolGPPilot] failed to load evolver: {exc}')

        elif os.path.exists(_GENOMES_PATH):
            try:
                with open(_GENOMES_PATH) as f:
                    genomes_data = json.load(f)
                leaf_ids = list(STATE_IDS)
                evolver = IslandEvolver(leaf_ids=leaf_ids, config={})
                for sid in leaf_ids:
                    gd = genomes_data.get(sid)
                    if not gd:
                        continue
                    genome = Genome.from_dict(gd)
                    genome.fitness = gd.get('fitness', 0.0)
                    if sid in evolver.populations:
                        evolver.populations[sid].individuals[0] = genome
                self.evolver = evolver
            except Exception as exc:  # pragma: no cover
                print(f'[CoEvolGPPilot] failed to load genomes: {exc}')

        if os.path.exists(_SHAPLEY_PATH):
            try:
                with open(_SHAPLEY_PATH) as f:
                    self.shapley = ShapleyFeedback.from_dict(json.load(f))
            except Exception as exc:  # pragma: no cover
                print(f'[CoEvolGPPilot] failed to load shapley state: {exc}')

    def _apply_genome(self, strategy, genome: dict) -> None:
        """Apply an aggregated genome to strategy HP with type/bounds safety.

        Mirrors IslandPilot._apply_genome so that both pipelines see the same
        strategy interface. Only ``_TUNABLE_GROUPS`` are overridden.
        """
        if not hasattr(strategy, 'hp') or not hasattr(strategy, 'hyperparameters'):
            return

        if self._hp_spec is None:
            try:
                hp_list = strategy.hyperparameters()
                self._hp_spec = {
                    h['name']: h for h in hp_list
                    if isinstance(h, dict) and 'name' in h
                }
            except Exception:
                self._hp_spec = {}

        if not self._hp_spec:
            return

        hp = strategy.hp
        for hp_name, spec in self._hp_spec.items():
            group = spec.get('group', '')
            if group not in _TUNABLE_GROUPS:
                continue
            if hp_name not in genome:
                continue
            val = genome[hp_name]
            hp_type = spec.get('type')
            if hp_type == 'categorical':
                options = spec.get('options', [])
                safe = _SAFE_OPTIONS.get(hp_name)
                if safe:
                    options = [o for o in options if o in safe]
                if not options:
                    continue
                if isinstance(val, (int, float)):
                    idx = int(round(val))
                    idx = max(0, min(idx, len(options) - 1))
                    hp[hp_name] = options[idx]
                elif val in options:
                    hp[hp_name] = val
            elif hp_type in (int, float) or hp_type in ('int', 'float'):
                lo = spec.get('min', float('-inf'))
                hi = spec.get('max', float('inf'))
                try:
                    val_f = float(val)
                except (TypeError, ValueError):
                    continue
                val_f = max(lo, min(hi, val_f))
                if hp_type in (int, 'int'):
                    val_f = int(round(val_f))
                hp[hp_name] = val_f

    def _compute_danger(self, strategy) -> float:
        candles = getattr(strategy, 'candles', None)
        if candles is None or len(candles) < 20:
            return 0.0
        closes = candles[-20:, 2]
        if closes[0] == 0:
            return 0.0
        returns = np.diff(closes) / (closes[:-1] + 1e-12)
        vol = float(np.std(returns))
        return float(np.clip(vol / 0.01, 0.0, 1.0))
